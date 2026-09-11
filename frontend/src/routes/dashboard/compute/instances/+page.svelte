<script lang="ts">
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { untrack } from 'svelte';
	import { page } from '$app/stores';
	import { auth } from '$lib/stores/auth';
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

	const mockupActive = $derived($page.data.mockup?.active === true);
	const selectableIds = $derived(new Set(instances.map((instance) => instance.id)));

	function openCreateEntryPoint() {
		if (mockupActive) {
			toast.info('mockup mode에서는 VM 생성 wizard를 제외합니다.');
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
		const cached = swrGet<Instance[]>(path);
		if (cached && instances.length === 0) {
			instances = cached;
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
				error = e instanceof ApiError ? `조회 실패 (${e.status}): ${(e as ApiError).message}` : '서버 오류';
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
		try {
			await apiMut('인스턴스 시작', () => api.post(`/api/v1/instances/${id}/start`, {}, $auth.token ?? undefined, $auth.projectId ?? undefined));
			ar.setBoost(4);
			await fetchInstances();
		} catch { /* error toast shown by apiMut */ }
	}

	async function stopInstance(id: string) {
		if (!await confirmDialog('인스턴스를 종료하시겠습니까?')) return;
		try {
			await apiMut('인스턴스 종료', () => api.post(`/api/v1/instances/${id}/stop`, {}, $auth.token ?? undefined, $auth.projectId ?? undefined));
			ar.setBoost(4);
			await fetchInstances();
		} catch { /* error toast shown by apiMut */ }
	}

	async function bulkAction(action: 'start' | 'stop' | 'delete') {
		const ids = [...selection.ids];
		const token = $auth.token ?? undefined;
		const projectId = $auth.projectId ?? undefined;
		if (ids.length === 0) return;

		const labels: Record<string, string> = { start: '시작', stop: '종료', delete: '삭제' };
		const verb = labels[action];

		if (action === 'stop' || action === 'delete') {
			const msg = action === 'delete'
				? `선택한 인스턴스 ${ids.length}개를 삭제하시겠습니까?\nManila share와 볼륨도 함께 삭제됩니다.`
				: `선택한 인스턴스 ${ids.length}개를 종료하시겠습니까?`;
			if (!await confirmDialog(msg)) return;
		}

		bulkActioning = true;
		const results: { id: string; ok: boolean }[] = [];
		for (let index = 0; index < ids.length; index += 50) {
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
		if (successfulIds.length > 0) toast.success(`${successfulIds.length}개 ${verb} 요청을 완료했습니다.`);
		if (failureCount > 0) toast.error(`${failureCount}개 ${verb}에 실패했습니다.`);

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
		if (!await confirmDialog('인스턴스를 보관하시겠습니까? (SHELVED_OFFLOADED 상태로 전환됩니다)')) return;
		try {
			await apiMut('인스턴스 보관', () => api.post(`/api/v1/instances/${id}/shelve`, {}, $auth.token ?? undefined, $auth.projectId ?? undefined));
			await fetchInstances();
		} catch { /* error toast shown by apiMut */ }
	}

	async function unshelveInstance(id: string) {
		if (!await confirmDialog('인스턴스 보관을 해제하시겠습니까?')) return;
		try {
			await apiMut('인스턴스 보관 해제', () => api.post(`/api/v1/instances/${id}/unshelve`, {}, $auth.token ?? undefined, $auth.projectId ?? undefined));
			await fetchInstances();
		} catch { /* error toast shown by apiMut */ }
	}

	async function deleteInstance(id: string, name: string) {
		if (!await confirmDialog(`"${name}" 인스턴스를 삭제하시겠습니까?\nManila share와 볼륨도 함께 삭제됩니다.`)) return;
		try {
			await apiMut('인스턴스 삭제', () => api.delete(`/api/v1/instances/${id}`, $auth.token ?? undefined, $auth.projectId ?? undefined));
			await fetchInstances();
		} catch { /* error toast shown by apiMut */ }
	}

	async function openConsole(id: string) {
		try {
			const data = await api.get<{ url: string }>(`/api/v1/instances/${id}/console`, $auth.token ?? undefined, $auth.projectId ?? undefined);
			window.open(data.url, '_blank', 'noopener,noreferrer');
		} catch {
			toast.error('콘솔 URL을 가져올 수 없습니다');
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

<PageShell class="bulk-selection-page pb-28 md:pb-32">
	<PageHeader breadcrumb="COMPUTE / INSTANCES" title="인스턴스">
		{#snippet actions()}
			<Button onclick={openCreateEntryPoint} variant="primary">+ VM 생성</Button>
		{/snippet}
	</PageHeader>
	<ResourceToolbar label="인스턴스 목록 도구">
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
		<Alert tone="danger" class="mb-4">{error}</Alert>
	{/if}


	{#if loading}
		<LoadingSkeleton variant="table" rows={5} />
	{:else if instances.length === 0}
		<EmptyState headline="인스턴스가 없습니다" description="첫 가상 머신을 생성해 프로젝트를 시작하세요.">
			{#snippet cta()}<Button onclick={openCreateEntryPoint} variant="primary">VM 생성</Button>{/snippet}
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
		ariaLabel="선택한 인스턴스 일괄 작업"
		actions={[
			{ key: 'start', label: '시작', tone: 'success', onAction: () => bulkAction('start') },
			{ key: 'stop', label: '종료', tone: 'warning', onAction: () => bulkAction('stop') },
			{ key: 'delete', label: '삭제', tone: 'danger', onAction: () => bulkAction('delete') },
		]}
		busy={bulkActioning}
		onClear={() => selection.clear()}
	/>
</PageShell>

{#if selectedInstanceId}
	<SlidePanel onClose={closeInstancePanel} ariaLabel="인스턴스 상세">
		<InstanceDetailPanel instanceId={selectedInstanceId} onClose={closeInstancePanel} />
	</SlidePanel>
{/if}
