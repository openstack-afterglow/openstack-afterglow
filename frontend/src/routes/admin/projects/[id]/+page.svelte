<script lang="ts">
  import DomainScope from '$lib/components/admin/domains/DomainScope.svelte';
  import AdminProjectDetailPage from '$lib/components/admin/projects/AdminProjectDetailPage.svelte';
</script>

<DomainScope>
  {#snippet children(domainId, domainName)}
    <AdminProjectDetailPage {domainId} {domainName} />
  {/snippet}
</DomainScope>
