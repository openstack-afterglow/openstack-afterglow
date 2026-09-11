<script lang="ts">
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import type { SwiftContainer, AccountMeta } from '$lib/types/objectStorage';
	import { Alert, Button, EmptyState, PageHeader, PageShell, ResourceToolbar, StatTile } from '$lib/components/ui';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import BucketCreateDialog from '$lib/components/object-storage/BucketCreateDialog.svelte';
	import BucketCardGrid from '$lib/components/object-storage/BucketCardGrid.svelte';
	import BucketCardSkeleton from '$lib/components/object-storage/BucketCardSkeleton.svelte';
	import BulkSelectionOverlay from '$lib/components/ui/BulkSelectionOverlay.svelte';
	import SelectionToolbar from '$lib/components/ui/SelectionToolbar.svelte';
	import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';
	import { createResourceSelection } from '$lib/utils/resourceSelection.svelte';
	import { executeBulkMutations } from '$lib/utils/bulkActions';
	import { toast } from '$lib/stores/toast';

	let containers = $state<SwiftContainer[]>([]);
	let deletedContainers = $state<SwiftContainer[]>([]);
	let account = $state<AccountMeta | null>(null);
	let loading = $state(true);
	let refreshing = $state(false);
	let trashLoading = $state(true);
	let activeError = $state('');
	let trashError = $state('');
	let accountLoading = $state(true);
	let accountError = $state('');
	let loadGeneration = 0;
	let deleting = $state<string | null>(null);
	let restoring = $state<string | null>(null);
	let showModal = $state(false);
	let busy = $state(false);
	let selectionDomain = $state<'active' | 'trash'>('active');
	const selection = createResourceSelection();
	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	function setSelectionDomain(domain: 'active' | 'trash') {
		if (selectionDomain !== domain) selection.clear();
		selectionDomain = domain;
	}

	function retainSelection() {
		selection.retain(selectionDomain === 'active'
			? containers.map((c) => c.name)
			: deletedContainers.map((c) => c.name));
	}

	async function load(refresh = false) {
		const requestToken = token;
		const requestProject = projectId;
		const generation = ++loadGeneration;
		const owns = () => generation === loadGeneration && token === requestToken && projectId === requestProject;
		if (containers.length === 0) loading = true;
		else refreshing = true;
		trashLoading = true;
		activeError = '';
		trashError = '';
		accountLoading = true;
		accountError = '';
		const opts = refresh ? { refresh: true } : undefined;
		const activePromise = api.get<SwiftContainer[]>('/api/v1/object-storage', requestToken, requestProject, opts)
			.then((value) => {
				if (!owns()) return;
				containers = value;
				retainSelection();
			})
			.catch((loadError) => {
				if (!owns()) return;
				containers = [];
				activeError = loadError instanceof Error ? loadError.message : '버킷 조회 실패';
			})
			.finally(() => {
				if (owns()) loading = false;
			});
		const trashPromise = api.get<SwiftContainer[]>('/api/v1/object-storage/trash/containers', requestToken, requestProject, opts)
			.then((value) => {
				if (!owns()) return;
				deletedContainers = value;
				retainSelection();
			})
			.catch((loadError) => {
				if (!owns()) return;
				deletedContainers = [];
				trashError = loadError instanceof Error ? loadError.message : '휴지통 버킷 조회 실패';
			})
			.finally(() => {
				if (owns()) trashLoading = false;
			});
		const accountPromise = api.get<AccountMeta>('/api/v1/object-storage/account', requestToken, requestProject, opts)
			.then((value) => {
				if (owns()) account = value;
			})
			.catch((loadError) => {
				if (!owns()) return;
				account = null;
				accountError = loadError instanceof Error ? loadError.message : '계정 통계 조회 실패';
			})
			.finally(() => {
				if (owns()) accountLoading = false;
			});
		await Promise.allSettled([activePromise, trashPromise, accountPromise]);
		if (owns()) refreshing = false;
	}

	async function forceRefresh() {
		await load(true);
	}

	function formatAccountBytes(bytes: number): string {
		if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GiB`;
		if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MiB`;
		if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
		return `${bytes} B`;
	}

	async function createContainer(name: string): Promise<string | true> {
		try {
			await api.post('/api/v1/object-storage', { name }, token, projectId);
			await load(true);
			return true;
		} catch (e) {
			return e instanceof ApiError ? e.message : '버킷 생성 실패';
		}
	}

	async function deleteContainer(name: string) {
		if (!await confirmDialog(`버킷 "${name}"을 휴지통으로 이동합니다. 보관 기간(기본 30일) 내에 복구할 수 있습니다. 계속하시겠습니까?`)) return;
		deleting = name;
		try {
			await api.delete(`/api/v1/object-storage/${encodeURIComponent(name)}`, token, projectId);
			await load(true);
		} catch (e) {
			toast.error('삭제 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		} finally {
			deleting = null;
		}
	}

	async function restoreContainer(name: string) {
		restoring = name;
		try {
			await api.post(`/api/v1/object-storage/trash/containers/${encodeURIComponent(name)}/restore`, {}, token, projectId);
			await load(true);
			toast.success(`버킷 "${name}" 복구 완료`);
		} catch (e) {
			toast.error('복구 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		} finally {
			restoring = null;
		}
	}

	async function purgeContainer(name: string) {
		if (!await confirmDialog(`버킷 "${name}"을 영구 삭제합니다. 이 작업은 되돌릴 수 없습니다. 계속하시겠습니까?`)) return;
		deleting = name;
		try {
			await api.delete(`/api/v1/object-storage/trash/containers/${encodeURIComponent(name)}`, token, projectId);
			await load(true);
		} catch (e) {
			toast.error('영구 삭제 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		} finally {
			deleting = null;
		}
	}

	async function runBulk(action: 'delete' | 'restore' | 'purge') {
		const ids = [...selection.ids];
		if (ids.length === 0) return;
		if (action === 'delete' && !await confirmDialog(`${ids.length}개 버킷을 휴지통으로 이동합니다. 보관 기간 내에 복구할 수 있습니다. 계속하시겠습니까?`)) return;
		if (action === 'purge' && !await confirmDialog(`${ids.length}개 버킷을 영구 삭제합니다. 이 작업은 되돌릴 수 없습니다. 계속하시겠습니까?`)) return;
		busy = true;
		const requestToken = token;
		const requestProject = projectId;
		const endpoint = (id: string) => action === 'delete'
			? `/api/v1/object-storage/${encodeURIComponent(id)}`
			: action === 'restore'
				? `/api/v1/object-storage/trash/containers/${encodeURIComponent(id)}/restore`
				: `/api/v1/object-storage/trash/containers/${encodeURIComponent(id)}`;
		const results = await executeBulkMutations(ids, (id) =>
			action === 'restore'
				? api.post(endpoint(id), {}, requestToken, requestProject)
				: api.delete(endpoint(id), requestToken, requestProject)
		);
		if ($auth.projectId === requestProject) {
			selection.remove(results.filter((r) => r.ok).map((r) => r.id));
			await load(true);
		}
		const successCount = results.filter((r) => r.ok).length;
		const failureCount = results.length - successCount;
		const label = action === 'delete' ? '휴지통 이동' : action === 'restore' ? '복구' : '영구 삭제';
		if (successCount) toast.success(`${successCount}개 ${label} 요청을 완료했습니다.`);
		if (failureCount) toast.error(`${failureCount}개 ${label}에 실패했습니다.`);
		busy = false;
	}

	const ar = createAutoRefresh(() => load(), {
		storageKey: 'dashboard-object-storage',
		invokeOnMount: false,
		defaultActive: true,
		defaultInterval: 30,
		intervalOptions: [10, 15, 30, 60],
	});

	$effect(() => {
		const pid = $auth.projectId;
		selection.clear();
		containers = [];
		deletedContainers = [];
		account = null;
		if (!pid) {
			loading = false;
			return;
		}
		untrack(() => load());
	});
</script>

<BucketCreateDialog bind:open={showModal} onCreate={createContainer} />

<PageShell class="bulk-selection-page space-y-4">
	<PageHeader breadcrumb="OBJECT STORAGE / BUCKETS" title="버킷">
		{#snippet actions()}
			<Button onclick={() => (showModal = true)} variant="primary">+ 버킷 생성</Button>
		{/snippet}
	</PageHeader>
	<ResourceToolbar label="버킷 목록 도구">
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
	<section aria-label="오브젝트 스토리지 계정 통계" class="mb-6">
		{#if accountLoading}
			<Alert tone="neutral">계정 통계를 불러오는 중...</Alert>
		{:else if accountError}
			<Alert tone="danger" title="계정 통계 조회 실패">{accountError}</Alert>
		{:else if account}
			<div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
				<StatTile label="버킷" value={account.container_count} accent="indigo" />
				<StatTile label="오브젝트" value={account.object_count} accent="cyan" />
				<StatTile label="사용량" value={formatAccountBytes(account.bytes_used)} accent="violet" />
			</div>
		{:else}
			<Alert tone="neutral">계정 통계가 없습니다.</Alert>
		{/if}
	</section>

	{#if activeError}
		<Alert tone="danger" class="mb-4" title="버킷 조회 실패">{activeError}</Alert>
	{/if}


	{#if loading}
		<BucketCardSkeleton />
	{:else if containers.length === 0 && !activeError}
		<EmptyState headline="버킷이 없습니다" description="오브젝트를 저장할 첫 버킷을 생성하세요." />
	{:else}
		{#if containers.length > 0}
			<div class="mb-3">
				<SelectionToolbar
					label="버킷"
					ariaLabel="버킷 전체 선택"
					checked={selectionDomain === 'active' && selection.count === containers.length}
					indeterminate={selectionDomain === 'active' && selection.count > 0 && selection.count < containers.length}
					selectedCount={selectionDomain === 'active' ? selection.count : 0}
					disabled={busy}
					onToggle={() => { setSelectionDomain('active'); selection.toggleAll(containers.map((c) => c.name)); }}
				/>
			</div>
			<BucketCardGrid
				{containers}
				{deleting}
				{refreshing}
				selectedIds={selectionDomain === 'active' ? selection.ids : new Set()}
				selectionDisabled={busy}
				onToggleSelect={(id) => { setSelectionDomain('active'); selection.toggle(id); }}
				onDelete={deleteContainer}
			/>
		{/if}
	{/if}

		{#if trashLoading}
			<Alert tone="neutral" class="mt-8">휴지통 버킷을 불러오는 중...</Alert>
		{:else if trashError}
			<Alert tone="danger" class="mt-8" title="휴지통 버킷 조회 실패">{trashError}</Alert>
		{/if}

		{#if deletedContainers.length > 0}
			<div class="mt-8">
				<h2 class="text-sm font-medium text-ink-2 mb-3 flex items-center gap-2">
					<span class="text-red-400">🗑</span> 삭제 대기 중 — 복구 가능
				</h2>
				<SelectionToolbar
					label="휴지통 버킷"
					ariaLabel="휴지통 버킷 전체 선택"
					checked={selectionDomain === 'trash' && selection.count === deletedContainers.length}
					indeterminate={selectionDomain === 'trash' && selection.count > 0 && selection.count < deletedContainers.length}
					selectedCount={selectionDomain === 'trash' ? selection.count : 0}
					disabled={busy}
					onToggle={() => { setSelectionDomain('trash'); selection.toggleAll(deletedContainers.map((c) => c.name)); }}
				/>
				<div class="space-y-2 mt-3">
					{#each deletedContainers as c (c.name)}
						{@const deletedAt = (c as SwiftContainer & { deleted_at?: number }).deleted_at}
						<div class="resource-selection-surface flex items-center justify-between px-4 py-3 rounded-lg border border-red-900/40 bg-red-950/10" data-selected={selectionDomain === 'trash' && selection.has(c.name)}>
							<div class="flex items-center gap-3">
								<SelectionCheckbox
									checked={selectionDomain === 'trash' && selection.has(c.name)}
									disabled={busy}
									ariaLabel={`${c.name} 선택`}
									onclick={() => { setSelectionDomain('trash'); selection.toggle(c.name); }}
								/>
								<div>
									<span class="text-sm font-medium text-red-300">{c.name}</span>
									{#if deletedAt}
										<span class="ml-2 text-xs text-ink-3">
											{new Date(deletedAt * 1000).toLocaleDateString('ko-KR')} 삭제
										</span>
									{/if}
								</div>
							</div>
							<div class="flex gap-2">
								<button onclick={() => restoreContainer(c.name)} disabled={restoring === c.name || busy} class="text-xs text-emerald-400 hover:text-emerald-300 disabled:text-ink-3 px-2 py-1 rounded border border-emerald-900 hover:border-emerald-700 disabled:border-line-2 transition-colors">{restoring === c.name ? '복구 중...' : '복구'}</button>
								<button onclick={() => purgeContainer(c.name)} disabled={deleting === c.name || busy} class="text-xs text-red-400 hover:text-red-300 disabled:text-ink-3 px-2 py-1 rounded border border-red-900 hover:border-red-700 disabled:border-line-2 transition-colors">{deleting === c.name ? '삭제 중...' : '영구 삭제'}</button>
							</div>
						</div>
					{/each}
				</div>
				<p class="mt-2 text-xs text-ink-3">삭제된 버킷은 보관 기간이 지나면 자동으로 영구 삭제됩니다. 보관 기간 동안 스토리지 용량을 차지합니다.</p>
			</div>
		{/if}

	<BulkSelectionOverlay
		count={selection.count}
		ariaLabel={selectionDomain === 'active' ? '선택한 버킷 일괄 작업' : '선택한 휴지통 버킷 일괄 작업'}
		busy={busy}
		actions={selectionDomain === 'active'
			? [{ key: 'delete', label: '휴지통으로 이동', tone: 'danger', onAction: () => runBulk('delete') }]
			: [
				{ key: 'restore', label: '복구', tone: 'success', onAction: () => runBulk('restore') },
				{ key: 'purge', label: '영구 삭제', tone: 'danger', onAction: () => runBulk('purge') },
			]}
		onClear={() => selection.clear()}
	/>
</PageShell>
