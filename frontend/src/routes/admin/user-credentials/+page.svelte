<script lang="ts">
  import CredentialManagement from '$lib/components/admin/credentials/CredentialManagement.svelte';
  import DomainScope from '$lib/components/admin/domains/DomainScope.svelte';
  import TutorialStartButton from '$lib/tutorial/TutorialStartButton.svelte';
  import { isAdmin, authReady, isMockAuthActive } from '$lib/stores/auth';
</script>

<DomainScope>
  {#snippet actions()}
    {#if !isMockAuthActive() && $authReady && $isAdmin}
      <TutorialStartButton tour="admin-user-credentials" compactOnMobile />
    {/if}
  {/snippet}
  {#snippet children(domainId, domainName)}
    <CredentialManagement kind="user" {domainId} {domainName} />
  {/snippet}
</DomainScope>
