<script lang="ts">
  import DomainScope from '$lib/components/admin/domains/DomainScope.svelte';
  import AdminGroupsPage from '$lib/components/admin/groups/AdminGroupsPage.svelte';
</script>

<DomainScope>
  {#snippet children(domainId, domainName)}
    <AdminGroupsPage {domainId} {domainName} />
  {/snippet}
</DomainScope>
