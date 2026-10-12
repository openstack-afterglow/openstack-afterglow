<script lang="ts">
	import { t } from '$lib/i18n/ns/instance';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { onDestroy, untrack } from 'svelte';
	import { page } from '$app/stores';
	import { auth, canWrite } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { createSwr } from '$lib/utils/swr.svelte';
	import { apiMut } from '$lib/api/mutations';
	import type { Instance } from '$lib/types/compute';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import InstanceDetailPanel from '$lib/components/InstanceDetailPanel.svelte';
	import SlidePanel from '$lib/components/SlidePanel.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import { Alert, Button, EmptyState, PageHeader, PageShell, ResourceToolbar } from '$lib/components/ui';
	import { openWizard } from '$lib/stores/wizard';
	import TutorialStartButton from '$lib/tutorial/TutorialStartButton.svelte';
	import InstancesTable from '$lib/components/instance/list/InstancesTable.svelte';
	import { toast } from '$lib/stores/toast';
	import { isTransitional } from '$lib/utils/instanceStatus';
	import BulkSelectionOverlay from '$lib/components/ui/BulkSelectionOverlay.svelte';
	import { createResourceSelection } from '$lib/utils/resourceSelection.svelte';

	let instances = $state<Instance[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let error = $state('');
	let selectedInstanceId = $state<string | null>(null);
	let underutilized = $state<Record<string, boolean>>({});
	const selection = createResourceSelection();
	let bulkActioning = $state(false);
	let loadGeneration = 0;
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

	const mockupActive = $derived($page.data.mockup?.active === true);
	const selectableIds = $derived(new Set(instances.map((instance) => instance.id)));

	function openCreateEntryPoint() {
		if (mockupActive) {
			toast.info(t('list.mockupCreateExcluded'));
			return;
		}
		openWizard();
	}
	const { swrGet, swrSet } = createSwr(() => $auth.projectId);

	async function fetchInstances(opts?: { refresh?: boolean }) {
		const path = '/api/v1/instances';
		const requestToken = $auth.token ?? undefined;
		const requestProjectId = $auth.projectId ?? undefined;
		const generation = ++loadGeneration;
		const requestRevision = scopeRevision;
		const cached = swrGet<Instance[]>(path);
		if (cached && instances.length === 0) {
			instances = cached;
			instancesRevision = requestRevision;
			selection.retain(cached.map((instance) => instance.id));
		}
		const listPromise = api.get<Instance[]>(path, requestToken, requestProjectId, opts);
		const summaryPromise = fetchSummaryBatch(requestToken, requestProjectId, generation, opts);
		try {
			const fetchedInstances = await listPromise;
			if (
				generation !== loadGeneration
				|| ($auth.token ?? undefined) !== requestToken
				|| ($auth.projectId ?? undefined) !== requestProjectId
			) return;
			instances = fetchedInstances;
			instancesRevision = requestRevision;
			selection.retain(fetchedInstances.map((instance) => instance.id));
			swrSet(path, instances);
			error = '';
		} catch (e) {
			if (
				generation === loadGeneration
				&& ($auth.token ?? undefined) === requestToken
				&& ($auth.projectId ?? undefined) === requestProjectId
				&& !cached
			) {
				error = e instanceof ApiError ? t('list.queryFailed', { status: e.status, message: e.message }) : t('list.serverError');
			}
		} finally {
			if (generation === loadGeneration && ($auth.projectId ?? undefined) === requestProjectId) {
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
	) {
		if (!requestToken) return;
		try {
			const resp = await api.get<{
				prometheus_available: boolean;
				instances: Record<string, { cpu_avg: number | null; mem_avg: number | null; underutilized: boolean }>;
			}>('/api/v1/instances/metrics-summary-batch', requestToken, requestProjectId, opts);
			if (
				generation !== loadGeneration
				|| ($auth.token ?? undefined) !== requestToken
				|| ($auth.projectId ?? undefined) !== requestProjectId
			) return;
			if (resp.prometheus_available) {
				const map: Record<string, boolean> = {};
				for (const [id, data] of Object.entries(resp.instances)) map[id] = data.underutilized;
				underutilized = map;
			}
		} catch {
			// Prometheus 미연결 등 — 배지 없음, 에러 미노출
		}
	}

	async function forceRefresh() {
		refreshing = true;
		try {
			await fetchInstances({ refresh: true });
		} finally {
			refreshing = false;
		}
	}

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
		try {
			await apiMut(t('list.startInstance'), () => api.post(`/api/v1/instances/${id}/start`, {}, $auth.token ?? undefined, $auth.projectId ?? undefined));
			ar.setBoost(4);
			await fetchInstances();
		} catch { /* error toast shown by apiMut */ }
	}

	async function stopInstance(id: string) {
		const revision = scopeRevision;
		const token = $auth.token ?? undefined;
		const projectId = $auth.projectId ?? undefined;
		if (!targetsAllowed([id], 'stop')) return;
		if (!await confirmDialog(`${t('list.confirmStop')}\n\n${t('panel.stoppedQuotaWarning')}`)) return;
		if (revision !== scopeRevision || !targetsAllowed([id], 'stop')) return;
		try {
			await apiMut(t('list.stopInstance'), () => api.post(`/api/v1/instances/${id}/stop`, {}, token, projectId));
			ar.setBoost(4);
			await fetchInstances();
		} catch { /* error toast shown by apiMut */ }
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
		if (action === 'stop' || action === 'delete') {
			const msg = action === 'delete'
				? `${t('list.confirmBulkDelete', { count: ids.length })}\n\n${t('panel.stoppedQuotaWarning')}`
				: `${t('list.confirmBulkStop', { count: ids.length })}\n\n${t('panel.stoppedQuotaWarning')}`;
			if (!await confirmDialog(msg)) return;
		}
		if (!owns()) return;

		bulkActioning = true;
		const results: { id: string; ok: boolean }[] = [];
		for (let index = 0; index < ids.length; index += 50) {
			if (!owns()) break;
			const chunk = ids.slice(index, index + 50);
			try {
				const response = await api.post<{ results: { id: string; ok: boolean }[] }>(
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
		if (failureCount > 0) toast.error(t(failureKeys[action], { count: failureCount }));

		try {
			if ($auth.projectId === projectId) {
				selection.remove(successfulIds);
				ar.setBoost(4);
				await fetchInstances();
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
		try {
			await apiMut(t('list.shelveInstance'), () => api.post(`/api/v1/instances/${id}/shelve`, {}, token, projectId));
			await fetchInstances();
		} catch { /* error toast shown by apiMut */ }
	}

	async function unshelveInstance(id: string) {
		const revision = scopeRevision;
		const token = $auth.token ?? undefined;
		const projectId = $auth.projectId ?? undefined;
		if (!targetsAllowed([id], 'unshelve')) return;
		if (!await confirmDialog(t('list.confirmUnshelve'))) return;
		if (revision !== scopeRevision || !targetsAllowed([id], 'unshelve')) return;
		try {
			await apiMut(t('list.unshelveInstance'), () => api.post(`/api/v1/instances/${id}/unshelve`, {}, token, projectId));
			await fetchInstances();
		} catch { /* error toast shown by apiMut */ }
	}

	async function deleteInstance(id: string, name: string) {
		const revision = scopeRevision;
		const token = $auth.token ?? undefined;
		const projectId = $auth.projectId ?? undefined;
		const targetProject = instances.find((row) => row.id === id)?.project_id;
		const owns = () => revision === scopeRevision && targetsAllowed([id], 'delete')
			&& instances.find((row) => row.id === id)?.project_id === targetProject;
		if (!owns()) return;
		if (!await confirmDialog(`${t('list.confirmDelete', { name })}\n\n${t('panel.stoppedQuotaWarning')}`)) return;
		if (!owns()) return;
		try {
			await apiMut(t('list.deleteInstance'), () => api.delete(`/api/v1/instances/${id}`, token, projectId));
			await fetchInstances();
		} catch { /* error toast shown by apiMut */ }
	}

	async function openConsole(id: string) {
		try {
			const data = await api.get<{ url: string }>(`/api/v1/instances/${id}/console`, $auth.token ?? undefined, $auth.projectId ?? undefined);
			window.open(data.url, '_blank', 'noopener,noreferrer');
		} catch {
			toast.error(t('list.consoleUrlFailed'));
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
		selectedInstanceId = id;
		history.pushState({ instanceId: id }, '', `/dashboard/compute/instances/${id}`);
	}

	function closeInstancePanel() {
		selectedInstanceId = null;
		history.pushState({}, '', '/dashboard/compute/instances');
	}

	$effect(() => {
		const projectId = $auth.projectId;
		untrack(() => {
			selection.clear();
			if (!projectId) return;
			loading = true;
			void fetchInstances();
		});
	});
</script>

<PageShell class="bulk-selection-page space-y-4 pb-28 md:pb-32">
	<PageHeader breadcrumb={t('list.breadcrumb')} title={t('list.title')}>
		{#snippet actions()}
			<Button onclick={openCreateEntryPoint} variant="primary">{t('list.createVmAction')}</Button>
		{/snippet}
	</PageHeader>
	<ResourceToolbar label={t('list.toolbar')}>
		{#snippet actions()}
			<TutorialStartButton tour="vm-create" />
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={refreshing}
				onManualRefresh={forceRefresh}
			/>
		{/snippet}
	</ResourceToolbar>

	{#if error}
		<Alert tone="danger">{error}</Alert>
	{/if}

	{#if loading}
		<LoadingSkeleton variant="table" rows={5} />
	{:else if instances.length === 0}
		<EmptyState headline={t('list.emptyTitle')} description={t('list.emptyDescription')}>
			{#snippet cta()}<Button onclick={openCreateEntryPoint} variant="primary">{t('list.createVm')}</Button>{/snippet}
		</EmptyState>
	{:else}
		<InstancesTable
			{instances}
			{underutilized}
			selectedIds={selection.ids}
			{selectableIds}
			selectionDisabled={bulkActioning}
			onSelect={openInstancePanel}
			onAction={handleAction}
			onToggleSelect={(id) => selection.toggle(id)}
			onToggleAll={() => selection.toggleAll(selectableIds)}
		/>
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

{#if selectedInstanceId}
	<SlidePanel onClose={closeInstancePanel} ariaLabel={t('list.instanceDetails')}>
		<InstanceDetailPanel instanceId={selectedInstanceId} onClose={closeInstancePanel} />
	</SlidePanel>
{/if}
