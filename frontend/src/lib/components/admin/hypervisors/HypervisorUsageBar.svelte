<script lang="ts">
	import UsageBar from '$lib/components/ui/UsageBar.svelte';

	let {
		used,
		total,
		label,
	}: {
		used: number;
		total: number;
		label: string;
	} = $props();

</script>

<div class="flex items-center gap-2">
	<UsageBar value={used} max={total} showValue={false} size="sm" class="w-14 shrink-0" />
	<span class="text-ink-2 text-xs">{label}</span>
</div>
