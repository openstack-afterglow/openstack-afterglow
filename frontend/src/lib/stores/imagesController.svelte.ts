import { api, ApiError } from '$lib/api/client';
import type { ImageInfo } from '$lib/types/compute';
import { createImageCatalog } from '$lib/stores/imageCatalog.svelte';
import type { CatalogSortMode, VerificationFilter } from '$lib/stores/imageCatalog.svelte';
import { confirmDialog } from '$lib/stores/confirm.svelte';
import { toast } from '$lib/stores/toast';
import { executeBulkMutations, type BulkMutationResult } from '$lib/utils/bulkActions';
import { createResourceSelection } from '$lib/utils/resourceSelection.svelte';

export interface ImagesControllerOpts {
  token: () => string | undefined;
  projectId: () => string | undefined;
}
export function createImagesController(opts: ImagesControllerOpts) {
  let images = $state<ImageInfo[]>([]);
  let loading = $state(true);
  let refreshing = $state(false);
  let error = $state('');
  let deleting = $state<string | null>(null);
  let togglingId = $state<string | null>(null);
  let selectedImageId = $state<string | null>(null);
  const catalog = createImageCatalog(() => images);
  let editTarget = $state<ImageInfo | null>(null);
  let showUploadModal = $state(false);
  let uploadInitialFile = $state<File | null>(null);
  let bulkActioning = $state(false);
  const selection = createResourceSelection();
  let fetchGeneration = 0;
  let fetchToken: string | undefined;
  let fetchProjectId: string | undefined;

  function openImagePanel(id: string) {
    selectedImageId = id;
    history.pushState({ imageId: id }, '', `/dashboard/compute/images/${id}`);
  }

  function closeImagePanel() {
    selectedImageId = null;
    history.pushState({}, '', '/dashboard/compute/images');
  }

  function handleImageDeleted(id: string) {
    images = images.filter(img => img.id !== id);
    selection.remove([id]);
  }

  function updateImage(updated: ImageInfo) {
    images = images.map(i => i.id === updated.id ? updated : i);
  }

  async function fetchImages(fetchOpts?: { refresh?: boolean }) {
    const generation = ++fetchGeneration;
    const token = opts.token();
    const projectId = opts.projectId();
    if (token !== fetchToken || projectId !== fetchProjectId) {
      images = [];
      selection.clear();
      error = '';
      loading = true;
    }
    fetchToken = token;
    fetchProjectId = projectId;
    const owns = () => generation === fetchGeneration && opts.token() === token && opts.projectId() === projectId;
    try {
      const fetched = await api.get<ImageInfo[]>('/api/v1/images', token, projectId, fetchOpts);
      if (!owns()) return;
      images = fetched;
      selection.retain(images.map((image) => image.id));
      error = '';
    } catch (e) {
      if (owns()) error = e instanceof ApiError ? `조회 실패 (${e.status})` : '서버 오류';
    } finally {
      if (owns()) loading = false;
    }
  }

  async function deleteImage(id: string, name: string) {
    if (!(await confirmDialog(`이미지 "${name}"을 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.`))) return;
    deleting = id;
    try {
      await api.delete(`/api/v1/images/${id}`, opts.token(), opts.projectId());
      images = images.filter(img => img.id !== id);
      selection.remove([id]);
    } catch (e) {
      toast.error('삭제 실패: ' + (e instanceof ApiError ? e.message : String(e)));
    } finally {
      deleting = null;
    }
  }

  async function toggleActivation(img: ImageInfo) {
    togglingId = img.id;
    try {
      const action = img.status === 'active' ? 'deactivate' : 'reactivate';
      await api.post(`/api/v1/images/${img.id}/${action}`, {}, opts.token(), opts.projectId());
      await fetchImages({ refresh: true });
    } catch (e) {
      toast.error('상태 변경 실패: ' + (e instanceof ApiError ? e.message : String(e)));
    } finally {
      togglingId = null;
    }
  }

  async function executeBulkAction(
    action: 'activate' | 'deactivate' | 'delete',
    ids: readonly string[],
  ): Promise<BulkMutationResult[]> {
    const token = opts.token();
    const projectId = opts.projectId();
    bulkActioning = true;
    try {
      const results = await executeBulkMutations(ids, (id) => {
        if (action === 'delete') return api.delete(`/api/v1/images/${id}`, token, projectId);
        const endpoint = action === 'activate' ? 'reactivate' : 'deactivate';
        return api.post(`/api/v1/images/${id}/${endpoint}`, {}, token, projectId);
      });
      if (opts.projectId() === projectId) {
        selection.remove(results.filter((result) => result.ok).map((result) => result.id));
        await fetchImages({ refresh: true });
      }
      return results;
    } finally {
      bulkActioning = false;
    }
  }

  async function forceRefresh() {
    refreshing = true;
    try {
      await fetchImages({ refresh: true });
    } finally {
      refreshing = false;
    }
  }
  return {
    get images() { return images; },
    get loading() { return loading; },
    set loading(v: boolean) { loading = v; },
    get refreshing() { return refreshing; },
    get error() { return error; },
    get deleting() { return deleting; },
    get togglingId() { return togglingId; },
    get selectedImageId() { return selectedImageId; },
    get bulkActioning() { return bulkActioning; },
    get selection() { return selection; },
    get distroFilter() { return catalog.distroFilter; },
    set distroFilter(v: string) { catalog.distroFilter = v; },
    get searchQuery() { return catalog.searchQuery; },
    set searchQuery(v: string) { catalog.searchQuery = v; },
    get repositoryFilter() { return catalog.repositoryFilter; },
    set repositoryFilter(v: string) { catalog.repositoryFilter = v; },
    get tagFilter() { return catalog.tagFilter; },
    set tagFilter(v: string) { catalog.tagFilter = v; },
    get verificationFilter() { return catalog.verificationFilter; },
    set verificationFilter(v: VerificationFilter) { catalog.verificationFilter = v; },
    get sortMode() { return catalog.sortMode; },
    set sortMode(v: CatalogSortMode) { catalog.sortMode = v; },
    get editTarget() { return editTarget; },
    set editTarget(v: ImageInfo | null) { editTarget = v; },
    get showUploadModal() { return showUploadModal; },
    set showUploadModal(v: boolean) { showUploadModal = v; },
    get uploadInitialFile() { return uploadInitialFile; },
    get allRepositoryGroups() { return catalog.allRepositoryGroups; },
    set uploadInitialFile(v: File | null) { uploadInitialFile = v; },
    get filteredImages() { return catalog.filteredImages; },
    get distroGroups() { return catalog.distroGroups; },
    get repositoryOptions() { return catalog.repositoryOptions; },
    get tagOptions() { return catalog.tagOptions; },
    get visibleRepositoryCount() { return catalog.visibleRepositoryCount; },
    get repositoryGroups() { return catalog.repositoryGroups; },
    openImagePanel,
    closeImagePanel,
    handleImageDeleted,
    updateImage,
    fetchImages,
    deleteImage,
    toggleActivation,
    executeBulkAction,
    forceRefresh,
    clearFilters: catalog.clearFilters,
  };
}
