<script lang="ts">
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { untrack } from 'svelte';
	import { pushState } from '$app/navigation';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import BulkSelectionOverlay, { type BulkSelectionAction } from '$lib/components/ui/BulkSelectionOverlay.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import { createResourceSelection } from '$lib/utils/resourceSelection.svelte';
	import { executeBulkMutations } from '$lib/utils/bulkActions';
	import DbCreatePanel from '$lib/components/database/DbCreatePanel.svelte';
	import SlidePanel from '$lib/components/SlidePanel.svelte';
	import DbInstanceDetailPanel from '$lib/components/database/DbInstanceDetailPanel.svelte';
	import DbInstancesTable from '$lib/components/database/DbInstancesTable.svelte';
	import type { DbInstance } from '$lib/types/database';
	import { toast } from '$lib/stores/toast';
	import { Button, EmptyState, PageHeader, PageShell, ResourceToolbar } from '$lib/components/ui';

	let instances = $state<DbInstance[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let deleting = $state<string | null>(null);
	let restarting = $state<string | null>(null);
	let showCreatePanel = $state(false);
	let selectedInstanceId = $state<string | null>(null);
	const selection = createResourceSelection();
	let bulkBusy = $state(false);
	const selectableIds = $derived(new Set(instances.map((instance) => instance.id)));

	function prefetchCreateMetadata() {
		const token = $auth.token ?? undefined;
		const projectId = $auth.projectId ?? undefined;
		void api.prefetch('/api/v1/database-instances/flavors', token, projectId);
		void api.prefetch('/api/v1/database-instances/datastores', token, projectId);
	}

	function openPanel(id: string) {
		selectedInstanceId = id;
		pushState(`/dashboard/database/instances/${id}`, { instanceId: id });
	}

	function closePanel() {
		selectedInstanceId = null;
		pushState('/dashboard/database/instances', {});
	}

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	async function load() {
		if (instances.length === 0) loading = true;
		else refreshing = true;
		const tokenSnapshot = $auth.token ?? undefined;
		const projectSnapshot = $auth.projectId ?? undefined;
		try {
			const nextInstances = await api.get<DbInstance[]>('/api/v1/database-instances', tokenSnapshot, projectSnapshot);
			if ($auth.projectId !== projectSnapshot) return;
			instances = nextInstances;
			selection.retain(nextInstances.map((instance) => instance.id));
		} catch {
			if ($auth.projectId === projectSnapshot) {
				instances = [];
				selection.clear();
			}
		} finally {
			if ($auth.projectId === projectSnapshot) {
				loading = false;
				refreshing = false;
			}
		}
	}

	async function forceRefresh() {
		const tokenSnapshot = $auth.token ?? undefined;
		const projectSnapshot = $auth.projectId ?? undefined;
		refreshing = true;
		try {
			const nextInstances = await api.get<DbInstance[]>('/api/v1/database-instances', tokenSnapshot, projectSnapshot, { refresh: true });
			if ($auth.projectId !== projectSnapshot) return;
			instances = nextInstances;
			selection.retain(nextInstances.map((instance) => instance.id));
		} catch {
			if ($auth.projectId === projectSnapshot) instances = [];
		} finally {
			if ($auth.projectId === projectSnapshot) refreshing = false;
		}
	}

	async function deleteInstance(id: string, name: string) {
		if (!await confirmDialog(`DB 인스턴스 "${name || id.slice(0, 8)}"를 삭제하시겠습니까?`)) return;
		deleting = id;
		try {
			await api.delete(`/api/v1/database-instances/${id}`, token, projectId);
			await load();
		} catch (e) {
			toast.error('삭제 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		} finally {
			deleting = null;
		}
	}

	async function restartInstance(id: string, name: string) {
		if (!await confirmDialog(`DB 인스턴스 "${name || id.slice(0, 8)}"를 재시작하시겠습니까?`)) return;
		restarting = id;
		try {
			await api.post(`/api/v1/database-instances/${id}/restart`, {}, token, projectId);
			await load();
		} catch (e) {
			toast.error('재시작 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		} finally {
			restarting = null;
		}
	}
	async function runBulk(action: 'restart' | 'delete') {
		const snapshot = [...selection.ids];
		if (snapshot.length === 0) return;
		const label = action === 'restart' ? '재시작' : '삭제';
		if (!await confirmDialog(`선택한 DB 인스턴스 ${snapshot.length}개를 ${label}하시겠습니까?`)) return;
		const tokenSnapshot = $auth.token ?? undefined;
		const projectSnapshot = $auth.projectId ?? undefined;
		bulkBusy = true;
		try {
			const results = await executeBulkMutations(snapshot, (id) => action === 'restart'
				? api.post(`/api/v1/database-instances/${id}/restart`, {}, tokenSnapshot, projectSnapshot)
				: api.delete(`/api/v1/database-instances/${id}`, tokenSnapshot, projectSnapshot));
			const successful = results.filter((result) => result.ok).map((result) => result.id);
			const failed = results.length - successful.length;
			if (successful.length > 0) toast.success(`${successful.length}개 ${label} 요청을 완료했습니다.`);
			if (failed > 0) toast.error(`${failed}개 ${label}에 실패했습니다.`);
			if ($auth.projectId === projectSnapshot) {
				selection.remove(successful);
				await load();
			}
		} finally {
			bulkBusy = false;
		}
	}

	const bulkActions: BulkSelectionAction[] = [
		{ key: 'restart', label: '재시작', tone: 'warning', onAction: () => runBulk('restart') },
		{ key: 'delete', label: '삭제', tone: 'danger', onAction: () => runBulk('delete') },
	];

	const ar = createAutoRefresh(() => load(), {
		storageKey: 'dashboard-database-instances',
		invokeOnMount: false,
		defaultActive: true,
		defaultInterval: 15,
		intervalOptions: [10, 15, 30, 60],
	});

	$effect(() => {
		const pid = $auth.projectId;
		instances = [];
		selection.clear();
		if (!pid) return;
		untrack(() => load());
	});
</script>

<DbCreatePanel bind:open={showCreatePanel} onCreated={load} />

{#if selectedInstanceId}
	<SlidePanel onClose={closePanel} ariaLabel="데이터베이스 인스턴스 상세" width="w-full md:w-[70vw] max-w-4xl">
		<DbInstanceDetailPanel
			instanceId={selectedInstanceId}
			token={$auth.token ?? undefined}
			projectId={$auth.projectId ?? undefined}
			onClose={closePanel}
			onDeleted={() => { closePanel(); load(); }}
		/>
	</SlidePanel>
{/if}

<PageShell class="bulk-selection-page space-y-4">
	<PageHeader breadcrumb="DATABASE / INSTANCES" title="DB 인스턴스">
		{#snippet actions()}
			<Button onclick={() => (showCreatePanel = true)} onintent={prefetchCreateMetadata} variant="primary">+ 인스턴스 생성</Button>
		{/snippet}
	</PageHeader>
	<ResourceToolbar label="데이터베이스 인스턴스 목록 도구">
		{#snippet actions()}
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={refreshing || loading}
				onManualRefresh={forceRefresh}
			/>
		{/snippet}
	</ResourceToolbar>

	{#if loading}
		<LoadingSkeleton variant="table" rows={5} />
	{:else if instances.length === 0}
		<EmptyState headline="DB 인스턴스가 없습니다" description="관리형 데이터베이스 인스턴스를 생성하세요." />
	{:else}
		<DbInstancesTable
			{instances}
			{refreshing}
			{restarting}
			{deleting}
			selectedIds={selection.ids}
			selectableIds={selectableIds}
			selectionDisabled={bulkBusy}
			onToggleSelect={(id) => selection.toggle(id)}
			onToggleAll={() => selection.toggleAll(selectableIds)}
			onOpen={openPanel}
			onRestart={restartInstance}
			onDelete={deleteInstance}
		/>
		<BulkSelectionOverlay count={selection.count} ariaLabel="선택한 DB 인스턴스 일괄 작업" actions={bulkActions} busy={bulkBusy} onClear={() => selection.clear()} />
	{/if}
</PageShell>
