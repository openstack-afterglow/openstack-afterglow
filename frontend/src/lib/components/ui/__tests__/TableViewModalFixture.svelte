<script lang="ts">
	import Modal from '../Modal.svelte';
	import TableViewFixture from './TableViewFixture.svelte';
	import { provideTableViewVisibility } from '$lib/utils/tableView.svelte';
	let { visible = true }: { visible?: boolean } = $props();
	provideTableViewVisibility(() => visible);
	let open = $state(false);
</script>

<button onclick={() => open = true}>Open table dialog</button>
<Modal {open} onClose={() => open = false} ariaLabel="Table dialog">
	<div hidden={!visible}><TableViewFixture /></div>
</Modal>
