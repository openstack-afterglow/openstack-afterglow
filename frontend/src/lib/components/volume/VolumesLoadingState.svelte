<script lang="ts">
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
</script>

<div class="grid grid-cols-3 gap-3.5 mb-5">
	{#each [1, 2, 3] as _}
		<div class="bg-surface-base border border-line rounded-lg p-5 animate-pulse">
			<div class="h-3 w-20 bg-surface-sunken rounded mb-3"></div>
			<div class="h-8 w-16 bg-surface-sunken rounded mb-3"></div>
			<div class="h-1.5 w-full bg-surface-sunken rounded-full"></div>
		</div>
	{/each}
</div>
<LoadingSkeleton variant="table" rows={5} />
