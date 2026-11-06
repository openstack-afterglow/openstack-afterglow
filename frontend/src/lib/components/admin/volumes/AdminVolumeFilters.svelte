<script lang="ts">
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	let { nameSearch = $bindable('') }: { nameSearch: string } = $props();
</script>

<RegexSearch id="admin-volume-search" bind:value={nameSearch} class="min-w-0 w-full md:flex-1" />
