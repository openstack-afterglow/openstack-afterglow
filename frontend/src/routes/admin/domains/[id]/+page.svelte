<script lang="ts">
  import { page } from '$app/state';
  import DomainScope from '$lib/components/admin/domains/DomainScope.svelte';
  import DomainMonitoring from '$lib/components/admin/domains/DomainMonitoring.svelte';
  import DomainBudgetEditor from '$lib/components/admin/domains/DomainBudgetEditor.svelte';
  import ComputePoolPanel from '$lib/components/iam/ComputePoolPanel.svelte';
  import VpnReservedRangesPanel from '$lib/components/iam/VpnReservedRangesPanel.svelte';
  import PageShell from '$lib/components/ui/PageShell.svelte';
</script>

<DomainScope initialDomainId={page.params.id}>
  {#snippet children(domainId, domainName)}
    <DomainMonitoring {domainId} {domainName} />
    <PageShell><ComputePoolPanel {domainId} adminMode /></PageShell>
    <PageShell><VpnReservedRangesPanel {domainId} adminMode /></PageShell>
    <DomainBudgetEditor {domainId} />
  {/snippet}
</DomainScope>
