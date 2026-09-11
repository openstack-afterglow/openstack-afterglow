<script lang="ts">
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { onDestroy, onMount } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import SlidePanel from '$lib/components/SlidePanel.svelte';
	import { projectNames } from '$lib/stores/projectNames';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import { createIntentPrefetchScheduler } from '$lib/utils/intentPrefetch';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import AdminImagesFilters from '$lib/components/admin/images/AdminImagesFilters.svelte';
	import AdminImagesTable from '$lib/components/admin/images/AdminImagesTable.svelte';
	import ImageEditModal from '$lib/components/admin/images/ImageEditModal.svelte';
	import type { AdminImage, PagedResponse } from '$lib/types/adminImage';
	import { toast } from '$lib/stores/toast';

	let images = $state<AdminImage[]>([]);
	let loading = $state(true), refreshing = $state(false), error = $state('');
	let searchInput = $state(''), searchFilter = $state(''), visibilityFilter = $state('');
	let pageSize = $state(20), markerStack = $state<string[]>([]), nextMarker = $state<string | null>(null);
	let selectedImageId = $state<string | null>(null);
	let editTarget = $state<AdminImage | null>(null), editForm = $state({ name: '', os_distro: '', visibility: 'private' });
	let editing = $state(false), editError = $state(''), togglingId = $state<string | null>(null);
	let loadGeneration = 0;

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);
	const curMarker = $derived(markerStack[markerStack.length - 1]);
	const nextPrefetch = createIntentPrefetchScheduler();
	function listPath(marker?: string): string {
		const params = new URLSearchParams({ limit: String(pageSize) });
		if (marker) params.set('marker', marker);
		if (searchFilter) params.set('search', searchFilter);
		if (visibilityFilter) params.set('visibility', visibilityFilter);
		return `/api/v1/admin/images?${params}`;
	}
	function prefetchNext() {
		if (!nextMarker) return;
		const path = listPath(nextMarker);
		const key = JSON.stringify([path, token ?? null, projectId ?? null]);
		nextPrefetch.intent(key, (signal) => api.prefetch(path, token, projectId, { signal }));
	}

	async function load(marker?: string, forceRefresh = false) {
		const generation = ++loadGeneration;
		const requestToken = $auth.token ?? undefined;
		const requestProjectId = $auth.projectId ?? undefined;
		const requestPageSize = pageSize;
		const requestSearchFilter = searchFilter;
		const requestVisibilityFilter = visibilityFilter;
		const requestPath = listPath(marker);
		const owns = () => generation === loadGeneration
			&& ($auth.token ?? undefined) === requestToken
			&& ($auth.projectId ?? undefined) === requestProjectId
			&& pageSize === requestPageSize
			&& searchFilter === requestSearchFilter
			&& visibilityFilter === requestVisibilityFilter
			&& listPath(marker) === requestPath;
		nextPrefetch.cancel();
		if (images.length === 0) loading = true; else refreshing = true;
		error = '';
		try {
			const res = await api.get<PagedResponse<AdminImage>>(
				requestPath,
				requestToken,
				requestProjectId,
				{ refresh: forceRefresh },
			);
			if (!owns()) return;
			images = res.items || [];
			nextMarker = res.next_marker;
			const path = nextMarker ? listPath(nextMarker) : null;
			const key = path ? JSON.stringify([path, requestToken ?? null, requestProjectId ?? null]) : null;
			nextPrefetch.schedule(key, (signal) => path ? api.prefetch(path, requestToken, requestProjectId, { signal }) : undefined);
		} catch (e) {
			if (!owns()) return;
			error = e instanceof ApiError ? e.message : '이미지 목록 조회 실패';
			images = [];
		} finally {
			if (owns()) {
				loading = false;
				refreshing = false;
			}
		}
	}

	function openEdit(img: AdminImage) {
		editTarget = img;
		editForm = { name: img.name, os_distro: img.os_distro || '', visibility: img.visibility };
		editError = '';
	}

	async function saveEdit() {
		if (!editTarget) return;
		editing = true; editError = '';
		try {
			await api.patch(`/api/v1/admin/images/${editTarget.id}`, {
				name: editForm.name || undefined, os_distro: editForm.os_distro || undefined, visibility: editForm.visibility || undefined,
			}, token, projectId);
			editTarget = null; await load(curMarker);
		} catch (e) { editError = e instanceof ApiError ? e.message : '수정 실패'; }
		finally { editing = false; }
	}

	async function deleteImage(img: AdminImage) {
		if (!await confirmDialog(`이미지 "${img.name}"을 삭제하시겠습니까?\n이 작업은 되돌릴 수 없습니다.`)) return;
		try { await api.delete(`/api/v1/admin/images/${img.id}`, token, projectId); await load(curMarker); }
		catch (e) { toast.error('삭제 실패: ' + (e instanceof ApiError ? e.message : String(e))); }
	}

	async function toggleActivation(img: AdminImage) {
		togglingId = img.id;
		try {
			await api.post(`/api/v1/admin/images/${img.id}/${img.status === 'active' ? 'deactivate' : 'reactivate'}`, {}, token, projectId);
			await load(curMarker);
		} catch (e) { toast.error('상태 변경 실패: ' + (e instanceof ApiError ? e.message : String(e))); }
		finally { togglingId = null; }
	}

	const ar = createAutoRefresh(() => { load(curMarker); },
		{ storageKey: 'admin-images', defaultInterval: 30, intervalOptions: [15, 30, 60], invokeOnMount: false });
	async function forceRefresh() { markerStack = []; nextMarker = null; await load(undefined, true); }

	onMount(() => {
		if (window.matchMedia('(max-width: 767px)').matches) pageSize = 10;
		load();
		projectNames.load(token, projectId);
	});

	onDestroy(() => { loadGeneration += 1; nextPrefetch.cancel(); });
</script>

<div class="p-4 md:p-6 max-w-7xl mx-auto">
	<PageHeader breadcrumb="COMPUTE / IMAGES" title="이미지">
		{#snippet actions()}
			<AutoRefreshControl bind:active={ar.active} bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions} refreshing={refreshing} onManualRefresh={forceRefresh} />
			<div class="flex items-center gap-1 text-xs text-ink-3 max-md:hidden">
				표시:
				{#each [10, 20, 30] as n}
					<button onclick={() => { pageSize = n; markerStack = []; nextMarker = null; load(); }}
						class="px-2 py-0.5 rounded {pageSize === n ? 'bg-action-warm text-ink-0' : 'bg-surface-sunken hover:bg-surface-selected text-ink-2'}"
					>{n}</button>
				{/each}
			</div>
		{/snippet}
	</PageHeader>

	<AdminImagesFilters bind:searchInput bind:visibilityFilter
		onSearchChange={(v) => { searchFilter = v; markerStack = []; nextMarker = null; load(); }}
		onVisibilityChange={() => { markerStack = []; nextMarker = null; load(); }}
	/>

	{#if error}
		<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>
	{/if}

	{#if loading}
		<LoadingSkeleton variant="table" rows={8} />
	{:else if images.length === 0}
		<div class="text-ink-3 text-sm">이미지가 없습니다</div>
	{:else}
		<AdminImagesTable {images} {selectedImageId} {togglingId} {markerStack} {nextMarker}
			onOpenDetail={(img) => { selectedImageId = img.id; }}
			onEdit={openEdit} onToggleActivation={toggleActivation} onDelete={deleteImage}
			onPrev={() => { const prev = markerStack.slice(0,-1); markerStack = prev; load(prev[prev.length-1]); }}
			onNext={() => { if (!nextMarker) return; markerStack = [...markerStack, nextMarker]; load(nextMarker); }}
			onintent={prefetchNext}
		/>
	{/if}
</div>

{#if selectedImageId}
	<SlidePanel onClose={() => { selectedImageId = null; }} ariaLabel="관리자 이미지 상세" width="w-full md:w-[50vw] max-w-2xl">
		{#await import('$lib/components/ImageDetailPanel.svelte') then { default: Panel }}
			<Panel imageId={selectedImageId} onClose={() => { selectedImageId = null; }} isAdmin={true} />
		{/await}
	</SlidePanel>
{/if}

<ImageEditModal bind:target={editTarget} bind:form={editForm} {editing} {editError} onSave={saveEdit} />
