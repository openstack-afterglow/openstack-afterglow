<script lang="ts">
	import { page } from '$app/stores';
	import { PageShell } from '$lib/components/ui';
	import SubnetIpInventory from '$lib/components/admin/networks/SubnetIpInventory.svelte';
</script>

<PageShell>
	<SubnetIpInventory subnetId={$page.params.id ?? ''} standalone />
</PageShell>
