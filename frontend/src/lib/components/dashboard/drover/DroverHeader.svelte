<script lang="ts">
	import { t } from '$lib/i18n/ns/drover-pages';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import TutorialStartButton from '$lib/tutorial/TutorialStartButton.svelte';
	import type { AutoRefreshController } from '$lib/utils/autoRefresh.svelte';
	import { k3sPermissions } from '$lib/stores/k3sPermissions';

	let {
		showDeleted = $bindable(),
		ar,
		refreshing,
		onForceRefresh,
		onOpenCreate,
		onOpenCreateIntent,
		onToggleDeleted,
	}: {
		showDeleted: boolean;
		ar: AutoRefreshController;
		refreshing: boolean;
		onForceRefresh: () => void;
		onOpenCreate: () => void;
		onOpenCreateIntent?: () => void;
		onToggleDeleted: () => void;
	} = $props();
</script>

<PageHeader breadcrumb={t('header.breadcrumb')} title={t('cluster.title')}>
	{#snippet actions()}
		<TutorialStartButton tour="drover" />
		<Button variant="secondary" size="sm" onclick={onToggleDeleted} ariaPressed={showDeleted}>
			{showDeleted ? t('header.hideDeleted') : t('header.showDeleted')}
		</Button>
		<AutoRefreshControl
			bind:active={ar.active}
			bind:intervalSeconds={ar.intervalSeconds}
			intervalOptions={ar.intervalOptions}
			{refreshing}
			onManualRefresh={onForceRefresh}
		/>
		<Button
			dataTour="drover-create-open"
			variant="primary"
			disabled={!$k3sPermissions.editClusters}
			onclick={onOpenCreate}
			onintent={onOpenCreateIntent}
		>
			{t('header.create')}
		</Button>
	{/snippet}
</PageHeader>
