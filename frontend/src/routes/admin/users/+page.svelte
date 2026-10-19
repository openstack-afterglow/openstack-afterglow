<script lang="ts">
  import DomainScope from '$lib/components/admin/domains/DomainScope.svelte';
  import AdminUsersPage from '$lib/components/admin/users/AdminUsersPage.svelte';
</script>

<DomainScope>
  {#snippet children(domainId, domainName)}
    <AdminUsersPage {domainId} {domainName} />
  {/snippet}
</DomainScope>
