import { onDestroy } from 'svelte';
import { auth, projectSwitching, logoutInProgress } from '$lib/stores/auth';
import { projectNames, type AdminProjectName } from '$lib/stores/projectNames';
import { domainsApi, type AdminDomain } from '$lib/api/domains';
import { t as td } from '$lib/i18n/ns/domain-admin';
import { api, ApiError } from '$lib/api/client';
import type { Quotas, QuotaUpdateResponse } from '$lib/types/quotas';
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
  loadProjects: () => Promise<void>;
  loadQuotas: (opts?: { preserveStatus?: boolean; background?: boolean }) => Promise<boolean>;
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
  let quotaGeneration = 0;
  let saveGeneration = 0;
  let directoryGeneration = 0;
  let domainsGeneration = 0;
  let authorityEpoch = 0;
  let disposed = false;


  const tok = opts.token;
  const pid = opts.projectId;

  function clearProjectResults() {
    ++scopeRevision;
    ++quotaGeneration; ++saveGeneration;
    quotas = null; quotaLoading = false;
    saving = false; savingSection = null;
    saveError = ''; saveSuccess = ''; sectionErrors = {}; sectionSuccesses = {};
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
    loadProjects,
    loadQuotas,
    saveSectionQuotas,
  };
}
