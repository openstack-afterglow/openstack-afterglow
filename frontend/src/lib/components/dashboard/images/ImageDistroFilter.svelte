<script lang="ts">
	import { KNOWN_DISTROS, osLabel } from '$lib/utils/imageOs';
	import { t } from '$lib/i18n/ns/images-keys';
	import AnimatedNumber from '$lib/components/ui/AnimatedNumber.svelte';

	let {
		distroFilter = $bindable('all'),
		counts,
	}: {
		distroFilter?: string;
		counts: Record<string, number>;
	} = $props();
</script>

<div class="flex flex-wrap gap-2 mb-5">
	{#each [['all', t('distroFilter.all')], ...KNOWN_DISTROS.map(d => [d, osLabel(d)]), ['other', t('distroFilter.other')]] as [key, label] (key)}
		{@const count = counts[key] ?? 0}
		{#if count > 0 || key === 'all'}
			<button
				onclick={() => distroFilter = key}
				class="px-3 py-1 rounded-full text-xs font-medium transition-colors {distroFilter === key ? 'bg-action-warm text-ink-0' : 'bg-surface-sunken text-ink-2 hover:text-ink-0'}"
			>
				{label} {#if count > 0}(<AnimatedNumber value={count} />){/if}
			</button>
		{/if}
	{/each}
</div>
