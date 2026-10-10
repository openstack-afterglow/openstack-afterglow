<script lang="ts">
	import { t } from '$lib/i18n/ns/images-keys';
	import type { ImageInfo } from '$lib/types/compute';

	let { image, showId = true, compact = false }: { image: ImageInfo; showId?: boolean; compact?: boolean } = $props();
	const digest = $derived.by(() => {
		const algorithm = image.os_hash_algo?.toLowerCase();
		const value = image.os_hash_value?.toLowerCase();
		if (algorithm === 'sha512' && value && /^[0-9a-f]{128}$/.test(value)) return { algorithm: 'SHA-512', value };
		if (algorithm === 'sha256' && value && /^[0-9a-f]{64}$/.test(value)) return { algorithm: 'SHA-256', value };
		return null;
	});
</script>

<div class="grid min-w-0 gap-0.5 font-mono text-xs text-ink-2">
	{#if digest}
		<code class="truncate" title={`${digest.algorithm}: ${digest.value}`} aria-label={`${digest.algorithm}: ${digest.value}`}>
			{#if compact}{digest.value.slice(0, 8)}{:else}{digest.algorithm} {digest.value.slice(0, 12)}…{digest.value.slice(-8)}{/if}
		</code>
	{:else}
		{@const label = image.status === 'saving' || image.status === 'queued' ? t('digest.calculatingHash') : t('digest.noHash')}
		<span class:truncate={compact} title={compact ? label : undefined}>{label}</span>
	{/if}
	{#if showId}
		<code title={image.id} aria-label={t('digest.imageId', { id: image.id })}>ID {image.id.slice(0, 8)}</code>
	{/if}
</div>
