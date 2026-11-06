<script lang="ts">
	import { t as tl } from '$lib/i18n/ns/common';
	import { t } from '$lib/i18n/ns/instance';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { confirmInstanceDeletion } from '$lib/utils/instanceDeleteConfirmation';
	import { onDestroy, untrack } from 'svelte';
	import { auth, canWrite } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { createSwr } from '$lib/utils/swr.svelte';
	import { apiMut } from '$lib/api/mutations';
	import type { Instance } from '$lib/types/compute';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import InstanceDetailPanel from '$lib/components/InstanceDetailPanel.svelte';
	import { invalidateInstanceDetailSelection } from '$lib/stores/instanceDetailController.svelte';
	import SlidePanel from '$lib/components/SlidePanel.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import { Alert, Button, EmptyState, PageHeader, PageShell, ResourceToolbar, SelectInput, Pagination } from '$lib/components/ui';
	import { openWizard, wizardOpen } from '$lib/stores/wizard';
	import TutorialStartButton from '$lib/tutorial/TutorialStartButton.svelte';
	import InstancesTable from '$lib/components/instance/list/InstancesTable.svelte';
	import { toast } from '$lib/stores/toast';
	import { isTransitional } from '$lib/utils/instanceStatus';
	import BulkSelectionOverlay from '$lib/components/ui/BulkSelectionOverlay.svelte';
	import { createResourceSelection } from '$lib/utils/resourceSelection.svelte';
	import { sortResources } from '$lib/utils/resourceSort';
	import { consumerInstanceFlavorLabel } from '$lib/utils/flavorDisplay';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { createTableView, type TableColumn } from '$lib/utils/tableView.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import { getStatusLabel } from '$lib/config/statusColors';
	import { beginExperienceAction, beginExperienceLoad, experienceApplied, experienceDiscarded, experienceState, type ExperienceContext } from '$lib/utils/experience';

	let instances = $state<Instance[]>([]);
	const columns = $derived<TableColumn<Instance>[]>([
		{ key: 'name', label: t('table.name'), value: row => row.name },
		{ key: 'status', label: t('table.status'), value: row => getStatusLabel(row.status, 'server'), filterValues: row => [row.status], format: value => getStatusLabel(String(value), 'server') },
		{ key: 'image', label: t('table.imageFlavor'), value: row => [row.image_name, consumerInstanceFlavorLabel(row)].filter(Boolean).join(' ') || null },
		{ key: 'ip', label: 'IP', value: row => (row.ip_addresses.find(ip => ip.type === 'fixed') ?? row.ip_addresses[0])?.addr },
		{ key: 'library', label: t('table.library'), value: row => row.union_libraries.filter(Boolean).join(', ') || null },
		{ key: 'strategy', label: t('table.strategy'), value: row => row.union_strategy, format: value => value === 'prebuilt' ? t('row.strategy.prebuilt') : value === 'dynamic' ? t('row.strategy.dynamic') : String(value) },
	]);
	let search = $state('');
	let pageSize = $state('20');
	let currentPage = $state(1);
	const view = createTableView({ rows: () => sortResources(instances, 'created_desc'), columns: () => columns, search: () => search, searchable: row => [row.name, row.id, ...columns.map(column => String(column.value(row) ?? ''))], locale: intlLocale });
	const filteredInstances = $derived(view.rows);
	const totalPages = $derived(Math.max(1, Math.ceil(filteredInstances.length / Number(pageSize))));
	const visiblePage = $derived(Math.min(currentPage, totalPages));
	const visibleInstances = $derived(filteredInstances.slice((visiblePage - 1) * Number(pageSize), visiblePage * Number(pageSize)));
	$effect(() => { search; view.sort; view.filters; untrack(() => { currentPage = 1; selection.clear(); }); });
	let loading = $state(true);
	let refreshing = $state(false);
	let error = $state('');
	let selectedInstanceId = $state<string | null>(null);
	let underutilized = $state<Record<string, boolean>>({});
	const selection = createResourceSelection();
	let bulkActioning = $state(false);
	let loadGeneration = 0;
	let viewAssignment = 0;
	let scopeRevision = $state(0);
	let instancesRevision = $state(-1);
	const unsubscribeAuth = auth.subscribe(() => { scopeRevision += 1; });
	onDestroy(() => { unsubscribeAuth(); scopeRevision += 1; });

	function targetsAllowed(ids: readonly string[], action: 'start' | 'stop' | 'delete' | 'shelve' | 'unshelve') {
		if (!$auth.token || !$canWrite || instancesRevision !== scopeRevision || ids.length === 0) return false;
		return ids.every((id) => {
			const row = instances.find((instance) => instance.id === id);
			if (!row) return false;
			if (action === 'stop') return row.status === 'ACTIVE';
			if (action === 'unshelve') return row.status === 'SHELVED' || row.status === 'SHELVED_OFFLOADED';
			return row.status === 'SHUTOFF';
		});
	}
	const canBulkDelete = $derived(targetsAllowed([...selection.ids], 'delete'));

	const selectableIds = $derived(new Set(visibleInstances.map((instance) => instance.id)));
	$effect(() => { const visibleIds = selectableIds; untrack(() => selection.retain(visibleIds)); });

	const { swrGet, swrSet } = createSwr(() => `${$auth.userId ?? ''}:${$auth.projectId ?? ''}:${scopeRevision}`);

	async function fetchInstances(opts?: { refresh?: boolean }, experience: ExperienceContext | undefined = beginExperienceLoad('compute', 'resource.list')) {
		const path = '/api/v1/instances';
		const requestToken = $auth.token ?? undefined;
		const requestProjectId = $auth.projectId ?? undefined;
		const generation = ++loadGeneration;
		const requestRevision = scopeRevision;
		const current = () => generation === loadGeneration && requestRevision === scopeRevision
			&& ($auth.token ?? undefined) === requestToken && ($auth.projectId ?? undefined) === requestProjectId;
		if (loading || refreshing) experienceState(experience, 'loading');
		const cached = swrGet<Instance[]>(path);
		if (cached && instances.length === 0) {
			instances = cached;
			instancesRevision = requestRevision;
			selection.retain(cached.map((instance) => instance.id));
			const assignment = ++viewAssignment;
			experienceState(experience, cached.length ? 'ready' : 'empty');
			if (experience) void experienceApplied(experience, { transport: 'cache' }, () => current() && viewAssignment === assignment);
		}
		const listPromise = api.withExperience(experience).get<Instance[]>(path, requestToken, requestProjectId, opts);
		const summaryPromise = fetchSummaryBatch(requestToken, requestProjectId, generation, opts, experience);
		try {
			const fetchedInstances = await listPromise;
			if (
				generation !== loadGeneration
				|| requestRevision !== scopeRevision
				|| ($auth.token ?? undefined) !== requestToken
				|| ($auth.projectId ?? undefined) !== requestProjectId
			) { experienceDiscarded(experience, 'stale'); return; }
			instances = fetchedInstances;
			instancesRevision = requestRevision;
			selection.retain(fetchedInstances.map((instance) => instance.id));
			swrSet(path, instances);
			error = '';
			const assignment = ++viewAssignment;
			experienceState(experience, instances.length ? 'ready' : 'empty');
			if (experience) void experienceApplied(experience, {}, () => current() && viewAssignment === assignment);
		} catch (e) {
			if (
				generation === loadGeneration
				&& requestRevision === scopeRevision
				&& ($auth.token ?? undefined) === requestToken
				&& ($auth.projectId ?? undefined) === requestProjectId
			) {
				error = e instanceof ApiError ? t('list.queryFailed', { status: e.status, message: e.message }) : t('list.serverError');
				const assignment = ++viewAssignment;
				experienceState(experience, 'error');
				if (experience) void experienceApplied(experience, {}, () => current() && viewAssignment === assignment);
			} else experienceDiscarded(experience, 'stale');
		} finally {
			if (generation === loadGeneration && requestRevision === scopeRevision
				&& ($auth.token ?? undefined) === requestToken && ($auth.projectId ?? undefined) === requestProjectId) {
				loading = false;
			}
		}
		void summaryPromise;
	}

	async function fetchSummaryBatch(
		requestToken: string | undefined,
		requestProjectId: string | undefined,
		generation: number,
		opts?: { refresh?: boolean },
		experience?: ExperienceContext,
	) {
		if (!requestToken) return;
		const requestRevision = scopeRevision;
		try {
			const resp = await api.withExperience(experience).get<{
				monitoring_available: boolean;
				instances: Record<string, { cpu_avg: number | null; mem_avg: number | null; underutilized: boolean }>;
			}>('/api/v1/instances/metrics-summary-batch', requestToken, requestProjectId, opts);
			if (
				generation !== loadGeneration
				|| requestRevision !== scopeRevision
				|| ($auth.token ?? undefined) !== requestToken
				|| ($auth.projectId ?? undefined) !== requestProjectId
			) return;
			if (resp.monitoring_available) {
				const map: Record<string, boolean> = {};
				for (const [id, data] of Object.entries(resp.instances)) map[id] = data.underutilized;
				underutilized = map;
			}
			else underutilized = {};
		} catch {
			// Monitoring unavailable: no measured recommendation badge.
		}
	}

	async function forceRefresh(experience?: ExperienceContext) {
		refreshing = true;
		try {
			await fetchInstances({ refresh: true }, experience);
		} finally {
			refreshing = false;
		}
	}

	let previousWizardOpen = false;
	$effect(() => {
		const open = $wizardOpen;
		if (previousWizardOpen && !open) {
			untrack(() => { if ($auth.token && $auth.projectId) void forceRefresh(); });
		}
		previousWizardOpen = open;
	});

	const ar = createAutoRefresh(() => fetchInstances(), {
		storageKey: 'dashboard-compute-instances',
		invokeOnMount: false,
		defaultActive: true,
		defaultInterval: 10,
		intervalOptions: [10, 15, 30, 60],
	});

	// 전이 중 인스턴스가 있으면 4초 가속, 모두 안정되면 해제
	$effect(() => {
		const hasTransitional = instances.some(i => isTransitional(i.status));
		ar.setBoost(hasTransitional ? 4 : null);
	});

	async function startInstance(id: string) {
		if (!targetsAllowed([id], 'start')) return;
		const experience = beginExperienceAction('compute', 'start', 'resource.list');
		try {
			await apiMut(t('list.startInstance'), () => api.withExperience(experience).post(`/api/v1/instances/${id}/start`, {}, $auth.token ?? undefined, $auth.projectId ?? undefined));
			ar.setBoost(4);
			await fetchInstances(undefined, experience);
		} catch {
			experienceState(experience, 'error');
			if (experience) void experienceApplied(experience);
		}
	}

	async function stopInstance(id: string) {
		const revision = scopeRevision;
		const token = $auth.token ?? undefined;
		const projectId = $auth.projectId ?? undefined;
		if (!targetsAllowed([id], 'stop')) return;
		if (!await confirmDialog(`${t('list.confirmStop')}\n\n${t('panel.stoppedQuotaWarning')}`)) return;
		if (revision !== scopeRevision || !targetsAllowed([id], 'stop')) return;
		const experience = beginExperienceAction('compute', 'stop', 'resource.list');
		try {
			await apiMut(t('list.stopInstance'), () => api.withExperience(experience).post(`/api/v1/instances/${id}/stop`, {}, token, projectId));
			ar.setBoost(4);
			await fetchInstances(undefined, experience);
		} catch {
			experienceState(experience, 'error');
			if (experience) void experienceApplied(experience);
		}
	}

	async function bulkAction(action: 'start' | 'stop' | 'delete') {
		const ids = [...selection.ids];
		const token = $auth.token ?? undefined;
		const projectId = $auth.projectId ?? undefined;
		const revision = scopeRevision;
		const selectedIds = selection.ids;
		const targetProjects = ids.map((id) => instances.find((row) => row.id === id)?.project_id);
		const targetStates = ids.map((id) => instances.find((row) => row.id === id)?.status);
		const owns = () => revision === scopeRevision && !!$auth.token && $canWrite
			&& instancesRevision === scopeRevision && ids.length > 0
			&& selection.ids === selectedIds && selection.ids.size === ids.length && ids.every((id) => selection.ids.has(id))
			&& ids.every((id, index) => {
				const row = instances.find((instance) => instance.id === id);
				return !!row && row.project_id === targetProjects[index] && row.status === targetStates[index]
					&& (action !== 'delete' || row.status === 'SHUTOFF');
			});
		if (bulkActioning || !owns()) return;
		if (action === 'delete') {
			if (!await confirmInstanceDeletion(`${t('list.confirmBulkDelete', { count: ids.length })}\n\n${t('panel.stoppedQuotaWarning')}`, {
				targets: ids.map(id => {
					const row = instances.find(row => row.id === id);
					return { id, name: row?.name, upperVolume: !!row?.union_upper_volume_id };
				}),
				adminMode: false,
				token,
				projectId,
				isCurrent: owns,
			})) return;
		} else if (action === 'stop') {
			if (!await confirmDialog(`${t('list.confirmBulkStop', { count: ids.length })}\n\n${t('panel.stoppedQuotaWarning')}`)) return;
		}
		if (!owns()) return;

		bulkActioning = true;
		const experience = beginExperienceAction('compute', action, 'resource.list');
		const results: { id: string; ok: boolean }[] = [];
		for (let index = 0; index < ids.length; index += 50) {
			if (!owns()) break;
			const chunk = ids.slice(index, index + 50);
			try {
				const response = await api.withExperience(experience).post<{ results: { id: string; ok: boolean }[] }>(
					'/api/v1/instances/bulk-action',
					{ action, instance_ids: chunk },
					token,
					projectId,
				);
				results.push(...response.results);
			} catch {
				results.push(...chunk.map((id) => ({ id, ok: false })));
			}
		}

		const successfulIds = results.filter((result) => result.ok).map((result) => result.id);
		const failureCount = results.length - successfulIds.length;
		const successKeys = {
			start: 'list.bulkStartSuccess',
			stop: 'list.bulkStopSuccess',
			delete: 'list.bulkDeleteSuccess',
		} as const;
		const failureKeys = {
			start: 'list.bulkStartFailed',
			stop: 'list.bulkStopFailed',
			delete: 'list.bulkDeleteFailed',
		} as const;
		if (successfulIds.length > 0) toast.success(t(successKeys[action], { count: successfulIds.length }));
		if (failureCount > 0) {
			toast.error(t(failureKeys[action], { count: failureCount }));
			experienceState(experience, 'error');
			if (experience) void experienceApplied(experience);
		}

		try {
			if ($auth.projectId === projectId) {
				selection.remove(successfulIds);
				ar.setBoost(4);
				await fetchInstances(undefined, experience);
			}
		} finally {
			bulkActioning = false;
		}
	}

	async function shelveInstance(id: string) {
		const revision = scopeRevision;
		const token = $auth.token ?? undefined;
		const projectId = $auth.projectId ?? undefined;
		const targetProject = instances.find((row) => row.id === id)?.project_id;
		const owns = () => revision === scopeRevision && targetsAllowed([id], 'shelve')
			&& instances.find((row) => row.id === id)?.project_id === targetProject;
		if (!owns()) return;
		if (!await confirmDialog(`${t('list.confirmShelve')}\n\n${t('panel.stoppedQuotaWarning')}`)) return;
		if (!owns()) return;
		const experience = beginExperienceAction('compute', 'update', 'resource.list');
		try {
			await apiMut(t('list.shelveInstance'), () => api.withExperience(experience).post(`/api/v1/instances/${id}/shelve`, {}, token, projectId));
			await fetchInstances(undefined, experience);
		} catch {
			experienceState(experience, 'error');
			if (experience) void experienceApplied(experience);
		}
	}

	async function unshelveInstance(id: string) {
		const revision = scopeRevision;
		const token = $auth.token ?? undefined;
		const projectId = $auth.projectId ?? undefined;
		if (!targetsAllowed([id], 'unshelve')) return;
		if (!await confirmDialog(t('list.confirmUnshelve'))) return;
		if (revision !== scopeRevision || !targetsAllowed([id], 'unshelve')) return;
		const experience = beginExperienceAction('compute', 'update', 'resource.list');
		try {
			await apiMut(t('list.unshelveInstance'), () => api.withExperience(experience).post(`/api/v1/instances/${id}/unshelve`, {}, token, projectId));
			await fetchInstances(undefined, experience);
		} catch {
			experienceState(experience, 'error');
			if (experience) void experienceApplied(experience);
		}
	}

	async function deleteInstance(id: string, name: string) {
		const revision = scopeRevision;
		const token = $auth.token ?? undefined;
		const projectId = $auth.projectId ?? undefined;
		const targetProject = instances.find((row) => row.id === id)?.project_id;
		const owns = () => revision === scopeRevision && targetsAllowed([id], 'delete')
			&& instances.find((row) => row.id === id)?.project_id === targetProject;
		if (!owns()) return;
		if (!await confirmInstanceDeletion(`${t('list.confirmDelete', { name })}\n\n${t('panel.stoppedQuotaWarning')}`, {
			targets: [{ id, name, upperVolume: !!instances.find(row => row.id === id)?.union_upper_volume_id }],
			adminMode: false,
			token,
			projectId,
			isCurrent: owns,
			includeRetainedVolumes: true,
		})) return;
		if (!owns()) return;
		const experience = beginExperienceAction('compute', 'delete', 'resource.list');
		try {
			await apiMut(t('list.deleteInstance'), () => api.withExperience(experience).delete(`/api/v1/instances/${id}`, token, projectId));
			await fetchInstances(undefined, experience);
		} catch {
			experienceState(experience, 'error');
			if (experience) void experienceApplied(experience);
		}
	}

	async function openConsole(id: string) {
		const experience = beginExperienceAction('compute', 'open', 'resource.list');
		try {
			const data = await api.withExperience(experience).get<{ url: string }>(`/api/v1/instances/${id}/console`, $auth.token ?? undefined, $auth.projectId ?? undefined);
			window.open(data.url, '_blank', 'noopener,noreferrer');
		} catch {
			toast.error(t('list.consoleUrlFailed'));
			experienceState(experience, 'error');
			if (experience) void experienceApplied(experience);
		}
	}

	async function handleAction(kind: 'console' | 'shelve' | 'unshelve' | 'delete' | 'start' | 'stop', instance: Instance) {
		if (kind === 'console') await openConsole(instance.id);
		else if (kind === 'shelve') await shelveInstance(instance.id);
		else if (kind === 'unshelve') await unshelveInstance(instance.id);
		else if (kind === 'delete') await deleteInstance(instance.id, instance.name);
		else if (kind === 'start') await startInstance(instance.id);
		else if (kind === 'stop') await stopInstance(instance.id);
	}

	function openInstancePanel(id: string) {
		invalidateInstanceDetailSelection();
		selectedInstanceId = id;
		history.pushState({ instanceId: id }, '', `/dashboard/compute/instances/${id}`);
	}

	function closeInstancePanel() {
		invalidateInstanceDetailSelection();
		selectedInstanceId = null;
		history.pushState({}, '', '/dashboard/compute/instances');
	}

	$effect(() => {
		const projectId = $auth.projectId;
		const token = $auth.token;
		void scopeRevision;
		untrack(() => {
			loadGeneration += 1;
			selection.clear();
			currentPage = 1;
			selectedInstanceId = null;
			instances = [];
			underutilized = {};
			error = '';
			if (!projectId || !token) { loading = false; return; }
			loading = true;
			void fetchInstances();
		});
	});
</script>

<PageShell class="bulk-selection-page space-y-4 pb-28 md:pb-32">
	<PageHeader breadcrumb={t('list.breadcrumb')} title={loading || error ? t('list.title') : t('list.titleWithCount', { count: instances.length })}>
		{#snippet actions()}
			<TutorialStartButton tour="vm-create" />
			<Button onclick={() => openWizard()} variant="primary" dataTour="vm-create-open">{t('list.createVmAction')}</Button>
		{/snippet}
	</PageHeader>
	{#if !loading && !error && instancesRevision === scopeRevision}
		<p class="text-sm tabular-nums text-ink-2" data-testid="instance-summary">{t('list.summary', { total: instances.length, active: instances.filter((instance) => instance.status === 'ACTIVE').length, errors: instances.filter((instance) => instance.status === 'ERROR').length })}</p>
	{/if}
	<ResourceToolbar label={t('list.toolbar')}>
		{#snippet filters()}
			<RegexSearch id="project-instance-search" bind:value={search} label={t('list.search')} placeholder={t('list.search')} />
		{/snippet}
		{#snippet actions()}
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={refreshing}
				onManualRefresh={() => forceRefresh(beginExperienceAction('compute', 'refresh', 'resource.list'))}
			/>
		{/snippet}
	</ResourceToolbar>
	<TableViewControls {view} />

	{#if error}
		<Alert tone="danger">{error}</Alert>
	{/if}

	<div class={loading || instancesRevision !== scopeRevision ? "flex min-h-[calc(100dvh-var(--app-header-height)-12rem)] flex-col" : ""} data-tour={!$wizardOpen && !loading && !refreshing && !error && instancesRevision === scopeRevision ? 'instance-list' : undefined}>
	{#if loading || (instances.length > 0 && instancesRevision !== scopeRevision)}
		<LoadingState variant="surface" label={tl('state.loadingNamed', { name: t('list.title') })} />
	{:else if error && instances.length === 0}
		<Button variant="secondary" onclick={() => forceRefresh(beginExperienceAction('compute', 'retry', 'resource.list'))}>{t('list.retry')}</Button>
	{:else if instances.length === 0}
		<EmptyState headline={t('list.emptyTitle')} description={t('list.emptyDescription')} />
	{:else if filteredInstances.length === 0}
		<EmptyState headline={t('list.filteredEmpty')} description={t('list.filteredEmptyDescription')}>
			{#snippet cta()}<Button variant="secondary" onclick={() => { search = ''; view.reset(); currentPage = 1; selection.clear(); }}>{t('list.clearFilters')}</Button>{/snippet}
		</EmptyState>
	{/if}
	{#if !loading && instancesRevision === scopeRevision}
			<InstancesTable
				instances={visibleInstances}
				{underutilized}
				{view}
				selectedIds={selection.ids}
				{selectableIds}
				selectionDisabled={bulkActioning}
				onSelect={openInstancePanel}
				onAction={handleAction}
				onToggleSelect={(id) => selection.toggle(id)}
				onToggleAll={() => selection.toggleAll(selectableIds)}
			/>
	{/if}
	</div>
	{#if !loading && instances.length > 0 && instancesRevision === scopeRevision}
		<footer class="flex flex-wrap items-end justify-between gap-3" data-testid="instance-list-footer">
			<p class="text-sm tabular-nums text-ink-2">{t('list.resultCount', { count: filteredInstances.length, total: instances.length })}</p>
			<div class="flex max-w-full flex-wrap items-end gap-3" data-testid="instance-pagination-controls">
			<div class="flex items-center gap-2"><label for="project-instance-page-size" class="text-xs text-ink-2">{t('list.pageSize')}</label><SelectInput id="project-instance-page-size" bind:value={pageSize} onchange={() => { currentPage = 1; selection.clear(); }}>{#each [10, 20, 30] as size}<option value={String(size)}>{size}</option>{/each}</SelectInput></div>
			<Pagination class="!mt-0" page={visiblePage} {totalPages} hasPrev={visiblePage > 1} hasNext={visiblePage < totalPages} onPrev={() => { currentPage = visiblePage - 1; selection.clear(); }} onNext={() => { currentPage = visiblePage + 1; selection.clear(); }} />
			</div>
		</footer>
	{/if}

	<BulkSelectionOverlay
		count={selection.count}
		ariaLabel={t('list.bulkActions')}
		actions={[
			{ key: 'start', label: t('list.start'), tone: 'success', onAction: () => bulkAction('start') },
			{ key: 'stop', label: t('list.stop'), tone: 'warning', onAction: () => bulkAction('stop') },
			...(canBulkDelete ? [{ key: 'delete', label: t('list.delete'), tone: 'danger' as const, onAction: () => bulkAction('delete') }] : []),
		]}
		busy={bulkActioning}
		onClear={() => selection.clear()}
	/>
</PageShell>

{#if selectedInstanceId && instancesRevision === scopeRevision}
	<SlidePanel onClose={closeInstancePanel} ariaLabel={t('list.instanceDetails')}>
		<InstanceDetailPanel instanceId={selectedInstanceId} onClose={closeInstancePanel} onUpdated={() => void fetchInstances({ refresh: true })} />
	</SlidePanel>
{/if}
