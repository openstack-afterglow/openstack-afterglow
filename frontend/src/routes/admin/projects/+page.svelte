<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api } from '$lib/api/client';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import { createIntentPrefetchScheduler } from '$lib/utils/intentPrefetch';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import AdminProjectTable from '$lib/components/admin/projects/AdminProjectTable.svelte';
	import Pagination from '$lib/components/ui/Pagination.svelte';
	import AdminProjectCreateModal from '$lib/components/admin/projects/AdminProjectCreateModal.svelte';
	import AdminProjectEditModal from '$lib/components/admin/projects/AdminProjectEditModal.svelte';
	import AdminProjectDeleteModal from '$lib/components/admin/projects/AdminProjectDeleteModal.svelte';
	import AdminProjectAccessModal from '$lib/components/admin/projects/AdminProjectAccessModal.svelte';

	import type { Project } from '$lib/types/project';
	import type { PagedResponse } from '$lib/types/common';

	let projects = $state<Project[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let pageSize = $state(20);
	let markerStack = $state<string[]>([]);
	let nextMarker = $state<string | null>(null);

	let showCreate = $state(false);
	let editProject = $state<Project | null>(null);
	let deleteProject = $state<Project | null>(null);
	let accessProject = $state<Project | null>(null);

	let copiedId = $state<string | null>(null);
	let loadGeneration = 0;

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);
	const nextPrefetch = createIntentPrefetchScheduler();
	function listPath(marker?: string): string {
		const params = new URLSearchParams({ limit: String(pageSize) });
		if (marker) params.set('marker', marker);
		return `/api/v1/admin/projects?${params}`;
	}
	function prefetchNext() {
		if (!nextMarker) return;
		const path = listPath(nextMarker);
		const key = JSON.stringify([path, token ?? null, projectId ?? null]);
		nextPrefetch.intent(key, (signal) => api.prefetch(path, token, projectId, { signal }));
	}

	function copyId(id: string) {
		navigator.clipboard.writeText(id).then(() => {
			copiedId = id;
			setTimeout(() => { copiedId = null; }, 1500);
		});
	}

	async function load(marker?: string) {
		const generation = ++loadGeneration;
		const requestToken = $auth.token ?? undefined;
		const requestProjectId = $auth.projectId ?? undefined;
		const requestPageSize = pageSize;
		const requestPath = listPath(marker);
		const owns = () => generation === loadGeneration
			&& ($auth.token ?? undefined) === requestToken
			&& ($auth.projectId ?? undefined) === requestProjectId
			&& pageSize === requestPageSize
			&& listPath(marker) === requestPath;
		nextPrefetch.cancel();
		if (projects.length === 0) loading = true;
		else refreshing = true;
		try {
			const res = await api.get<PagedResponse<Project>>(requestPath, requestToken, requestProjectId);
			if (!owns()) return;
			projects = res.items;
			nextMarker = res.next_marker;
			const path = nextMarker ? listPath(nextMarker) : null;
			const key = path ? JSON.stringify([path, requestToken ?? null, requestProjectId ?? null]) : null;
			nextPrefetch.schedule(key, (signal) => path ? api.prefetch(path, requestToken, requestProjectId, { signal }) : undefined);
		} catch {
			if (owns()) projects = [];
		} finally {
			if (owns()) {
				loading = false;
				refreshing = false;
			}
		}
	}

	function autoRefreshLoad() { load(markerStack[markerStack.length - 1]); }

	const ar = createAutoRefresh(autoRefreshLoad, {
		storageKey: 'admin-projects',
		invokeOnMount: false,
		defaultActive: true,
		defaultInterval: 60,
		intervalOptions: [30, 60],
	});

	onMount(() => {
		if (window.matchMedia('(max-width: 767px)').matches) pageSize = 10;
		load();
	});

	onDestroy(() => { loadGeneration += 1; nextPrefetch.cancel(); });
</script>

<div class="p-4 md:p-6 max-w-7xl mx-auto">
	<PageHeader breadcrumb="IDENTITY / PROJECTS" title="프로젝트">
		{#snippet actions()}
			<button
				onclick={() => { showCreate = true; }}
				class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-action-on-warm text-sm font-medium rounded-lg"
			>+ 생성</button>
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={loading || refreshing}
				onManualRefresh={() => load()}
			/>
			<div class="flex items-center gap-1 text-xs text-ink-3 max-md:hidden">
				표시:
				{#each [10, 20, 30] as n}
					<button
						onclick={() => { pageSize = n; markerStack = []; nextMarker = null; load(); }}
						class="px-2 py-0.5 rounded {pageSize === n ? 'bg-action-warm text-ink-0' : 'bg-surface-sunken hover:bg-surface-selected text-ink-2'}"
					>{n}</button>
				{/each}
			</div>
		{/snippet}
	</PageHeader>

	{#if loading}
		<LoadingSkeleton variant="table" rows={5} />
	{:else}
		<div class="bg-surface-base border border-line rounded-lg p-5">
			<AdminProjectTable
				{projects}
				{copiedId}
				onCopyId={copyId}
				onEdit={(p) => (editProject = p)}
				onAccess={(p) => (accessProject = p)}
				onDelete={(p) => (deleteProject = p)}
			/>
		</div>
		<Pagination
			page={markerStack.length + 1}
			hasPrev={markerStack.length > 0}
			hasNext={!!nextMarker}
			onPrev={() => { const prev = markerStack.slice(0, -1); markerStack = prev; load(prev[prev.length - 1]); }}
			onNext={() => { if (nextMarker) { markerStack = [...markerStack, nextMarker]; load(nextMarker); } }}
			onintent={prefetchNext}
		/>
	{/if}
</div>

<AdminProjectCreateModal bind:open={showCreate} onCreated={() => load()} />
<AdminProjectEditModal   project={editProject}   onClose={() => (editProject = null)}   onSuccess={() => load()} />
<AdminProjectDeleteModal project={deleteProject} onClose={() => (deleteProject = null)} onSuccess={() => load()} />
<AdminProjectAccessModal project={accessProject} onClose={() => (accessProject = null)} />
