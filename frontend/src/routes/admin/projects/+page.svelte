<script lang="ts">
  import DomainScope from '$lib/components/admin/domains/DomainScope.svelte';
  import AdminProjectsPage from '$lib/components/admin/projects/AdminProjectsPage.svelte';
  import TutorialStartButton from '$lib/tutorial/TutorialStartButton.svelte';
</script>

<DomainScope>
  {#snippet actions()}
    <TutorialStartButton tour="admin-projects" compactOnMobile />
  {/snippet}
  {#snippet children(domainId, domainName)}
    <AdminProjectsPage {domainId} {domainName} />
  {/snippet}
</DomainScope>
