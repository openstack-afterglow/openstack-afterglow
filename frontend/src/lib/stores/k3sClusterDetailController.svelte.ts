import { t } from '$lib/i18n/ns/drover';
import { getContext, setContext } from 'svelte';
import { api, ApiError, fetchWithAuth } from '$lib/api/client';
import { downloadBlobAs } from '$lib/utils/downloadBlob';
import { streamK3sProgress } from '$lib/api/k3sSseStream';
import { maybeMockHead, symbolNoMatch } from '$lib/mockup/transport';
import { toast } from '$lib/stores/toast';
import { invalidateInstanceDetailSelection } from '$lib/stores/instanceDetailController.svelte';
import type { NetworkInfo } from '$lib/types/networks';
import type { K3sCluster, K3sClusterHealth, K3sInterfaceInfo, ConfigMapInfo, SecretInfo, PodInfo, ServiceInfo, DeploymentInfo, ReplicaSetInfo } from '$lib/types/k3s';
import { listNodeInterfaces, attachNodeInterface, detachNodeInterface } from '$lib/api/k3s';
import {
  listNamespaces,
  listConfigMaps,
  listSecrets,
  createConfigMap,
  updateConfigMap,
  deleteConfigMap,
  createSecret,
  updateSecret,
  deleteSecret
} from '$lib/api/k3sResources';
import {
  listPods,
  deletePod,
  getPodLog,
  listServices,
  deleteService,
  listDeployments,
  listReplicaSets,
  restartDeployment as apiRestartDeployment,
  scaleDeployment as apiScaleDeployment,
} from '$lib/api/k3sWorkloads';
import { confirmDialog } from '$lib/stores/confirm.svelte';
import { get } from 'svelte/store';
import { k3sPermissions, type KubeconfigGrade } from './k3sPermissions';
import { K3S_DELETE_STEPS } from '$lib/components/k3sSteps';
import { beginExperienceAction, beginExperienceLoad, experienceApplied, experienceDiscarded, experienceState, recordExperience, type ExperienceAction, type ExperienceContext } from '$lib/utils/experience';

export type ActiveTab = 'main' | 'configmaps' | 'secrets' | 'services' | 'workloads' | 'pods' | 'stampede';

export type { K3sCluster, K3sClusterHealth };

export const statusColor: Record<string, string> = {
  ACTIVE:       'text-green-400 bg-green-900/30',
  CREATING:     'text-yellow-400 bg-yellow-900/30',
  PROVISIONING: 'text-blue-400 bg-blue-900/30',
  SCALING:      'text-cyan-400 bg-cyan-900/30',
  DELETING:     'text-orange-400 bg-orange-900/30',
  ERROR:        'text-red-400 bg-red-900/30',
};

export const healthColor: Record<string, string> = {
  HEALTHY:     'text-green-400 bg-green-900/30 border-green-800',
  DEGRADED:    'text-yellow-400 bg-yellow-900/30 border-yellow-800',
  UNHEALTHY:   'text-red-400 bg-red-900/30 border-red-800',
  UNREACHABLE: 'text-gray-400 bg-gray-800/30 border-gray-700',
  UNKNOWN:     'text-gray-500 bg-gray-800/30 border-gray-700',
};

export interface K3sClusterDetailControllerOpts {
  clusterId: () => string;
  token: () => string | undefined;
  projectId: () => string | undefined;
  userId: () => string | null | undefined;
  adminMode: () => boolean;
  onClose?: () => void;
}

export function createK3sClusterDetailController(opts: K3sClusterDetailControllerOpts) {
  let generation = 0;
  let workloadGeneration = 0;
  let clusterRequest = 0;
  let cluster = $state<K3sCluster | null>(null);
  let health = $state<K3sClusterHealth | null>(null);
  let loading = $state(true);
  let error = $state('');
  let deleting = $state(false);
  let deleteProgress = $state<{ step: string; pct: number; msg: string; error: string } | null>(null);
  let kubeconfigAvailable = $state(false);
  let checkingHealth = $state(false);
  let viewingInstanceId = $state<string | null>(null);
  let scalingTarget = $state<number | null>(null);
  let scaling = $state(false);
  let scaleError = $state('');
  let initialCheckDone = $state(false);
  let interfaces = $state<Record<string, K3sInterfaceInfo[]>>({});
  let networks = $state<NetworkInfo[]>([]);
  let interfaceActioning = $state<string | null>(null); // vmId or `${vmId}:${portId}`
  let namespaces = $state<string[]>([]);
  let selectedNamespace = $state('');
  let configMaps = $state<ConfigMapInfo[]>([]);
  let secrets = $state<SecretInfo[]>([]);
  let cmActioning = $state<string | null>(null); // `${ns}:${name}`
  let namespacesLoaded = $state(false);
  let shellOpen = $state(false);
  let activeTab = $state<ActiveTab>('main');
  let pods = $state<PodInfo[]>([]);
  let services = $state<ServiceInfo[]>([]);
  let deployments = $state<DeploymentInfo[]>([]);
  let replicasets = $state<ReplicaSetInfo[]>([]);
  let workloadActioning = $state<string | null>(null); // `${ns}:${kind}:${name}`
  let podsLoaded = $state(false);
  let servicesLoaded = $state(false);
  let deploymentsLoaded = $state(false);

  const apiBase = $derived(opts.adminMode() ? '/api/v1/admin/k3s-clusters' : '/api/v1/k3s/clusters');
  const isActive = $derived(cluster?.status === 'ACTIVE');

  // Assignment revisions describe actual writes, never whether a response should be applied.
  const assignments = new Map<string, number>();
  function observe(key: string, action: ExperienceAction, context?: ExperienceContext, workload = false, allowed: () => boolean = () => true) {
    const component = key === 'delete' ? 'shared.stream' : 'resource.detail';
    const ctx = context ?? (action === 'load' ? beginExperienceLoad('k3s', component) : beginExperienceAction('k3s', action, component));
    const id = opts.clusterId();
    const projectId = opts.projectId();
    const userId = opts.userId();
    const admin = opts.adminMode();
    const epoch = generation;
    const workloadEpoch = workloadGeneration;
    const namespace = selectedNamespace;
    const current = () => epoch === generation && opts.clusterId() === id && opts.projectId() === projectId && opts.userId() === userId && opts.adminMode() === admin && (!workload || (workloadEpoch === workloadGeneration && namespace === selectedNamespace)) && allowed();
    experienceState(ctx, 'loading');
    return {
      ctx, current,
      applied(state: 'ready' | 'empty' | 'error' | 'disabled', step?: number) {
        const assignment = (assignments.get(key) ?? 0) + 1;
        assignments.set(key, assignment);
        experienceState(ctx, state, step);
        void experienceApplied(ctx, {}, () => assignments.get(key) === assignment && current());
      },
      discarded() { experienceDiscarded(ctx, 'stale'); },
    };
  }

  async function loadCluster(context?: ExperienceContext) {
    const id = opts.clusterId();
    const projectId = opts.projectId();
    const userId = opts.userId();
    const epoch = generation;
    const request = ++clusterRequest;
    if (!id || !projectId) return;
    const current = () => epoch === generation && request === clusterRequest && opts.clusterId() === id && opts.projectId() === projectId && opts.userId() === userId;
    const observation = observe('cluster', 'load', context);
    try {
      const value = await api.withExperience(observation.ctx).get<K3sCluster>(`${apiBase}/${id}`, opts.token(), projectId);
      if (!current()) { observation.discarded(); return; }
      cluster = value;
      if (scalingTarget === null && cluster) scalingTarget = cluster.agent_count;
      error = '';
      observation.applied(cluster ? 'ready' : 'empty');
    } catch (e) {
      if (!current()) { observation.discarded(); return; }
      error = e instanceof ApiError ? t('detail.lookupFailed', { status: e.status }) : t('detail.serverError');
      observation.applied('error');
    } finally {
      if (current()) loading = false;
    }
  }

  async function loadHealth() {
    const id = opts.clusterId();
    if (!id || !cluster || cluster.status !== 'ACTIVE') return;
    const observation = observe('health', 'load');
    try {
      health = await api.withExperience(observation.ctx).get<K3sClusterHealth>(`/api/v1/k3s/clusters/${id}/health`, opts.token(), opts.projectId());
      observation.applied(health ? 'ready' : 'empty');
    } catch {
      // 404는 아직 헬스 데이터 없음 — 무시
      if (observation.current()) experienceState(observation.ctx, health ? 'ready' : 'empty');
    }
  }

  async function triggerHealthCheck() {
    if (!get(k3sPermissions).inventory) return;
    const id = opts.clusterId();
    if (!id || checkingHealth) return;
    const observation = observe('health', 'verify', undefined, false, () => get(k3sPermissions).inventory);
    checkingHealth = true;
    try {
      health = await api.withExperience(observation.ctx).post<K3sClusterHealth>(`/api/v1/k3s/clusters/${id}/health/check`, {}, opts.token(), opts.projectId());
      observation.applied(health ? 'ready' : 'empty');
    } catch {
      // rate limit(429) 등 — 무시
      if (observation.current()) experienceState(observation.ctx, health ? 'ready' : 'empty');
    } finally {
      checkingHealth = false;
    }
  }

  // Always request the explicit native grade, including on the administrator surface.
  // The ungraded administrator endpoint returns the irrevocable stored certificate.

  async function checkKubeconfig() {
    const grade = get(k3sPermissions).kubeconfigGrade;
    if (!grade) { kubeconfigAvailable = false; return; }
    const id = opts.clusterId();
    if (!id || !cluster || cluster.status !== 'ACTIVE') return;
    const userId = opts.userId();
    const projectId = opts.projectId();
    const epoch = generation;
    const observation = observe('kubeconfig-check', 'load', undefined, false, () => get(k3sPermissions).kubeconfigGrade === grade);
    try {
      const path = `/api/v1/k3s/clusters/${id}/kubeconfig?grade=${grade}`;
      const mock = await maybeMockHead(path, opts.token(), opts.projectId());
      if (epoch !== generation || get(k3sPermissions).kubeconfigGrade !== grade || opts.userId() !== userId || opts.projectId() !== projectId || opts.clusterId() !== id) { observation.discarded(); return; }
      if (mock !== symbolNoMatch) {
        kubeconfigAvailable = mock.ok;
        observation.applied(mock.ok ? 'ready' : 'empty');
        return;
      }
      const res = await fetchWithAuth(path, {
        method: 'HEAD',
      }, opts.token(), opts.projectId(), { experience: observation.ctx });
      if (epoch !== generation || get(k3sPermissions).kubeconfigGrade !== grade || opts.userId() !== userId || opts.projectId() !== projectId || opts.clusterId() !== id) { observation.discarded(); return; }
      kubeconfigAvailable = res.ok;
      observation.applied(res.ok ? 'ready' : 'empty');
    } catch {
      kubeconfigAvailable = false;
      observation.applied('error');
    }
  }

  /** `full` requests the irrevocable stored administrator certificate and needs an explicit confirmation. */
  async function downloadKubeconfig(full = false) {
    const grade: KubeconfigGrade | null = full
      ? (get(k3sPermissions).adminCredentials ? 'admin' : null)
      : get(k3sPermissions).kubeconfigGrade;
    if (!grade) return;
    const id = opts.clusterId();
    if (!id || !cluster) return;
    const userId = opts.userId();
    const projectId = opts.projectId();
    const epoch = generation;
    const name = cluster.name;
    if (full) {
      if (!(await confirmDialog(t('detail.confirmAdminKubeconfig', { name })))) return;
      if (epoch !== generation || !get(k3sPermissions).adminCredentials || opts.userId() !== userId || opts.projectId() !== projectId || opts.clusterId() !== id) return;
    }
    const observation = observe('kubeconfig-download', 'export', undefined, false, () => {
      const permission = get(k3sPermissions);
      return full ? permission.adminCredentials : grade === 'editor' ? permission.workloads : permission.credentials;
    });
    try {
      const { blob } = await api.withExperience(observation.ctx).downloadBlob(`/api/v1/k3s/clusters/${id}/kubeconfig?grade=${grade}`, opts.token(), projectId);
      // Recheck the requested grade as well as identity before disclosing this native-issued credential.
      const current = get(k3sPermissions);
      if (epoch !== generation || (full ? !current.adminCredentials : grade === 'editor' ? !current.workloads : !current.credentials) || opts.userId() !== userId || opts.projectId() !== projectId || opts.clusterId() !== id) { observation.discarded(); return; }
      downloadBlobAs(blob, `kubeconfig-${name}.yaml`);
      if (observation.current()) experienceState(observation.ctx, 'ready');
    } catch (e) {
      if (observation.current()) experienceState(observation.ctx, 'error');
      if (e instanceof ApiError && e.status === 404) toast.warning(t('detail.kubeconfigPending'));
      else toast.error(t('detail.downloadFailed', { error: e instanceof ApiError ? e.message : String(e) }));
    }
  }

  async function deleteCluster() {
    if (!get(k3sPermissions).administerClusters) return;
    const c = cluster;
    const id = opts.clusterId();
    const userId = opts.userId();
    const projectId = opts.projectId();
    const epoch = generation;
    if (!c || !(await confirmDialog(t('detail.confirmDelete', { name: c.name })))) return;
    if (epoch !== generation || !get(k3sPermissions).administerClusters || opts.userId() !== userId || opts.projectId() !== projectId || opts.clusterId() !== id) return;
    const observation = observe('delete', 'delete', undefined, false, () => get(k3sPermissions).administerClusters);
    let observedStep = '';
    deleting = true;
    deleteProgress = { step: '', pct: 0, msg: t('detail.preparingDelete'), error: '' };
    try {
      for await (const msg of streamK3sProgress(
        `${apiBase}/${id}/delete-async`,
        { method: 'POST', token: opts.token(), projectId: opts.projectId(), experience: observation.ctx },
      )) {
        deleteProgress = { step: msg.step, pct: msg.progress, msg: msg.message, error: msg.error ?? '' };
        if (msg.step !== observedStep) {
          observedStep = msg.step;
          const stage = K3S_DELETE_STEPS.findIndex(item => item.id === msg.step);
          if (stage >= 0) {
            experienceState(observation.ctx, msg.step === 'completed' ? 'ready' : 'loading', stage + 1);
            const appliedStep = msg.step;
            void experienceApplied(observation.ctx, {}, () => observation.current() && deleteProgress?.step === appliedStep);
          }
        }
        if (msg.step === 'completed') {
          opts.onClose?.();
          return;
        }
        if (msg.step === 'failed') {
          deleteProgress = { ...deleteProgress, error: msg.error ?? t('detail.unknownError') };
          deleting = false;
          observation.applied('error');
          return;
        }
      }
      if (observation.current()) recordExperience(observation.ctx, 'telemetry.gap', { reason: 'transport_failed' });
      else observation.discarded();
    } catch (e) {
      deleteProgress = { step: 'failed', pct: 0, msg: t('detail.deleteFailed'), error: String(e) };
      deleting = false;
      observation.applied('error');
    }
  }

  async function applyScale() {
    if (!get(k3sPermissions).editClusters) return;
    const c = cluster;
    const id = opts.clusterId();
    if (scalingTarget === null || !c) return;
    if (scalingTarget === c.agent_vm_ids.length && scalingTarget === c.agent_count) return;
    const userId = opts.userId();
    const projectId = opts.projectId();
    const epoch = generation;
    if (!(await confirmDialog(t('detail.confirmScale', { current: c.agent_vm_ids.length, target: scalingTarget })))) return;
    if (epoch !== generation || !get(k3sPermissions).editClusters || opts.userId() !== userId || opts.projectId() !== projectId || opts.clusterId() !== id) return;
    const observation = observe('scale', 'update', undefined, false, () => get(k3sPermissions).editClusters);
    scaling = true;
    scaleError = '';
    try {
      await api.withExperience(observation.ctx).patch(`${apiBase}/${id}/scale`, { agent_count: scalingTarget }, opts.token(), opts.projectId());
      await loadCluster(observation.ctx);
    } catch (e) {
      scaleError = e instanceof ApiError ? e.message : String(e);
      observation.applied('error');
    } finally {
      scaling = false;
    }
  }

  function incrementScale() {
    if (!get(k3sPermissions).editClusters) return;
    scalingTarget = Math.min(10, (scalingTarget ?? cluster?.agent_count ?? 0) + 1);
  }

  function decrementScale() {
    if (!get(k3sPermissions).editClusters) return;
    scalingTarget = Math.max(0, (scalingTarget ?? cluster?.agent_count ?? 0) - 1);
  }

  async function loadNetworks() {
    if (networks.length > 0) return;
    const observation = observe('networks', 'load');
    try {
      networks = await api.withExperience(observation.ctx).get<NetworkInfo[]>('/api/v1/networks', opts.token(), opts.projectId());
      observation.applied(networks.length ? 'ready' : 'empty');
    } catch {
      networks = [];
      observation.applied('error');
    }
  }

  async function loadInterfaces(vmIds: string[], context?: ExperienceContext) {
    const id = opts.clusterId();
    if (!id) return;
    const observation = observe('interfaces', 'load', context);
    await Promise.all(
      vmIds.map(async (vmId) => {
        try {
          const list = await listNodeInterfaces(id, vmId, opts.token(), opts.projectId(), observation.ctx);
          interfaces = { ...interfaces, [vmId]: list };
          observation.applied(list.length ? 'ready' : 'empty');
        } catch {
          // 개별 노드 실패는 무시
        }
      })
    );
    if (observation.current()) experienceState(observation.ctx, Object.values(interfaces).some(list => list.length > 0) ? 'ready' : 'empty');
  }

  async function attachInterface(vmId: string, netId: string) {
    if (!get(k3sPermissions).editClusters) return;
    const id = opts.clusterId();
    if (!id || interfaceActioning) return;
    const observation = observe('interface-mutation', 'attach', undefined, false, () => get(k3sPermissions).editClusters);
    interfaceActioning = vmId;
    try {
      await attachNodeInterface(id, vmId, netId, opts.token(), opts.projectId(), observation.ctx);
      const list = await listNodeInterfaces(id, vmId, opts.token(), opts.projectId(), observation.ctx);
      interfaces = { ...interfaces, [vmId]: list };
      observation.applied(list.length ? 'ready' : 'empty');
    } catch (e) {
      if (observation.current()) experienceState(observation.ctx, 'error');
      throw e;
    } finally {
      interfaceActioning = null;
    }
  }

  async function detachInterface(vmId: string, portId: string) {
    if (!get(k3sPermissions).administerClusters) return;
    const id = opts.clusterId();
    if (!id || interfaceActioning) return;
    const observation = observe('interface-mutation', 'detach', undefined, false, () => get(k3sPermissions).administerClusters);
    interfaceActioning = `${vmId}:${portId}`;
    try {
      await detachNodeInterface(id, vmId, portId, opts.token(), opts.projectId(), observation.ctx);
      const list = await listNodeInterfaces(id, vmId, opts.token(), opts.projectId(), observation.ctx);
      interfaces = { ...interfaces, [vmId]: list };
      observation.applied(list.length ? 'ready' : 'empty');
    } catch (e) {
      if (observation.current()) experienceState(observation.ctx, 'error');
      throw e;
    } finally {
      interfaceActioning = null;
    }
  }

  async function loadNamespaces() {
    const id = opts.clusterId();
    if (!id || namespacesLoaded) return;
    const userId = opts.userId();
    const projectId = opts.projectId();
    const epoch = generation;
    const observation = observe('namespaces', 'load');
    try {
      const ns = await listNamespaces(id, opts.token(), opts.projectId(), observation.ctx);
      if (epoch !== generation || opts.userId() !== userId || opts.projectId() !== projectId || opts.clusterId() !== id) { observation.discarded(); return; }
      namespaces = ns;
      if (!namespaces.includes(selectedNamespace)) {
        selectedNamespace = namespaces[0] ?? '';
      }
      namespacesLoaded = true;
      observation.applied(namespaces.length ? 'ready' : 'empty');
    } catch {
      if (epoch !== generation) { observation.discarded(); return; }
      namespaces = [];
      selectedNamespace = '';
      observation.applied('error');
    }
  }

  async function loadConfigMaps() {
    if (!get(k3sPermissions).workloads) { configMaps = []; return; }
    const id = opts.clusterId();
    if (!id) return;
    if (!selectedNamespace) return;
    const userId = opts.userId();
    const projectId = opts.projectId();
    const namespace = selectedNamespace;
    const epoch = generation;
    const workloadEpoch = workloadGeneration;
    const observation = observe('configmaps', 'load', undefined, true, () => get(k3sPermissions).workloads);
    try {
      const items = await listConfigMaps(id, namespace, opts.token(), projectId, observation.ctx);
      if (epoch !== generation || workloadEpoch !== workloadGeneration || !get(k3sPermissions).workloads || opts.userId() !== userId || opts.projectId() !== projectId || opts.clusterId() !== id || selectedNamespace !== namespace) { observation.discarded(); return; }
      configMaps = items;
      observation.applied(configMaps.length ? 'ready' : 'empty');
    } catch {
      if (epoch !== generation || workloadEpoch !== workloadGeneration) { observation.discarded(); return; }
      configMaps = [];
      observation.applied('error');
    }
  }

  async function loadSecrets() {
    if (!get(k3sPermissions).workloads) { secrets = []; return; }
    const id = opts.clusterId();
    if (!id) return;
    if (!selectedNamespace) return;
    const userId = opts.userId();
    const projectId = opts.projectId();
    const namespace = selectedNamespace;
    const epoch = generation;
    const workloadEpoch = workloadGeneration;
    const observation = observe('secrets', 'load', undefined, true, () => get(k3sPermissions).workloads);
    try {
      const items = await listSecrets(id, namespace, opts.token(), projectId, observation.ctx);
      if (epoch !== generation || workloadEpoch !== workloadGeneration || !get(k3sPermissions).workloads || opts.userId() !== userId || opts.projectId() !== projectId || opts.clusterId() !== id || selectedNamespace !== namespace) { observation.discarded(); return; }
      secrets = items;
      observation.applied(secrets.length ? 'ready' : 'empty');
    } catch {
      if (epoch !== generation || workloadEpoch !== workloadGeneration) { observation.discarded(); return; }
      secrets = [];
      observation.applied('error');
    }
  }

  function captureWorkloadScope() {
    const id = opts.clusterId();
    const namespace = selectedNamespace;
    const projectId = opts.projectId();
    const userId = opts.userId();
    const token = opts.token();
    const epoch = generation;
    const workloadEpoch = workloadGeneration;
    if (!id || !namespace || !projectId || !userId || !token) return null;
    return { id, namespace, projectId, token,
      current: () => epoch === generation && workloadEpoch === workloadGeneration && opts.clusterId() === id && opts.projectId() === projectId && opts.userId() === userId && selectedNamespace === namespace,
    };
  }

  async function saveConfigMap(name: string, data: Record<string, string>, isNew: boolean) {
    if (!get(k3sPermissions).workloads) return;
    const scope = captureWorkloadScope();
    if (!scope || cmActioning) return;
    const observation = observe('configmaps', isNew ? 'create' : 'update', undefined, true, () => get(k3sPermissions).workloads);
    cmActioning = `${scope.namespace}:${name}`;
    try {
      if (isNew) {
        const cm = await createConfigMap(scope.id, scope.namespace, { name, data }, scope.token, scope.projectId, observation.ctx);
        if (!scope.current() || !get(k3sPermissions).workloads) { observation.discarded(); return; }
        configMaps = [...configMaps, cm];
      } else {
        const cm = await updateConfigMap(scope.id, scope.namespace, name, { data }, scope.token, scope.projectId, observation.ctx);
        if (!scope.current() || !get(k3sPermissions).workloads) { observation.discarded(); return; }
        configMaps = configMaps.map((c) => (c.name === name ? cm : c));
      }
      observation.applied('ready');
    } catch (e) {
      if (observation.current()) experienceState(observation.ctx, 'error');
      throw e;
    } finally {
      if (scope.current()) cmActioning = null;
    }
  }

  async function deleteCm(name: string) {
    if (!get(k3sPermissions).workloads) return;
    const scope = captureWorkloadScope();
    if (!scope || cmActioning) return;
    if (!(await confirmDialog(t('configMaps.confirmDelete', { name })))) return;
    if (!scope.current() || !get(k3sPermissions).workloads || cmActioning) return;
    const observation = observe('configmaps', 'delete', undefined, true, () => get(k3sPermissions).workloads);
    cmActioning = `${scope.namespace}:${name}`;
    try {
      await deleteConfigMap(scope.id, scope.namespace, name, scope.token, scope.projectId, observation.ctx);
      if (!scope.current() || !get(k3sPermissions).workloads) { observation.discarded(); return; }
      configMaps = configMaps.filter((c) => c.name !== name);
      observation.applied(configMaps.length ? 'ready' : 'empty');
    } catch (e) {
      if (observation.current()) experienceState(observation.ctx, 'error');
      throw e;
    } finally {
      if (scope.current()) cmActioning = null;
    }
  }

  async function saveSecret(name: string, type: string, data: Record<string, string>, isNew: boolean) {
    if (!get(k3sPermissions).workloads || (type !== 'Opaque' && !get(k3sPermissions).adminCredentials)) return;
    const scope = captureWorkloadScope();
    if (!scope || cmActioning) return;
    const observation = observe('secrets', isNew ? 'create' : 'update', undefined, true, () => get(k3sPermissions).workloads && (type === 'Opaque' || get(k3sPermissions).adminCredentials));
    cmActioning = `${scope.namespace}:${name}`;
    try {
      if (isNew) {
        const s = await createSecret(scope.id, scope.namespace, { name, type, data }, scope.token, scope.projectId, observation.ctx);
        if (!scope.current() || !get(k3sPermissions).workloads || (type !== 'Opaque' && !get(k3sPermissions).adminCredentials)) { observation.discarded(); return; }
        secrets = [...secrets, s];
      } else {
        const s = await updateSecret(scope.id, scope.namespace, name, { type, data }, scope.token, scope.projectId, observation.ctx);
        if (!scope.current() || !get(k3sPermissions).workloads || (type !== 'Opaque' && !get(k3sPermissions).adminCredentials)) { observation.discarded(); return; }
        secrets = secrets.map((x) => (x.name === name ? s : x));
      }
      observation.applied('ready');
    } catch (e) {
      if (observation.current()) experienceState(observation.ctx, 'error');
      throw e;
    } finally {
      if (scope.current()) cmActioning = null;
    }
  }

  async function deleteSecretItem(name: string) {
    if (!get(k3sPermissions).workloads) return;
    const scope = captureWorkloadScope();
    if (!scope || cmActioning) return;
    if (!(await confirmDialog(t('secrets.confirmDelete', { name })))) return;
    if (!scope.current() || !get(k3sPermissions).workloads || cmActioning) return;
    const observation = observe('secrets', 'delete', undefined, true, () => get(k3sPermissions).workloads);
    cmActioning = `${scope.namespace}:${name}`;
    try {
      await deleteSecret(scope.id, scope.namespace, name, scope.token, scope.projectId, observation.ctx);
      if (!scope.current() || !get(k3sPermissions).workloads) { observation.discarded(); return; }
      secrets = secrets.filter((s) => s.name !== name);
      observation.applied(secrets.length ? 'ready' : 'empty');
    } catch (e) {
      if (observation.current()) experienceState(observation.ctx, 'error');
      throw e;
    } finally {
      if (scope.current()) cmActioning = null;
    }
  }

  function openShell() {
    if (!get(k3sPermissions).workloads) return;
    const observation = observe('shell', 'open', undefined, true, () => get(k3sPermissions).workloads);
    shellOpen = true;
    observation.applied('ready');
  }
  function closeShell() {
    const observation = observe('shell', 'close');
    shellOpen = false;
    observation.applied('disabled');
  }

  function _invalidateWorkloadCaches() {
    podsLoaded = false;
    servicesLoaded = false;
    deploymentsLoaded = false;
    pods = [];
    services = [];
    deployments = [];
    replicasets = [];
  }

  async function loadPods() {
    const id = opts.clusterId();
    if (!id) return;
    const observation = observe('pods', 'load', undefined, true);
    try {
      pods = await listPods(id, selectedNamespace, opts.token(), opts.projectId(), observation.ctx);
      podsLoaded = true;
      observation.applied(pods.length ? 'ready' : 'empty');
    } catch {
      pods = [];
      observation.applied('error');
    }
  }

  async function loadServices() {
    const id = opts.clusterId();
    if (!id) return;
    const observation = observe('services', 'load', undefined, true);
    try {
      services = await listServices(id, selectedNamespace, opts.token(), opts.projectId(), observation.ctx);
      servicesLoaded = true;
      observation.applied(services.length ? 'ready' : 'empty');
    } catch {
      services = [];
      observation.applied('error');
    }
  }

  async function loadDeployments() {
    const id = opts.clusterId();
    if (!id) return;
    const observation = observe('deployments', 'load', undefined, true);
    try {
      const [deps, rss] = await Promise.all([
        listDeployments(id, selectedNamespace, opts.token(), opts.projectId(), observation.ctx),
        listReplicaSets(id, selectedNamespace, opts.token(), opts.projectId(), observation.ctx),
      ]);
      deployments = deps;
      replicasets = rss;
      deploymentsLoaded = true;
      observation.applied(deployments.length || replicasets.length ? 'ready' : 'empty');
    } catch {
      deployments = [];
      replicasets = [];
      observation.applied('error');
    }
  }

  async function removePod(name: string) {
    if (!get(k3sPermissions).workloads) return;
    const id = opts.clusterId();
    if (!id || !selectedNamespace || workloadActioning) return;
    const userId = opts.userId();
    const projectId = opts.projectId();
    const namespace = selectedNamespace;
    const confirmed = await confirmDialog(t('detail.confirmDeletePod', { name }));
    if (!confirmed || !get(k3sPermissions).workloads || opts.userId() !== userId || opts.projectId() !== projectId || opts.clusterId() !== id || selectedNamespace !== namespace) return;
    const observation = observe('pods', 'delete', undefined, true, () => get(k3sPermissions).workloads);
    workloadActioning = `${selectedNamespace}:pod:${name}`;
    try {
      await deletePod(id, selectedNamespace, name, opts.token(), opts.projectId(), observation.ctx);
      pods = pods.filter((p) => p.name !== name);
      observation.applied(pods.length ? 'ready' : 'empty');
    } catch (e) {
      if (observation.current()) experienceState(observation.ctx, 'error');
      toast.error(e instanceof ApiError ? e.message : t('detail.deletePodFailed'));
    } finally {
      workloadActioning = null;
    }
  }

  async function removeSvc(name: string) {
    if (!get(k3sPermissions).workloads) return;
    const id = opts.clusterId();
    if (!id || !selectedNamespace || workloadActioning) return;
    const userId = opts.userId();
    const projectId = opts.projectId();
    const namespace = selectedNamespace;
    const confirmed = await confirmDialog(t('detail.confirmDeleteService', { name }));
    if (!confirmed || !get(k3sPermissions).workloads || opts.userId() !== userId || opts.projectId() !== projectId || opts.clusterId() !== id || selectedNamespace !== namespace) return;
    const observation = observe('services', 'delete', undefined, true, () => get(k3sPermissions).workloads);
    workloadActioning = `${selectedNamespace}:svc:${name}`;
    try {
      await deleteService(id, selectedNamespace, name, opts.token(), opts.projectId(), observation.ctx);
      services = services.filter((s) => s.name !== name);
      observation.applied(services.length ? 'ready' : 'empty');
    } catch (e) {
      if (observation.current()) experienceState(observation.ctx, 'error');
      toast.error(e instanceof ApiError ? e.message : t('detail.deleteServiceFailed'));
    } finally {
      workloadActioning = null;
    }
  }

  async function rolloutRestartDeployment(name: string) {
    if (!get(k3sPermissions).workloads) return;
    const id = opts.clusterId();
    if (!id || !selectedNamespace || workloadActioning) return;
    const observation = observe('deployments', 'restart', undefined, true, () => get(k3sPermissions).workloads);
    workloadActioning = `${selectedNamespace}:deploy:${name}`;
    try {
      const updated = await apiRestartDeployment(id, selectedNamespace, name, opts.token(), opts.projectId(), observation.ctx);
      deployments = deployments.map((d) => (d.name === name ? updated : d));
      observation.applied('ready');
      toast.success(t('detail.restartRequested', { name }));
    } catch (e) {
      if (observation.current()) experienceState(observation.ctx, 'error');
      toast.error(e instanceof ApiError ? e.message : t('detail.restartFailed'));
    } finally {
      workloadActioning = null;
    }
  }

  async function scaleDeploymentTo(name: string, replicas: number) {
    if (!get(k3sPermissions).workloads) return;
    const id = opts.clusterId();
    if (!id || !selectedNamespace || workloadActioning) return;
    const observation = observe('deployments', 'update', undefined, true, () => get(k3sPermissions).workloads);
    workloadActioning = `${selectedNamespace}:deploy:${name}`;
    try {
      const updated = await apiScaleDeployment(id, selectedNamespace, name, replicas, opts.token(), opts.projectId(), observation.ctx);
      deployments = deployments.map((d) => (d.name === name ? updated : d));
      observation.applied('ready');
    } catch (e) {
      if (observation.current()) experienceState(observation.ctx, 'error');
      toast.error(e instanceof ApiError ? e.message : t('detail.scaleFailed'));
    } finally {
      workloadActioning = null;
    }
  }

  async function fetchPodLog(name: string, opts2: { container?: string; tailLines?: number }) {
    if (!get(k3sPermissions).credentials) return null;
    const id = opts.clusterId();
    if (!id || !selectedNamespace) return null;
    const epoch = generation;
    const workloadEpoch = workloadGeneration;
    const userId = opts.userId();
    const projectId = opts.projectId();
    const namespace = selectedNamespace;
    const observation = observe('pod-log', 'inspect', undefined, true, () => get(k3sPermissions).credentials);
    try {
      const result = await getPodLog(id, namespace, name, opts2, opts.token(), projectId, observation.ctx);
      if (epoch !== generation || workloadEpoch !== workloadGeneration || !get(k3sPermissions).credentials || opts.userId() !== userId || opts.projectId() !== projectId || opts.clusterId() !== id || selectedNamespace !== namespace) { observation.discarded(); return null; }
      // This owner returns logs; it does not own their eventual rendered content.
      if (observation.current()) experienceState(observation.ctx, 'ready');
      else observation.discarded();
      return result;
    } catch (e) {
      if (observation.current()) experienceState(observation.ctx, 'error');
      else observation.discarded();
      toast.error(e instanceof ApiError ? e.message : t('detail.podLogFailed'));
      return null;
    }
  }

  function reset() {
    invalidateInstanceDetailSelection();
    generation += 1;
    cluster = null;
    health = null;
    loading = true;
    error = '';
    deleteProgress = null;
    deleting = false;
    scalingTarget = null;
    initialCheckDone = false;
    kubeconfigAvailable = false;
    scaleError = '';
    interfaces = {};
    networks = [];
    interfaceActioning = null;
    namespaces = [];
    selectedNamespace = '';
    configMaps = [];
    secrets = [];
    cmActioning = null;
    namespacesLoaded = false;
    shellOpen = false;
    activeTab = 'main';
    pods = [];
    services = [];
    deployments = [];
    replicasets = [];
    workloadActioning = null;
    podsLoaded = false;
    servicesLoaded = false;
    deploymentsLoaded = false;
  }

  function setViewingInstance(id: string | null) {
    invalidateInstanceDetailSelection();
    viewingInstanceId = id;
  }

  function clearViewingInstance() {
    invalidateInstanceDetailSelection();
    viewingInstanceId = null;
  }

  return {
    get cluster() { return cluster; },
    get health() { return health; },
    get loading() { return loading; },
    get error() { return error; },
    get deleting() { return deleting; },
    get deleteProgress() { return deleteProgress; },
    get kubeconfigAvailable() { return kubeconfigAvailable; },
    get checkingHealth() { return checkingHealth; },
    get viewingInstanceId() { return viewingInstanceId; },
    get scalingTarget() { return scalingTarget; },
    set scalingTarget(v: number | null) { scalingTarget = v; },
    get scaling() { return scaling; },
    get scaleError() { return scaleError; },
    get initialCheckDone() { return initialCheckDone; },
    set initialCheckDone(v: boolean) { initialCheckDone = v; },
    get apiBase() { return apiBase; },
    get adminMode() { return opts.adminMode(); },
    get projectId() { return opts.projectId(); },
    get isActive() { return isActive; },
    get interfaces() { return interfaces; },
    get networks() { return networks; },
    get interfaceActioning() { return interfaceActioning; },
    loadCluster,
    loadHealth,
    triggerHealthCheck,
    checkKubeconfig,
    downloadKubeconfig,
    deleteCluster,
    applyScale,
    incrementScale,
    decrementScale,
    reset,
    setViewingInstance,
    clearViewingInstance,
    loadNetworks,
    loadInterfaces,
    attachInterface,
    detachInterface,
    get namespaces() { return namespaces; },
    get selectedNamespace() { return selectedNamespace; },
    set selectedNamespace(v: string) {
      if (v !== selectedNamespace) {
        workloadGeneration += 1;
        cmActioning = null;
        selectedNamespace = v;
        _invalidateWorkloadCaches();
        configMaps = [];
        secrets = [];
      }
    },
    get configMaps() { return configMaps; },
    get secrets() { return secrets; },
    get cmActioning() { return cmActioning; },
    loadNamespaces,
    loadConfigMaps,
    loadSecrets,
    saveConfigMap,
    deleteCm,
    saveSecret,
    deleteSecretItem,
    get shellOpen() { return shellOpen; },
    openShell,
    closeShell,
    get activeTab() { return activeTab; },
    set activeTab(v: ActiveTab) { activeTab = v; },
    get pods() { return pods; },
    get services() { return services; },
    get deployments() { return deployments; },
    get replicasets() { return replicasets; },
    get workloadActioning() { return workloadActioning; },
    get podsLoaded() { return podsLoaded; },
    get servicesLoaded() { return servicesLoaded; },
    get deploymentsLoaded() { return deploymentsLoaded; },
    loadPods,
    loadServices,
    loadDeployments,
    removePod,
    removeSvc,
    rolloutRestartDeployment,
    scaleDeploymentTo,
    fetchPodLog,
  };
}

export type K3sClusterDetailController = ReturnType<typeof createK3sClusterDetailController>;

const K3S_CLUSTER_DETAIL_KEY = Symbol('k3s-cluster-detail');

export function provideK3sClusterDetailController(store: K3sClusterDetailController) {
  setContext(K3S_CLUSTER_DETAIL_KEY, store);
}

export function useK3sClusterDetailController(): K3sClusterDetailController {
  const store = getContext<K3sClusterDetailController | undefined>(K3S_CLUSTER_DETAIL_KEY);
  if (!store) throw new Error('useK3sClusterDetailController must be called within K3sClusterDetailPanel');
  return store;
}
