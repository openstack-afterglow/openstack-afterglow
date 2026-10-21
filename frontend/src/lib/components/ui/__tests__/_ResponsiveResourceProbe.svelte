<script lang="ts">
	import ResponsiveTable from '../ResponsiveTable.svelte';
	import CompactResourceCard from '../CompactResourceCard.svelte';
	let { onInspect }: { onInspect: () => void } = $props();
	let selected = $state(false);
</script>
<ResponsiveTable>
	{#snippet cards()}
		<CompactResourceCard {selected}>
			<h2>Example VM</h2>
			<label><input type="checkbox" checked={selected} onchange={(event) => selected = event.currentTarget.checked} />Select VM</label>
			<p>SHUTOFF · 2 CPU</p>
			{#snippet details()}<p>vm-immutable-id</p>{/snippet}
			{#snippet actions()}<button onclick={onInspect}>Inspect VM</button>{/snippet}
		</CompactResourceCard>
	{/snippet}
	<table><thead><tr><th>Name</th><th>Select</th><th>State</th><th>Actions</th></tr></thead><tbody><tr><td>Example VM</td><td><label><input type="checkbox" checked={selected} onchange={(event) => selected = event.currentTarget.checked} />Select VM</label></td><td>SHUTOFF</td><td><button onclick={onInspect}>Inspect VM</button></td></tr></tbody></table>
</ResponsiveTable>
