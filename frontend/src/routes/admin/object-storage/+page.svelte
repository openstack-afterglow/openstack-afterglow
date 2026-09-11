<script lang="ts">
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { onMount } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import type { SwiftContainer } from '$lib/types/common';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import { formatStorage } from '$lib/utils/format';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import BucketCreateModal from '$lib/components/object-storage/buckets/BucketCreateModal.svelte';
	import BucketTable from '$lib/components/object-storage/buckets/BucketTable.svelte';
	import QuarantineNotice from '$lib/components/object-storage/buckets/QuarantineNotice.svelte';
	import TrashNotice from '$lib/components/object-storage/buckets/TrashNotice.svelte';
	import { toast } from '$lib/stores/toast';

	interface AccountMeta {
		container_count: number;
		object_count: number;
		bytes_used: number;
	}

	let containers = $state<SwiftContainer[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let deleting = $state<string | null>(null);
	let showModal = $state(false);

	const account = $derived<AccountMeta>({
		container_count: containers.length,
		object_count: containers.reduce((s, c) => s + (c.count || 0), 0),
		bytes_used: containers.reduce((s, c) => s + (c.bytes || 0), 0),
	});

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	async function load() {
		if (containers.length === 0) loading = true;
		else refreshing = true;
		try {
			containers = await api.get<SwiftContainer[]>(
				'/api/v1/object-storage?all_projects=true&include_quarantine=true&include_trash=true&include_deleted=true',
				token, projectId
			);
		} catch {
			containers = [];
		} finally {
			loading = false;
			refreshing = false;
		}
	}

	async function createContainer(name: string): Promise<string | true> {
		try {
			await api.post('/api/v1/object-storage', { name }, token, projectId);
			await load();
			return true;
		} catch (e) {
			return e instanceof ApiError ? e.message : '버킷 생성 실패';
		}
	}

	async function deleteContainer(name: string) {
		if (!await confirmDialog(`버킷 "${name}"을 휴지통으로 이동합니다. 보관 기간 내에 복구할 수 있습니다. 계속하시겠습니까?`)) return;
		deleting = name;
		try {
			await api.delete(`/api/v1/object-storage/${encodeURIComponent(name)}`, token, projectId);
			await load();
		} catch (e) {
			toast.error('삭제 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		} finally {
			deleting = null;
		}
	}

	const ar = createAutoRefresh(load, {
		storageKey: 'admin-object-storage',
		invokeOnMount: false,
		defaultActive: true,
		defaultInterval: 30,
		intervalOptions: [15, 30, 60]
	});

	onMount(load);
</script>

<BucketCreateModal bind:open={showModal} onCreate={createContainer} />

<div class="p-4 md:p-8 max-w-7xl mx-auto">
	<PageHeader breadcrumb="STORAGE / OBJECT STORAGE" title="오브젝트 스토리지">
		{#snippet actions()}
			<button
				onclick={() => { showModal = true; }}
				class="text-xs text-ink-0 bg-indigo-600 hover:bg-indigo-500 transition-colors px-3 py-1.5 rounded border border-indigo-500"
			>+ 버킷 생성</button>
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={loading || refreshing}
				onManualRefresh={load}
			/>
		{/snippet}
	</PageHeader>

	{#if account}
		<div class="grid grid-cols-3 gap-4 mb-6">
			<div class="bg-surface-base border border-line rounded-xl p-4">
				<div class="text-xs text-ink-3 uppercase tracking-wide mb-1">버킷</div>
				<div class="text-2xl font-bold text-ink-0">{account.container_count}</div>
			</div>
			<div class="bg-surface-base border border-line rounded-xl p-4">
				<div class="text-xs text-ink-3 uppercase tracking-wide mb-1">오브젝트</div>
				<div class="text-2xl font-bold text-ink-0">{account.object_count}</div>
			</div>
			<div class="bg-surface-base border border-line rounded-xl p-4">
				<div class="text-xs text-ink-3 uppercase tracking-wide mb-1">사용 용량</div>
				<div class="text-2xl font-bold text-ink-0">{formatStorage(account.bytes_used / 1_000_000_000)}</div>
			</div>
		</div>
	{/if}

	{#if loading}
		<LoadingSkeleton variant="table" rows={5} />
	{:else if containers.length === 0}
		<div class="text-ink-3 text-sm">버킷가 없습니다</div>
	{:else}
		<BucketTable {containers} deletingId={deleting} {refreshing} onDelete={deleteContainer} />
		{#if containers.some((c) => c.is_quarantine)}
			<QuarantineNotice />
		{/if}
		{#if containers.some((c) => c.is_trash || c.is_deleted)}
			<TrashNotice />
		{/if}
	{/if}
</div>
