import { getContext, setContext } from 'svelte';
import { api, ApiError } from '$lib/api/client';
import { confirmDialog } from '$lib/stores/confirm.svelte';
import { toast } from '$lib/stores/toast';
import type { Instance } from '$lib/types/compute';
import type { Volume, VolumeSnapshot } from '$lib/types/volume';

export type { Volume, VolumeSnapshot };

export const statusColor: Record<string, string> = {
  available:      'text-green-400 bg-green-900/30',
  creating:       'text-amber-400 bg-amber-900/30',
  deleting:       'text-orange-400 bg-orange-900/30',
  error:          'text-red-400 bg-red-900/30',
  in_use:         'text-blue-400 bg-blue-900/30',
  reserved:       'text-purple-400 bg-purple-900/30',
  attaching:      'text-cyan-400 bg-cyan-900/30',
  detaching:      'text-amber-400 bg-amber-900/30',
  error_deleting: 'text-rose-400 bg-rose-900/30',
};

export type AttachmentInstanceName =
  | { state: 'loading' }
  | { state: 'resolved'; name: string }
  | { state: 'unavailable' };

export interface VolumeDetailOpts {
  volumeId: () => string;
  token: () => string | undefined;
  projectId: () => string | undefined;
  onDeleted?: () => void;
  onClose?: () => void;
  onRenamed?: (volume: Volume) => void;
  volumeSnapshotsEnabled?: () => boolean;
}

export function attachmentServerId(attachment: Record<string, unknown>): string {
  const value = attachment.server_id;
  return typeof value === 'string' ? value : '';
}

export function createVolumeDetailController(opts: VolumeDetailOpts) {
  let volume = $state<Volume | null>(null);
  let snapshots = $state<VolumeSnapshot[]>([]);
  let instances = $state<Instance[]>([]);
  let loading = $state(true);
  let error = $state('');
  let deleting = $state(false);
  let deletingSnapshot = $state<string | null>(null);

  let showSnapshotForm = $state(false);
  let snapshotName = $state('');
  let snapshotDesc = $state('');
  let creatingSnapshot = $state(false);
  let snapshotError = $state('');

  let showAttachModal = $state(false);
  let attachInstanceId = $state('');
  let attaching = $state(false);
  let attachError = $state('');
  let showRenameModal = $state(false);
  let attachmentNames = $state<Record<string, AttachmentInstanceName>>({});
  const volumeSnapshotsOn = () => opts.volumeSnapshotsEnabled?.() ?? true;
  // Every load/reset bumps the generation so responses for a previous volume or
  // project never overwrite the currently displayed detail.
  let generation = 0;
  // Instance names are cached per project so auto refresh does not refetch every
  // attached server. reset() and project changes replace the cache object, so a
  // late response can never write another tenant's (or a stale) name.
  let nameCache = { projectId: undefined as string | undefined, requested: new Set<string>() };

  const canDelete = $derived(
    !!volume && (volume.attachments?.length ?? 0) === 0 && !deleting
  );

  function resolveAttachmentNames(vol: Volume, proj: string | undefined) {
    if (nameCache.projectId !== proj) {
      nameCache = { projectId: proj, requested: new Set() };
      attachmentNames = {};
    }
    const cache = nameCache;
    const tok = opts.token();
    for (const serverId of new Set(vol.attachments.map(attachmentServerId))) {
      if (!serverId || cache.requested.has(serverId)) continue;
      cache.requested.add(serverId);
      attachmentNames = { ...attachmentNames, [serverId]: { state: 'loading' } };
      api.get<Instance>(`/api/v1/instances/${encodeURIComponent(serverId)}`, tok, proj)
        .then(
          (inst): AttachmentInstanceName => (inst?.name ? { state: 'resolved', name: inst.name } : { state: 'unavailable' }),
          (): AttachmentInstanceName => ({ state: 'unavailable' }),
        )
        .then((result) => {
          if (nameCache !== cache || opts.projectId() !== proj) return;
          attachmentNames = { ...attachmentNames, [serverId]: result };
        });
    }
  }

  function attachmentName(serverId: string): AttachmentInstanceName {
    return attachmentNames[serverId] ?? { state: 'loading' };
  }

  async function loadAll() {
    const id = opts.volumeId();
    const tok = opts.token();
    const proj = opts.projectId();
    const gen = ++generation;
    try {
      const snapshotRequest = volumeSnapshotsOn()
        ? api.get<VolumeSnapshot[]>(`/api/v1/volume-snapshots?volume_id=${id}`, tok, proj).catch(() => [] as VolumeSnapshot[])
        : Promise.resolve([] as VolumeSnapshot[]);
      const [vol, snaps] = await Promise.all([
        api.get<Volume>(`/api/v1/volumes/${id}`, tok, proj),
        snapshotRequest,
      ]);
      if (gen !== generation || opts.volumeId() !== id || opts.projectId() !== proj) return;
      volume = vol;
      snapshots = snaps;
      error = '';
      resolveAttachmentNames(vol, proj);
    } catch (e) {
      if (gen !== generation || opts.volumeId() !== id || opts.projectId() !== proj) return;
      error = e instanceof ApiError ? e.message : '볼륨 정보를 불러올 수 없습니다';
    } finally {
      if (gen === generation) loading = false;
    }
  }

  function reset() {
    generation += 1;
    volume = null;
    snapshots = [];
    instances = [];
    loading = true;
    error = '';
    showSnapshotForm = false;
    snapshotName = '';
    snapshotDesc = '';
    snapshotError = '';
    showAttachModal = false;
    attachInstanceId = '';
    attachError = '';
    showRenameModal = false;
    nameCache = { projectId: undefined, requested: new Set() };
    attachmentNames = {};
  }

  function openRenameModal() {
    if (!volume) return;
    showRenameModal = true;
  }

  function closeRenameModal() {
    showRenameModal = false;
  }

  function applyRenamedVolume(updated: Volume) {
    showRenameModal = false;
    if (!volume || updated.id !== volume.id) return;
    volume = { ...volume, ...updated };
    opts.onRenamed?.(updated);
    void loadAll();
  }

  async function openAttachModal() {
    showAttachModal = true;
    attachError = '';
    try {
      instances = await api.get<Instance[]>('/api/v1/instances', opts.token(), opts.projectId());
    } catch {
      instances = [];
    }
  }

  function closeAttachModal() {
    showAttachModal = false;
    attachError = '';
  }

  async function attachVolume() {
    if (!attachInstanceId) return;
    attaching = true;
    attachError = '';
    try {
      await api.post(
        `/api/v1/instances/${attachInstanceId}/volumes`,
        { volume_id: opts.volumeId() },
        opts.token(),
        opts.projectId(),
      );
      showAttachModal = false;
      attachInstanceId = '';
      await loadAll();
    } catch (e) {
      attachError = e instanceof ApiError ? e.message : '연결 실패';
    } finally {
      attaching = false;
    }
  }

  async function deleteVolume() {
    const v = volume;
    const id = opts.volumeId();
    if (!v) return;
    if (!(await confirmDialog(`볼륨 "${v.name || id.slice(0, 8)}"을 삭제하시겠습니까?`))) return;
    deleting = true;
    try {
      await api.delete(`/api/v1/volumes/${id}`, opts.token(), opts.projectId());
      opts.onDeleted?.();
      opts.onClose?.();
    } catch (e) {
      toast.error('삭제 실패: ' + (e instanceof ApiError ? e.message : String(e)));
    } finally {
      deleting = false;
    }
  }

  function startSnapshot() {
    if (!volumeSnapshotsOn()) return;
    showSnapshotForm = true;
    snapshotError = '';
  }

  function cancelSnapshot() {
    showSnapshotForm = false;
    snapshotName = '';
    snapshotDesc = '';
    snapshotError = '';
  }

  async function createSnapshot() {
    if (!volumeSnapshotsOn()) return;
    if (!snapshotName.trim()) return;
    creatingSnapshot = true;
    snapshotError = '';
    try {
      await api.post(
        '/api/v1/volume-snapshots',
        { volume_id: opts.volumeId(), name: snapshotName.trim(), description: snapshotDesc.trim() || undefined },
        opts.token(),
        opts.projectId(),
      );
      snapshotName = '';
      snapshotDesc = '';
      showSnapshotForm = false;
      await loadAll();
    } catch (e) {
      snapshotError = e instanceof ApiError ? e.message : '스냅샷 생성 실패';
    } finally {
      creatingSnapshot = false;
    }
  }

  async function deleteSnapshot(id: string, name: string) {
    if (!volumeSnapshotsOn()) return;
    if (!(await confirmDialog(`스냅샷 "${name || id.slice(0, 8)}"을 삭제하시겠습니까?`))) return;
    deletingSnapshot = id;
    try {
      await api.delete(`/api/v1/volume-snapshots/${id}`, opts.token(), opts.projectId());
      snapshots = snapshots.filter(s => s.id !== id);
    } catch (e) {
      toast.error('삭제 실패: ' + (e instanceof ApiError ? e.message : String(e)));
    } finally {
      deletingSnapshot = null;
    }
  }

  return {
    get volume() { return volume; },
    get snapshots() { return snapshots; },
    get instances() { return instances; },
    get loading() { return loading; },
    get error() { return error; },
    get deleting() { return deleting; },
    get deletingSnapshot() { return deletingSnapshot; },
    get showSnapshotForm() { return showSnapshotForm; },
    set showSnapshotForm(v: boolean) { showSnapshotForm = v; },
    get snapshotName() { return snapshotName; },
    set snapshotName(v: string) { snapshotName = v; },
    get snapshotDesc() { return snapshotDesc; },
    set snapshotDesc(v: string) { snapshotDesc = v; },
    get creatingSnapshot() { return creatingSnapshot; },
    get snapshotError() { return snapshotError; },
    get showAttachModal() { return showAttachModal; },
    get attachInstanceId() { return attachInstanceId; },
    set attachInstanceId(v: string) { attachInstanceId = v; },
    get attaching() { return attaching; },
    get attachError() { return attachError; },
    get canDelete() { return canDelete; },
    get showRenameModal() { return showRenameModal; },
    loadAll,
    reset,
    attachmentName,
    openRenameModal,
    closeRenameModal,
    applyRenamedVolume,
    openAttachModal,
    closeAttachModal,
    attachVolume,
    deleteVolume,
    startSnapshot,
    cancelSnapshot,
    createSnapshot,
    deleteSnapshot,
  };
}

export type VolumeDetailController = ReturnType<typeof createVolumeDetailController>;

const VOLUME_DETAIL_KEY = Symbol('volume-detail');

export function provideVolumeDetailController(store: VolumeDetailController) {
  setContext(VOLUME_DETAIL_KEY, store);
}

export function useVolumeDetailController(): VolumeDetailController {
  const store = getContext<VolumeDetailController | undefined>(VOLUME_DETAIL_KEY);
  if (!store) throw new Error('useVolumeDetailController must be called within VolumeDetailPanel');
  return store;
}
