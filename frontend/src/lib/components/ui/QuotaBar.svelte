<script lang="ts">
	import UsageBar from './UsageBar.svelte';
	import type { DesignTone } from '$lib/design/tokens';

	interface Props {
		label: string;
		used: number;
		limit: number;
		color?: string;
		size?: 'xs' | 'sm' | 'md';
		showValue?: boolean;
		tone?: DesignTone;
		class?: string;
	}

	let { label, used, limit, color: _color, tone, size = 'xs', showValue = true, class: className = '' }: Props = $props();
</script>

<UsageBar {label} value={used} max={limit} {tone} {size} {showValue} class={className} />
