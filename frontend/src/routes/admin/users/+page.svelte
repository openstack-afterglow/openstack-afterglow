<script lang="ts">
  import DomainScope from '$lib/components/admin/domains/DomainScope.svelte';
  import AdminUsersPage from '$lib/components/admin/users/AdminUsersPage.svelte';
  import TutorialStartButton from '$lib/tutorial/TutorialStartButton.svelte';
  import { t } from '$lib/i18n/ns/tutorial';
</script>

<DomainScope>
  {#snippet actions()}
    <!-- The page header keeps the admin-identity view tour; this button names the create/delete tour. -->
    <TutorialStartButton tour="admin-users" label={t('tours.adminUsers.startLabel')} compactOnMobile />
  {/snippet}
  {#snippet children(domainId, domainName)}
    <AdminUsersPage {domainId} {domainName} />
  {/snippet}
</DomainScope>
