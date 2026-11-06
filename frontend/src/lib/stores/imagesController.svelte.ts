import { t } from '$lib/i18n/ns/images-keys';
import { api, ApiError } from '$lib/api/client';
import type { ImageInfo } from '$lib/types/compute';
import { createImageCatalog, type ImageCatalogState } from '$lib/stores/imageCatalog.svelte';

import { confirmDialog } from '$lib/stores/confirm.svelte';
import { toast } from '$lib/stores/toast';
import { executeBulkMutations, type BulkMutationResult } from '$lib/utils/bulkActions';
import { createResourceSelection } from '$lib/utils/resourceSelection.svelte';
import { beginExperienceAction, beginExperienceLoad, experienceApplied, experienceDiscarded, experienceState } from '$lib/utils/experience';

export interface ImagesControllerOpts {
  token: () => string | undefined;
  projectId: () => string | undefined;
  viewOwner?: () => string;
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
  let repositoryOwner: string | undefined;
  let repositoryStates = $state<Record<string, ImageCatalogState>>({});
  function repositoryState(repository: string): ImageCatalogState {
    if (!Object.hasOwn(repositoryStates, repository)) repositoryStates = { ...repositoryStates, [repository]: { searchQuery: '', view: { sort: null, filters: {} } } };
    return repositoryStates[repository];
  }

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

  async function fetchImages(fetchOpts?: { refresh?: boolean }, experience = beginExperienceLoad('compute', 'resource.list')) {
    const generation = ++fetchGeneration;
    const token = opts.token();
    const projectId = opts.projectId();
    const viewOwner = opts.viewOwner?.() ?? projectId ?? '';
    if (repositoryOwner !== viewOwner) {
      repositoryOwner = viewOwner;
      repositoryStates = {};
    }
    if (token !== fetchToken || projectId !== fetchProjectId) {
      images = [];
      selection.clear();
      error = '';
      loading = true;
    }
    fetchToken = token;
    fetchProjectId = projectId;
    const owns = () => generation === fetchGeneration && opts.token() === token && opts.projectId() === projectId
      && (opts.viewOwner?.() ?? opts.projectId() ?? '') === viewOwner;
    if (loading || refreshing) experienceState(experience, 'loading');
    try {
      const fetched = await api.withExperience(experience).get<ImageInfo[]>('/api/v1/images', token, projectId, fetchOpts);
      if (!owns()) { experienceDiscarded(experience, 'stale'); return; }
      images = fetched;
      selection.retain(images.map((image) => image.id));
      error = '';
      experienceState(experience, images.length ? 'ready' : 'empty');
      if (experience) void experienceApplied(experience);
    } catch (e) {
      if (owns()) {
        error = e instanceof ApiError ? t('imagesController.loadFailed', { status: e.status }) : t('imagesController.serverError');
        experienceState(experience, 'error');
        if (experience) void experienceApplied(experience);
      } else experienceDiscarded(experience, 'stale');
    } finally {
      if (owns()) loading = false;
    }
  }

  async function deleteImage(id: string, name: string) {
    if (!(await confirmDialog(t('imagesController.deleteConfirm', { name })))) return;
    deleting = id;
    const experience = beginExperienceAction('compute', 'delete', 'resource.list');
    try {
      await api.withExperience(experience).delete(`/api/v1/images/${id}`, opts.token(), opts.projectId());
      images = images.filter(img => img.id !== id);
      selection.remove([id]);
      experienceState(experience, images.length ? 'ready' : 'empty');
      if (experience) void experienceApplied(experience);
    } catch (e) {
      toast.error(t('imagesController.deleteFailed', { message: e instanceof ApiError ? e.message : String(e) }));
      experienceState(experience, 'error');
      if (experience) void experienceApplied(experience);
    } finally {
      deleting = null;
    }
  }

  async function toggleActivation(img: ImageInfo) {
    togglingId = img.id;
    const experience = beginExperienceAction('compute', 'update', 'resource.list');
    try {
      const action = img.status === 'active' ? 'deactivate' : 'reactivate';
      await api.withExperience(experience).post(`/api/v1/images/${img.id}/${action}`, {}, opts.token(), opts.projectId());
      await fetchImages({ refresh: true }, experience);
    } catch (e) {
      toast.error(t('imagesController.statusChangeFailed', { message: e instanceof ApiError ? e.message : String(e) }));
      experienceState(experience, 'error');
      if (experience) void experienceApplied(experience);
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
    const experience = beginExperienceAction('compute', action === 'delete' ? 'delete' : 'update', 'resource.list');
    bulkActioning = true;
    try {
      const results = await executeBulkMutations(ids, (id) => {
        if (action === 'delete') return api.withExperience(experience).delete(`/api/v1/images/${id}`, token, projectId);
        const endpoint = action === 'activate' ? 'reactivate' : 'deactivate';
        return api.withExperience(experience).post(`/api/v1/images/${id}/${endpoint}`, {}, token, projectId);
      });
      if (results.some((result) => !result.ok)) experienceState(experience, 'error');
      if (opts.projectId() === projectId) {
        selection.remove(results.filter((result) => result.ok).map((result) => result.id));
        await fetchImages({ refresh: true }, experience);
      }
      return results;
    } finally {
      bulkActioning = false;
    }
  }

  async function forceRefresh() {
    refreshing = true;
    try {
      await fetchImages({ refresh: true }, beginExperienceAction('compute', 'refresh', 'resource.list'));
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
    catalog,
    view: catalog.view,
    repositoryState,
    get repositoryStates() { return repositoryStates; },
    get searchQuery() { return catalog.searchQuery; },
    set searchQuery(v: string) { catalog.searchQuery = v; },

    get editTarget() { return editTarget; },
    set editTarget(v: ImageInfo | null) { editTarget = v; },
    get showUploadModal() { return showUploadModal; },
    set showUploadModal(v: boolean) { showUploadModal = v; },
    get uploadInitialFile() { return uploadInitialFile; },
    get allRepositoryGroups() { return catalog.allRepositoryGroups; },
    set uploadInitialFile(v: File | null) { uploadInitialFile = v; },
    get filteredImages() { return catalog.filteredImages; },

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
