<script lang="ts">
  import DomainScope from '$lib/components/admin/domains/DomainScope.svelte';
  import AdminGroupsPage from '$lib/components/admin/groups/AdminGroupsPage.svelte';
  import TutorialStartButton from '$lib/tutorial/TutorialStartButton.svelte';
</script>

<DomainScope>
  {#snippet actions()}
    <TutorialStartButton tour="admin-groups" compactOnMobile />
  {/snippet}
  {#snippet children(domainId, domainName)}
    <AdminGroupsPage {domainId} {domainName} />
  {/snippet}
</DomainScope>
