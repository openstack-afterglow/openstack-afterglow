<script lang="ts">
	import UsageBar from './UsageBar.svelte';
	import type { DesignTone } from '$lib/design/tokens';

	interface Props {
		label: string;
		used: number;
		total: number;
		unit?: string;
		size?: 'xs' | 'sm' | 'md';
		tone?: DesignTone;
		class?: string;
	}

	let { label, used, total, unit = '', tone, size = 'sm', class: className = '' }: Props = $props();
</script>

<UsageBar {label} value={used} max={total} {unit} {tone} {size} class={className} />
