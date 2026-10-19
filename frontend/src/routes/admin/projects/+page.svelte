<script lang="ts">
  import DomainScope from '$lib/components/admin/domains/DomainScope.svelte';
  import AdminProjectsPage from '$lib/components/admin/projects/AdminProjectsPage.svelte';
</script>

<DomainScope>
  {#snippet children(domainId, domainName)}
    <AdminProjectsPage {domainId} {domainName} />
  {/snippet}
</DomainScope>
