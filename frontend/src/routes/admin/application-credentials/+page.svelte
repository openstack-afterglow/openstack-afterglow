<script lang="ts">
  import CredentialManagement from '$lib/components/admin/credentials/CredentialManagement.svelte';
  import DomainScope from '$lib/components/admin/domains/DomainScope.svelte';
  import TutorialStartButton from '$lib/tutorial/TutorialStartButton.svelte';
</script>

<DomainScope>
  {#snippet actions()}
    <TutorialStartButton tour="admin-application-credentials" compactOnMobile />
  {/snippet}
  {#snippet children(domainId, domainName)}
    <CredentialManagement kind="application" {domainId} {domainName} />
  {/snippet}
</DomainScope>
