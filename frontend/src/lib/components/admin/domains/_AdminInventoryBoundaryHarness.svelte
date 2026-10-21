<script lang="ts">
	import type { Component } from 'svelte';
	import AdminInventoryBoundary from './AdminInventoryBoundary.svelte';
	let { page: Page }: { page: Component } = $props();
</script>
<AdminInventoryBoundary><Page /></AdminInventoryBoundary>
