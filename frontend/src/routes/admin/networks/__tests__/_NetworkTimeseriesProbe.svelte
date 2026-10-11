<script lang="ts">
	import type { TsPoint } from '$lib/types/common';
	let { data, loading, range, onRangeChange }: {
		data: TsPoint[];
		loading: boolean;
		range: string;
		onRangeChange: (range: string) => void;
	} = $props();
</script>

<div aria-label="Network history" aria-busy={loading}>
	<output>{JSON.stringify(data)}</output>
	<span>{range}</span>
	<button onclick={() => onRangeChange('1d')}>One day</button>
	<button onclick={() => onRangeChange('30d')}>Thirty days</button>
</div>
