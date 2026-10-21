<script lang="ts">
	import type { Snippet } from 'svelte';
	import { adminInventoryScope } from '$lib/stores/adminInventoryScope';
	let { children }: { children: Snippet } = $props();
</script>

{#key $adminInventoryScope.revision}
	{@render children()}
{/key}
