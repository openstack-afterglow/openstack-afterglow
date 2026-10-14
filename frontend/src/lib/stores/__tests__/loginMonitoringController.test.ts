import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { get } from 'svelte/store';
import { createLoginMonitoringController } from '../loginMonitoringController.svelte';
import LoginMonitoringPage from '$lib/components/admin/logins/LoginMonitoring.svelte';
import { auth, authReady, projectSwitching } from '$lib/stores/auth';
import { ApiError } from '$lib/api/errors';
import { t } from '$lib/i18n/ns/login-monitoring';
import type { LoginMonitoring, MonitoringAuthority } from '$lib/types/loginMonitoring';

const { request } = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock('$lib/api/loginMonitoring', () => ({ monitoringRequest: request }));
const authority: MonitoringAuthority = { token: 'token-a', userId: 'actor-a', projectId: 'project-a', admin: true, ready: true };
const directory = { items: [{ id: 'selected', name: 'Selected' }, { id: 'other', name: 'Other' }], next_marker: null };
function snapshot(id = 'selected'): LoginMonitoring {
  return { user: { id, name: 'Selected' }, window: '24h', as_of: '2026-10-14T12:00:00+00:00', from_at: '2026-10-13T12:00:00+00:00', observed_interval_seconds: 300,
    history: { state: 'ready', events: [{ at: '2026-10-14T11:59:00+00:00', project_id: 'project-record', resource_type: 'auth', action: 'login', status: 'success', auth_method: 'federated' }],
      timeline: [{ at: '2026-10-14T11:00:00+00:00', successes: 2, recorded_failures: 0 }], hour_distribution: Array.from({ length: 24 }, (_, hour) => ({ hour, successes: hour === 11 ? 2 : 0, recorded_failures: 0 })), login_successes: 2, recorded_login_failures: 0, failure_history: 'not_collected' },
    sessions: { state: 'ready', valid_count: 1, observed_recent_count: 1, items: [{ started_at: '2026-10-14T11:00:00+00:00', last_seen: '2026-10-14T11:59:00+00:00', expires_at: '2026-10-14T12:00:00+00:00', refresh_expires_at: '2026-10-15T12:00:00+00:00', project_id: 'session-project', device_type: 'desktop', os: 'Linux', auth_method: 'password', observed_recently: true }] } };
}
beforeEach(() => {
  request.mockReset().mockImplementation((path: string) => Promise.resolve(path.includes('/users?') ? directory : snapshot()));
});
afterEach(() => { cleanup(); authReady.set(false); projectSwitching.set(false); });

async function ready() {
  const ctrl = createLoginMonitoringController(); ctrl.setAuthority(authority);
  await ctrl.selectUser('selected'); return ctrl;
}

describe('login-monitoring scope fences', () => {
  it.each(['token', 'userId', 'projectId', 'admin', 'ready'] as const)('masks selected-user data immediately on %s transition', async field => {
    const ctrl = await ready(); expect(ctrl.data?.user.id).toBe('selected');
    ctrl.setAuthority({ ...authority, [field]: field === 'admin' || field === 'ready' ? false : 'changed' });
    expect(ctrl.data).toBeNull(); expect(ctrl.selectedUser).toBe(''); expect(ctrl.users).toEqual([]); ctrl.dispose();
  });
  it.each(['selection', 'window', 'scopeABA', 'dispose'] as const)('rejects late selected-user response after %s', async event => {
    const ctrl = await ready(), pending = Promise.withResolvers<LoginMonitoring>();
    request.mockImplementationOnce(() => pending.promise); const old = ctrl.load();
    if (event === 'selection') await ctrl.selectUser('other');
    if (event === 'window') await ctrl.selectWindow('30d');
    if (event === 'scopeABA') { ctrl.setAuthority({ ...authority, projectId: 'project-b' }); ctrl.setAuthority(authority); }
    if (event === 'dispose') ctrl.dispose();
    pending.resolve(snapshot('late-response')); await old;
    expect(ctrl.data?.user.id).not.toBe('late-response'); ctrl.dispose();
  });
  it('does not fetch without current admin authority or selected user', async () => {
    const ctrl = createLoginMonitoringController(); ctrl.setAuthority({ ...authority, admin: false });
    await ctrl.selectUser('selected'); await ctrl.loadUsers(); expect(request).not.toHaveBeenCalled(); ctrl.dispose();
  });
  it('distinguishes native-denied directory from verified empty and supports paginated search inventory', async () => {
    const ctrl = createLoginMonitoringController();
    request.mockRejectedValueOnce(new ApiError(403, '', 'login_monitoring_native_denied'));
    ctrl.setAuthority(authority);
    await vi.waitFor(() => expect(ctrl.directoryError).toBe('login_monitoring_native_denied'));
    expect(ctrl.allowed).toBe(true); expect(ctrl.users).toEqual([]);
    request.mockResolvedValueOnce({ items: [], next_marker: null }); await ctrl.loadUsers();
    expect(ctrl.directoryError).toBe(''); expect(ctrl.users).toEqual([]);
    request.mockResolvedValueOnce({ items: [{ id: 'first', name: 'First' }], next_marker: 'first' }); await ctrl.loadUsers();
    request.mockResolvedValueOnce({ items: [{ id: 'last', name: 'Last' }], next_marker: null }); await ctrl.loadUsers(true);
    expect(ctrl.users.map(user => user.id)).toEqual(['first', 'last']);
    expect(request.mock.calls.at(-1)?.[0]).toContain('marker=first'); ctrl.dispose();
  });
  it('directory refresh may repeat its first marker, but load-more stalls are visible', async () => {
    const ctrl = createLoginMonitoringController();
    request.mockResolvedValue({ items: [{ id: 'first', name: 'First' }], next_marker: 'first' });
    ctrl.setAuthority(authority); await vi.waitFor(() => expect(ctrl.directoryLoading).toBe(false));
    await ctrl.loadUsers(); expect(ctrl.directoryError).toBe('');
    await ctrl.loadUsers(true); expect(ctrl.directoryError).toBe('login_monitoring_unavailable');
    expect(ctrl.users.map(user => user.id)).toEqual(['first']); ctrl.dispose();
  });
  it('late directory results cannot survive project ABA', async () => {
    const pending = Promise.withResolvers<typeof directory>(); request.mockImplementationOnce(() => pending.promise);
    const ctrl = createLoginMonitoringController(); ctrl.setAuthority(authority);
    ctrl.setAuthority({ ...authority, projectId: 'b' }); ctrl.setAuthority(authority);
    pending.resolve({ items: [{ id: 'late-user', name: 'Late' }], next_marker: null });
    await vi.waitFor(() => expect(ctrl.directoryLoading).toBe(false));
    expect(ctrl.users.some(user => user.id === 'late-user')).toBe(false); ctrl.dispose();
  });
  it('revokes local authority after platform denial and rejects already pending data', async () => {
    const ctrl = await ready();
    const pending = Promise.withResolvers<LoginMonitoring>();
    request.mockImplementationOnce(() => pending.promise);
    const old = ctrl.load();
    request.mockRejectedValueOnce(new ApiError(403, '', 'login_monitoring_admin_denied'));
    await ctrl.loadUsers();
    expect(ctrl.allowed).toBe(false);
    expect(ctrl.data).toBeNull(); expect(ctrl.users).toEqual([]);
    ctrl.setAuthority(authority);
    pending.resolve(snapshot('late-private-user')); await old;
    expect(ctrl.allowed).toBe(false); expect(ctrl.data).toBeNull();
    request.mockImplementation((path: string) => Promise.resolve(path.includes('/users?') ? directory : snapshot('other')));
    ctrl.setAuthority({ ...authority, token: 'new-verified-token' });
    await ctrl.selectUser('other'); expect(ctrl.data?.user.id).toBe('other');
    ctrl.dispose();
  });
});

async function mountSelected(data = snapshot()) {
  request.mockImplementation((path: string) => Promise.resolve(path.includes('/users?') ? directory : data));
  auth.set({ ...get(auth), token: 'token-a', userId: 'actor-a', username: 'Actor', projectId: 'project-a', isSystemAdmin: true });
  authReady.set(true); projectSwitching.set(false);
  render(LoginMonitoringPage);
  await vi.waitFor(() => expect(screen.getByRole('option', { name: 'Selected · selected' })).toBeTruthy());
  await vi.waitFor(() => expect((screen.getByRole('combobox', { name: t('user') }) as HTMLSelectElement).disabled).toBe(false));
  await fireEvent.change(screen.getByRole('combobox', { name: t('user') }), { target: { value: 'selected' } });
}

describe('selected-user monitoring consumer', () => {
  it('enables selection when authentication becomes ready before inventory returns', async () => {
    const pending = Promise.withResolvers<typeof directory>();
    request.mockImplementation(() => pending.promise);
    auth.set({ ...get(auth), token: 'ready-token', userId: 'actor-a', projectId: 'project-a', isSystemAdmin: true });
    authReady.set(false);
    render(LoginMonitoringPage);
    const selector = screen.getByRole('combobox', { name: t('user') }) as HTMLSelectElement;
    expect(selector.disabled).toBe(true);
    authReady.set(true);
    await vi.waitFor(() => expect(selector.disabled).toBe(false));
    pending.resolve(directory);
    await vi.waitFor(() => expect(screen.getByRole('option', { name: 'Selected · selected' })).toBeTruthy());
  });
  it('searches and selects users, renders actual timestamps/method/project, and names observation limitations', async () => {
    await mountSelected();
    await vi.waitFor(() => expect(screen.getByText('session-project')).toBeTruthy());
    expect(screen.getByText(t('observationNotice'))).toBeTruthy(); expect(screen.getByText(t('failuresNotice'))).toBeTruthy();
    expect(screen.getByText(t('federated'))).toBeTruthy(); expect(screen.getByText(t('lastSeen'))).toBeTruthy();
    await fireEvent.input(screen.getByRole('searchbox', { name: t('search') }), { target: { value: 'Other' } });
    expect(screen.getByRole('option', { name: 'Other · other' })).toBeTruthy();
    await fireEvent.change(screen.getByRole('combobox', { name: t('range') }), { target: { value: '7d' } });
    await vi.waitFor(() => expect(request.mock.calls.some(([path]) => path.endsWith('window=7d'))).toBe(true));
    projectSwitching.set(true);
    await vi.waitFor(() => expect(screen.queryByText('session-project')).toBeNull());
  });
  it.each(['unknown', 'unavailable', 'partial'] as const)('shows %s sessions as unknown, never verified empty', async state => {
    const data = snapshot(); data.sessions = { state, valid_count: null, observed_recent_count: null, items: state === 'partial' ? [] : null };
    await mountSelected(data);
    const key = state === 'unknown' ? 'sessionsUnknown' : state === 'partial' ? 'sessionsPartial' : 'sessionsUnavailable';
    await vi.waitFor(() => expect(screen.getByText(t(key))).toBeTruthy());
    expect(screen.queryByText(t('emptySessions'))).toBeNull(); expect(screen.getAllByText(t('unknown')).length).toBeGreaterThan(0);
  });
  it('DB outage is explicit and does not hide independently valid Redis sessions', async () => {
    const data = snapshot(); data.history = { state: 'unavailable', events: null, timeline: null, hour_distribution: null, login_successes: null, recorded_login_failures: null, failure_history: 'not_collected' };
    await mountSelected(data); await vi.waitFor(() => expect(screen.getByText(t('historyUnavailable'))).toBeTruthy());
    expect(screen.getByText('session-project')).toBeTruthy(); expect(screen.queryByText(t('emptyEvents'))).toBeNull();
    expect(screen.queryByRole('img', { name: t('timeline') })).toBeNull();
  });
  it('does not render missing failed-login collection as zero failures', async () => {
    await mountSelected(); await vi.waitFor(() => expect(screen.getByText('session-project')).toBeTruthy());
    expect(screen.getByText(t('failures')).nextElementSibling?.textContent).toBe(t('unknown'));
    expect(screen.getByText(t('failuresNotice'))).toBeTruthy();
  });
  it('nonexistent selected users stay errors rather than becoming zero activity', async () => {
    await mountSelected(); await vi.waitFor(() => expect(screen.getByText('session-project')).toBeTruthy());
    request.mockRejectedValueOnce(new ApiError(404, '', 'login_monitoring_user_not_found'));
    await fireEvent.change(screen.getByRole('combobox', { name: t('user') }), { target: { value: 'other' } });
    await vi.waitFor(() => expect(screen.getByText(t('notFound'))).toBeTruthy());
    expect(screen.queryByText('session-project')).toBeNull(); expect(screen.queryByText(t('emptyEvents'))).toBeNull();
  });
});
