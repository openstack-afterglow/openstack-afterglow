<script lang="ts">
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
</script>

<div class="grid grid-cols-3 gap-3.5 mb-5" aria-hidden="true">
	{#each [1, 2, 3] as _}
		<div class="bg-surface-base border border-line rounded-lg p-5">
			<div class="motion-skeleton h-3 w-20 rounded mb-3"></div>
			<div class="motion-skeleton h-8 w-16 rounded mb-3"></div>
			<div class="motion-skeleton h-1.5 w-full rounded-full"></div>
		</div>
	{/each}
</div>
<LoadingSkeleton variant="table" rows={5} />
