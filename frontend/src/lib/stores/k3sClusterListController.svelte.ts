import { t } from '$lib/i18n/ns/drover';
import { api, ApiError } from '$lib/api/client';
import { streamK3sProgress } from '$lib/api/k3sSseStream';
import { toast } from '$lib/stores/toast';
import { K3S_CREATE_STEPS } from '$lib/components/k3sSteps';
import { downloadBlobAs } from '$lib/utils/downloadBlob';
import type { K3sCluster } from '$lib/types/k3s';
import type { K3sProgressController } from '$lib/stores/k3sProgress.svelte';
import { confirmDialog } from '$lib/stores/confirm.svelte';
import { get } from 'svelte/store';
import { k3sPermissions } from './k3sPermissions';

export interface K3sClusterListOpts {
  token: () => string | undefined;
  projectId: () => string | undefined;
  userId: () => string | null | undefined;
  progress: K3sProgressController;
}

export function createK3sClusterListController(opts: K3sClusterListOpts) {
  let clusters = $state<K3sCluster[]>([]);
  let loading = $state(true);
  let refreshing = $state(false);
  let error = $state('');
  let deleting = $state<string | null>(null);
  let showDeleted = $state(false);
  let showModal = $state(false);
  let creating = $state(false);
  let createError = $state('');
  let inflight: AbortController | null = null;

  async function fetchClusters(fetchOpts?: { refresh?: boolean }) {
    inflight?.abort();
    const ctrl = new AbortController();
    inflight = ctrl;
    try {
      const qs = showDeleted ? '?include_deleted=true' : '';
      const data = await api.get<K3sCluster[]>(
        `/api/v1/k3s/clusters${qs}`,
        opts.token(), opts.projectId(),
        { ...(fetchOpts ?? {}), signal: ctrl.signal },
      );
      if (ctrl.signal.aborted) return;
      clusters = data;
      error = '';
    } catch (e) {
      if (ctrl.signal.aborted) return;
      if (e instanceof ApiError && e.status === 503) {
        error = t('list.serviceUnavailable');
      } else {
        error = e instanceof ApiError ? t('list.lookupFailed', { status: e.status }) : t('list.serverError');
      }
    } finally {
      if (inflight === ctrl) inflight = null;
      loading = false;
    }
  }

  async function createCluster(form: {
    name: string; agent_count: number; agent_flavor_id: string;
    network_id: string; key_name: string; os_type: string; template_id?: string;
    master_count: number; stampede_enabled?: boolean;
  }) {
    if (!get(k3sPermissions).editClusters) return;
    creating = true;
    createError = '';
    opts.progress.begin('create', t('list.preparingCreate'));
    const clusterName = form.name;
    let prevStep = '';
    try {
      const body = {
        name: form.name,
        agent_count: form.agent_count,
        os_type: form.os_type,
        ...(form.agent_flavor_id ? { agent_flavor_id: form.agent_flavor_id } : {}),
        ...(form.network_id ? { network_id: form.network_id } : {}),
        ...(get(k3sPermissions).adminCredentials && form.key_name ? { key_name: form.key_name } : {}),
        ...(form.template_id ? { template_id: form.template_id } : {}),
        ...(form.stampede_enabled ? { stampede_enabled: true } : {}),
      };
      for await (const msg of streamK3sProgress('/api/v1/k3s/clusters/async', {
        method: 'POST', body, token: opts.token(), projectId: opts.projectId(),
      })) {
        opts.progress.apply(msg);
        if (msg.step !== prevStep && !opts.progress.visible && msg.step !== 'completed' && msg.step !== 'failed') {
          const stepLabel = K3S_CREATE_STEPS.find(s => s.id === msg.step)?.label ?? msg.step;
          toast.info(t('list.stepProgress', { name: clusterName, step: stepLabel }));
        }
        prevStep = msg.step;
        if (msg.step === 'completed') {
          toast.success(t('list.createCompleted', { name: clusterName || t('list.defaultClusterName'), seconds: opts.progress.elapsedSeconds }));
        } else if (msg.step === 'failed') {
          toast.error(t('list.createFailed', { error: msg.error || t('list.unknownError') }));
        }
      }
    } catch (e) {
      opts.progress.failWith(String(e));
    } finally {
      opts.progress.end();
      creating = false;
      await fetchClusters();
    }
  }

  async function deleteCluster(id: string, name: string) {
    if (!get(k3sPermissions).administerClusters) return;
    const userId = opts.userId();
    const projectId = opts.projectId();
    if (!(await confirmDialog(t('list.confirmDelete', { name })))) return;
    if (!get(k3sPermissions).administerClusters || opts.userId() !== userId || opts.projectId() !== projectId) return;
    deleting = id;
    opts.progress.begin('delete');
    try {
      for await (const msg of streamK3sProgress(`/api/v1/k3s/clusters/${id}/delete-async`, {
        method: 'POST', token: opts.token(), projectId: opts.projectId(),
      })) {
        opts.progress.apply(msg);
        if (msg.step === 'completed') toast.success(t('list.deleteCompleted', { name, seconds: opts.progress.elapsedSeconds }));
        else if (msg.step === 'failed') toast.error(t('list.deleteFailed', { error: msg.error || t('list.unknownError') }));
      }
    } catch (e) {
      opts.progress.failWith(String(e));
      toast.error(t('list.deleteFailed', { error: String(e) }));
    } finally {
      opts.progress.end();
      deleting = null;
      await fetchClusters();
    }
  }

  async function downloadKubeconfig(id: string, name: string) {
    const grade = get(k3sPermissions).kubeconfigGrade;
    if (!grade) return;
    const userId = opts.userId();
    const projectId = opts.projectId();
    try {
      const { blob } = await api.downloadBlob(`/api/v1/k3s/clusters/${id}/kubeconfig?grade=${grade}`, opts.token(), projectId);
      // A native-authorized response must not disclose credentials after the requested grade is revoked.
      const current = get(k3sPermissions);
      if ((grade === 'editor' ? !current.workloads : !current.credentials) || opts.userId() !== userId || opts.projectId() !== projectId) return;
      downloadBlobAs(blob, `kubeconfig-${name}.yaml`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        toast.warning(t('list.kubeconfigPending'));
      } else {
        toast.error(t('list.downloadFailed', { error: e instanceof ApiError ? e.message : String(e) }));
      }
    }
  }

  async function forceRefresh() {
    refreshing = true;
    try {
      await fetchClusters({ refresh: true });
    } finally {
      refreshing = false;
    }
  }

  function toggleDeleted() {
    showDeleted = !showDeleted;
    fetchClusters();
  }

  return {
    get clusters() { return clusters; },
    get loading() { return loading; },
    set loading(v: boolean) { loading = v; },
    get refreshing() { return refreshing; },
    get error() { return error; },
    get deleting() { return deleting; },
    get showDeleted() { return showDeleted; },
    set showDeleted(v: boolean) { showDeleted = v; },
    get showModal() { return showModal; },
    set showModal(v: boolean) { showModal = v && get(k3sPermissions).editClusters; },
    get creating() { return creating; },
    get createError() { return createError; },
    fetchClusters,
    createCluster,
    deleteCluster,
    downloadKubeconfig,
    forceRefresh,
    toggleDeleted,
  };
}
