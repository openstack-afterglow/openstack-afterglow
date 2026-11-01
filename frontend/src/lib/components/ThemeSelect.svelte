<script lang="ts">
	import { tick } from 'svelte';
	import { theme, resolvedTheme, type ThemePreference } from '$lib/stores/theme';
	import { defineMessages, getLocale } from '$lib/i18n/runtime.svelte';
	import type { Locale } from '$lib/i18n/locales';
	import type source from '$lib/i18n/messages/ko/shell.json';

	let { id, locale, class: className = '' }: { id: string; locale?: Locale; class?: string } = $props();
	const t = defineMessages<typeof source>('shell', import.meta.glob<Record<string, string>>('../i18n/messages/*/shell.json', { eager: true, import: 'default' }), () => locale ?? getLocale());
	let menu = $state<HTMLDetailsElement | null>(null);
	let trigger = $state<HTMLElement | null>(null);
	let choices = $state<HTMLDivElement | null>(null);
	let menuLeft = $state<number | null>(null);
	const options: ThemePreference[] = ['light', 'dark', 'system'];
	const icons: Record<ThemePreference, string> = {
		light: 'M12 3v1m0 16v1M3 12h1m16 0h1M5.6 5.6l.7.7m11.4 11.4.7.7M5.6 18.4l.7-.7m11.4-11.4.7-.7M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0',
		dark: 'M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z',
		system: 'M3 4h18v13H3zM8 21h8M12 17v4',
	};
	const currentLabel = $derived($theme === 'system' ? t('theme.systemCurrent', { mode: t($resolvedTheme === 'dark' ? 'theme.dark' : 'theme.light') }) : t($theme === 'dark' ? 'theme.dark' : 'theme.light'));

	function positionMenu() {
		if (!menu || !choices) return;
		const rect = menu.getBoundingClientRect();
		const width = parseFloat(getComputedStyle(choices).width);
		menuLeft = Math.max(8, Math.min(rect.right - width, document.documentElement.clientWidth - width - 8)) - rect.left;
	}
	function close(restoreFocus = false) {
		if (menu) menu.open = false;
		if (restoreFocus) trigger?.focus();
	}
	function choose(value: ThemePreference) {
		theme.set(value);
		close(true);
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
		if (menu) menu.open = true;
		await tick();
		const items = Array.from(choices?.querySelectorAll<HTMLButtonElement>('button') ?? []);
		const index = items.indexOf(origin as HTMLButtonElement);
		const next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : index < 0 ? (event.key === 'ArrowUp' ? items.length - 1 : 0) : (index + (event.key === 'ArrowUp' ? -1 : 1) + items.length) % items.length;
		items[next]?.focus();
	}
</script>

<svelte:document onclick={(event) => { if (menu?.open && event.target instanceof Node && !menu.contains(event.target)) close(); }} />
<svelte:window onresize={() => { if (menu?.open) positionMenu(); }} />

<details bind:this={menu} class="theme-select {className}" onfocusout={(event) => { if (event.relatedTarget instanceof Node && !menu?.contains(event.relatedTarget)) close(); }}>
	<summary {id} bind:this={trigger} class="theme-trigger" aria-label={t('theme.chooseCurrent', { mode: currentLabel })} title={t('theme.chooseCurrent', { mode: currentLabel })} aria-haspopup="menu" onkeydown={keydown} onclick={positionMenu}>
		<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d={icons[$theme]} /></svg>
	</summary>
	<div bind:this={choices} class="theme-menu" role="menu" aria-label={t('theme.choose')} style:left={menuLeft === null ? undefined : `${menuLeft}px`} style:right={menuLeft === null ? undefined : 'auto'}>
		{#each options as option}
			<button type="button" role="menuitemradio" class="theme-choice" class:selected={$theme === option} aria-checked={$theme === option} onclick={() => choose(option)} onkeydown={keydown}>
				<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d={icons[option]} /></svg>
				<span>{t(option === 'system' ? 'theme.system' : option === 'dark' ? 'theme.dark' : 'theme.light')}</span>
				{#if $theme === option}<svg class="selected-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="m5 12 4 4L19 6" /></svg>{/if}
			</button>
		{/each}
		<p class="theme-resolved" aria-live="polite">{currentLabel}</p>
	</div>
</details>

<style>
	.theme-select { position: relative; flex-shrink: 0; }
	.theme-trigger { display: flex; width: 2.75rem; height: 2.75rem; align-items: center; justify-content: center; list-style: none; cursor: pointer; border-radius: var(--radius-md); color: var(--color-ink-2); transition: color var(--motion-duration-fast), background-color var(--motion-duration-fast); }
	.theme-trigger::-webkit-details-marker { display: none; }
	svg { width: 1rem; height: 1rem; flex-shrink: 0; }
	.theme-trigger:hover, .theme-choice:hover { background: var(--color-surface-selected); color: var(--color-ink-0); }
	.theme-trigger:focus-visible, .theme-choice:focus-visible { outline: none; box-shadow: var(--focus-ring); }
	.theme-menu { position: absolute; top: calc(100% + 0.5rem); right: 0; z-index: var(--z-popover); width: 16rem; max-width: calc(100vw - 1rem); padding: 0.375rem; border: 1px solid var(--color-line); border-radius: var(--radius-md); background: var(--color-surface-raised); box-shadow: var(--shadow-popover); }
	.theme-choice { display: flex; width: 100%; min-height: 2.75rem; align-items: center; gap: 0.625rem; padding: 0.5rem 0.625rem; border-radius: var(--radius-md); text-align: left; color: var(--color-ink-1); font-size: 0.875rem; }
	.theme-choice.selected { background: var(--color-surface-selected); color: var(--color-ink-0); font-weight: 600; }
	.selected-check { margin-left: auto; }
	.theme-resolved { margin: 0.375rem 0.625rem; padding-top: 0.5rem; border-top: 1px solid var(--color-line); font-size: 0.8125rem; color: var(--color-ink-2); }
	@media (min-width: 1024px) { .theme-trigger { width: 2rem; height: 2rem; } }
</style>
