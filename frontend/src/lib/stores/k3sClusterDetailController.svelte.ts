import { getContext, setContext } from 'svelte';
import { api, ApiError, fetchWithAuth } from '$lib/api/client';
import { downloadBlobAs } from '$lib/utils/downloadBlob';
import { streamK3sProgress } from '$lib/api/k3sSseStream';
import { maybeMockHead, symbolNoMatch } from '$lib/mockup/transport';
import { toast } from '$lib/stores/toast';
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
  adminMode: () => boolean;
  onClose?: () => void;
}

export function createK3sClusterDetailController(opts: K3sClusterDetailControllerOpts) {
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
  let selectedNamespace = $state('default');
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

  async function loadCluster() {
    const id = opts.clusterId();
    if (!id) return;
    try {
      cluster = await api.get<K3sCluster>(`${apiBase}/${id}`, opts.token(), opts.projectId());
      if (scalingTarget === null && cluster) scalingTarget = cluster.agent_count;
      error = '';
    } catch (e) {
      error = e instanceof ApiError ? `조회 실패 (${e.status})` : '서버 오류';
    } finally {
      loading = false;
    }
  }

  async function loadHealth() {
    const id = opts.clusterId();
    if (!id || !cluster || cluster.status !== 'ACTIVE') return;
    try {
      health = await api.get<K3sClusterHealth>(`/api/v1/k3s/clusters/${id}/health`, opts.token(), opts.projectId());
    } catch {
      // 404는 아직 헬스 데이터 없음 — 무시
    }
  }

  async function triggerHealthCheck() {
    const id = opts.clusterId();
    if (!id || checkingHealth) return;
    checkingHealth = true;
    try {
      health = await api.post<K3sClusterHealth>(`/api/v1/k3s/clusters/${id}/health/check`, {}, opts.token(), opts.projectId());
    } catch {
      // rate limit(429) 등 — 무시
    } finally {
      checkingHealth = false;
    }
  }

  async function checkKubeconfig() {
    const id = opts.clusterId();
    if (!id || !cluster || cluster.status !== 'ACTIVE') return;
    try {
      const path = `${apiBase}/${id}/kubeconfig`;
      const mock = await maybeMockHead(path, opts.token(), opts.projectId());
      if (mock !== symbolNoMatch) {
        kubeconfigAvailable = mock.ok;
        return;
      }
      const res = await fetchWithAuth(path, {
        method: 'HEAD',
      }, opts.token(), opts.projectId());
      kubeconfigAvailable = res.ok;
    } catch {
      kubeconfigAvailable = false;
    }
  }

  async function downloadKubeconfig() {
    const id = opts.clusterId();
    if (!id || !cluster) return;
    try {
      const { blob } = await api.downloadBlob(`${apiBase}/${id}/kubeconfig`, opts.token(), opts.projectId());
      downloadBlobAs(blob, `kubeconfig-${cluster.name}.yaml`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) toast.warning('kubeconfig가 아직 준비되지 않았습니다.');
      else toast.error(`다운로드 실패: ${e instanceof ApiError ? e.message : String(e)}`);
    }
  }

  async function deleteCluster() {
    const c = cluster;
    const id = opts.clusterId();
    if (!c || !(await confirmDialog(`Drover 클러스터 "${c.name}"을 삭제하시겠습니까?`))) return;
    deleting = true;
    deleteProgress = { step: '', pct: 0, msg: '삭제 준비 중...', error: '' };
    try {
      for await (const msg of streamK3sProgress(
        `${apiBase}/${id}/delete-async`,
        { method: 'POST', token: opts.token(), projectId: opts.projectId() },
      )) {
        deleteProgress = { step: msg.step, pct: msg.progress, msg: msg.message, error: msg.error ?? '' };
        if (msg.step === 'completed') {
          opts.onClose?.();
          return;
        }
        if (msg.step === 'failed') {
          deleteProgress = { ...deleteProgress, error: msg.error ?? '알 수 없는 오류' };
          deleting = false;
          return;
        }
      }
    } catch (e) {
      deleteProgress = { step: 'failed', pct: 0, msg: '삭제 실패', error: String(e) };
      deleting = false;
    }
  }

  async function applyScale() {
    const c = cluster;
    const id = opts.clusterId();
    if (scalingTarget === null || !c) return;
    if (scalingTarget === c.agent_vm_ids.length && scalingTarget === c.agent_count) return;
    if (!(await confirmDialog(`에이전트 수를 ${c.agent_vm_ids.length}개에서 ${scalingTarget}개로 변경하시겠습니까?`))) return;
    scaling = true;
    scaleError = '';
    try {
      await api.patch(`${apiBase}/${id}/scale`, { agent_count: scalingTarget }, opts.token(), opts.projectId());
      await loadCluster();
    } catch (e) {
      scaleError = e instanceof ApiError ? e.message : String(e);
    } finally {
      scaling = false;
    }
  }

  function incrementScale() {
    scalingTarget = Math.min(10, (scalingTarget ?? cluster?.agent_count ?? 0) + 1);
  }

  function decrementScale() {
    scalingTarget = Math.max(0, (scalingTarget ?? cluster?.agent_count ?? 0) - 1);
  }

  async function loadNetworks() {
    if (networks.length > 0) return;
    try {
      networks = await api.get<NetworkInfo[]>('/api/v1/networks', opts.token(), opts.projectId());
    } catch {
      networks = [];
    }
  }

  async function loadInterfaces(vmIds: string[]) {
    const id = opts.clusterId();
    if (!id) return;
    await Promise.all(
      vmIds.map(async (vmId) => {
        try {
          const list = await listNodeInterfaces(id, vmId, opts.token(), opts.projectId());
          interfaces = { ...interfaces, [vmId]: list };
        } catch {
          // 개별 노드 실패는 무시
        }
      })
    );
  }

  async function attachInterface(vmId: string, netId: string) {
    const id = opts.clusterId();
    if (!id || interfaceActioning) return;
    interfaceActioning = vmId;
    try {
      await attachNodeInterface(id, vmId, netId, opts.token(), opts.projectId());
      const list = await listNodeInterfaces(id, vmId, opts.token(), opts.projectId());
      interfaces = { ...interfaces, [vmId]: list };
    } finally {
      interfaceActioning = null;
    }
  }

  async function detachInterface(vmId: string, portId: string) {
    const id = opts.clusterId();
    if (!id || interfaceActioning) return;
    interfaceActioning = `${vmId}:${portId}`;
    try {
      await detachNodeInterface(id, vmId, portId, opts.token(), opts.projectId());
      const list = await listNodeInterfaces(id, vmId, opts.token(), opts.projectId());
      interfaces = { ...interfaces, [vmId]: list };
    } finally {
      interfaceActioning = null;
    }
  }

  async function loadNamespaces() {
    const id = opts.clusterId();
    if (!id || namespacesLoaded) return;
    try {
      const ns = await listNamespaces(id, opts.token(), opts.projectId());
      namespaces = ns;
      if (!namespaces.includes(selectedNamespace)) {
        selectedNamespace = namespaces[0] ?? 'default';
      }
      namespacesLoaded = true;
    } catch {
      namespaces = ['default'];
    }
  }

  async function loadConfigMaps() {
    const id = opts.clusterId();
    if (!id) return;
    try {
      configMaps = await listConfigMaps(id, selectedNamespace, opts.token(), opts.projectId());
    } catch {
      configMaps = [];
    }
  }

  async function loadSecrets() {
    const id = opts.clusterId();
    if (!id) return;
    try {
      secrets = await listSecrets(id, selectedNamespace, opts.token(), opts.projectId());
    } catch {
      secrets = [];
    }
  }

  async function saveConfigMap(name: string, data: Record<string, string>, isNew: boolean) {
    const id = opts.clusterId();
    if (!id || cmActioning) return;
    cmActioning = `${selectedNamespace}:${name}`;
    try {
      if (isNew) {
        const cm = await createConfigMap(id, selectedNamespace, { name, data }, opts.token(), opts.projectId());
        configMaps = [...configMaps, cm];
      } else {
        const cm = await updateConfigMap(id, selectedNamespace, name, { data }, opts.token(), opts.projectId());
        configMaps = configMaps.map((c) => (c.name === name ? cm : c));
      }
    } finally {
      cmActioning = null;
    }
  }

  async function deleteCm(name: string) {
    const id = opts.clusterId();
    if (!id || cmActioning) return;
    cmActioning = `${selectedNamespace}:${name}`;
    try {
      await deleteConfigMap(id, selectedNamespace, name, opts.token(), opts.projectId());
      configMaps = configMaps.filter((c) => c.name !== name);
    } finally {
      cmActioning = null;
    }
  }

  async function saveSecret(name: string, type: string, data: Record<string, string>, isNew: boolean) {
    const id = opts.clusterId();
    if (!id || cmActioning) return;
    cmActioning = `${selectedNamespace}:${name}`;
    try {
      if (isNew) {
        const s = await createSecret(id, selectedNamespace, { name, type, data }, opts.token(), opts.projectId());
        secrets = [...secrets, s];
      } else {
        const s = await updateSecret(id, selectedNamespace, name, { type, data }, opts.token(), opts.projectId());
        secrets = secrets.map((x) => (x.name === name ? s : x));
      }
    } finally {
      cmActioning = null;
    }
  }

  async function deleteSecretItem(name: string) {
    const id = opts.clusterId();
    if (!id || cmActioning) return;
    cmActioning = `${selectedNamespace}:${name}`;
    try {
      await deleteSecret(id, selectedNamespace, name, opts.token(), opts.projectId());
      secrets = secrets.filter((s) => s.name !== name);
    } finally {
      cmActioning = null;
    }
  }

  function openShell() { shellOpen = true; }
  function closeShell() { shellOpen = false; }

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
    try {
      pods = await listPods(id, selectedNamespace, opts.token(), opts.projectId());
      podsLoaded = true;
    } catch {
      pods = [];
    }
  }

  async function loadServices() {
    const id = opts.clusterId();
    if (!id) return;
    try {
      services = await listServices(id, selectedNamespace, opts.token(), opts.projectId());
      servicesLoaded = true;
    } catch {
      services = [];
    }
  }

  async function loadDeployments() {
    const id = opts.clusterId();
    if (!id) return;
    try {
      const [deps, rss] = await Promise.all([
        listDeployments(id, selectedNamespace, opts.token(), opts.projectId()),
        listReplicaSets(id, selectedNamespace, opts.token(), opts.projectId()),
      ]);
      deployments = deps;
      replicasets = rss;
      deploymentsLoaded = true;
    } catch {
      deployments = [];
      replicasets = [];
    }
  }

  async function removePod(name: string) {
    const id = opts.clusterId();
    if (!id || workloadActioning) return;
    const confirmed = await confirmDialog(`Pod "${name}"를 삭제하시겠습니까?`);
    if (!confirmed) return;
    workloadActioning = `${selectedNamespace}:pod:${name}`;
    try {
      await deletePod(id, selectedNamespace, name, opts.token(), opts.projectId());
      pods = pods.filter((p) => p.name !== name);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : 'Pod 삭제 실패');
    } finally {
      workloadActioning = null;
    }
  }

  async function removeSvc(name: string) {
    const id = opts.clusterId();
    if (!id || workloadActioning) return;
    const confirmed = await confirmDialog(`Service "${name}"를 삭제하시겠습니까?`);
    if (!confirmed) return;
    workloadActioning = `${selectedNamespace}:svc:${name}`;
    try {
      await deleteService(id, selectedNamespace, name, opts.token(), opts.projectId());
      services = services.filter((s) => s.name !== name);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : 'Service 삭제 실패');
    } finally {
      workloadActioning = null;
    }
  }

  async function rolloutRestartDeployment(name: string) {
    const id = opts.clusterId();
    if (!id || workloadActioning) return;
    workloadActioning = `${selectedNamespace}:deploy:${name}`;
    try {
      const updated = await apiRestartDeployment(id, selectedNamespace, name, opts.token(), opts.projectId());
      deployments = deployments.map((d) => (d.name === name ? updated : d));
      toast.success(`Deployment "${name}" 재시작 요청`);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : 'Deployment 재시작 실패');
    } finally {
      workloadActioning = null;
    }
  }

  async function scaleDeploymentTo(name: string, replicas: number) {
    const id = opts.clusterId();
    if (!id || workloadActioning) return;
    workloadActioning = `${selectedNamespace}:deploy:${name}`;
    try {
      const updated = await apiScaleDeployment(id, selectedNamespace, name, replicas, opts.token(), opts.projectId());
      deployments = deployments.map((d) => (d.name === name ? updated : d));
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : 'Deployment 스케일 실패');
    } finally {
      workloadActioning = null;
    }
  }

  async function fetchPodLog(name: string, opts2: { container?: string; tailLines?: number }) {
    const id = opts.clusterId();
    if (!id) return null;
    try {
      return await getPodLog(id, selectedNamespace, name, opts2, opts.token(), opts.projectId());
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : 'Pod 로그 조회 실패');
      return null;
    }
  }

  function reset() {
    cluster = null;
    health = null;
    loading = true;
    error = '';
    deleteProgress = null;
    deleting = false;
    scalingTarget = null;
    initialCheckDone = false;
    scaleError = '';
    interfaces = {};
    networks = [];
    interfaceActioning = null;
    namespaces = [];
    selectedNamespace = 'default';
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
    viewingInstanceId = id;
  }

  function clearViewingInstance() {
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
