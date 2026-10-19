<script lang="ts">
  import { page } from '$app/state';
  import DomainScope from '$lib/components/admin/domains/DomainScope.svelte';
  import DomainMonitoring from '$lib/components/admin/domains/DomainMonitoring.svelte';
  import DomainBudgetEditor from '$lib/components/admin/domains/DomainBudgetEditor.svelte';
</script>

<DomainScope initialDomainId={page.params.id}>
  {#snippet children(domainId, domainName)}
    <DomainMonitoring {domainId} {domainName} />
    <DomainBudgetEditor {domainId} />
  {/snippet}
</DomainScope>
