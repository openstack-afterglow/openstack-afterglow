import { onDestroy } from 'svelte';
import { auth, projectSwitching, logoutInProgress } from '$lib/stores/auth';
import { projectNames, type AdminProjectName } from '$lib/stores/projectNames';
import { domainsApi, type AdminDomain } from '$lib/api/domains';
import { t as td } from '$lib/i18n/ns/domain-admin';
import { api, ApiError } from '$lib/api/client';
import type { Quotas, QuotaUpdateResponse, GpuQuota, GpuDefaultQuota } from '$lib/types/quotas';
import { t } from '$lib/i18n/ns/admin-identity';

export interface AdminQuotasControllerOpts {
  token: () => string | undefined;
  projectId: () => string | undefined;
  userId?: () => string | undefined;
}

export interface AdminQuotasController {
  readonly projects: AdminProjectName[];
  readonly domains: AdminDomain[];
  selectedDomainId: string;
  readonly scopeRevision: number;
  readonly domainsLoading: boolean;
  readonly domainsError: string;
  readonly projectsError: string;
  loadDomains: () => Promise<void>;
  selectedProjectId: string;
  readonly quotas: Quotas | null;
  readonly loading: boolean;
  readonly refreshing: boolean;
  readonly quotaLoading: boolean;
  readonly saving: boolean;
  readonly savingSection: string | null;
  readonly saveError: string;
  readonly saveSuccess: string;
  readonly sectionErrors: Record<string, string>;
  readonly sectionSuccesses: Record<string, string>;
  readonly gpuQuotaMap: Record<string, GpuQuota>;
  readonly gpuDefaultMap: Record<string, number>;
  readonly allGpuTypes: string[];
  readonly gpuQuotaRows: GpuQuota[];
  readonly gpuQuotaLoading: boolean;
  readonly gpuQuotaError: string;
  readonly gpuDefaultLoading: boolean;
  readonly gpuDefaultError: string;
  readonly gpuDefaultSuccess: string;
  readonly gpuQuotas: GpuQuota[];
  loadProjects: () => Promise<void>;
  loadGpuAliases: () => Promise<void>;
  loadGpuDefaults: (opts?: { background?: boolean }) => Promise<void>;
  loadQuotas: (opts?: { preserveStatus?: boolean; background?: boolean }) => Promise<boolean>;
  loadGpuQuotas: (opts?: { background?: boolean }) => Promise<void>;
  setGpuDefault: (gpuType: string, limit: number) => Promise<void>;
  setGpuQuota: (gpuType: string, limit: number) => Promise<void>;
  deleteGpuQuota: (gpuType: string) => Promise<void>;
  saveSectionQuotas: (
    section: 'compute' | 'volume' | 'network' | 'file_storage',
    changes: Record<string, number>,
  ) => Promise<{ success: boolean; status?: string; updated?: string[]; errors?: Record<string, string>; refreshed?: boolean; refreshError?: string }>;
}

export function createAdminQuotasController(opts: AdminQuotasControllerOpts): AdminQuotasController {
  let directory = $state<AdminProjectName[]>([]);
  let domains = $state<AdminDomain[]>([]);
  let selectedDomainId = $state('');
  let scopeRevision = $state(0);
  let domainsLoading = $state(false);
  let domainsError = $state('');
  let projectsError = $state('');
  const projects = $derived(selectedDomainId ? directory.filter(project => project.domain_id === selectedDomainId) : directory);
  let selectedProjectId = $state('');
  let quotas = $state<Quotas | null>(null);
  let loading = $state(true);
  let refreshing = $state(false);
  let quotaLoading = $state(false);
  let saving = $state(false);
  let savingSection = $state<string | null>(null);
  let saveError = $state('');
  let saveSuccess = $state('');
  let sectionErrors = $state<Record<string, string>>({});
  let sectionSuccesses = $state<Record<string, string>>({});
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
  let saveGeneration = 0;
  let directoryGeneration = 0;
  let domainsGeneration = 0;
  let defaultsGeneration = 0;
  let aliasesGeneration = 0;
  let authorityEpoch = 0;
  let disposed = false;

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

  function clearProjectResults() {
    ++scopeRevision;
    ++quotaGeneration; ++gpuQuotaGeneration; ++saveGeneration;
    quotas = null; quotaLoading = false;
    saving = false; savingSection = null;
    saveError = ''; saveSuccess = ''; sectionErrors = {}; sectionSuccesses = {};
    gpuQuotas = []; gpuQuotaLoading = false; gpuQuotaError = '';
    gpuDefaultSuccess = '';
  }

  function captureContext(projectScoped = true) {
    const token = tok(), projectId = pid(), epoch = authorityEpoch;
    const revision = scopeRevision;
    return {
      token, projectId,
      owns: () => !disposed && epoch === authorityEpoch && token === tok() && projectId === pid()
        && (!projectScoped || revision === scopeRevision),
    };
  }

  let authority: string | undefined;
  const unsubscribeAuth = auth.subscribe(state => {
    const next = JSON.stringify([!!state.token, state.sessionId, state.userId, state.identityDomainId, state.domainId, state.projectId, state.isSystemAdmin]);
    if (authority === next) return;
    const initial = authority === undefined;
    authority = next;
    if (!initial) resetAuthority();
  });
  const unsubscribeSwitching = projectSwitching.subscribe(active => { if (active) resetAuthority(); });
  const unsubscribeLogout = logoutInProgress.subscribe(active => { if (active) resetAuthority(); });
  function resetAuthority() {
    ++authorityEpoch;
    clearProjectResults();
    directory = []; domains = []; selectedDomainId = ''; selectedProjectId = '';
    gpuAliases = []; gpuDefaults = []; gpuDefaultError = ''; gpuDefaultLoading = false;
    projectsError = ''; domainsError = ''; domainsLoading = false; loading = false; refreshing = false;
  }
  onDestroy(() => {
    disposed = true; ++authorityEpoch;
    unsubscribeAuth(); unsubscribeSwitching(); unsubscribeLogout();
  });

  async function loadDomains() {
    const context = captureContext(false), generation = ++domainsGeneration;
    const owns = () => context.owns() && generation === domainsGeneration;
    domainsLoading = true; domainsError = '';
    try {
      const response = await domainsApi.list(context);
      if (owns()) domains = response.items;
    } catch (error) {
      if (owns()) { domains = []; domainsError = error instanceof ApiError ? error.message : td('scope.loadFailed'); }
    } finally { if (owns()) domainsLoading = false; }
  }

  async function loadProjects() {
    const context = captureContext(false), generation = ++directoryGeneration;
    const owns = () => context.owns() && generation === directoryGeneration;
    if (directory.length === 0) loading = true;
    else refreshing = true;
    projectsError = '';
    try {
      const result = await projectNames.loadMetadata(context.token, context.projectId, opts.userId?.());
      if (!owns()) return;
      directory = [...result.projects];
      if (result.failed) projectsError = t('quotaPage.unavailable');
      if (selectedProjectId && !projects.some(project => project.id === selectedProjectId)) {
        selectedProjectId = ''; clearProjectResults();
      }
    } catch {
      if (owns()) { directory = []; selectedProjectId = ''; clearProjectResults(); projectsError = t('quotaPage.unavailable'); }
    } finally { if (owns()) { loading = false; refreshing = false; } }
  }

  async function loadGpuAliases() {
    const context = captureContext(false), generation = ++aliasesGeneration;
    const owns = () => context.owns() && generation === aliasesGeneration;
    try {
      const res = await api.get<{ aliases: string[] }>('/api/v1/admin/gpu-aliases', context.token, context.projectId);
      if (owns()) gpuAliases = res.aliases ?? [];
    } catch {
      if (owns()) gpuAliases = [];
    }
  }

  async function loadGpuDefaults(opts?: { background?: boolean }) {
    const context = captureContext(false), generation = ++defaultsGeneration;
    const owns = () => context.owns() && generation === defaultsGeneration;
    if (!opts?.background) { gpuDefaultLoading = true; }
    gpuDefaultError = '';
    try {
      const loaded = await api.get<GpuDefaultQuota[]>('/api/v1/admin/gpu-quotas/defaults', context.token, context.projectId);
      if (owns()) gpuDefaults = loaded;
    } catch (e) {
      if (!owns()) return;
      gpuDefaultError = e instanceof ApiError ? e.message : t('quotaController.defaultsLoadFailed');
      gpuDefaults = [];
    } finally { if (owns()) gpuDefaultLoading = false; }
  }

  async function setGpuDefault(gpuType: string, limit: number) {
    const context = captureContext(false), projectContext = captureContext();
    gpuDefaultError = ''; gpuDefaultSuccess = '';
    try {
      await api.put('/api/v1/admin/gpu-quotas/defaults', { gpu_type: gpuType, limit }, context.token, context.projectId);
      if (!context.owns()) return;
      gpuDefaultSuccess = t('quotaController.defaultsSaved');
      await loadGpuDefaults({ background: true });
      if (projectContext.owns() && selectedProjectId) await loadGpuQuotas({ background: true });
    } catch (e) {
      if (context.owns()) gpuDefaultError = e instanceof ApiError ? e.message : t('quotaController.defaultsSetFailed');
    }
  }

  async function loadQuotas(opts?: { preserveStatus?: boolean; background?: boolean }): Promise<boolean> {
    const targetProjectId = selectedProjectId;
    const context = captureContext();
    const requestToken = tok();
    const requestProjectId = pid();
    const generation = ++quotaGeneration;
    const owns = () => generation === quotaGeneration && context.owns() && selectedProjectId === targetProjectId;
    if (!targetProjectId) { quotas = null; quotaLoading = false; return false; }
    if (!opts?.background) quotaLoading = true;
    if (!opts?.preserveStatus) {
      saveError = '';
      saveSuccess = '';
      sectionErrors = {};
      sectionSuccesses = {};
    }
    const quotaPromise = api.get<Quotas>(`/api/v1/admin/quotas/${targetProjectId}`, requestToken, requestProjectId);
    if (!opts?.background) void loadGpuQuotas();
    try {
      const loadedQuotas = await quotaPromise;
      if (!owns()) return false;
      quotas = loadedQuotas;
      return true;
    } catch {
      if (owns() && !opts?.background) quotas = null;
      return false;
    } finally {
      if (owns()) quotaLoading = false;
    }
  }

  async function loadGpuQuotas(opts?: { background?: boolean }) {
    const targetProjectId = selectedProjectId;
    const context = captureContext();
    const requestToken = tok();
    const requestProjectId = pid();
    const generation = ++gpuQuotaGeneration;
    const owns = () => generation === gpuQuotaGeneration && context.owns() && selectedProjectId === targetProjectId;
    if (!targetProjectId) { gpuQuotas = []; gpuQuotaLoading = false; return; }
    if (!opts?.background) { gpuQuotaLoading = true; }
    gpuQuotaError = '';
    try {
      const loaded = await api.get<GpuQuota[]>(`/api/v1/admin/gpu-quotas/${targetProjectId}`, requestToken, requestProjectId);
      if (owns()) gpuQuotas = loaded;
    } catch (e) {
      if (!owns()) return;
      gpuQuotaError = e instanceof ApiError ? e.message : t('quotaController.gpuLoadFailed');
      gpuQuotas = [];
    } finally {
      if (owns()) gpuQuotaLoading = false;
    }
  }

  async function setGpuQuota(gpuType: string, limit: number) {
    const targetProjectId = selectedProjectId, context = captureContext();
    if (!targetProjectId) return;
    gpuQuotaError = '';
    try {
      await api.put(`/api/v1/admin/gpu-quotas/${targetProjectId}`, { gpu_type: gpuType, limit }, context.token, context.projectId);
      if (context.owns()) await loadGpuQuotas({ background: true });
    } catch (e) {
      if (context.owns()) gpuQuotaError = e instanceof ApiError ? e.message : t('quotaController.gpuSetFailed');
    }
  }

  async function deleteGpuQuota(gpuType: string) {
    const targetProjectId = selectedProjectId, context = captureContext();
    if (!targetProjectId) return;
    try {
      await api.delete(`/api/v1/admin/gpu-quotas/${targetProjectId}/${encodeURIComponent(gpuType)}`, context.token, context.projectId);
      if (context.owns()) await loadGpuQuotas({ background: true });
    } catch (e) {
      if (context.owns()) gpuQuotaError = e instanceof ApiError ? e.message : t('quotaController.gpuDeleteFailed');
    }
  }

  async function saveSectionQuotas(
    section: 'compute' | 'volume' | 'network' | 'file_storage',
    changes: Record<string, number>,
  ): Promise<{ success: boolean; status?: string; updated?: string[]; errors?: Record<string, string>; refreshed?: boolean; refreshError?: string }> {
    const targetProjectId = selectedProjectId;
    const context = captureContext();
    const requestToken = tok();
    const requestProjectId = pid();
    const generation = quotaGeneration;
    const saveRequest = ++saveGeneration;
    const validContext = () => saveRequest === saveGeneration && context.owns() && selectedProjectId === targetProjectId;
    const owns = () => generation === quotaGeneration && validContext();

    if (!targetProjectId || !owns()) {
      return { success: false };
    }

    if (Object.keys(changes).length === 0) {
      return { success: false };
    }

    const payload = changes;

    saving = true;
    savingSection = section;
    const nextErrors = { ...sectionErrors };
    delete nextErrors[section];
    sectionErrors = nextErrors;
    const nextSuccesses = { ...sectionSuccesses };
    delete nextSuccesses[section];
    sectionSuccesses = nextSuccesses;
    saveError = '';
    saveSuccess = '';

    try {
      const res = await api.put<QuotaUpdateResponse>(
        `/api/v1/admin/quotas/${targetProjectId}`,
        payload,
        requestToken,
        requestProjectId,
      );

      if (!owns()) {
        return { success: false };
      }

      const sectionErr = res.errors?.[section];
      if (res.updated?.includes(section) && !sectionErr) {
        const refreshed = await loadQuotas({ preserveStatus: true, background: true });
        if (!validContext()) return { ...res, success: false };
        if (refreshed) {
          sectionSuccesses = { ...sectionSuccesses, [section]: t('quotaController.saved') };
          saveSuccess = t('quotaController.saved');
          return { ...res, success: true, refreshed: true };
        }
        const refreshError = t('quotaController.refreshFailed');
        sectionErrors = { ...sectionErrors, [section]: refreshError };
        saveError = refreshError;
        return { ...res, success: true, refreshed: false, refreshError };
      }
      const errMsg = sectionErr || Object.values(res.errors ?? {}).join(', ') || t('quotaController.partialSaveFailed');
      sectionErrors = { ...sectionErrors, [section]: errMsg };
      saveError = errMsg;
      return { ...res, success: false };
    } catch (e) {
      if (validContext()) {
        const errMsg = e instanceof ApiError ? e.message : t('quotaController.saveFailed');
        sectionErrors = { ...sectionErrors, [section]: errMsg };
        saveError = errMsg;
      }
      return { success: false };
    } finally {
      if (validContext()) {
        saving = false;
        savingSection = null;
      }
    }
  }


  return {
    get projects() { return projects; },
    get domains() { return domains; },
    get domainsLoading() { return domainsLoading; },
    get domainsError() { return domainsError; },
    get projectsError() { return projectsError; },
    get scopeRevision() { return scopeRevision; },
    get selectedDomainId() { return selectedDomainId; },
    set selectedDomainId(value: string) {
      if (value === selectedDomainId) return;
      selectedDomainId = value;
      clearProjectResults();
      if (!projects.some(project => project.id === selectedProjectId)) {
        selectedProjectId = '';
      }
    },
    loadDomains,
    get selectedProjectId() { return selectedProjectId; },
    set selectedProjectId(v: string) {
      const next = selectedDomainId && !projects.some(project => project.id === v) ? '' : v;
      if (selectedProjectId !== next) {
        selectedProjectId = next;
        clearProjectResults();
        quotaLoading = !!next;
        gpuQuotaLoading = !!next;
      }
    },
    get quotas() { return quotas; },
    get loading() { return loading; },
    get refreshing() { return refreshing; },
    get quotaLoading() { return quotaLoading; },
    get saving() { return saving; },
    get savingSection() { return savingSection; },
    get saveError() { return saveError; },
    get saveSuccess() { return saveSuccess; },
    get sectionErrors() { return sectionErrors; },
    get sectionSuccesses() { return sectionSuccesses; },
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
    loadProjects,
    loadGpuAliases,
    loadGpuDefaults,
    loadQuotas,
    loadGpuQuotas,
    setGpuDefault,
    setGpuQuota,
    deleteGpuQuota,
    saveSectionQuotas,
  };
}
