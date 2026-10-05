<script lang="ts">
	import { t } from '$lib/i18n/ns/waygate';
	import { auth } from '$lib/stores/auth';
	import { createWaygateProjectScope } from '$lib/utils/waygateProjectScope';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import WaygateProjectWorkspace from './WaygateProjectWorkspace.svelte';

	let { admin = false }: { admin?: boolean } = $props();
	const scope = createWaygateProjectScope(auth);
</script>

{#key $scope}
	{#if $scope}
		<WaygateProjectWorkspace scope={$scope} {admin} />
	{:else}
		<div class="p-4 md:p-8">
			<PageHeader breadcrumb={admin ? t('workspace.breadcrumb.admin') : t('workspace.breadcrumb.network')} title={admin ? t('workspace.adminTitle') : 'Waygate'} />
			<Alert tone="info">{t('workspace.selectProject')}</Alert>
		</div>
	{/if}
{/key}
