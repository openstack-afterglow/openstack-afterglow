<script lang="ts">
	import { onMount } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import type { FloatingIpInfo, NetworkInfo } from '$lib/types/networks';
	import Modal from '$lib/components/ui/Modal.svelte';

	let fips = $state<FloatingIpInfo[]>([]);
	let loading = $state(true);

	// 생성 모달
	let showCreate = $state(false);
	let creating = $state(false);
	let createError = $state('');
	let externalNets = $state<NetworkInfo[]>([]);
	let selectedNetId = $state('');

	// 삭제 확인
	let deleteFip = $state<FloatingIpInfo | null>(null);
	let deleting = $state(false);
	let deleteError = $state('');

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	async function load() {
		loading = true;
		try {
			fips = await api.get<FloatingIpInfo[]>('/api/v1/admin/all-floating-ips', token, projectId);
		} catch {
			fips = [];
		} finally {
			loading = false;
		}
	}

	function prefetchExternalNetworks() {
		void api.prefetch('/api/v1/admin/all-networks', token, projectId);
	}

	async function openCreate() {
		showCreate = true; createError = '';
		try {
			const nets = await api.get<NetworkInfo[]>('/api/v1/admin/all-networks', token, projectId);
			externalNets = nets.filter(n => n.is_external);
			selectedNetId = externalNets.length > 0 ? externalNets[0].id : '';
		} catch {
			externalNets = [];
		}
	}

	async function createFip() {
		if (!selectedNetId) return;
		creating = true; createError = '';
		try {
			await api.post('/api/v1/admin/floating-ips', { floating_network_id: selectedNetId }, token, projectId);
			showCreate = false; await load();
		} catch (e) { createError = e instanceof ApiError ? e.message : '생성 실패'; } finally { creating = false; }
	}

	async function confirmDelete() {
		if (!deleteFip) return;
		deleting = true; deleteError = '';
		try {
			await api.delete(`/api/v1/admin/floating-ips/${deleteFip.id}`, token, projectId);
			deleteFip = null; await load();
		} catch (e) { deleteError = e instanceof ApiError ? e.message : '삭제 실패'; } finally { deleting = false; }
	}

	const ar = createAutoRefresh(load, {
		storageKey: 'admin-floating-ips',
		invokeOnMount: false,
		defaultActive: true,
		defaultInterval: 30,
		intervalOptions: [15, 30, 60]
	});

	onMount(load);
</script>

<div class="p-4 md:p-6 max-w-7xl mx-auto">
	<PageHeader breadcrumb="NETWORK / FLOATING IPs" title="Floating IP">
		{#snippet actions()}
			<button onclick={openCreate} onpointerenter={prefetchExternalNetworks} onfocus={prefetchExternalNetworks} class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-ink-0 text-sm font-medium rounded-lg">+ 생성</button>
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={loading}
				onManualRefresh={load}
			/>
		{/snippet}
	</PageHeader>

	{#if loading}
		<div class="text-ink-3 text-sm">로딩 중...</div>
	{:else}
		<div class="overflow-x-auto">
			<table class="w-full text-sm">
				<thead>
					<tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
						<th class="text-left py-2 pr-4">Floating IP</th>
						<th class="text-left py-2 pr-4">Fixed IP</th>
						<th class="text-left py-2 pr-4">상태</th>
						<th class="text-left py-2 pr-4">프로젝트</th>
						<th class="text-left py-2">액션</th>
					</tr>
				</thead>
				<tbody>
					{#each fips as f (f.id)}
						<tr class="border-b border-line/50 text-xs hover:bg-surface-sunken/30 transition-colors">
							<td class="py-2 pr-4 font-mono text-green-400">{f.floating_ip_address}</td>
							<td class="py-2 pr-4 font-mono text-ink-2">{f.fixed_ip_address ?? '-'}</td>
							<td class="py-2 pr-4 {f.port_id ? 'text-green-400' : 'text-ink-3'}">
								{f.port_id ? '할당됨' : '미할당'}
							</td>
							<td class="py-2 pr-4 text-ink-3 font-mono">{f.project_id?.slice(0, 8) ?? '-'}</td>
							<td class="py-2">
								{#if !f.port_id}
									<button onclick={() => { deleteFip = f; deleteError = ''; }}
										class="px-2 py-0.5 text-xs bg-red-900/30 hover:bg-red-900/50 text-red-400 rounded">삭제</button>
								{/if}
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
		<div class="mt-3 flex gap-4 text-xs text-ink-3">
			<span>총 {fips.length}개</span>
			<span class="text-green-400">할당됨: {fips.filter(f => f.port_id).length}개</span>
			<span>미할당: {fips.filter(f => !f.port_id).length}개</span>
		</div>
	{/if}
</div>

<!-- 생성 모달 -->
<Modal bind:open={showCreate} ariaLabel="Floating IP 생성">
	<div class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]">
		<h2 class="text-lg font-semibold text-ink-0 mb-5">Floating IP 생성</h2>
		{#if createError}<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{createError}</div>{/if}
		<div>
			<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-page-146">외부 네트워크</label>
			{#if externalNets.length === 0}
				<div class="text-xs text-red-400">외부 네트워크가 없습니다</div>
			{:else}
				<select id="field-page-146" bind:value={selectedNetId} class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none">
					{#each externalNets as n}
						<option value={n.id}>{n.name || n.id.slice(0, 8)}</option>
					{/each}
				</select>
			{/if}
		</div>
		<div class="flex justify-end gap-3 mt-6">
			<button onclick={() => { showCreate = false; }} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">취소</button>
			<button onclick={createFip} disabled={creating || !selectedNetId} class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-ink-0 text-sm font-medium rounded-lg disabled:opacity-30">{creating ? '생성 중...' : '생성'}</button>
		</div>
	</div>
</Modal>

<!-- 삭제 확인 모달 -->
{#if deleteFip}
	<Modal open={true} onClose={() => { deleteFip = null; }} ariaLabel="Floating IP 삭제">
		<div class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-sm mx-4 shadow-[var(--shadow-restraint)]">
			<h2 class="text-lg font-semibold text-ink-0 mb-3">Floating IP 삭제</h2>
			<p class="text-sm text-ink-2 mb-4"><span class="text-ink-0 font-mono">{deleteFip.floating_ip_address}</span>을 삭제하시겠습니까?</p>
			{#if deleteError}<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{deleteError}</div>{/if}
			<div class="flex justify-end gap-3">
				<button onclick={() => { deleteFip = null; }} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">취소</button>
				<button onclick={confirmDelete} disabled={deleting} class="px-4 py-2 bg-red-600 hover:bg-red-500 text-ink-0 text-sm font-medium rounded-lg disabled:opacity-30">{deleting ? '삭제 중...' : '삭제'}</button>
			</div>
		</div>
	</Modal>
{/if}
