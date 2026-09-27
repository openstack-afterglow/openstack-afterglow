<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { toast } from '$lib/stores/toast';
	import { projectNames } from '$lib/stores/projectNames';
	import { createImageCatalog, currentImagesByReference } from '$lib/stores/imageCatalog.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import SlidePanel from '$lib/components/SlidePanel.svelte';
	import ImageUploadModal from '$lib/components/ImageUploadModal.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import ImageCatalogToolbar, { type CatalogViewMode } from '$lib/components/dashboard/images/ImageCatalogToolbar.svelte';
	import ImageRepositoryCard from '$lib/components/dashboard/images/ImageRepositoryCard.svelte';
	import ImageDistroFilter from '$lib/components/dashboard/images/ImageDistroFilter.svelte';
	import AdminImagesTable from '$lib/components/admin/images/AdminImagesTable.svelte';
	import ImageEditModal from '$lib/components/admin/images/ImageEditModal.svelte';
	import { Alert, Button, Card, EmptyState, Field, PageHeader, PageShell, Pagination, ResourceToolbar, SelectInput } from '$lib/components/ui';
	import type { AdminImage, PagedResponse } from '$lib/types/adminImage';

	let images = $state<AdminImage[]>([]);
	let loading = $state(true), refreshing = $state(false), error = $state('');
	let visibilityFilter = $state('all');
	let pageSize = $state('12'), page = $state(1);
	let viewMode = $state<CatalogViewMode>('repositories');
	let selectedRepository = $state<string | null>(null);
	let selectedImageId = $state<string | null>(null);
	let showUploadModal = $state(false);
	let editTarget = $state<AdminImage | null>(null);
	let editForm = $state({ name: '', os_distro: '', visibility: 'private' });
	let editing = $state(false), editError = $state('');
	let togglingId = $state<string | null>(null), verifyingId = $state<string | null>(null);
	let loadGeneration = 0;
	let loadedProject: string | undefined;

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);
	const visibleImages = $derived(visibilityFilter === 'all' ? images : images.filter((image) => image.visibility === visibilityFilter));
	const catalog = createImageCatalog(() => visibleImages, () => images);
	const currentImageIds = $derived(new Set([...currentImagesByReference(images).values()].map((image) => image.id)));
	const selectedGroup = $derived(catalog.repositoryGroups.find((group) => group.repository === selectedRepository) ?? null);
	const showingRepositories = $derived(viewMode === 'repositories' && !selectedGroup);
	const tagImages = $derived(selectedGroup?.images ?? catalog.filteredImages);
	const resultCount = $derived(showingRepositories ? catalog.repositoryGroups.length : tagImages.length);
	const totalPages = $derived(Math.max(1, Math.ceil(resultCount / Number(pageSize))));
	const currentPage = $derived(Math.min(page, totalPages));
	const offset = $derived((currentPage - 1) * Number(pageSize));
	const pageGroups = $derived(catalog.repositoryGroups.slice(offset, offset + Number(pageSize)));
	const pageImages = $derived(tagImages.slice(offset, offset + Number(pageSize)));
	const verificationUnavailable = $derived(images.some((image) => image.verification_status === 'unavailable'));

	$effect(() => {
		// Filter/view changes reset UI pagination; background refresh keeps the current page.
		void [catalog.searchQuery, catalog.repositoryFilter, catalog.tagFilter, catalog.distroFilter,
			catalog.verificationFilter, catalog.sortMode, visibilityFilter, viewMode, selectedRepository, pageSize];
		page = 1;
	});
	$effect(() => {
		if (selectedRepository && !selectedGroup) selectedRepository = null;
	});

	async function load(forceRefresh = false) {
		const generation = ++loadGeneration;
		const requestToken = token, requestProjectId = projectId;
		const owns = () => generation === loadGeneration && token === requestToken && projectId === requestProjectId;
		if (images.length === 0) loading = true; else refreshing = true;
		error = '';
		try {
			// Group only a complete catalog: marker boundaries must never split repositories.
			const collected = new Map<string, AdminImage>();
			const markers = new Set<string>();
			let marker: string | null = null;
			do {
				const params = new URLSearchParams({ limit: '100' });
				if (marker) params.set('marker', marker);
				const response: PagedResponse<AdminImage> = await api.get(
					`/api/v1/admin/images?${params}`, requestToken, requestProjectId, { refresh: forceRefresh },
				);
				if (!owns()) return;
				for (const image of response.items) collected.set(image.id, image);
				marker = response.next_marker;
				if (marker && markers.has(marker)) throw new Error('이미지 목록의 다음 페이지를 확인할 수 없습니다. 새로고침해 주세요.');
				if (marker) markers.add(marker);
			} while (marker);
			images = [...collected.values()];
			if (selectedImageId && !collected.has(selectedImageId)) selectedImageId = null;
		} catch (e) {
			if (owns()) error = e instanceof Error ? e.message : '이미지 목록 조회 실패. 새로고침해 주세요.';
		} finally {
			if (owns()) { loading = false; refreshing = false; }
		}
	}

	function clearFilters() {
		catalog.clearFilters();
		visibilityFilter = 'all';
		selectedRepository = null;
	}
	function changeViewMode(mode: CatalogViewMode) {
		viewMode = mode;
		selectedRepository = null;
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
			editTarget = null;
			await load(true);
		} catch (e) { editError = e instanceof ApiError ? e.message : '수정 실패'; }
		finally { editing = false; }
	}
	async function deleteImage(img: AdminImage) {
		if (!await confirmDialog(`이미지 "${img.name}" (${img.id})을 삭제하시겠습니까?\n이 작업은 되돌릴 수 없습니다.`)) return;
		try {
			await api.delete(`/api/v1/admin/images/${img.id}`, token, projectId);
			await load(true);
		} catch (e) { toast.error('삭제 실패: ' + (e instanceof Error ? e.message : String(e))); }
	}
	async function toggleActivation(img: AdminImage) {
		togglingId = img.id;
		try {
			await api.post(`/api/v1/admin/images/${img.id}/${img.status === 'active' ? 'deactivate' : 'reactivate'}`, {}, token, projectId);
			await load(true);
		} catch (e) { toast.error('상태 변경 실패: ' + (e instanceof Error ? e.message : String(e))); }
		finally { togglingId = null; }
	}
	async function toggleVerification(img: AdminImage) {
		const verified = img.verification_status !== 'verified';
		verifyingId = img.id;
		try {
			await api.put(`/api/v1/admin/images/${img.id}/verification`, { verified }, token, projectId);
			toast.success(verified ? '관리자 검증을 승인했습니다.' : '관리자 검증을 해제했습니다.');
			await load(true);
		} catch (e) { toast.error('검증 상태 변경 실패: ' + (e instanceof Error ? e.message : String(e))); }
		finally { verifyingId = null; }
	}

	const ar = createAutoRefresh(() => load(), {
		storageKey: 'admin-images', defaultInterval: 30, intervalOptions: [15, 30, 60], invokeOnMount: false,
	});
	$effect(() => {
		const currentToken = token, currentProject = projectId;
		untrack(() => {
			loadGeneration += 1;
			if (!currentToken || currentProject !== loadedProject) {
				images = [];
				selectedImageId = null;
				selectedRepository = null;
			}
			loadedProject = currentProject;
			if (!currentToken) { loading = false; return; }
			void load();
			void projectNames.load(currentToken, currentProject);
		});
	});
	onDestroy(() => { loadGeneration += 1; });
</script>

<PageShell max="7xl" class="space-y-4">
	<PageHeader breadcrumb="COMPUTE / IMAGES" title="이미지">
		{#snippet actions()}<Button variant="primary" onclick={() => showUploadModal = true}>이미지 업로드</Button>{/snippet}
	</PageHeader>
	<ResourceToolbar label="관리자 이미지 목록 도구">
		{#snippet filters()}
			<Field label="공개 범위" for="admin-image-visibility">
				<SelectInput id="admin-image-visibility" bind:value={visibilityFilter}>
					<option value="all">모든 공개 범위</option><option value="public">Public</option>
					<option value="community">Community</option><option value="shared">Shared</option><option value="private">Private</option>
				</SelectInput>
			</Field>
			<Field label="페이지당 표시" for="admin-image-page-size">
				<SelectInput id="admin-image-page-size" bind:value={pageSize}>
					{#each [12, 24, 48] as size}<option value={String(size)}>{size}개</option>{/each}
				</SelectInput>
			</Field>
		{/snippet}
		{#snippet actions()}
			<AutoRefreshControl bind:active={ar.active} bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions} {refreshing} onManualRefresh={() => load(true)} />
		{/snippet}
	</ResourceToolbar>
	{#if error}
		<Alert tone="danger" title="이미지 목록 조회 실패">{error}
			{#snippet actions()}<Button variant="secondary" size="sm" onclick={() => load(true)}>다시 시도</Button>{/snippet}
		</Alert>
	{/if}
	{#if verificationUnavailable}<Alert tone="warning">검증 상태를 불러오지 못했습니다. 미검증 이미지와 구분해 표시하며, 새로고침으로 다시 확인할 수 있습니다.</Alert>{/if}
	{#if loading}
		<LoadingSkeleton variant="card" rows={6} />
	{:else}
		<ImageCatalogToolbar bind:searchQuery={catalog.searchQuery} bind:repositoryFilter={catalog.repositoryFilter}
			bind:tagFilter={catalog.tagFilter} bind:verificationFilter={catalog.verificationFilter} bind:sortMode={catalog.sortMode}
			{viewMode} repositoryOptions={catalog.repositoryOptions} tagOptions={catalog.tagOptions}
			resultCount={catalog.filteredImages.length} totalCount={images.length} repositoryCount={catalog.visibleRepositoryCount}
			onClear={clearFilters} onViewModeChange={changeViewMode} />
		<ImageDistroFilter bind:distroFilter={catalog.distroFilter} counts={catalog.distroGroups} />
		<p class="text-xs text-ink-2">관리자 검증은 업로드 또는 명시적 승인 기록입니다. 공개 범위와 별개이며 악성코드 검사 결과를 뜻하지 않습니다.</p>
		{#if resultCount === 0}
			<EmptyState headline={error ? '목록을 표시할 수 없습니다' : images.length ? '검색 결과가 없습니다' : '이미지가 없습니다'}
				description={images.length ? 'repository, tag, 검증 상태 또는 공개 범위 필터를 바꿔보세요.' : '이미지를 업로드하면 카탈로그에 표시됩니다.'} />
		{:else}
			{#if showingRepositories}
				<div class="grid grid-cols-1 gap-3.5 md:grid-cols-2 xl:grid-cols-3" aria-label="이미지 repository 목록">
					{#each pageGroups as group (group.repository)}
						<ImageRepositoryCard {group} onOpen={() => selectedRepository = group.repository} onOpenTag={(id) => selectedImageId = id} />
					{/each}
				</div>
			{:else}
				{#if selectedGroup}
					<Card padding="lg">
						<Button variant="ghost" size="sm" onclick={() => selectedRepository = null}>← repository 목록</Button>
						<h2 class="mt-2 break-all font-mono text-base font-semibold text-ink-0">{selectedGroup.repository}</h2>
						<p class="mt-1 text-xs text-ink-2">{selectedGroup.tags.length}개 tag · {selectedGroup.images.length}개 업로드 · 현재 및 이전 이미지의 SHA 해시와 관리 작업</p>
					</Card>
				{/if}
				<AdminImagesTable images={pageImages} {selectedImageId} {togglingId} {verifyingId} {currentImageIds}
					onOpenDetail={(img) => selectedImageId = img.id} onEdit={openEdit} onToggleActivation={toggleActivation}
					onDelete={deleteImage} onToggleVerification={toggleVerification} />
			{/if}
			<Pagination page={currentPage} {totalPages} total={resultCount} pageSize={Number(pageSize)}
				hasPrev={currentPage > 1} hasNext={currentPage < totalPages} note={showingRepositories ? 'repository' : '이미지'}
				onPrev={() => page = currentPage - 1} onNext={() => page = currentPage + 1} />
		{/if}
	{/if}
</PageShell>

{#if selectedImageId}
	<SlidePanel onClose={() => selectedImageId = null} ariaLabel="관리자 이미지 상세" width="w-full md:w-[50vw] max-w-2xl">
		{#await import('$lib/components/ImageDetailPanel.svelte') then { default: Panel }}
			<Panel imageId={selectedImageId} onClose={() => selectedImageId = null} isAdmin={true} onDelete={() => { selectedImageId = null; void load(true); }} />
		{/await}
	</SlidePanel>
{/if}
<ImageEditModal bind:target={editTarget} bind:form={editForm} {editing} {editError} onSave={saveEdit} />
<ImageUploadModal bind:open={showUploadModal} {token} {projectId} onUploaded={() => load(true)} />
