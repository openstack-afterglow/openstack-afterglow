<script lang="ts">
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { onMount } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import DbCreatePanel from '$lib/components/database/DbCreatePanel.svelte';
	import GrafanaEmbed from '$lib/components/monitoring/GrafanaEmbed.svelte';
	import type { DbInstance } from '$lib/types/database';
	import { toast } from '$lib/stores/toast';

	let instances = $state<DbInstance[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let deleting = $state<string | null>(null);
	let restarting = $state<string | null>(null);

	let showCreatePanel = $state(false);

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);


	async function load() {
		if (instances.length === 0) loading = true;
		else refreshing = true;
		try {
			instances = await api.get<DbInstance[]>('/api/v1/database-instances?all_projects=true', token, projectId);
		} catch {
			instances = [];
		} finally {
			loading = false;
			refreshing = false;
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

	const ar = createAutoRefresh(load, {
		storageKey: 'admin-database-instances',
		invokeOnMount: false,
		defaultActive: true,
		defaultInterval: 15,
		intervalOptions: [10, 15, 30, 60]
	});

	onMount(load);
</script>

<DbCreatePanel bind:open={showCreatePanel} onCreated={load} />

<div class="p-4 md:p-8 max-w-7xl mx-auto">
	<PageHeader breadcrumb="STORAGE / DATABASE INSTANCES" title="DB 인스턴스">
		{#snippet actions()}
			<button onclick={() => (showCreatePanel = true)}
				class="text-xs text-action-on-warm bg-action-warm hover:bg-action-warm-hover transition-colors px-3 py-1.5 rounded border border-action-warm">+ 인스턴스 생성</button>
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={loading || refreshing}
				onManualRefresh={load}
			/>
		{/snippet}
	</PageHeader>

	{#if loading}
		<LoadingSkeleton variant="table" rows={5} />
	{:else if instances.length === 0}
		<div class="text-ink-3 text-sm">DB 인스턴스가 없습니다</div>
	{:else}
		<div class="overflow-x-auto">
			<table class="w-full text-sm">
				<thead>
					<tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
						<th class="text-left py-3 px-4 font-medium">이름</th>
						<th class="text-left py-3 px-4 font-medium">상태</th>
						<th class="text-left py-3 px-4 font-medium">Datastore</th>
						<th class="text-left py-3 px-4 font-medium">크기 (GB)</th>
						<th class="text-left py-3 px-4 font-medium">ID</th>
						<th class="text-left py-3 px-4 font-medium">생성일</th>
						<th class="text-right py-3 px-4 font-medium">액션</th>
					</tr>
				</thead>
				<tbody>
					{#each instances as inst}
						<tr class="border-b border-line/50 hover:bg-surface-sunken/30 transition-colors">
							<td class="py-3 px-4">
								<a href="/admin/database-instances/{inst.id}" class="text-action-warm hover:text-action-warm-hover font-medium max-md:block max-md:max-w-[66vw] max-md:truncate" title={inst.name}>{inst.name}</a>
							</td>
							<td class="py-3 px-4"><StatusChip status={inst.status} /></td>
							<td class="py-3 px-4 text-ink-2">{inst.datastore?.type ?? '-'} {inst.datastore?.version ?? ''}</td>
							<td class="py-3 px-4 text-ink-2">{inst.size || '-'}</td>
							<td class="py-3 px-4 text-ink-3 font-mono text-xs">{inst.id.slice(0, 8)}…</td>
							<td class="py-3 px-4 text-ink-3 text-xs">{inst.created_at ? inst.created_at.slice(0, 10) : '-'}</td>
							<td class="py-3 px-4 text-right">
								<div class="flex justify-end gap-1">
									<button onclick={() => restartInstance(inst.id, inst.name)} disabled={restarting === inst.id}
										class="text-action-warm hover:text-action-warm-hover disabled:text-ink-3 text-xs px-2 py-1 rounded border border-action-warm hover:border-action-warm disabled:border-line-2 transition-colors">
										{restarting === inst.id ? '...' : '재시작'}
									</button>
									<button onclick={(e) => { e.stopPropagation(); deleteInstance(inst.id, inst.name); }} disabled={deleting === inst.id}
										class="text-red-400 hover:text-red-300 disabled:text-ink-3 text-xs px-2 py-1 rounded border border-red-900 hover:border-red-700 disabled:border-line-2 transition-colors">
										{deleting === inst.id ? '...' : '삭제'}
									</button>
								</div>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}

	{#if !loading}
	<div class="mt-8">
		<h2 class="text-xs font-semibold text-ink-3 uppercase tracking-wide mb-3">MySQL 메트릭 (mysqld_exporter)</h2>
		<GrafanaEmbed dashboardKey="mysqld" height={400} />
	</div>
	{/if}
</div>
