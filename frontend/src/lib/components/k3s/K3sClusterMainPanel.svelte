<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { api } from '$lib/api/client';
	import K3sClusterHeader from './K3sClusterHeader.svelte';
	import K3sDeleteProgress from './K3sDeleteProgress.svelte';
	import K3sClusterInfoCard from './K3sClusterInfoCard.svelte';
	import K3sClusterNodesCard from './K3sClusterNodesCard.svelte';
	import K3sClusterVmList from './K3sClusterVmList.svelte';
	import K3sNodegroupsSection from './K3sNodegroupsSection.svelte';
	import K3sClusterNetworksCard from './K3sClusterNetworksCard.svelte';
	import { useK3sClusterDetailController } from '$lib/stores/k3sClusterDetailController.svelte';

	const s = useK3sClusterDetailController();

	const isStampede = $derived(s.cluster?.stampede_enabled === true);
	const canEnableStampede = $derived(!isStampede && s.cluster?.status === 'ACTIVE');

	let disabling = $state(false);
	let enabling = $state(false);

	async function disableStampede() {
		if (!s.cluster?.id || disabling) return;
		disabling = true;
		const token = $auth.token ?? undefined;
		const projectId = $auth.projectId ?? undefined;
		try {
			await api.post(`/api/v1/k3s/clusters/${s.cluster.id}/stampede/disable`, {}, token, projectId);
		} catch {
			// best-effort
		} finally {
			disabling = false;
		}
	}

	async function enableStampede() {
		if (!s.cluster?.id || enabling) return;
		enabling = true;
		const token = $auth.token ?? undefined;
		const projectId = $auth.projectId ?? undefined;
		try {
			await api.post(`/api/v1/k3s/clusters/${s.cluster.id}/stampede/enable`, {}, token, projectId);
		} catch {
			// best-effort
		} finally {
			enabling = false;
		}
	}
</script>

<K3sClusterHeader />
{#if s.deleteProgress}<K3sDeleteProgress />{/if}

{#if isStampede}
	<div class="mb-3 flex items-center justify-between bg-surface-selected/20 border border-action-warm/40 rounded-lg px-3 py-2.5">
		<div class="flex items-center gap-2">
			<span class="text-action-warm text-sm font-medium">⚡ Stampede 모드</span>
			<span class="text-xs text-action-warm/70">노드그룹의 Stampede 설정에 따라 자동 스케일링이 동작합니다</span>
		</div>
		<button
			onclick={disableStampede}
			disabled={disabling}
			class="text-xs text-action-warm/70 hover:text-red-400 disabled:opacity-50 transition-colors px-2 py-1 rounded"
		>{disabling ? '...' : '비활성화'}</button>
	</div>
{:else if canEnableStampede}
	<div class="mb-3 flex items-center justify-between bg-surface-sunken/50 border border-line-2 rounded-lg px-3 py-2.5">
		<div class="flex items-center gap-2">
			<span class="text-ink-2 text-sm">Stampede 오토스케일</span>
			<span class="text-xs text-ink-3">노드그룹별 min/max 설정 후 활성화하세요</span>
		</div>
		<button
			onclick={enableStampede}
			disabled={enabling}
			class="text-xs text-ink-2 hover:text-action-warm-hover disabled:opacity-50 transition-colors px-2 py-1 rounded border border-line-2 hover:border-action-warm"
		>{enabling ? '...' : '활성화'}</button>
	</div>
{/if}

<div class="grid grid-cols-1 @3xl/panel:grid-cols-2 gap-3 mb-4">
	<K3sClusterInfoCard />
	<K3sClusterNodesCard />
</div>
<K3sClusterVmList />
<K3sNodegroupsSection />
<K3sClusterNetworksCard />
