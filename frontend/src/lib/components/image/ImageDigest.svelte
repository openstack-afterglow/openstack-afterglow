<script lang="ts">
	import type { ImageInfo } from '$lib/types/compute';

	let { image }: { image: ImageInfo } = $props();
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
			{digest.algorithm} {digest.value.slice(0, 12)}…{digest.value.slice(-8)}
		</code>
	{:else}
		<span>{image.status === 'saving' || image.status === 'queued' ? '해시 계산 중' : '해시 없음'}</span>
	{/if}
	<code title={image.id} aria-label={`이미지 ID: ${image.id}`}>ID {image.id.slice(0, 8)}</code>
</div>
