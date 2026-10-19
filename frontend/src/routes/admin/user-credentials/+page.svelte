<script lang="ts">
  import CredentialManagement from '$lib/components/admin/credentials/CredentialManagement.svelte';
  import DomainScope from '$lib/components/admin/domains/DomainScope.svelte';
</script>

<DomainScope>
  {#snippet children(domainId, domainName)}
    <CredentialManagement kind="user" {domainId} {domainName} />
  {/snippet}
</DomainScope>
