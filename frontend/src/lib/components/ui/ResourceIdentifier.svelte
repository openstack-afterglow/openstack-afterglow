<script lang="ts">
	import { onDestroy } from 'svelte';
	import Button from './Button.svelte';
	import { t } from '$lib/i18n/ns/common';
	import { abbreviatedIdentifier } from '$lib/utils/adminIdentityLabel';

	interface Props {
		id: string | null | undefined;
		compact?: boolean;
		class?: string;
	}

	let { id, compact = true, class: className = '' }: Props = $props();
	let feedback = $state<'copied' | 'failed' | null>(null);
	let feedbackId = $state<string | null>(null);
	let disposed = false;
	onDestroy(() => { disposed = true; });

	async function copy(event: MouseEvent) {
		event.stopPropagation();
		if (!id) return;
		const requestedId = id;
		feedback = null;
		feedbackId = requestedId;
		try {
			await navigator.clipboard.writeText(requestedId);
			if (!disposed && id === requestedId) feedback = 'copied';
		} catch {
			if (!disposed && id === requestedId) feedback = 'failed';
		}
	}
</script>

<span class="resource-identifier {className}" data-resource-identifier>
	{#if id}
		<code title={id}>{compact && id.length > 8 ? `${abbreviatedIdentifier(id)}…` : id}</code>
		<Button variant="ghost" size="icon" ariaLabel={`${t('resource.copyId')}: ${id}`} title={t('resource.copyId')} onclick={copy}>
			<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" aria-hidden="true">
				<rect x="8" y="8" width="12" height="12" rx="2" />
				<path d="M16 8V4a1 1 0 0 0-1-1H4a1 1 0 0 0-1 1v11a1 1 0 0 0 1 1h4" />
			</svg>
		</Button>
		<span aria-live="polite" aria-atomic="true" class:sr-only={feedbackId !== id || feedback !== 'failed'}>
			{#if feedbackId === id && feedback === 'copied'}{t('resource.idCopied')}{/if}
			{#if feedbackId === id && feedback === 'failed'}{t('resource.idCopyFailed')} <code>{id}</code>{/if}
		</span>
	{:else}
		<span>{t('resource.unknownId')}</span>
	{/if}
</span>

<style>
	.resource-identifier { display: inline-flex; align-items: center; flex-wrap: wrap; gap: 0.25rem; max-width: 100%; color: var(--color-ink-2); font-size: var(--type-identifier); }
	code { font-family: var(--font-mono); font-size: var(--type-identifier); overflow-wrap: anywhere; }
	[aria-live]:not(.sr-only) { flex-basis: 100%; white-space: normal; color: var(--color-state-danger-text); }
</style>
