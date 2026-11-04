import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createLoginMonitoringController } from '../loginMonitoringController.svelte';
import { createAdminCredentialsController } from '../adminCredentialsController.svelte';
import { createInfrastructureTopologyController } from '../infrastructureTopologyController.svelte';
import { makeSnapshot, makeTrace } from '$lib/components/admin/infrastructure-topology/__tests__/fixtures';
import { ApiError } from '$lib/api/errors';
import type { LoginMonitoring } from '$lib/types/loginMonitoring';
import type { InfrastructureTopologySnapshot } from '$lib/types/infrastructureTopology';
import type * as ExperienceModule from '$lib/utils/experience';

const { monitoring, credentials, topologyRead, topologySubmit, replay } = vi.hoisted(() => ({
  monitoring: vi.fn(), credentials: vi.fn(), topologyRead: vi.fn(), topologySubmit: vi.fn(),
  replay: { begin: vi.fn(), load: vi.fn(), state: vi.fn(), applied: vi.fn(), discarded: vi.fn() },
}));
vi.mock('$lib/api/loginMonitoring', () => ({ monitoringRequest: monitoring }));
vi.mock('$lib/api/adminCredentials', () => ({ credentialRequest: credentials }));
vi.mock('$lib/api/infrastructureTopology', () => ({ getInfrastructureTopology: topologyRead, submitInfrastructureTrace: topologySubmit }));
vi.mock('$lib/utils/experience', async importOriginal => ({
  ...await importOriginal<typeof ExperienceModule>(),
  beginExperienceAction: replay.begin, beginExperienceLoad: replay.load, experienceState: replay.state,
  experienceApplied: replay.applied, experienceDiscarded: replay.discarded,
}));

const authority = { token: 'private-token', userId: 'private-actor', projectId: 'private-project', admin: true, ready: true };
const disposals: (() => void)[] = [];
const directory = { items: [{ id: 'private-selected', name: 'Private display name' }], next_marker: null };
const app = { id: 'private-credential', domain_id: 'private-domain', user_id: authority.userId, project_id: authority.projectId,
  name: 'private-credential-name', description: '', expires_at: null, roles: [{ id: 'private-role', name: 'reader' }], unrestricted: false };

beforeEach(() => {
  vi.resetAllMocks();
  replay.begin.mockImplementation((feature, action, component) => Object.freeze({ feature, action, component, source: replay.begin.mock.calls.length }));
  replay.load.mockImplementation((feature, component) => Object.freeze({ feature, action: 'load', component, source: replay.load.mock.calls.length }));
  monitoring.mockResolvedValue(directory);
  topologyRead.mockImplementation(async () => makeSnapshot());
  topologySubmit.mockResolvedValue(makeTrace('queued'));
  credentials.mockImplementation(async (path: string, _domain, _authority, method) => {
    if (path.includes('/users?')) return { items: [{ id: authority.userId, domain_id: 'private-domain', name: 'Private actor name' }], next_marker: null };
    if (path.endsWith('/context')) return { domain_id: 'private-domain', user_id: authority.userId, project_id: authority.projectId, roles: app.roles };
    if (method === 'POST') return { ...app, secret: 'one-time-private-secret' };
    return { items: [] };
  });
});
afterEach(() => { for (const dispose of disposals.splice(0)) dispose(); });

async function selectedMonitoring() {
  const controller = createLoginMonitoringController(); disposals.push(controller.dispose);
  controller.setAuthority(authority);
  await vi.waitFor(() => expect(controller.directoryLoading).toBe(false));
  return controller;
}

async function credentialCreation() {
  const controller = createAdminCredentialsController('application', 'private-domain'); disposals.push(controller.dispose);
  controller.setAuthority(authority);
  await vi.waitFor(() => expect(controller.directoryLoading || controller.loading).toBe(false));
  await controller.open('create');
  controller.draft.name = 'private-input-name'; controller.draft.role_ids = ['private-role'];
  return controller;
}

describe('workspace-family replay state ownership', () => {
  it('records the directory state only after publication and passes the captured context to its physical helper', async () => {
    const pending = Promise.withResolvers<typeof directory>(); monitoring.mockReturnValueOnce(pending.promise);
    const controller = createLoginMonitoringController(); disposals.push(controller.dispose);
    controller.setAuthority(authority);
    const context = monitoring.mock.calls[0][2];
    expect(context).toBe(replay.load.mock.results[0].value);
    expect(replay.begin).not.toHaveBeenCalled();
    expect(replay.state).toHaveBeenCalledWith(context, 'loading');
    expect(replay.applied).not.toHaveBeenCalled();
    pending.resolve(directory);
    await vi.waitFor(() => expect(controller.directoryLoading).toBe(false));
    expect(controller.users).toHaveLength(1);
    expect(replay.state).toHaveBeenCalledWith(context, 'ready');
    expect(replay.applied).toHaveBeenCalledWith(context, {}, expect.any(Function));
    const owns = replay.applied.mock.calls.find(([value]) => value === context)![2] as () => boolean;
    expect(owns()).toBe(true); controller.dispose(); expect(owns()).toBe(false);
  });

  it('distinguishes human load-more from the automatic directory read and carries that action into its response publication', async () => {
    monitoring.mockResolvedValueOnce({ ...directory, next_marker: 'private-page-marker' });
    const controller = await selectedMonitoring();
    expect(replay.begin).not.toHaveBeenCalled();
    monitoring.mockResolvedValueOnce({ items: [], next_marker: null });
    await controller.loadUsers(true);
    const context = monitoring.mock.calls.at(-1)![2];
    expect(replay.begin).toHaveBeenCalledWith('monitoring', 'load', 'resource.list');
    expect(context).toBe(replay.begin.mock.results.at(-1)!.value);
    expect(replay.applied).toHaveBeenCalledWith(context, {}, expect.any(Function));
    expect(JSON.stringify(replay.state.mock.calls)).not.toContain('private-page-marker');
  });

  it('fences topology DOM commitment by the actual published snapshot across same-authority replacement', async () => {
    const controller = createInfrastructureTopologyController(); disposals.push(controller.dispose);
    controller.setAuthority(authority);
    await vi.waitFor(() => expect(controller.loading).toBe(false));
    const originalSnapshot = controller.snapshot;
    const originalGuard = replay.applied.mock.calls.at(-1)![2] as () => boolean;
    expect(originalGuard()).toBe(true);
    await controller.load();
    expect(controller.snapshot).not.toBe(originalSnapshot);
    expect(originalGuard()).toBe(false);
    const currentGuard = replay.applied.mock.calls.at(-1)![2] as () => boolean;
    expect(currentGuard()).toBe(true);
    controller.setVisible(false);
    expect(currentGuard()).toBe(false);
  });

  it('does not commit an accepted trace row after its same-owner readback replaces that row', async () => {
    const controller = createInfrastructureTopologyController(); disposals.push(controller.dispose);
    controller.setAuthority(authority);
    await vi.waitFor(() => expect(controller.loading).toBe(false));
    const readback = Promise.withResolvers<InfrastructureTopologySnapshot>();
    topologyRead.mockReturnValueOnce(readback.promise);
    replay.applied.mockClear();
    await controller.submitTrace();
    const context = topologySubmit.mock.calls[0][4];
    const acceptedGuard = replay.applied.mock.calls.find(([value]) => value === context)![2] as () => boolean;
    expect(controller.snapshot?.hosts[0].traces[0].status).toBe('queued');
    expect(acceptedGuard()).toBe(true);
    const acceptedSnapshot = controller.snapshot;
    readback.resolve(makeSnapshot());
    await vi.waitFor(() => expect(controller.snapshot).not.toBe(acceptedSnapshot));
    expect(acceptedGuard()).toBe(false);
    expect(JSON.stringify(replay.state.mock.calls)).not.toContain('203.0.113.9');
  });

  it('records selection clearing and an unselected range change as local disabled state, not a missing read result', async () => {
    const controller = await selectedMonitoring();
    const reads = monitoring.mock.calls.length;
    await controller.selectUser('');
    const clearing = replay.begin.mock.results.at(-1)!.value;
    expect(replay.state).toHaveBeenCalledWith(clearing, 'disabled');
    expect(replay.applied).toHaveBeenCalledWith(clearing);
    await controller.selectWindow('30d');
    const range = replay.begin.mock.results.at(-1)!.value;
    expect(replay.state).toHaveBeenCalledWith(range, 'disabled');
    expect(replay.applied).toHaveBeenCalledWith(range);
    expect(monitoring).toHaveBeenCalledTimes(reads);
  });

  it('publishes the cleared application-credential selection without dispatching an invented empty-user query', async () => {
    const controller = await credentialCreation();
    const reads = credentials.mock.calls.length;
    await controller.selectUser('');
    const context = replay.begin.mock.results.at(-1)!.value;
    expect(controller.items).toEqual([]);
    expect(controller.mode).toBeNull();
    expect(replay.state).toHaveBeenCalledWith(context, 'disabled');
    expect(replay.applied).toHaveBeenCalledWith(context);
    expect(credentials).toHaveBeenCalledTimes(reads);
  });

  it.each(['scopeABA', 'selection', 'unmounted'] as const)('does not claim a late selected-user response was applied after %s', async boundary => {
    const controller = await selectedMonitoring();
    const pending = Promise.withResolvers<LoginMonitoring>(); monitoring.mockReturnValueOnce(pending.promise);
    const loading = controller.selectUser('private-selected');
    const context = monitoring.mock.calls.at(-1)![2];
    if (boundary === 'scopeABA') { controller.setAuthority({ ...authority, projectId: 'other-private-project' }); controller.setAuthority(authority); }
    else if (boundary === 'selection') await controller.selectUser('');
    else controller.dispose();
    pending.resolve({ user: { id: 'private-selected' } } as LoginMonitoring); await loading;
    expect(replay.applied.mock.calls.some(([value]) => value === context)).toBe(false);
    expect(replay.discarded).toHaveBeenCalledWith(context, boundary === 'unmounted' ? 'unmounted' : 'stale');
    expect(controller.data).toBeNull();
  });

  it('keeps read failure distinct from empty and never records the remote error or private selector', async () => {
    const controller = await selectedMonitoring();
    monitoring.mockRejectedValueOnce(new ApiError(503, 'private-error-body', 'login_monitoring_unavailable'));
    await controller.selectUser('private-selected');
    const context = monitoring.mock.calls.at(-1)![2];
    expect(controller.error).toBe('login_monitoring_unavailable');
    expect(replay.state).toHaveBeenCalledWith(context, 'error');
    expect(replay.state.mock.calls.some(([value, state]) => value === context && state === 'empty')).toBe(false);
    const observations = JSON.stringify([...replay.state.mock.calls, ...replay.applied.mock.calls]);
    for (const sensitive of ['private-error-body', 'private-selected', authority.token, authority.userId, authority.projectId]) expect(observations).not.toContain(sensitive);
  });

  it('links credential creation and the followup list without collecting issued secrets, names, roles or scope', async () => {
    const controller = await credentialCreation();
    await controller.submit();
    const mutation = credentials.mock.calls.find(([, , , method]) => method === 'POST')!;
    const context = mutation[5];
    expect(context).toMatchObject({ feature: 'admin', action: 'create', component: 'resource.detail' });
    expect(controller.issued?.secret).toBe('one-time-private-secret');
    expect(credentials.mock.calls.some(([path, , , method, , value]) => method === 'GET' && !path.includes('/users?') && !path.endsWith('/context') && value === context)).toBe(true);
    expect(replay.applied.mock.calls.some(([value]) => value === context)).toBe(true);
    const observations = JSON.stringify([...replay.state.mock.calls, ...replay.applied.mock.calls, ...replay.discarded.mock.calls]);
    for (const sensitive of ['one-time-private-secret', 'private-input-name', 'private-credential', 'private-role', 'private-domain', authority.token, authority.userId, authority.projectId]) expect(observations).not.toContain(sensitive);
  });

  it('discards a late credential mutation after domain ABA without treating receipt as issued state', async () => {
    const controller = await credentialCreation();
    const pending = Promise.withResolvers<unknown>(); credentials.mockReturnValueOnce(pending.promise);
    const submitting = controller.submit();
    const context = credentials.mock.calls.at(-1)![5];
    controller.setScope('other-private-domain'); controller.setScope('private-domain');
    pending.resolve({ ...app, secret: 'late-private-secret' }); await submitting;
    expect(controller.issued).toBeNull();
    expect(replay.applied.mock.calls.some(([value]) => value === context)).toBe(false);
    expect(replay.discarded).toHaveBeenCalledWith(context, 'stale');
  });
});
