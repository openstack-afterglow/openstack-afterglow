<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { useK3sClusterDetailController } from '$lib/stores/k3sClusterDetailController.svelte';
	import K3sNodegroupCard from '$lib/components/dashboard/drover/K3sNodegroupCard.svelte';
	import K3sNodegroupCreateModal from '$lib/components/dashboard/drover/K3sNodegroupCreateModal.svelte';
	import K3sNodegroupEditModal from '$lib/components/dashboard/drover/K3sNodegroupEditModal.svelte';
	import type { K3sNodegroup } from '$lib/types/k3s';

	const s = useK3sClusterDetailController();

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);
	const clusterId = $derived(s.cluster?.id ?? '');

	let nodegroups = $state<K3sNodegroup[]>([]);
	let loading = $state(false);
	let showCreate = $state(false);
	let editTarget = $state<K3sNodegroup | null>(null);
	let deleteTarget = $state<K3sNodegroup | null>(null);
	let deleteError = $state('');
	let deleting = $state(false);

	async function load() {
		if (!clusterId) return;
		loading = true;
		try {
			nodegroups = await api.get<K3sNodegroup[]>(
				`/api/v1/k3s/clusters/${clusterId}/nodegroups`,
				token,
				projectId,
			);
		} catch {
			nodegroups = [];
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		if (clusterId) void load();
	});

	async function confirmDelete() {
		if (!deleteTarget) return;
		deleting = true;
		deleteError = '';
		try {
			await api.delete(`/api/v1/k3s/clusters/${clusterId}/nodegroups/${deleteTarget.id}`, token, projectId);
			deleteTarget = null;
			await load();
		} catch (e) {
			deleteError = e instanceof ApiError ? e.message : '삭제 실패';
		} finally {
			deleting = false;
		}
	}
</script>

<div class="bg-surface-base border border-line rounded-xl p-4">
	<div class="flex items-center justify-between mb-3">
		<h3 class="text-xs text-ink-3 uppercase tracking-wide">노드그룹</h3>
		<button
			onclick={() => { showCreate = true; }}
			class="text-xs text-action-warm hover:text-action-warm-hover transition-colors"
		>+ 추가</button>
	</div>

	{#if loading}
		<div class="text-xs text-ink-3 py-2">불러오는 중...</div>
	{:else if nodegroups.length === 0}
		<div class="text-xs text-ink-3 py-2">노드그룹 정보가 없습니다.</div>
	{:else}
		<div class="space-y-2">
			{#each nodegroups as ng (ng.id)}
				<K3sNodegroupCard
					nodegroup={ng}
					onEdit={(n) => { editTarget = n; }}
					onDelete={(n) => { deleteTarget = n; deleteError = ''; }}
				/>
			{/each}
		</div>
	{/if}
</div>

{#if editTarget}
	<K3sNodegroupEditModal
		clusterId={clusterId}
		nodegroup={editTarget}
		{token}
		{projectId}
		onClose={() => { editTarget = null; }}
		onSaved={() => { editTarget = null; void load(); }}
	/>
{/if}

{#if showCreate}
	<K3sNodegroupCreateModal
		{clusterId}
		{token}
		{projectId}
		onClose={() => { showCreate = false; }}
		onSaved={() => { showCreate = false; void load(); }}
	/>
{/if}

{#if deleteTarget}
	<div
		class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
		onclick={(event) => { if (event.target === event.currentTarget) (() => (deleteTarget = null))(); }}
		onkeydown={(e) => e.key === 'Escape' && (deleteTarget = null)}
		role="dialog"
		tabindex="-1"
	>
		<div
			class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-sm mx-4 shadow-[var(--shadow-restraint)]"
		>
			<h2 class="text-lg font-semibold text-ink-0 mb-3">노드그룹 삭제</h2>
			<p class="text-sm text-ink-2 mb-5">
				<strong class="text-ink-0">{deleteTarget.name}</strong> 노드그룹을 삭제합니다.
			</p>
			{#if deleteError}
				<div class="mb-3 text-red-400 text-xs bg-red-900/20 border border-red-800 rounded px-3 py-2">{deleteError}</div>
			{/if}
			<div class="flex justify-end gap-3">
				<button onclick={() => (deleteTarget = null)} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0">취소</button>
				<button
					onclick={confirmDelete}
					disabled={deleting}
					class="px-4 py-2 bg-red-700 hover:bg-red-600 disabled:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg"
				>{deleting ? '삭제 중...' : '삭제'}</button>
			</div>
		</div>
	</div>
{/if}
