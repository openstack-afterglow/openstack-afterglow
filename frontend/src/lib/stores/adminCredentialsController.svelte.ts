import { credentialRequest } from '$lib/api/adminCredentials';
import { ApiError } from '$lib/api/errors';
import { t } from '$lib/i18n/ns/admin-identity';
import type {
  ApplicationCredential, ApplicationCredentialIssued, ApplicationCredentialInput,
  UserCredential, UserCredentialDetail, UserCredentialInput, CredentialAuthority,
  CredentialCreationContext, CredentialUser,
} from '$lib/types/adminCredential';

export function createAdminCredentialsController(kind: 'application' | 'user') {
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
  const allowed = () => !disposed && authority.admin && authority.ready && !!authority.token && !!authority.userId && !!authority.projectId;
  const query = () => selectedUser ? `?user_id=${encodeURIComponent(selectedUser)}` : '';
  const capture = () => { const e = epoch, a = { ...authority }; return { a, owns: () => allowed() && e === epoch }; };
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
    return t('credentials.unavailable');
  };

  function close() {
    ++modalTicket;
    mode = null; detail = null; issued = null; context = null; busy = false; modalError = '';
    draft = { name: '', description: '', role_ids: [], expires_at: '', user_id: '', project_id: '', type: '', blob: '' };
  }
  function setAuthority(next: CredentialAuthority) {
    if (next.token && next.token === deniedToken) next = { ...next, admin: false };
    if (Object.keys(next).every(key => next[key as keyof CredentialAuthority] === authority[key as keyof CredentialAuthority])) return;
    authority = { ...next }; ++epoch; ++listTicket; ++directoryTicket; close();
    items = []; users = []; selectedUser = next.userId ?? ''; error = ''; directoryError = ''; loading = false; directoryLoading = false;
    if (allowed()) { void load(); void loadUsers(); }
  }
  async function loadUsers() {
    if (!allowed()) return;
    const { a, owns } = capture(), ticket = ++directoryTicket;
    directoryLoading = true; directoryError = '';
    try {
      const all: CredentialUser[] = [], seen = new Set<string>(), markers = new Set<string>();
      let marker: string | null = null;
      do {
        const page: { items: CredentialUser[]; next_marker: string | null } = await credentialRequest(`/api/v1/admin/users?limit=100${marker ? `&marker=${encodeURIComponent(marker)}` : ''}`, a);
        if (!owns() || ticket !== directoryTicket) return;
        for (const user of page.items) if (!seen.has(user.id)) { seen.add(user.id); all.push(user); }
        if (page.next_marker && (markers.has(page.next_marker) || !page.items.length)) throw new Error('Directory pagination stalled');
        if (page.next_marker) markers.add(page.next_marker);
        marker = page.next_marker;
      } while (marker);
      users = all;
    } catch (e) { if (owns() && ticket === directoryTicket) directoryError = failure(e); }
    finally { if (owns() && ticket === directoryTicket) directoryLoading = false; }
  }
  async function selectUser(id: string) { ++listTicket; selectedUser = id; close(); items = []; await load(); }
  async function load() {
    if (!allowed()) return;
    const { a, owns } = capture(), ticket = ++listTicket;
    loading = true; error = '';
    try {
      const result = await credentialRequest<{ items: (ApplicationCredential | UserCredential)[] }>(base + query(), a);
      if (owns() && ticket === listTicket) items = result.items;
    } catch (e) { if (owns() && ticket === listTicket) { items = []; error = failure(e); } }
    finally { if (owns() && ticket === listTicket) loading = false; }
  }
  async function open(next: 'create' | 'detail' | 'delete', item?: ApplicationCredential | UserCredential) {
    if (!allowed()) return;
    close(); mode = next; detail = item ?? null;
    draft.user_id = selectedUser || authority.userId || '';
    draft.project_id = authority.projectId || '';
    if (next === 'delete') return;
    const { a, owns } = capture(), ticket = modalTicket;
    busy = true;
    try {
      if (next === 'create' && kind === 'application') {
        const result = await credentialRequest<CredentialCreationContext>(`${base}/context`, a);
        if (owns() && ticket === modalTicket) context = result;
      }
      else if (next === 'detail' && item) {
        const result = await credentialRequest<ApplicationCredential | UserCredentialDetail>(`${base}/${encodeURIComponent(item.id)}${kind === 'application' ? query() : ''}`, a);
        if (owns() && ticket === modalTicket) detail = result;
      }
    } catch (e) { if (owns() && ticket === modalTicket) modalError = failure(e); }
    finally { if (owns() && ticket === modalTicket) busy = false; }
  }
  async function reveal(edit = false) {
    if (!allowed() || kind !== 'user' || !detail || busy) return;
    const { a, owns } = capture(), ticket = ++modalTicket, id = detail.id;
    busy = true; modalError = '';
    try {
      const result = await credentialRequest<UserCredentialDetail>(`${base}/${encodeURIComponent(id)}?sensitive=true`, a);
      if (!owns() || ticket !== modalTicket) return;
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
    const { a, owns } = capture(), ticket = modalTicket, action = mode, id = detail?.id;
    if (kind === 'application' && action === 'create' && (!context || !draft.role_ids.length)) { modalError = t('credentials.chooseRoles'); return; }
    busy = true; modalError = '';
    try {
      let result: ApplicationCredentialIssued | UserCredential | undefined;
      if (action === 'delete' && id) await credentialRequest(`${base}/${encodeURIComponent(id)}${kind === 'application' ? query() : ''}`, a, 'DELETE');
      else {
        const body: ApplicationCredentialInput | UserCredentialInput = kind === 'application'
          ? { name: draft.name, description: draft.description, role_ids: draft.role_ids, ...(draft.expires_at ? { expires_at: new Date(draft.expires_at).toISOString() } : {}) }
          : { user_id: draft.user_id, project_id: draft.project_id || null, type: draft.type, blob: draft.blob };
        result = await credentialRequest(base + (action === 'edit' && id ? `/${encodeURIComponent(id)}` : ''), a, action === 'edit' ? 'PATCH' : 'POST', body);
      }
      if (!owns() || ticket !== modalTicket) return;
      close();
      if (kind === 'application' && action === 'create') { issued = result as ApplicationCredentialIssued; mode = 'issued'; }
      void load();
    } catch (e) { if (owns() && ticket === modalTicket) modalError = failure(e); }
    finally { if (owns() && ticket === modalTicket) busy = false; }
  }
  function dispose() { disposed = true; ++epoch; ++directoryTicket; close(); items = []; users = []; }
  return {
    get items() { return items; }, get users() { return users; }, get selectedUser() { return selectedUser; },
    get loading() { return loading; }, get error() { return error; }, get directoryLoading() { return directoryLoading; }, get directoryError() { return directoryError; },
    get busy() { return busy; }, get modalError() { return modalError; }, get mode() { return mode; }, get detail() { return detail; },
    get issued() { return issued; }, get context() { return context; }, get draft() { return draft; }, get allowed() { return allowed(); },
    close, setAuthority, load, loadUsers, selectUser, open, reveal, submit, dispose,
  };
}
