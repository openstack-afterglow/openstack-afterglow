<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-ops';
	import { auth } from '$lib/stores/auth';
	import { api } from '$lib/api/client';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import MonitoringSummaryTab from '$lib/components/admin/monitoring/MonitoringSummaryTab.svelte';
	import InstanceMetricsTab from '$lib/components/admin/monitoring/InstanceMetricsTab.svelte';
	import type { MonitoringSummary } from '$lib/components/admin/monitoring/MonitoringSummaryTab.svelte';
	import TutorialStartButton from '$lib/tutorial/TutorialStartButton.svelte';
	import { PageShell, Tabs } from '$lib/components/ui';

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	let tab = $state<'summary' | 'instances'>('summary');
	const monitoringTabs = [
		{ value: 'summary', get label() { return t('monitoring.page.summaryTab'); }, panelId: 'admin-monitoring-panel-summary', dataTour: 'admin-monitoring-summary-tab' },
		{ value: 'instances', get label() { return t('monitoring.page.instancesTab'); }, panelId: 'admin-monitoring-panel-instances', dataTour: 'admin-monitoring-instances-tab' },
	];

	let summary = $state<MonitoringSummary | null>(null);
	let loading = $state(true);
	let refreshing = $state(false);

	async function load() {
		if (!summary) loading = true;
		else refreshing = true;
		try {
			summary = await api.get<MonitoringSummary>('/api/v1/admin/monitoring/summary', token, projectId);
		} catch {
			summary = null;
		} finally {
			loading = false;
			refreshing = false;
		}
	}

	const ar = createAutoRefresh(load, {
		storageKey: 'admin-monitoring',
		defaultActive: true,
		defaultInterval: 15,
		intervalOptions: [10, 15, 30, 60]
	});

	let instancesLoading = $state(false);
	let refreshRef: (() => void) | undefined;
</script>

<PageShell class="max-w-7xl">
	<div data-tour="admin-monitoring-header">
	<PageHeader breadcrumb={t('monitoring.page.breadcrumb')} title={t('monitoring.page.title')}>
		{#snippet actions()}
			<TutorialStartButton tour="admin-monitoring" compactOnMobile />
			{#if tab === 'summary'}
				<AutoRefreshControl
					bind:active={ar.active}
					bind:intervalSeconds={ar.intervalSeconds}
					intervalOptions={ar.intervalOptions}
					refreshing={loading || refreshing}
					onManualRefresh={load}
				/>
			{:else}
				<button
					onclick={() => refreshRef?.()}
					disabled={instancesLoading}
					class="text-xs px-3 py-1.5 rounded border border-line-2 text-ink-2 hover:text-ink-1 hover:border-line-2 disabled:opacity-40 transition-colors"
				>
					{instancesLoading ? t('monitoring.loading') : t('monitoring.refresh')}
				</button>
			{/if}
		{/snippet}
	</PageHeader>
	</div>

	<Tabs
		id="admin-monitoring-tabs"
		value={tab}
		items={monitoringTabs}
		ariaLabel={t('monitoring.page.title')}
		onchange={(value) => { tab = value as typeof tab; }}
		class="mb-6"
	/>

	<div
		id={`admin-monitoring-panel-${tab}`}
		role="tabpanel"
		aria-labelledby={`admin-monitoring-tabs-${tab}`}
		tabindex="0"
	>
	{#if tab === 'summary'}
		<MonitoringSummaryTab {summary} {loading} {refreshing} />
	{:else}
		<InstanceMetricsTab
			{token}
			{projectId}
			onReload={fn => (refreshRef = fn)}
			bind:loadingInstances={instancesLoading}
		/>
	{/if}
	</div>

</PageShell>
