<script lang="ts">
	import { onMount } from 'svelte';
	import { LOCALES, LOCALE_NATIVE_NAMES, LOCALE_SHORT_NAMES, isLocale } from './locales';
	import { getLocale, setLocale } from './runtime.svelte';
	import { t } from './ns/shell';

	interface Props {
		/** Stable id; also used to return focus after page content remounts in the new language. */
		id: string;
		/** `compact` fits the console header; `labelled` shows the native language name. */
		variant?: 'compact' | 'labelled';
		class?: string;
	}

	let { id, variant = 'compact', class: className = '' }: Props = $props();
	let select = $state<HTMLSelectElement | null>(null);
	const REFOCUS_KEY = 'afterglow.i18n.refocus';

	function change(event: Event) {
		const value = (event.currentTarget as HTMLSelectElement).value;
		if (!isLocale(value) || value === getLocale()) return;
		try {
			sessionStorage.setItem(REFOCUS_KEY, id);
		} catch {
			// Focus restoration is best effort; the language change itself must not fail.
		}
		setLocale(value);
	}

	onMount(() => {
		try {
			if (sessionStorage.getItem(REFOCUS_KEY) !== id) return;
			sessionStorage.removeItem(REFOCUS_KEY);
		} catch {
			return;
		}
		select?.focus();
	});
</script>

<div class="locale-select {variant} {className}">
	<svg class="globe" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
		<circle cx="12" cy="12" r="9" />
		<path stroke-linecap="round" stroke-linejoin="round" d="M3 12h18M12 3c2.5 2.7 3.75 5.7 3.75 9S14.5 18.3 12 21c-2.5-2.7-3.75-5.7-3.75-9S9.5 5.7 12 3z" />
	</svg>
	<span class="current" aria-hidden="true">{variant === 'labelled' ? LOCALE_NATIVE_NAMES[getLocale()] : LOCALE_SHORT_NAMES[getLocale()]}</span>
	<select bind:this={select} {id} value={getLocale()} onchange={change} aria-label={t('locale.label')} title={t('locale.label')}>
		{#each LOCALES as locale (locale)}
			<option value={locale} lang={locale}>{LOCALE_NATIVE_NAMES[locale]}</option>
		{/each}
	</select>
</div>

<style>
	.locale-select {
		position: relative;
		display: inline-flex;
		flex-shrink: 0;
		align-items: center;
		justify-content: center;
		gap: 0.375rem;
		border-radius: var(--radius-md);
		color: var(--color-ink-2);
		font-size: 0.75rem;
		font-weight: 600;
		transition:
			background var(--motion-duration-fast) var(--motion-ease-standard),
			color var(--motion-duration-fast) var(--motion-ease-standard);
	}

	.locale-select:hover {
		background: var(--color-surface-sunken);
		color: var(--color-ink-0);
	}

	.locale-select:has(select:focus-visible) {
		box-shadow: var(--focus-ring);
	}

	.compact {
		min-width: 2.75rem;
		height: 2.75rem;
		padding: 0 0.5rem;
	}

	.labelled {
		height: 2.75rem;
		border: 1px solid var(--color-line-2);
		background: var(--color-surface-sunken);
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

	select {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		cursor: pointer;
		opacity: 0;
		font-size: 1rem;
	}

	@media (min-width: 1024px) {
		.compact {
			min-width: 2rem;
			height: 2rem;
		}

		.labelled {
			height: 2.25rem;
		}
	}
</style>
