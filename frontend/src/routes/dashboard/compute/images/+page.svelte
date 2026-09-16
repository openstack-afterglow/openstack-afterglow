<script lang="ts">
  import { untrack } from 'svelte';
  import { auth } from '$lib/stores/auth';
  import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
  import { createImagesController } from '$lib/stores/imagesController.svelte';
  import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
  import ImageDetailPanel from '$lib/components/ImageDetailPanel.svelte';
  import ImageUploadModal from '$lib/components/ImageUploadModal.svelte';
  import SlidePanel from '$lib/components/SlidePanel.svelte';
  import ImageDistroFilter from '$lib/components/dashboard/images/ImageDistroFilter.svelte';
  import ImageCatalogToolbar, { type CatalogViewMode } from '$lib/components/dashboard/images/ImageCatalogToolbar.svelte';
  import ImageRepositoryCard from '$lib/components/dashboard/images/ImageRepositoryCard.svelte';
  import ImageRepositoryDetail from '$lib/components/dashboard/images/ImageRepositoryDetail.svelte';
  import ImageCard from '$lib/components/dashboard/images/ImageCard.svelte';
  import ImageEditModal from '$lib/components/dashboard/images/ImageEditModal.svelte';
  import ImageDropOverlay from '$lib/components/dashboard/images/ImageDropOverlay.svelte';
  import { confirmDialog } from '$lib/stores/confirm.svelte';
  import { toast } from '$lib/stores/toast';
  import { partitionBulkIds } from '$lib/utils/bulkActions';
  import { Alert, BulkSelectionOverlay, Button, EmptyState, PageHeader, PageShell, ResourceToolbar, SelectionToolbar } from '$lib/components/ui';

  const ctrl = createImagesController({
    token: () => $auth.token ?? undefined,
    projectId: () => $auth.projectId ?? undefined,
  });
  let viewMode = $state<CatalogViewMode>('repositories');
  let selectedRepository = $state<string | null>(null);
  const selectedRepositoryGroup = $derived(
    ctrl.allRepositoryGroups.find((group) => group.repository === selectedRepository) ?? null
  );

  function changeViewMode(mode: CatalogViewMode) {
    viewMode = mode;
    selectedRepository = null;
    ctrl.selection.clear();
  }

  function openRepository(repository: string) {
    selectedRepository = repository;
    ctrl.selection.clear();
  }

  function openRepositoryTag(imageId: string) {
    ctrl.openImagePanel(imageId);
  }

  $effect(() => {
    if (selectedRepository && !selectedRepositoryGroup) selectedRepository = null;
  });

  const ar = createAutoRefresh(() => ctrl.fetchImages(), {
    storageKey: 'dashboard-compute-images',
    invokeOnMount: false,
    defaultActive: true,
    defaultInterval: 60,
    intervalOptions: [10, 15, 30, 60],
  });

  const ownedImageIds = $derived(new Set(
    ctrl.filteredImages
      .filter((image) => image.owner === $auth.projectId)
      .map((image) => image.id),
  ));
  const selectedImageIds = $derived([...ctrl.selection.ids]);
  const allOwnedSelected = $derived(
    ownedImageIds.size > 0 && [...ownedImageIds].every((id) => ctrl.selection.has(id)),
  );
  const activatable = $derived(partitionBulkIds(
    selectedImageIds,
    ctrl.filteredImages.filter((image) => image.status === 'deactivated').map((image) => image.id),
  ));
  const deactivatable = $derived(partitionBulkIds(
    selectedImageIds,
    ctrl.filteredImages.filter((image) => image.status === 'active').map((image) => image.id),
  ));

  async function bulkAction(action: 'activate' | 'deactivate' | 'delete') {
    const candidates = action === 'activate'
      ? activatable
      : action === 'deactivate'
        ? deactivatable
        : { eligible: selectedImageIds, skipped: [] };
    if (candidates.eligible.length === 0) return;

    const labels: Record<'activate' | 'deactivate' | 'delete', string> = {
      activate: '활성화',
      deactivate: '비활성화',
      delete: '삭제',
    };
    const label = labels[action];
    const excludedNotice = candidates.skipped.length > 0
      ? `\n${candidates.skipped.length}개는 현재 상태에서 제외됩니다.`
      : '';
    if (action === 'delete' || candidates.skipped.length > 0) {
      const prompt = action === 'delete'
        ? `선택한 이미지 ${candidates.eligible.length}개를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.${excludedNotice}`
        : `선택한 이미지 ${candidates.eligible.length}개를 ${label}하시겠습니까?${excludedNotice}`;
      if (!await confirmDialog(prompt)) return;
    }

    const results = await ctrl.executeBulkAction(action, [...candidates.eligible]);
    const successCount = results.filter((result) => result.ok).length;
    const failureCount = results.length - successCount;
    if (successCount > 0) toast.success(`${successCount}개 ${label} 요청을 완료했습니다.`);
    if (failureCount > 0) toast.error(`${failureCount}개 ${label}에 실패했습니다.`);
    if (candidates.skipped.length > 0) {
      toast.warning(`${candidates.skipped.length}개는 현재 상태에서 ${label}할 수 없어 제외했습니다.`);
    }
  }

  $effect(() => {
    const pid = $auth.projectId;
    untrack(() => {
      ctrl.selection.clear();
      if (!pid) return;
      ctrl.loading = true;
      void ctrl.fetchImages();
    });
  });

  $effect(() => {
    const visibleOwnedIds = ownedImageIds;
    untrack(() => ctrl.selection.retain(visibleOwnedIds));
  });
</script>

<ImageEditModal
  target={ctrl.editTarget}
  onClose={() => ctrl.editTarget = null}
  onSaved={(updated) => ctrl.updateImage(updated)}
/>

<ImageDropOverlay onFile={(f) => { ctrl.uploadInitialFile = f; ctrl.showUploadModal = true; }} />

<PageShell class="bulk-selection-page space-y-4">
  <PageHeader breadcrumb="COMPUTE / IMAGES" title="이미지">
    {#snippet actions()}
      <Button onclick={() => { ctrl.uploadInitialFile = null; ctrl.showUploadModal = true; }} variant="primary">
        + 이미지 업로드
      </Button>
    {/snippet}
  </PageHeader>
  <ResourceToolbar label="이미지 목록 도구">
    {#snippet actions()}
      <AutoRefreshControl
        bind:active={ar.active}
        bind:intervalSeconds={ar.intervalSeconds}
        intervalOptions={ar.intervalOptions}
        refreshing={ctrl.refreshing}
        onManualRefresh={ctrl.forceRefresh}
      />
      <Button
        onclick={() => ctrl.sortOrder = ctrl.sortOrder === 'desc' ? 'asc' : 'desc'}
        variant="secondary"
        size="sm"
      >날짜 {ctrl.sortOrder === 'desc' ? '↓ 최신순' : '↑ 오래된순'}</Button>
    {/snippet}
  </ResourceToolbar>

  {#if ctrl.error}<Alert tone="danger">{ctrl.error}</Alert>{/if}

  {#if ctrl.loading}
    <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3.5">
      {#each Array(8) as _}
        <div class="animate-pulse h-32 bg-surface-base border border-line rounded-lg"></div>
      {/each}
    </div>
  {:else}
    <ImageCatalogToolbar
      bind:searchQuery={ctrl.searchQuery}
      bind:repositoryFilter={ctrl.repositoryFilter}
      bind:tagFilter={ctrl.tagFilter}
      bind:sortMode={ctrl.sortMode}
      {viewMode}
      repositoryOptions={ctrl.repositoryOptions}
      tagOptions={ctrl.tagOptions}
      resultCount={ctrl.filteredImages.length}
      totalCount={ctrl.images.length}
      repositoryCount={ctrl.visibleRepositoryCount}
      onClear={ctrl.clearFilters}
      onViewModeChange={changeViewMode}
    />
    <ImageDistroFilter bind:distroFilter={ctrl.distroFilter} counts={ctrl.distroGroups} />

    {#if ctrl.filteredImages.length === 0}
      <EmptyState
        headline={ctrl.images.length === 0 ? '이미지가 없습니다' : '검색 결과가 없습니다'}
        description={ctrl.images.length > 0 ? 'repository, tag, OS 필터를 바꿔보세요.' : '이미지를 업로드하면 카탈로그에 표시됩니다.'}
      />
    {:else if selectedRepositoryGroup}
      <ImageRepositoryDetail
        group={selectedRepositoryGroup}
        onBack={() => selectedRepository = null}
        onOpenTag={openRepositoryTag}
      />
    {:else if viewMode === 'repositories'}
      <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3.5">
        {#each ctrl.repositoryGroups as group (group.repository)}
          <ImageRepositoryCard
            {group}
            onOpen={() => openRepository(group.repository)}
            onOpenTag={openRepositoryTag}
          />
        {/each}
      </div>
    {:else}
      <div class="mb-3">
        <SelectionToolbar
          label="이미지 tag"
          ariaLabel="이미지 tag 전체 선택"
          checked={allOwnedSelected}
          indeterminate={selectedImageIds.length > 0 && !allOwnedSelected}
          selectedCount={ctrl.selection.count}
          disabled={ctrl.bulkActioning || ownedImageIds.size === 0}
          onToggle={() => ctrl.selection.toggleAll(ownedImageIds)}
        />
      </div>
      <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3.5">
        {#each ctrl.filteredImages as img (img.id)}
          <ImageCard
            {img}
            isOwner={img.owner === $auth.projectId}
            toggling={ctrl.togglingId === img.id}
            deleting={ctrl.deleting === img.id}
            selected={ctrl.selection.has(img.id)}
            selectable={img.owner === $auth.projectId}
            selectionDisabled={ctrl.bulkActioning}
            onSelect={ctrl.openImagePanel}
            onToggleSelect={() => ctrl.selection.toggle(img.id)}
            onToggleActivation={ctrl.toggleActivation}
            onEdit={(i) => ctrl.editTarget = i}
            onDelete={ctrl.deleteImage}
          />
        {/each}
      </div>
    {/if}
  {/if}
  {#if viewMode === 'tags' && !selectedRepositoryGroup}
  <BulkSelectionOverlay
    count={ctrl.selection.count}
    ariaLabel="선택한 이미지 일괄 작업"
    actions={[
      {
        key: 'activate',
        label: '활성화',
        tone: 'success',
        disabled: activatable.eligible.length === 0,
        onAction: () => bulkAction('activate'),
      },
      {
        key: 'deactivate',
        label: '비활성화',
        tone: 'warning',
        disabled: deactivatable.eligible.length === 0,
        onAction: () => bulkAction('deactivate'),
      },
      {
        key: 'delete',
        label: '삭제',
        tone: 'danger',
        disabled: selectedImageIds.length === 0,
        onAction: () => bulkAction('delete'),
      },
    ]}
    busy={ctrl.bulkActioning}
    onClear={() => ctrl.selection.clear()}
  />
  {/if}
</PageShell>

<ImageUploadModal
  bind:open={ctrl.showUploadModal}
  token={$auth.token ?? undefined}
  projectId={$auth.projectId ?? undefined}
  initialFile={ctrl.uploadInitialFile}
  onUploaded={() => ctrl.fetchImages({ refresh: true })}
  onClose={() => { ctrl.uploadInitialFile = null; }}
/>

{#if ctrl.selectedImageId}
  <SlidePanel onClose={ctrl.closeImagePanel} ariaLabel="이미지 상세" width="w-full md:w-[60vw] max-w-2xl">
    <ImageDetailPanel
      imageId={ctrl.selectedImageId}
      onClose={ctrl.closeImagePanel}
      onDelete={ctrl.handleImageDeleted}
    />
  </SlidePanel>
{/if}
