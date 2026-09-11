<script lang="ts">
	import { KNOWN_DISTROS, osLabel } from '$lib/utils/imageOs';

	let {
		distroFilter = $bindable('all'),
		counts,
	}: {
		distroFilter?: string;
		counts: Record<string, number>;
	} = $props();
</script>

<div class="flex flex-wrap gap-2 mb-5">
	{#each [['all', '전체'], ...KNOWN_DISTROS.map(d => [d, osLabel(d)]), ['other', '기타']] as [key, label]}
		{@const count = counts[key] ?? 0}
		{#if count > 0 || key === 'all'}
			<button
				onclick={() => distroFilter = key}
				class="px-3 py-1 rounded-full text-xs font-medium transition-colors {distroFilter === key ? 'bg-action-warm text-ink-0' : 'bg-surface-sunken text-ink-2 hover:text-ink-0'}"
			>
				{label} {count > 0 ? `(${count})` : ''}
			</button>
		{/if}
	{/each}
</div>
