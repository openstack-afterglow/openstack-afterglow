import { t } from '$lib/i18n/ns/volume';
import { api, ApiError } from '$lib/api/client';
import { createSwr } from '$lib/utils/swr.svelte';
import { apiMut } from '$lib/api/mutations';
import { wizard, openWizard } from '$lib/stores/wizard';
import type { QuotaItem } from '$lib/types/quotas';
import type { Volume, Snapshot } from '$lib/types/volume';
import { confirmDialog } from '$lib/stores/confirm.svelte';

interface VolumeQuotas { storage: { volumes: QuotaItem; gigabytes: QuotaItem; }; }

export interface VolumesControllerOpts {
  token: () => string | undefined;
  projectId: () => string | undefined;
  volumeSnapshotsEnabled?: () => boolean;
}

/** Preselect this volume in the existing VM wizard without launching a VM. */
export function bootFromVolume(vol: Volume) {
  wizard.update(s => ({
    ...s,
    bootSource: 'volume',
    bootVolumeId: vol.id,
    bootVolumeName: vol.name,
    imageId: null,
    imageName: null,
  }));
  openWizard();
}

export function createVolumesController(opts: VolumesControllerOpts) {
  const { swrGet, swrSet } = createSwr(opts.projectId);
  let volumes = $state<Volume[]>([]);
  let snapshots = $state<Snapshot[]>([]);
  let loading = $state(true);
  let refreshing = $state(false);
  let error = $state('');
  let deleting = $state<string | null>(null);
  let snapshotsLoading = $state(true);
  let snapshotsError = $state('');
  let quotasError = $state('');
  let showModal = $state(false);
  let showTransferModal = $state(false);
  let transferVolumeId = $state('');
  let transferVolumeName = $state('');
  let transferMode = $state<'create' | 'receive' | 'list'>('create');
  let tab = $state<'volumes' | 'snapshots'>('volumes');
  let selectedVolumeId = $state<string | null>(null);
  let openActionMenu = $state<string | null>(null);
  let openSnapshotActionMenu = $state<string | null>(null);
  let extendTargetVol = $state<Volume | null>(null);
  let backupTargetVol = $state<Volume | null>(null);
  let snapshotTargetVol = $state<Volume | null>(null);
  let renameTargetVol = $state<Volume | null>(null);
  let detailRefreshKey = $state(0);
  let quotas = $state<VolumeQuotas | null>(null);

  const volumeSnapshotsOn = () => opts.volumeSnapshotsEnabled?.() ?? true;
  // Only the newest list request may write state, so a slow pre-rename or
  // previous-project response cannot overwrite fresher data.
  let volumesRequestSeq = 0;
  let snapshotsRequestSeq = 0;
  let quotasRequestSeq = 0;

  async function fetchVolumes(manual = false) {
    const path = '/api/v1/volumes';
    const seq = ++volumesRequestSeq;
    const cached = swrGet<Volume[]>(path);
    if (cached && volumes.length === 0) volumes = cached;
    if (manual) refreshing = true;
    try {
      const fresh = await api.get<Volume[]>(path, opts.token(), opts.projectId(), manual ? { refresh: true } : undefined);
      if (seq !== volumesRequestSeq) return;
      volumes = fresh;
      swrSet(path, volumes);
      error = '';
    } catch (e) {
      if (seq !== volumesRequestSeq) return;
      error = e instanceof ApiError ? t('listController.fetchFailed', { status: e.status }) : t('listController.serverError');
    } finally {
      if (seq === volumesRequestSeq) {
        loading = false;
        refreshing = false;
      }
    }
  }

  async function fetchSnapshots(manual = false) {
    const seq = ++snapshotsRequestSeq;
    const project = opts.projectId();
    const token = opts.token();
    const owns = () => seq === snapshotsRequestSeq && project === opts.projectId() && token === opts.token();
    if (!volumeSnapshotsOn()) {
      snapshots = [];
      snapshotsError = '';
      snapshotsLoading = false;
      return;
    }
    try {
      const result = await api.get<Snapshot[]>('/api/v1/volume-snapshots', token, project, manual ? { refresh: true } : undefined);
      if (!owns()) return;
      snapshots = result;
      snapshotsError = '';
    } catch {
      if (owns()) snapshotsError = t('page.snapshotsUnavailable');
    } finally {
      if (owns()) snapshotsLoading = false;
    }
  }

  async function fetchQuotas(manual = false) {
    const seq = ++quotasRequestSeq;
    const project = opts.projectId();
    const token = opts.token();
    const owns = () => seq === quotasRequestSeq && project === opts.projectId() && token === opts.token();
    try {
      const result = await api.get<VolumeQuotas>('/api/v1/dashboard/quotas', token, project, manual ? { refresh: true } : undefined);
      if (!owns()) return;
      quotas = result;
      quotasError = '';
    } catch {
      if (owns()) { quotas = null; quotasError = t('page.quotasUnavailable'); }
    }
  }

  async function fetchAll(manual = false) {
    await Promise.allSettled([fetchVolumes(manual), fetchSnapshots(manual), fetchQuotas(manual)]);
  }

  function openVolumePanel(id: string) {
    selectedVolumeId = id;
    history.pushState({ volumeId: id }, '', `/dashboard/volumes/${id}`);
  }

  function closeVolumePanel() {
    selectedVolumeId = null;
    history.pushState({}, '', '/dashboard/volumes');
  }

  function refreshSelectedDetail() {
    if (selectedVolumeId) detailRefreshKey += 1;
  }

  async function deleteVolume(id: string, name: string) {
    if (!(await confirmDialog(t('listController.deleteConfirm', { name: name || id.slice(0, 8) })))) return;
    deleting = id;
    try {
      await apiMut(t('listController.delete'), () => api.delete(`/api/v1/volumes/${id}`, opts.token(), opts.projectId()));
      await fetchVolumes();
    } catch {
      // error toast shown by apiMut
    } finally {
      deleting = null;
    }
  }

  async function deleteSnapshot(id: string, name: string) {
    if (!volumeSnapshotsOn()) return;
    if (!(await confirmDialog(t('listController.deleteSnapshotConfirm', { name: name || id.slice(0, 8) })))) return;
    deleting = id;
    try {
      await apiMut(t('listController.deleteSnapshot'), () =>
        api.delete(`/api/v1/volume-snapshots/${id}`, opts.token(), opts.projectId()),
      );
      await fetchSnapshots();
    } catch {
      // error toast shown by apiMut
    } finally {
      deleting = null;
    }
  }

  function openTransferModal(id = '', name = '', mode: 'create' | 'receive' | 'list' = 'create') {
    transferVolumeId = id;
    transferVolumeName = name;
    transferMode = mode;
    showTransferModal = true;
  }

  async function forceDeleteVolume(id: string, name: string) {
    if (!(await confirmDialog(t('listController.forceDeleteConfirm', { name: name || id.slice(0, 8) })))) return;
    deleting = id;
    try {
      await apiMut(t('listController.forceDelete'), () => api.post(`/api/v1/volumes/${id}/force-delete`, {}, opts.token(), opts.projectId()));
      await fetchVolumes();
    } catch {
      // error toast shown by apiMut
    } finally {
      deleting = null;
    }
  }

  /** Apply a successful PATCH response to the list and any open detail panel, then resync. */
  function applyRenamedVolume(updated: Volume, source: 'list' | 'detail') {
    renameTargetVol = null;
    volumes = volumes.map((vol) => (vol.id === updated.id ? { ...vol, ...updated } : vol));
    swrSet('/api/v1/volumes', volumes);
    if (source === 'list' && selectedVolumeId === updated.id) detailRefreshKey += 1;
    void fetchVolumes();
  }

  /** Drop per-project UI targets so a project switch never acts on the previous tenant's volume. */
  function resetProjectScope() {
    snapshotsRequestSeq += 1;
    quotasRequestSeq += 1;
    snapshotsLoading = true;
    snapshotsError = '';
    quotasError = '';
    snapshots = [];
    quotas = null;
    renameTargetVol = null;
    extendTargetVol = null;
    backupTargetVol = null;
    snapshotTargetVol = null;
    showTransferModal = false;
    openActionMenu = null;
    openSnapshotActionMenu = null;
    if (selectedVolumeId) closeVolumePanel();
  }

  return {
    get volumes() { return volumes; },
    get snapshots() { return snapshots; },
    get loading() { return loading; },
    set loading(v: boolean) { loading = v; },
    get refreshing() { return refreshing; },
    get error() { return error; },
    get snapshotsLoading() { return snapshotsLoading; },
    get snapshotsError() { return snapshotsError; },
    get quotasError() { return quotasError; },
    get deleting() { return deleting; },
    get showModal() { return showModal; },
    set showModal(v: boolean) { showModal = v; },
    get showTransferModal() { return showTransferModal; },
    set showTransferModal(v: boolean) { showTransferModal = v; },
    get transferVolumeId() { return transferVolumeId; },
    get transferVolumeName() { return transferVolumeName; },
    get transferMode() { return transferMode; },
    get tab() { return tab; },
    set tab(v: 'volumes' | 'snapshots') { tab = v; },
    get selectedVolumeId() { return selectedVolumeId; },
    get openActionMenu() { return openActionMenu; },
    set openActionMenu(v: string | null) { openActionMenu = v; },
    get openSnapshotActionMenu() { return openSnapshotActionMenu; },
    set openSnapshotActionMenu(v: string | null) { openSnapshotActionMenu = v; },
    get extendTargetVol() { return extendTargetVol; },
    set extendTargetVol(v: Volume | null) { extendTargetVol = v; },
    get backupTargetVol() { return backupTargetVol; },
    set backupTargetVol(v: Volume | null) { backupTargetVol = v; },
    get snapshotTargetVol() { return snapshotTargetVol; },
    set snapshotTargetVol(v: Volume | null) { snapshotTargetVol = v; },
    get renameTargetVol() { return renameTargetVol; },
    set renameTargetVol(v: Volume | null) { renameTargetVol = v; },
    get detailRefreshKey() { return detailRefreshKey; },
    get quotas() { return quotas; },
    fetchVolumes,
    fetchSnapshots,
    fetchQuotas,
    fetchAll,
    openVolumePanel,
    closeVolumePanel,
    refreshSelectedDetail,
    deleteVolume,
    deleteSnapshot,
    openTransferModal,
    forceDeleteVolume,
    bootFromVolume,
    applyRenamedVolume,
    resetProjectScope,
  };
}
