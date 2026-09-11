<script lang="ts">
	import type { Snippet } from 'svelte';

	let {
		value,
		label,
		valueClass = 'text-ink-0',
		size = 'md',
		labelExtra,
	}: {
		value: number | string;
		label: string;
		valueClass?: string;
		size?: 'sm' | 'md' | 'lg';
		labelExtra?: Snippet;
	} = $props();

	const padding = { sm: 'p-2', md: 'p-3', lg: 'p-4' };
	const fontSize = { sm: 'text-lg', md: 'text-2xl', lg: 'text-2xl' };
</script>

<div class="bg-surface-sunken rounded-lg text-center {padding[size]}">
	<div class="font-bold {fontSize[size]} {valueClass}">{value}</div>
	<div class="text-xs text-ink-3 mt-1">
		{label}{#if labelExtra} {@render labelExtra()}{/if}
	</div>
</div>
