import { monitoringRequest } from '$lib/api/loginMonitoring';
import { ApiError } from '$lib/api/errors';
import type { LoginMonitoring, LoginWindow, MonitoringAuthority, MonitoringUser } from '$lib/types/loginMonitoring';
import { beginExperienceAction, beginExperienceLoad, experienceApplied, experienceDiscarded, experienceState, type ExperienceContext } from '$lib/utils/experience';

export function createLoginMonitoringController() {
  let authority = $state<MonitoringAuthority>({ admin: false, ready: false });
  let deniedToken: string | undefined;
  let epoch = 0, selectionTicket = 0, directoryTicket = 0;
  let disposed = $state(false);
  let users = $state<MonitoringUser[]>([]), selectedUser = $state(''), window = $state<LoginWindow>('24h');
  let data = $state<LoginMonitoring | null>(null), loading = $state(false), error = $state('');
  let directoryLoading = $state(false), directoryError = $state(''), nextMarker = $state<string | null>(null);
  const markers = new Set<string>();
  const allowed = () => !disposed && authority.admin && authority.ready && !!authority.token && !!authority.userId && !!authority.projectId;
  const capture = () => { const e = epoch, a = { ...authority }; return { a, owns: () => allowed() && e === epoch }; };
  const failure = (e: unknown) => {
    const code = e instanceof ApiError ? e.code ?? 'login_monitoring_unavailable' : 'login_monitoring_unavailable';
    if (code === 'login_monitoring_admin_denied') {
      deniedToken = authority.token;
      setAuthority({ ...authority, admin: false });
    }
    return code;
  };
  function setAuthority(next: MonitoringAuthority) {
    if (next.token && next.token === deniedToken) next = { ...next, admin: false };
    if (Object.keys(next).every(key => next[key as keyof MonitoringAuthority] === authority[key as keyof MonitoringAuthority])) return;
    authority = { ...next }; ++epoch; ++selectionTicket; ++directoryTicket;
    data = null; users = []; selectedUser = ''; error = ''; directoryError = ''; loading = false; directoryLoading = false; nextMarker = null; markers.clear();
    if (allowed()) void loadUsers();
  }
  async function loadUsers(more = false) {
    if (!allowed() || directoryLoading || (more && !nextMarker)) return;
    const { a, owns } = capture(), ticket = ++directoryTicket, marker = more ? nextMarker : null;
    const experience = more ? beginExperienceAction('monitoring', 'load', 'resource.list') : beginExperienceLoad('monitoring', 'resource.list');
    const current = () => owns() && ticket === directoryTicket;
    directoryLoading = true; directoryError = '';
    experienceState(experience, 'loading');
    try {
      const page = await monitoringRequest<{ items: MonitoringUser[]; next_marker: string | null }>(`/api/v1/admin/monitoring/logins/users?limit=100${marker ? `&marker=${encodeURIComponent(marker)}` : ''}`, a, experience);
      if (!current()) { experienceDiscarded(experience, disposed ? 'unmounted' : 'stale'); return; }
      if (page.next_marker && ((more && markers.has(page.next_marker)) || !page.items.length)) throw new Error('Directory pagination stalled');
      if (!more) markers.clear();
      if (page.next_marker) markers.add(page.next_marker);
      const unique = new Map((more ? users : []).map(user => [user.id, user]));
      for (const user of page.items) unique.set(user.id, user);
      users = [...unique.values()]; nextMarker = page.next_marker;
      experienceState(experience, users.length ? 'ready' : 'empty');
      void experienceApplied(experience, {}, current);
    } catch (e) {
      if (current()) { directoryError = failure(e); experienceState(experience, 'error'); void experienceApplied(experience, {}, current); }
      else experienceDiscarded(experience, disposed ? 'unmounted' : 'stale');
    }
    finally { if (owns() && ticket === directoryTicket) directoryLoading = false; }
  }
  function load() {
    return loadAttempt(beginExperienceAction('monitoring', 'refresh', 'resource.detail'));
  }
  async function loadAttempt(parentExperience?: ExperienceContext) {
    if (!allowed() || !selectedUser) return;
    const { a, owns } = capture(), ticket = ++selectionTicket, id = selectedUser, range = window;
    const experience = parentExperience ?? beginExperienceLoad('monitoring', 'resource.detail');
    const current = () => owns() && ticket === selectionTicket;
    data = null; loading = true; error = '';
    experienceState(experience, 'loading');
    try {
      const result = await monitoringRequest<LoginMonitoring>(`/api/v1/admin/monitoring/logins/users/${encodeURIComponent(id)}?window=${range}`, a, experience);
      if (!current()) { experienceDiscarded(experience, disposed ? 'unmounted' : 'stale'); return; }
      data = result;
      experienceState(experience, result.history.state === 'unavailable' || result.sessions.state === 'unavailable' ? 'error' : 'ready');
      void experienceApplied(experience, {}, current);
    } catch (e) {
      if (current()) { error = failure(e); experienceState(experience, 'error'); void experienceApplied(experience, {}, current); }
      else experienceDiscarded(experience, disposed ? 'unmounted' : 'stale');
    }
    finally { if (owns() && ticket === selectionTicket) loading = false; }
  }
  async function selectUser(id: string) {
    const experience = beginExperienceAction('monitoring', 'select', 'resource.detail');
    ++selectionTicket; selectedUser = id; data = null; error = ''; loading = false;
    if (!id) { experienceState(experience, 'disabled'); void experienceApplied(experience); return; }
    await loadAttempt(experience);
  }
  async function selectWindow(range: LoginWindow) {
    const experience = beginExperienceAction('monitoring', 'select', 'resource.detail');
    ++selectionTicket; window = range; data = null;
    if (!selectedUser) { experienceState(experience, 'disabled'); void experienceApplied(experience); return; }
    await loadAttempt(experience);
  }
  function dispose() { disposed = true; ++epoch; ++selectionTicket; ++directoryTicket; data = null; users = []; }
  return { get users() { return users; }, get selectedUser() { return selectedUser; }, get window() { return window; },
    get data() { return data; }, get loading() { return loading; }, get error() { return error; },
    get directoryLoading() { return directoryLoading; }, get directoryError() { return directoryError; }, get nextMarker() { return nextMarker; }, get allowed() { return allowed(); },
    setAuthority, loadUsers, selectUser, selectWindow, load, dispose };
}
