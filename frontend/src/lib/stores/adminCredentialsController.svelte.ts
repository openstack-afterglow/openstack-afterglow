import { credentialRequest } from '$lib/api/adminCredentials';
import { ApiError } from '$lib/api/errors';
import { t } from '$lib/i18n/ns/admin-identity';
import { t as dt } from '$lib/i18n/ns/domain-admin';
import type {
  ApplicationCredential, ApplicationCredentialIssued, ApplicationCredentialInput,
  UserCredential, UserCredentialDetail, UserCredentialInput, CredentialAuthority,
  CredentialCreationContext, CredentialUser,
} from '$lib/types/adminCredential';

export function createAdminCredentialsController(kind: 'application' | 'user', initialDomainId: string) {
  let domainId = $state(initialDomainId);
  let authority = $state<CredentialAuthority>({ admin: false, ready: false });
  let deniedToken: string | undefined;
  let epoch = 0, listTicket = 0, modalTicket = 0, directoryTicket = 0;
  let disposed = $state(false);
  let items = $state<(ApplicationCredential | UserCredential)[]>([]);
  let users = $state<CredentialUser[]>([]);
  let directoryLoading = $state(false), directoryError = $state('');
  let selectedUser = $state('');
  let loading = $state(false), error = $state(''), busy = $state(false), modalError = $state('');
  let mode = $state<'create' | 'detail' | 'edit' | 'delete' | 'issued' | null>(null);
  let detail = $state<ApplicationCredential | UserCredentialDetail | null>(null);
  let issued = $state<ApplicationCredentialIssued | null>(null);
  let context = $state<CredentialCreationContext | null>(null);
  let draft = $state({ name: '', description: '', role_ids: [] as string[], expires_at: '', user_id: '', project_id: '', type: '', blob: '' });
  const base = `/api/v1/admin/${kind === 'application' ? 'application' : 'user'}-credentials`;
  const allowed = () => !disposed && !!domainId.trim() && authority.admin && authority.ready && !!authority.token && !!authority.userId && !!authority.projectId;
  const query = (userId = selectedUser) => userId ? `?user_id=${encodeURIComponent(userId)}` : '';
  const capture = () => { const e = epoch, a = { ...authority }, d = domainId; return { a, d, owns: () => allowed() && e === epoch && d === domainId }; };
  const canCreate = () => allowed() && !directoryLoading && !directoryError && (kind === 'user' || (selectedUser === authority.userId && users.some(user => user.id === authority.userId)));
  function assertScope(resource: { domain_id: string }) {
    if (resource.domain_id !== domainId) throw new ApiError(403, 'credential_scope_denied', 'credential_scope_denied');
  }
  const failure = (e: unknown) => {
    const code = e instanceof ApiError ? e.code : undefined;
    if (code === 'credential_native_denied') return t('credentials.denied');
    if (code === 'credential_admin_denied') {
      deniedToken = authority.token;
      setAuthority({ ...authority, admin: false });
      return t('credentials.denied');
    }
    if (code === 'credential_scope_denied') return t('credentials.scopeDenied');
    if (code === 'credential_not_found') return t('credentials.notFound');
    if (code === 'credential_conflict') return t('credentials.conflict');
    if (code === 'credential_invalid_input' || code === 'credential_native_invalid') return t('credentials.invalid');
    if (code === 'credential_rollback_failed') return dt('credentials.rollbackFailed');
    return t('credentials.unavailable');
  };

  function close() {
    ++modalTicket;
    mode = null; detail = null; issued = null; context = null; busy = false; modalError = '';
    draft = { name: '', description: '', role_ids: [], expires_at: '', user_id: '', project_id: '', type: '', blob: '' };
  }
  function reset() {
    ++epoch; ++listTicket; ++directoryTicket; close();
    items = []; users = []; selectedUser = ''; error = ''; directoryError = ''; loading = false; directoryLoading = false;
    if (allowed()) { void load(); void loadUsers(); }
  }
  function setScope(next: string) {
    if (next === domainId) return;
    domainId = next; reset();
  }
  function setAuthority(next: CredentialAuthority) {
    if (next.token && next.token === deniedToken) next = { ...next, admin: false };
    if (['token', 'userId', 'projectId', 'admin', 'ready'].every(key => next[key as keyof CredentialAuthority] === authority[key as keyof CredentialAuthority])) return;
    authority = { ...next }; reset();
  }
  async function loadUsers() {
    if (!allowed()) return;
    const { a, d, owns } = capture(), ticket = ++directoryTicket;
    directoryLoading = true; directoryError = ''; users = [];
    try {
      const all: CredentialUser[] = [], seen = new Set<string>(), markers = new Set<string>();
      let marker: string | null = null;
      do {
        const page: { items: CredentialUser[]; next_marker: string | null } = await credentialRequest(`/api/v1/admin/users?limit=100${marker ? `&marker=${encodeURIComponent(marker)}` : ''}`, d, a);
        if (!owns() || ticket !== directoryTicket) return;
        for (const user of page.items) {
          assertScope(user);
          if (!seen.has(user.id)) { seen.add(user.id); all.push(user); }
        }
        if (page.next_marker && (markers.has(page.next_marker) || !page.items.length)) throw new Error('Directory pagination stalled');
        if (page.next_marker) markers.add(page.next_marker);
        marker = page.next_marker;
      } while (marker);
      users = all;
      if (selectedUser && !all.some(user => user.id === selectedUser)) {
        ++listTicket; selectedUser = ''; close(); items = []; loading = false; error = '';
        if (kind === 'user') void load();
      }
      if (kind === 'application' && !selectedUser && all.some(user => user.id === a.userId)) {
        selectedUser = a.userId!;
        void load();
      }
    } catch (e) { if (owns() && ticket === directoryTicket) directoryError = failure(e); }
    finally { if (owns() && ticket === directoryTicket) directoryLoading = false; }
  }
  async function selectUser(id: string) {
    if (id && !users.some(user => user.id === id)) return;
    ++listTicket; selectedUser = id; close(); items = []; loading = false; error = ''; await load();
  }
  async function load() {
    if (!allowed() || (kind === 'application' && !selectedUser)) return;
    const { a, d, owns } = capture(), ticket = ++listTicket;
    loading = true; error = '';
    try {
      const result = await credentialRequest<{ items: (ApplicationCredential | UserCredential)[] }>(base + query(), d, a);
      if (!owns() || ticket !== listTicket) return;
      for (const item of result.items) {
        assertScope(item);
        if (selectedUser && item.user_id !== selectedUser) throw new ApiError(403, 'credential_scope_denied', 'credential_scope_denied');
      }
      items = result.items;
    } catch (e) { if (owns() && ticket === listTicket) { items = []; error = failure(e); } }
    finally { if (owns() && ticket === listTicket) loading = false; }
  }
  async function open(next: 'create' | 'detail' | 'delete', item?: ApplicationCredential | UserCredential) {
    if (!allowed() || (next === 'create' && !canCreate()) || (next !== 'create' && !item)) return;
    if (item && item.domain_id !== domainId) { error = t('credentials.scopeDenied'); return; }
    close(); mode = next; detail = item ?? null;
    draft.user_id = selectedUser;
    if (next === 'delete') return;
    const { a, d, owns } = capture(), ticket = modalTicket;
    busy = true;
    try {
      if (next === 'create' && kind === 'application') {
        const result = await credentialRequest<CredentialCreationContext>(`${base}/context`, d, a);
        if (!owns() || ticket !== modalTicket) return;
        assertScope(result);
        if (result.user_id !== a.userId || result.project_id !== a.projectId) throw new ApiError(403, 'credential_scope_denied', 'credential_scope_denied');
        context = result;
      }
      else if (next === 'detail' && item) {
        const result = await credentialRequest<ApplicationCredential | UserCredentialDetail>(`${base}/${encodeURIComponent(item.id)}${kind === 'application' ? query(item.user_id) : ''}`, d, a);
        if (!owns() || ticket !== modalTicket) return;
        assertScope(result);
        if (result.id !== item.id || result.user_id !== item.user_id) throw new ApiError(403, 'credential_scope_denied', 'credential_scope_denied');
        detail = result;
      }
    } catch (e) { if (owns() && ticket === modalTicket) modalError = failure(e); }
    finally { if (owns() && ticket === modalTicket) busy = false; }
  }
  async function reveal(edit = false) {
    if (!allowed() || kind !== 'user' || !detail || busy) return;
    const { a, d, owns } = capture(), ticket = ++modalTicket, id = detail.id, userId = detail.user_id, projectId = detail.project_id;
    busy = true; modalError = '';
    try {
      const result = await credentialRequest<UserCredentialDetail>(`${base}/${encodeURIComponent(id)}?sensitive=true`, d, a);
      if (!owns() || ticket !== modalTicket) return;
      assertScope(result);
      if (result.id !== id || result.user_id !== userId || result.project_id !== projectId) throw new ApiError(403, 'credential_scope_denied', 'credential_scope_denied');
      detail = result;
      if (edit) {
        mode = 'edit'; draft.user_id = result.user_id; draft.project_id = result.project_id ?? ''; draft.type = result.type; draft.blob = result.blob ?? '';
      }
    } catch (e) { if (owns() && ticket === modalTicket) modalError = failure(e); }
    finally { if (owns() && ticket === modalTicket) busy = false; }
  }
  async function submit() {
    if (!allowed() || busy || (mode !== 'create' && mode !== 'edit' && mode !== 'delete')) return;
    if (kind === 'application' && mode === 'edit') return;
    if ((mode === 'edit' || mode === 'delete') && !detail) return;
    if (mode === 'create' && !canCreate()) return;
    const { a, d, owns } = capture(), ticket = modalTicket, action = mode, id = detail?.id;
    if (kind === 'application' && action === 'create' && (!context || !draft.role_ids.length)) { modalError = t('credentials.chooseRoles'); return; }
    busy = true; modalError = '';
    try {
      let result: ApplicationCredentialIssued | UserCredential | undefined;
      if (action === 'delete' && id) await credentialRequest(`${base}/${encodeURIComponent(id)}${kind === 'application' ? query(detail!.user_id) : ''}`, d, a, 'DELETE');
      else {
        const body: ApplicationCredentialInput | UserCredentialInput = kind === 'application'
          ? { name: draft.name, description: draft.description, role_ids: draft.role_ids, ...(draft.expires_at ? { expires_at: new Date(draft.expires_at).toISOString() } : {}) }
          : { user_id: draft.user_id, project_id: draft.project_id || null, type: draft.type, blob: draft.blob };
        result = await credentialRequest(base + (action === 'edit' && id ? `/${encodeURIComponent(id)}` : ''), d, a, action === 'edit' ? 'PATCH' : 'POST', body);
      }
      if (!owns() || ticket !== modalTicket) return;
      if (result) {
        assertScope(result);
        const userId = kind === 'application' ? a.userId : draft.user_id;
        const projectId = kind === 'application' ? a.projectId : draft.project_id || null;
        if (result.user_id !== userId || result.project_id !== projectId || (action === 'edit' && result.id !== id)) throw new ApiError(403, 'credential_scope_denied', 'credential_scope_denied');
      }
      close();
      if (kind === 'application' && action === 'create') { issued = result as ApplicationCredentialIssued; mode = 'issued'; }
      void load();
    } catch (e) {
      if (owns() && ticket === modalTicket) {
        modalError = failure(e);
        if (e instanceof ApiError && e.code === 'credential_rollback_failed') void load();
      }
    }
    finally { if (owns() && ticket === modalTicket) busy = false; }
  }
  function dispose() { disposed = true; ++epoch; ++directoryTicket; close(); items = []; users = []; }
  return {
    get items() { return items; }, get users() { return users; }, get selectedUser() { return selectedUser; },
    get loading() { return loading; }, get error() { return error; }, get directoryLoading() { return directoryLoading; }, get directoryError() { return directoryError; },
    get busy() { return busy; }, get modalError() { return modalError; }, get mode() { return mode; }, get detail() { return detail; },
    get issued() { return issued; }, get context() { return context; }, get draft() { return draft; }, get allowed() { return allowed(); }, get canCreate() { return canCreate(); },
    close, setScope, setAuthority, load, loadUsers, selectUser, open, reveal, submit, dispose,
  };
}
