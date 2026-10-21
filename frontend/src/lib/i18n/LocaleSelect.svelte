<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { invalidate } from '$app/navigation';
	import { LOCALES, LOCALE_NATIVE_NAMES, LOCALE_SHORT_NAMES, type Locale } from './locales';
	import { getLocale, setLocale } from './runtime.svelte';
	import { t } from './ns/shell';

	interface Props {
		/** Stable id; also used to return focus after page content remounts in the new language. */
		id: string;
		/** `compact` fits app chrome; `labelled` shows the native language name. */
		variant?: 'compact' | 'labelled';
		/** Documentation supplies shareable language links; navigation persists the same app preference. */
		locale?: Locale;
		label?: string;
		href?: (locale: Locale) => string;
		open?: boolean;
		class?: string;
	}

	let { id, variant = 'compact', locale, label, href, open = $bindable(false), class: className = '' }: Props = $props();
	let menu = $state<HTMLDetailsElement | null>(null);
	let trigger = $state<HTMLElement | null>(null);
	let choices = $state<HTMLDivElement | null>(null);
	let menuLeft = $state<number | null>(null);
	const current = $derived(locale ?? getLocale());
	const languageLabel = $derived(label ?? t('locale.label'));
	const REFOCUS_KEY = 'afterglow.i18n.refocus';

	function positionMenu() {
		if (!menu || !choices) return;
		const rect = menu.getBoundingClientRect();
		const width = parseFloat(getComputedStyle(choices).width);
		if (!Number.isFinite(width)) return;
		// Match the existing anchored ActionMenu's 8px viewport margin.
		menuLeft = Math.min(Math.max(8, rect.right - width), document.documentElement.clientWidth - width - 8) - rect.left;
	}

	function close(restoreFocus = false) {
		if (menu) menu.open = false;
		open = false;
		if (restoreFocus) trigger?.focus();
	}

	async function change(value: Locale) {
		close(true);
		if (value === getLocale()) return;
		try {
			sessionStorage.setItem(REFOCUS_KEY, id);
		} catch {
			// Focus restoration is best effort; changing language must not fail.
		}
		setLocale(value);
		await invalidate('afterglow:locale');
		await tick();
		if (trigger?.isConnected) {
			trigger.focus();
			try {
				if (sessionStorage.getItem(REFOCUS_KEY) === id) sessionStorage.removeItem(REFOCUS_KEY);
			} catch {
				// Retained app chrome already has focus without a restoration flag.
			}
		}
	}

	async function keydown(event: KeyboardEvent) {
		if (event.key === 'Escape' && menu?.open) {
			event.preventDefault();
			event.stopPropagation();
			close(true);
			return;
		}
		if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
		event.preventDefault();
		const origin = event.currentTarget;
		positionMenu();
		open = true;
		await tick();
		const items = Array.from(choices?.querySelectorAll<HTMLElement>('button, a[href]') ?? []);
		const index = items.indexOf(origin as HTMLElement);
		const next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1
			: index < 0 ? (event.key === 'ArrowUp' ? items.length - 1 : 0)
				: (index + (event.key === 'ArrowUp' ? -1 : 1) + items.length) % items.length;
		items[next]?.focus();
	}

	function focusout(event: FocusEvent) {
		if (event.relatedTarget instanceof Node && !menu?.contains(event.relatedTarget)) close();
	}

	onMount(() => {
		try {
			if (sessionStorage.getItem(REFOCUS_KEY) !== id) return;
			sessionStorage.removeItem(REFOCUS_KEY);
		} catch {
			return;
		}
		trigger?.focus();
	});
</script>

<svelte:document onclick={(event) => {
	if (menu?.open && event.target instanceof Node && !menu.contains(event.target)) close();
}} />
<svelte:window onresize={() => { if (menu?.open) positionMenu(); }} />

<details class="locale-select {variant} {className}" bind:this={menu} bind:open onfocusout={focusout}>
	<summary bind:this={trigger} {id} class="locale-trigger" aria-label={`${languageLabel}: ${LOCALE_NATIVE_NAMES[current]}`} title={languageLabel} onkeydown={keydown} onclick={positionMenu}>
		<svg class="globe" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
			<circle cx="12" cy="12" r="9" />
			<path stroke-linecap="round" stroke-linejoin="round" d="M3 12h18M12 3c2.5 2.7 3.75 5.7 3.75 9S14.5 18.3 12 21c-2.5-2.7-3.75-5.7-3.75-9S9.5 5.7 12 3z" />
		</svg>
		<span class="current" aria-hidden="true">{variant === 'labelled' ? LOCALE_NATIVE_NAMES[current] : LOCALE_SHORT_NAMES[current]}</span>
		<svg class="chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="m6 9 6 6 6-6" /></svg>
	</summary>
	<div bind:this={choices} class="locale-menu" role="group" aria-label={languageLabel} style:left={menuLeft === null ? undefined : `${menuLeft}px`} style:right={menuLeft === null ? undefined : 'auto'}>
		{#each LOCALES as language (language)}
			{#if href}
				<a class="locale-choice" class:selected={language === current} href={href(language)} lang={language} hreflang={language} aria-current={language === current ? 'page' : undefined} onkeydown={keydown} onclick={() => close()}>{LOCALE_NATIVE_NAMES[language]}</a>
			{:else}
				<button class="locale-choice" class:selected={language === current} type="button" lang={language} aria-pressed={language === current} onkeydown={keydown} onclick={() => change(language)}>{LOCALE_NATIVE_NAMES[language]}</button>
			{/if}
		{/each}
	</div>
</details>

<style>
	.locale-select { position: relative; display: inline-block; flex-shrink: 0; }
	.locale-trigger {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.375rem;
		border-radius: var(--radius-md);
		color: var(--color-ink-2);
		font-size: 0.75rem;
		font-weight: 600;
		cursor: pointer;
		list-style: none;
		transition: background var(--motion-duration-fast) var(--motion-ease-standard), color var(--motion-duration-fast) var(--motion-ease-standard);
	}
	.locale-trigger::-webkit-details-marker { display: none; }
	.locale-trigger:hover { background: var(--color-surface-sunken); color: var(--color-ink-0); }
	.locale-trigger:focus-visible, .locale-choice:focus-visible { outline: none; box-shadow: var(--focus-ring); }

	.compact .locale-trigger {
		min-width: 2.75rem;
		height: 2.75rem;
		padding: 0 0.5rem;
	}

	.labelled .locale-trigger {
		height: 2.75rem;
		padding: 0 0.75rem;
		color: var(--color-ink-1);
		font-size: 0.8125rem;
		font-weight: 500;
	}

	.globe {
		width: 1rem;
		height: 1rem;
		flex-shrink: 0;
	}

	.current {
		line-height: 1;
		white-space: nowrap;
	}

	.chevron { width: 0.75rem; height: 0.75rem; flex-shrink: 0; }
	.locale-menu {
		position: absolute;
		right: 0;
		top: calc(100% + 0.5rem);
		z-index: var(--z-popover);
		display: grid;
		width: 10rem;
		max-width: calc(100vw - 2rem);
		max-height: calc(100dvh - 6rem);
		overflow-y: auto;
		padding: 0.375rem;
		border: 1px solid var(--color-line);
		border-radius: var(--radius-md);
		background: var(--color-surface-raised);
	}
	.locale-choice {
		display: flex;
		min-height: 2.75rem;
		align-items: center;
		border-radius: var(--radius-md);
		padding: 0.5rem 0.75rem;
		color: var(--color-ink-1);
		font-size: 0.8125rem;
		font-weight: 500;
		text-align: left;
		text-decoration: none;
		white-space: nowrap;
		cursor: pointer;
	}
	.locale-choice:hover, .locale-choice.selected { background: var(--color-surface-selected); }

	@media (min-width: 1024px) {
		.compact .locale-trigger {
			min-width: 2rem;
			height: 2rem;
		}
	}
</style>
