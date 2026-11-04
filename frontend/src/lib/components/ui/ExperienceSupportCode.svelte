<script lang="ts">
	import { onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { experienceHealth, experienceSupportCode } from '$lib/utils/experience';
	import { t } from '$lib/i18n/ns/shared';
	import Button from './Button.svelte';

	let mounted = $state(false);
	let copiedCode = $state<string | null>(null);
	let failedCode = $state<string | null>(null);
	let copying = $state(false);
	const code = $derived(mounted ? $experienceSupportCode : null);
	const partial = $derived($experienceHealth.status !== 'ready' || $experienceHealth.dropped > 0 || $experienceHealth.failedBatches > 0);

	onMount(() => {
		mounted = true;
		return () => { mounted = false; };
	});
	$effect(() => {
		code;
		copiedCode = null;
		failedCode = null;
		copying = false;
	});

	async function copyCode() {
		const current = get(experienceSupportCode);
		if (!mounted || !current || current !== code || copying) return;
		copying = true;
		copiedCode = null;
		failedCode = null;
		try {
			if (!navigator.clipboard?.writeText) throw new Error('clipboard_unavailable');
			await navigator.clipboard.writeText(current);
			if (mounted && get(experienceSupportCode) === current) copiedCode = current;
		} catch {
			if (mounted && get(experienceSupportCode) === current) failedCode = current;
		} finally {
			if (mounted && get(experienceSupportCode) === current) copying = false;
		}
	}
</script>

{#if code}
	<details class="support-code">
		<summary>{t('support.label')}</summary>
		<div class="support-content">
			<code>{code}</code>
			<Button variant="secondary" size="sm" class="support-copy" onclick={copyCode} disabled={copying} ariaLabel={t('support.copy')}>
				{copiedCode === code ? t('support.copied') : t('support.copy')}
			</Button>
			<p>{t('support.help')}</p>
			{#if partial}<p>{t('support.partial')}</p>{/if}
			<p role="status" aria-live="polite">{failedCode === code ? t('support.unavailable') : copiedCode === code ? t('support.copied') : ''}</p>
		</div>
	</details>
{/if}

<style>
	.support-code { min-width: 0; max-width: 26rem; color: var(--color-ink-2); font-size: var(--type-support); }
	summary { display: list-item; min-height: var(--control-touch-height); padding: 0.75rem; cursor: pointer; overflow-wrap: anywhere; }
	summary:hover { color: var(--color-ink-0); }
	summary:focus-visible { outline: none; border-radius: var(--radius-md); box-shadow: var(--focus-ring); }
	.support-content { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem; padding: 0 0.75rem 0.75rem; }
	.support-code .support-content :global(.support-copy) { max-width: 100%; min-width: 0; white-space: normal; overflow-wrap: anywhere; }
	code { flex: 1 1 12rem; min-width: 0; overflow-wrap: anywhere; word-break: break-all; color: var(--color-ink-1); font-family: var(--font-mono); font-size: var(--type-identifier); user-select: all; }
	p { flex-basis: 100%; margin: 0; line-height: 1.5; overflow-wrap: anywhere; }
	p:empty { display: none; }
</style>
