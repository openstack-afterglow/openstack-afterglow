<script lang="ts">
	import { auth, logoutInProgress } from '$lib/stores/auth';
	import { authDisplayContext } from '$lib/stores/authDisplayContext';
	import AdminLumenServiceKeys from '$lib/components/admin/chat/AdminLumenServiceKeys.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import { t } from '$lib/i18n/ns/chat-settings';
</script>

<svelte:head><title>{t('domainBilling.inventoryTitle')} · Lumen</title></svelte:head>
<PageShell>
	<PageHeader breadcrumb="Lumen" title={t('domainBilling.inventoryTitle')} subtitle={t('domainBilling.inventoryDescription')} />
	{#if $authDisplayContext.ready && !$logoutInProgress && $auth.isSystemAdmin}
		{#key $authDisplayContext.key}
			<AdminLumenServiceKeys scopeKey={$authDisplayContext.key} />
		{/key}
	{:else}
		<Alert flat tone="danger">{t('domainBilling.adminDenied')}</Alert>
	{/if}
</PageShell>
