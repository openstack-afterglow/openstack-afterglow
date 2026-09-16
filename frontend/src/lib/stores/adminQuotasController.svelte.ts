export interface FlavorReconcileOperation {
  flavor_id: string;
  flavor_name: string;
  gpu_demand: Record<string, number>;
  desired_access: boolean;
  current_access: boolean;
  action: 'add' | 'remove' | 'none';
  applied?: boolean;
}

export interface FlavorReconcileResponse {
  project_id: string;
  applied: boolean;
  status: 'ok' | 'partial';
  operations: FlavorReconcileOperation[];
  errors: Array<{ flavor_id?: string; flavor_name?: string; code: string; action?: string }>;
  enforcement_scope: string;
}

import { api, ApiError } from '$lib/api/client';
import type { Project, Quotas, GpuQuota, GpuDefaultQuota } from '$lib/types/quotas';

export interface AdminQuotasControllerOpts {
  token: () => string | undefined;
  projectId: () => string | undefined;
}

export function createAdminQuotasController(opts: AdminQuotasControllerOpts) {
  let projects = $state<Project[]>([]);
  let selectedProjectId = $state('');
  let selectedProjectName = $state('');
  let projectSearch = $state('');
  let quotas = $state<Quotas | null>(null);
  let loading = $state(true);
  let refreshing = $state(false);
  let quotaLoading = $state(false);
  let saving = $state(false);
  let saveError = $state('');
  let saveSuccess = $state('');
  let gpuAliases = $state<string[]>([]);
  let gpuQuotas = $state<GpuQuota[]>([]);
  let gpuDefaults = $state<GpuDefaultQuota[]>([]);
  let gpuQuotaLoading = $state(false);
  let gpuQuotaError = $state('');
  let gpuDefaultLoading = $state(false);
  let gpuDefaultError = $state('');
  let gpuDefaultSuccess = $state('');
  let gpuQuotaGeneration = 0;
  let quotaGeneration = 0;
  let reconcilePreview = $state<FlavorReconcileResponse | null>(null);
  let reconcileLoading = $state(false);

  const gpuQuotaMap = $derived(Object.fromEntries(gpuQuotas.map(q => [q.gpu_type, q])));
  const gpuDefaultMap = $derived(Object.fromEntries(gpuDefaults.map(q => [q.gpu_type, q.limit])));
  const allGpuTypes = $derived(
    [...new Set([...gpuAliases, ...gpuDefaults.map(d => d.gpu_type), ...gpuQuotas.map(q => q.gpu_type)])].sort()
  );
  const gpuQuotaRows = $derived(
    allGpuTypes.map((gpuType): GpuQuota => {
      const current = gpuQuotaMap[gpuType];
      if (current) return current;
      const limit = gpuDefaultMap[gpuType] ?? 0;
      return {
        gpu_type: gpuType,
        limit,
        in_use: 0,
        available: limit === -1 ? -1 : limit,
      };
    }),
  );

  const tok = opts.token;
  const pid = opts.projectId;

  async function loadProjects() {
    if (projects.length === 0) loading = true;
    else refreshing = true;
    try {
      const res = await api.get<{ id: string; name: string }[]>('/api/v1/admin/projects/names', tok(), pid());
      projects = res || [];
    } catch { projects = []; }
    finally { loading = false; refreshing = false; }
  }

  async function loadGpuAliases() {
    try {
      const res = await api.get<{ aliases: string[] }>('/api/v1/admin/gpu-aliases', tok(), pid());
      gpuAliases = res.aliases ?? [];
    } catch {
      gpuAliases = [];
    }
  }

  async function loadGpuDefaults(opts?: { background?: boolean }) {
    if (!opts?.background) { gpuDefaultLoading = true; }
    gpuDefaultError = '';
    try {
      gpuDefaults = await api.get<GpuDefaultQuota[]>('/api/v1/admin/gpu-quotas/defaults', tok(), pid());
    } catch (e) {
      gpuDefaultError = e instanceof ApiError ? e.message : '기본 GPU quota 조회 실패';
      gpuDefaults = [];
    } finally { if (!opts?.background) gpuDefaultLoading = false; }
  }

  async function setGpuDefault(gpuType: string, limit: number) {
    gpuDefaultError = ''; gpuDefaultSuccess = '';
    try {
      await api.put('/api/v1/admin/gpu-quotas/defaults', { gpu_type: gpuType, limit }, tok(), pid());
      gpuDefaultSuccess = '기본 GPU quota 저장됨';
      await loadGpuDefaults({ background: true });
      if (selectedProjectId) await loadGpuQuotas({ background: true });
    } catch (e) {
      gpuDefaultError = e instanceof ApiError ? e.message : '기본 GPU quota 설정 실패';
    }
  }

  async function loadQuotas() {
    const targetProjectId = selectedProjectId;
    const requestToken = tok();
    const requestProjectId = pid();
    const generation = ++quotaGeneration;
    const owns = () => generation === quotaGeneration
      && selectedProjectId === targetProjectId
      && tok() === requestToken
      && pid() === requestProjectId;
    if (!targetProjectId) { quotas = null; quotaLoading = false; return; }
    quotaLoading = true; saveError = ''; saveSuccess = '';
    const quotaPromise = api.get<Quotas>(`/api/v1/admin/quotas/${targetProjectId}`, requestToken, requestProjectId);
    const gpuPromise = loadGpuQuotas();
    try {
      const loadedQuotas = await quotaPromise;
      if (owns()) quotas = loadedQuotas;
    } catch {
      if (owns()) quotas = null;
    } finally {
      if (owns()) quotaLoading = false;
    }
    await gpuPromise;
    void loadReconcilePreview();
  }

  async function loadGpuQuotas(opts?: { background?: boolean }) {
    const targetProjectId = selectedProjectId;
    const requestToken = tok();
    const requestProjectId = pid();
    const generation = ++gpuQuotaGeneration;
    const owns = () => generation === gpuQuotaGeneration
      && selectedProjectId === targetProjectId
      && tok() === requestToken
      && pid() === requestProjectId;
    if (!targetProjectId) { gpuQuotas = []; gpuQuotaLoading = false; return; }
    if (!opts?.background) { gpuQuotaLoading = true; }
    gpuQuotaError = '';
    try {
      const loaded = await api.get<GpuQuota[]>(`/api/v1/admin/gpu-quotas/${targetProjectId}`, requestToken, requestProjectId);
      if (owns()) gpuQuotas = loaded;
    } catch (e) {
      if (!owns()) return;
      gpuQuotaError = e instanceof ApiError ? e.message : 'GPU quota 조회 실패';
      gpuQuotas = [];
    } finally {
      if (owns()) gpuQuotaLoading = false;
    }
    void loadReconcilePreview();
  }

  async function setGpuQuota(gpuType: string, limit: number) {
    if (!selectedProjectId) return;
    gpuQuotaError = '';
    try {
      await api.put(`/api/v1/admin/gpu-quotas/${selectedProjectId}`, { gpu_type: gpuType, limit }, tok(), pid());
      await loadGpuQuotas({ background: true });
    } catch (e) {
      gpuQuotaError = e instanceof ApiError ? e.message : 'GPU quota 설정 실패';
    }
  }

  async function deleteGpuQuota(gpuType: string) {
    if (!selectedProjectId) return;
    try {
      await api.delete(`/api/v1/admin/gpu-quotas/${selectedProjectId}/${encodeURIComponent(gpuType)}`, tok(), pid());
      await loadGpuQuotas({ background: true });
    } catch (e) {
      gpuQuotaError = e instanceof ApiError ? e.message : 'GPU quota 삭제 실패';
    }
  }

  async function loadReconcilePreview(gpuLimits?: Record<string, number>) {
    const targetProjectId = selectedProjectId;
    if (!targetProjectId) {
      reconcilePreview = null;
      return;
    }
    reconcileLoading = true;
    try {
      const res = await api.post<FlavorReconcileResponse>(
        '/api/v1/admin/flavors/access-reconcile',
        { project_id: targetProjectId, apply: false, gpu_limits: gpuLimits },
        tok(),
        pid(),
      );
      if (selectedProjectId === targetProjectId) reconcilePreview = res;
    } catch {
      if (selectedProjectId === targetProjectId) reconcilePreview = null;
    } finally {
      if (selectedProjectId === targetProjectId) reconcileLoading = false;
    }
  }

  async function saveQuotas(form: { instances: number; cores: number; ram: number; volumes: number; gigabytes: number }) {
    if (!selectedProjectId) return;
    saving = true; saveError = ''; saveSuccess = '';
    try {
      await api.put(`/api/v1/admin/quotas/${selectedProjectId}`, form, tok(), pid());
      saveSuccess = '저장되었습니다';
      await loadQuotas();
    } catch (e) { saveError = e instanceof ApiError ? e.message : '저장 실패'; }
    finally { saving = false; }
  }

  return {
    get projects() { return projects; },
    get selectedProjectId() { return selectedProjectId; },
    set selectedProjectId(v: string) { selectedProjectId = v; },
    get selectedProjectName() { return selectedProjectName; },
    set selectedProjectName(v: string) { selectedProjectName = v; },
    get projectSearch() { return projectSearch; },
    set projectSearch(v: string) { projectSearch = v; },
    get quotas() { return quotas; },
    get loading() { return loading; },
    get refreshing() { return refreshing; },
    get quotaLoading() { return quotaLoading; },
    get saving() { return saving; },
    get saveError() { return saveError; },
    get saveSuccess() { return saveSuccess; },
    get gpuQuotaMap() { return gpuQuotaMap; },
    get gpuDefaultMap() { return gpuDefaultMap; },
    get allGpuTypes() { return allGpuTypes; },
    get gpuQuotaRows() { return gpuQuotaRows; },
    get gpuQuotaLoading() { return gpuQuotaLoading; },
    get gpuQuotaError() { return gpuQuotaError; },
    get gpuDefaultLoading() { return gpuDefaultLoading; },
    get gpuDefaultError() { return gpuDefaultError; },
    get gpuDefaultSuccess() { return gpuDefaultSuccess; },
    get gpuQuotas() { return gpuQuotas; },
    get reconcilePreview() { return reconcilePreview; },
    get reconcileLoading() { return reconcileLoading; },
    loadReconcilePreview,
    loadProjects,
    loadGpuAliases,
    loadGpuDefaults,
    loadQuotas,
    loadGpuQuotas,
    setGpuDefault,
    setGpuQuota,
    deleteGpuQuota,
    saveQuotas,
  };
}
