import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createAdminAnnouncementsController } from '../adminAnnouncementsController.svelte';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { ApiError } from '$lib/api/errors';
import type * as ClientModule from '$lib/api/client';
import type * as DomainsModule from '$lib/api/domains';
import type * as ExperienceModule from '$lib/utils/experience';
const mocks = vi.hoisted(() => ({
  get: vi.fn(), post: vi.fn(), list: vi.fn(), withExperience: vi.fn(),
  begin: vi.fn(), state: vi.fn(), applied: vi.fn(), discarded: vi.fn(),
}));
vi.mock('$lib/api/client', async (importOriginal) => ({ ...(await importOriginal<typeof ClientModule>()), api: mocks }));
vi.mock('$lib/api/domains', async (importOriginal) => ({ ...(await importOriginal<typeof DomainsModule>()), domainsApi: { list: mocks.list } }));
vi.mock('$lib/utils/experience', async (importOriginal) => ({
  ...(await importOriginal<typeof ExperienceModule>()),
  beginExperienceAction: mocks.begin, beginExperienceLoad: mocks.begin, experienceState: mocks.state,
  experienceApplied: mocks.applied, experienceDiscarded: mocks.discarded,
}));
const options = { token: () => 'token', projectId: () => 'project' };
beforeEach(() => {
  vi.resetAllMocks(); initLocale('en');
  mocks.withExperience.mockReturnValue(mocks);
  mocks.list.mockResolvedValue({ items: [{ id: 'a', name: 'A' }, { id: 'b', name: 'B' }] });
  mocks.get.mockResolvedValue({ items: [], next_marker: null });
});
afterEach(() => initLocale('ko'));

describe('announcement scoped user recipients', () => {
  it('does not fetch an implicit global directory and retains all-user announcement semantics', async () => {
    const ctrl = createAdminAnnouncementsController(options);
    await ctrl.loadUsers();
    expect(mocks.get).not.toHaveBeenCalled();
    mocks.get.mockResolvedValue([]);
    mocks.post.mockResolvedValue({});
    const payload = { title: 'Maintenance', body: 'Notice', severity: 'info' as const, target_type: 'all' as const, target_id: null, starts_at: null, ends_at: null };
    expect(await ctrl.create(payload)).toEqual({ status: 'ok' });
    expect(mocks.post).toHaveBeenCalledWith('/api/v1/admin/announcements', payload, 'token', 'project', { cache: 'no-store', replayOnUnauthorized: false });
    ctrl.dispose();
  });
  it('publishes only a complete selected-domain directory and drops an old domain result', async () => {
    const ctrl = createAdminAnnouncementsController(options);
    await ctrl.loadDomains();
    const pending = Promise.withResolvers<{ items: unknown[]; next_marker: null }>();
    mocks.get.mockReturnValueOnce(pending.promise);
    ctrl.selectDomain('a');
    mocks.get.mockResolvedValue({ items: [{ id: 'bob', name: 'Bob', domain_id: 'b' }], next_marker: null });
    ctrl.selectDomain('b');
    await vi.waitFor(() => expect(ctrl.allUsers.map(user => user.id)).toEqual(['bob']));
    pending.resolve({ items: [{ id: 'alice', name: 'Alice', domain_id: 'a' }], next_marker: null });
    await vi.waitFor(() => expect(ctrl.usersLoading).toBe(false));
    expect(ctrl.allUsers.map(user => user.id)).toEqual(['bob']);
    expect(mocks.get.mock.calls[0][0]).toContain('domain_id=a');
    expect(mocks.get.mock.calls[1][0]).toContain('domain_id=b');
    ctrl.dispose();
  });
  it('does not publish first-page recipients until every selected-domain page is verified', async () => {
    const ctrl = createAdminAnnouncementsController(options); await ctrl.loadDomains();
    const lastPage = Promise.withResolvers<{ items: unknown[]; next_marker: null }>();
    mocks.get.mockResolvedValueOnce({ items: [{ id: 'alice', name: 'Alice', domain_id: 'a' }], next_marker: 'next /+' }).mockReturnValueOnce(lastPage.promise);
    ctrl.selectDomain('a');
    await vi.waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(2));
    expect(ctrl.usersLoading).toBe(true); expect(ctrl.allUsers).toEqual([]);
    const query = new URL(mocks.get.mock.calls[1][0], 'https://afterglow.test').searchParams;
    expect(query.get('domain_id')).toBe('a'); expect(query.get('marker')).toBe('next /+');
    lastPage.resolve({ items: [{ id: 'second', name: 'Second', domain_id: 'a' }], next_marker: null });
    await vi.waitFor(() => expect(ctrl.allUsers.map(user => user.id)).toEqual(['alice', 'second']));
    expect(ctrl.usersLoading).toBe(false); ctrl.dispose();
  });
  it('rejects foreign-domain recipients instead of publishing a partial catalog', async () => {
    const ctrl = createAdminAnnouncementsController(options); await ctrl.loadDomains();
    mocks.get.mockResolvedValue({ items: [{ id: 'foreign', name: 'Foreign', domain_id: 'b' }], next_marker: null });
    ctrl.selectDomain('a');
    await vi.waitFor(() => expect(ctrl.usersError).not.toBe(''));
    expect(ctrl.allUsers).toEqual([]); ctrl.dispose();
  });
  it('keeps native directory denial visible rather than asserting an empty success', async () => {
    const ctrl = createAdminAnnouncementsController(options); await ctrl.loadDomains();
    mocks.get.mockRejectedValue(new ApiError(403, 'native_denied'));
    ctrl.selectDomain('a');
    await vi.waitFor(() => expect(ctrl.usersError).toBe('native_denied'));
    expect(ctrl.allUsers).toEqual([]);
    ctrl.dispose();
  });
  it('requires an explicit domain before project lookup or project-target submission', async () => {
    const ctrl = createAdminAnnouncementsController(options);
    await ctrl.loadProjects();
    expect(mocks.get).not.toHaveBeenCalled();
    expect(await ctrl.create({ title: 'Maintenance', body: 'Notice', severity: 'info', target_type: 'project', target_id: 'project-a', starts_at: null, ends_at: null })).toEqual({ status: 'invalid' });
    expect(mocks.post).not.toHaveBeenCalled(); ctrl.dispose();
  });
  it('filters project recipients by exact domain and drops late project responses after domain ABA', async () => {
    const ctrl = createAdminAnnouncementsController(options); await ctrl.loadDomains();
    const pending = Promise.withResolvers<unknown>();
    mocks.get.mockReturnValueOnce(pending.promise).mockResolvedValue([{ id: 'current', name: 'Current', domain_id: 'a' }]);
    ctrl.selectDomain('a', 'project'); ctrl.selectDomain('b', 'project'); ctrl.selectDomain('a', 'project');
    await vi.waitFor(() => expect(ctrl.allProjects.map(project => project.id)).toEqual(['current']));
    pending.resolve([{ id: 'stale', name: 'Stale', domain_id: 'a' }]);
    await Promise.resolve(); await Promise.resolve();
    expect(ctrl.allProjects.map(project => project.id)).toEqual(['current']);
    expect(mocks.get.mock.calls.every(([path]) => path.startsWith('/api/v1/admin/projects/names?domain_id='))).toBe(true);
    ctrl.dispose();
  });
  it('rejects foreign project catalogs and preserves native project lookup denial', async () => {
    const ctrl = createAdminAnnouncementsController(options); await ctrl.loadDomains();
    mocks.get.mockResolvedValue([{ id: 'foreign', name: 'Foreign', domain_id: 'b' }]);
    ctrl.selectDomain('a', 'project');
    await vi.waitFor(() => expect(ctrl.projectsError).not.toBe(''));
    expect(ctrl.allProjects).toEqual([]);
    mocks.get.mockRejectedValue(new ApiError(403, 'native_project_denied'));
    await ctrl.loadProjects(); expect(ctrl.projectsError).toBe('native_project_denied'); ctrl.dispose();
  });
  it('cannot publish a project-target creation result after the selected domain changes', async () => {
    const ctrl = createAdminAnnouncementsController(options); await ctrl.loadDomains();
    mocks.get.mockResolvedValue([{ id: 'target', name: 'Target', domain_id: 'a' }]); ctrl.selectDomain('a', 'project');
    await vi.waitFor(() => expect(ctrl.projectsLoading).toBe(false));
    const pending = Promise.withResolvers<unknown>(); mocks.post.mockReturnValueOnce(pending.promise);
    const saving = ctrl.create({ title: 'Maintenance', body: 'Notice', severity: 'info', target_type: 'project', target_id: 'target', starts_at: null, ends_at: null });
    ctrl.selectDomain('', 'project'); pending.resolve({});
    expect(await saving).toEqual({ status: 'invalid' }); expect(ctrl.allProjects).toEqual([]); ctrl.dispose();
  });
  it.each(['domain', 'authority'] as const)('drops creation success and refreshed rows when %s changes during the post-create GET', async transition => {
    let token = 'token';
    const ctrl = createAdminAnnouncementsController({ token: () => token, projectId: options.projectId });
    await ctrl.loadDomains();
    mocks.get.mockResolvedValue([{ id: 'target', name: 'Target', domain_id: 'a' }]); ctrl.selectDomain('a', 'project');
    await vi.waitFor(() => expect(ctrl.projectsLoading).toBe(false));
    const refresh = Promise.withResolvers<unknown>();
    mocks.post.mockResolvedValue({}); mocks.get.mockReturnValueOnce(refresh.promise);
    const saving = ctrl.create({ title: 'Maintenance', body: 'Notice', severity: 'info', target_type: 'project', target_id: 'target', starts_at: null, ends_at: null });
    await vi.waitFor(() => expect(mocks.get).toHaveBeenCalledWith('/api/v1/admin/announcements', 'token', 'project'));
    if (transition === 'authority') token = 'replacement-token';
    ctrl.selectDomain('', 'project');
    refresh.resolve([{ id: 99, title: 'Obsolete refresh' }]);
    expect(await saving).toEqual({ status: 'invalid' }); expect(ctrl.announcements).toEqual([]); expect(ctrl.error).toBe(''); ctrl.dispose();
  });

  it('passes the passive domain context through the directory helper', async () => {
    const experience = { actionId: 'domain-directory' };
    mocks.begin.mockReturnValue(experience);
    const ctrl = createAdminAnnouncementsController(options);
    await ctrl.loadDomains();
    expect(mocks.list).toHaveBeenCalledWith({ token: 'token', projectId: 'project' }, { experience });
    expect(mocks.applied).toHaveBeenCalledWith(experience, {}, expect.any(Function));
    ctrl.dispose();
  });

  it.each(['user', 'project'] as const)('does not treat a %s retry button MouseEvent as an inherited context', async target => {
    const ctrl = createAdminAnnouncementsController(options);
    await ctrl.loadDomains();
    mocks.get.mockResolvedValue(target === 'user' ? { items: [], next_marker: null } : []);
    ctrl.selectDomain('a', target);
    await vi.waitFor(() => expect(target === 'user' ? ctrl.usersLoading : ctrl.projectsLoading).toBe(false));
    vi.clearAllMocks();
    const experience = { actionId: 'manual-retry' };
    mocks.begin.mockReturnValue(experience);
    const retry: (event: MouseEvent) => Promise<void> = target === 'user' ? ctrl.loadUsers : ctrl.loadProjects;
    await retry(new MouseEvent('click'));
    expect(mocks.withExperience).toHaveBeenCalledExactlyOnceWith(experience);
    expect(mocks.begin).toHaveBeenCalledExactlyOnceWith('iam', 'resource.list');
    ctrl.dispose();
  });

  it('discards a superseded primary load rather than applying obsolete or empty state', async () => {
    const oldExperience = { actionId: 'old' }, currentExperience = { actionId: 'current' };
    mocks.begin.mockReturnValueOnce(oldExperience).mockReturnValueOnce(currentExperience);
    const pending = Promise.withResolvers<unknown>();
    mocks.get.mockReturnValueOnce(pending.promise).mockResolvedValueOnce([{ id: 2 }]);
    const ctrl = createAdminAnnouncementsController(options);
    const oldLoad = ctrl.load(); await ctrl.load();
    pending.resolve([{ id: 1, title: 'private-obsolete-title' }]); await oldLoad;
    expect(ctrl.announcements.map(row => row.id)).toEqual([2]);
    expect(mocks.discarded).toHaveBeenCalledWith(oldExperience, 'stale');
    expect(mocks.applied.mock.calls.filter(call => call[0] === oldExperience)).toEqual([]);
    expect(mocks.applied).toHaveBeenCalledWith(currentExperience, {}, expect.any(Function));
    expect(JSON.stringify([mocks.state.mock.calls, mocks.discarded.mock.calls])).not.toContain('private-obsolete-title');
    ctrl.dispose();
  });

  it('carries the create context through readback while keeping mutation replay options unchanged', async () => {
    const experience = { actionId: 'create' };
    mocks.begin.mockReturnValue(experience); mocks.post.mockResolvedValue({}); mocks.get.mockResolvedValue([]);
    const ctrl = createAdminAnnouncementsController(options);
    const payload = { title: 'private-title', body: 'private-body', severity: 'info' as const, target_type: 'all' as const, target_id: null, starts_at: null, ends_at: null };
    expect(await ctrl.create(payload)).toEqual({ status: 'ok' });
    expect(mocks.begin).toHaveBeenCalledExactlyOnceWith('admin', 'create', 'resource.list');
    expect(mocks.withExperience.mock.calls).toEqual([[experience], [experience]]);
    expect(mocks.post).toHaveBeenCalledWith('/api/v1/admin/announcements', payload, 'token', 'project', { cache: 'no-store', replayOnUnauthorized: false });
    expect(mocks.state).toHaveBeenLastCalledWith(experience, 'empty');
    expect(JSON.stringify([mocks.begin.mock.calls, mocks.state.mock.calls, mocks.applied.mock.calls])).not.toMatch(/private-title|private-body/);
    ctrl.dispose();
  });

  it('describes uncertain writes as an error view, never as an inferred failed business operation', async () => {
    const experience = { actionId: 'unknown-write' };
    mocks.begin.mockReturnValue(experience); mocks.post.mockRejectedValue(new TypeError('private-transport-error'));
    const ctrl = createAdminAnnouncementsController(options);
    const result = await ctrl.create({ title: 'private-title', body: 'private-body', severity: 'info', target_type: 'all', target_id: null, starts_at: null, ends_at: null });
    expect(result.status).toBe('indeterminate');
    expect(mocks.state).toHaveBeenLastCalledWith(experience, 'error');
    expect(JSON.stringify([mocks.state.mock.calls, mocks.applied.mock.calls])).not.toMatch(/private-|failed|succeeded/);
    ctrl.dispose();
  });
});

describe('announcement email intent and logical owner', () => {
  const payload = { title: 'Scheduled maintenance', body: 'Plain text', severity: 'info' as const, target_type: 'all' as const, starts_at: '2099-01-01T00:00:00Z', send_email: true, email_operation_id: 'd06803e9-63c6-4a4f-a1ad-af62f2b08250' };
  const emailOperation = { operation_id: payload.email_operation_id, kind: 'announcement', status: 'pending', counts: { pending: 2, dispatching: 0, accepted: 0, failed: 0, unknown: 0, cancelled: 0 } };
  it('preserves explicit scheduled email intent and publishes the durable operation receipt', async () => {
    const ctrl = createAdminAnnouncementsController(options);
    mocks.post.mockResolvedValue({ id: 42, email_operation: emailOperation }); mocks.get.mockResolvedValue([]);
    expect(await ctrl.create(payload)).toEqual({ status: 'ok' });
    expect(mocks.post).toHaveBeenCalledWith('/api/v1/admin/announcements', payload, 'token', 'project', { cache: 'no-store', replayOnUnauthorized: false });
    expect(ctrl.emailOperation).toEqual(emailOperation); ctrl.dispose();
  });
  it('preserves accepted creation through same-owner bearer renewal and uses the fresh token for readback', async () => {
    let token = 'token';
    const ctrl = createAdminAnnouncementsController({ token: () => token, projectId: options.projectId, ownerKey: () => 'logical-login', ownerEpoch: () => 1 });
    const pending = Promise.withResolvers<unknown>(); mocks.post.mockReturnValueOnce(pending.promise); mocks.get.mockResolvedValue([]);
    const saving = ctrl.create(payload); token = 'renewed-token'; pending.resolve({ id: 42, email_operation: emailOperation });
    expect(await saving).toEqual({ status: 'ok' }); expect(ctrl.emailOperation).toEqual(emailOperation);
    expect(mocks.get).toHaveBeenCalledWith('/api/v1/admin/announcements', 'renewed-token', 'project'); ctrl.dispose();
  });
  it('discards late email receipts after synchronous logical-owner ABA and never overlaps creation', async () => {
    let epoch = 1;
    const ctrl = createAdminAnnouncementsController({ ...options, ownerKey: () => 'logical-login', ownerEpoch: () => epoch });
    const pending = Promise.withResolvers<unknown>(); mocks.post.mockReturnValueOnce(pending.promise);
    const saving = ctrl.create(payload); expect(await ctrl.create(payload)).toEqual({ status: 'invalid' }); expect(mocks.post).toHaveBeenCalledTimes(1);
    epoch++; ctrl.invalidateOwner(); epoch++; ctrl.invalidateOwner();
    pending.resolve({ id: 42, email_operation: emailOperation });
    expect(await saving).toEqual({ status: 'invalid' }); expect(ctrl.emailOperation).toBeNull(); expect(ctrl.announcements).toEqual([]); ctrl.dispose();
  });
  it.each([
    [new ApiError(422, 'private-validation-text', 'mail_invalid_schedule'), 'rejected'],
    [new ApiError(503, 'private-identity-text', 'mail_identity_unavailable'), 'rejected'],
    [new ApiError(503, 'private-storage-text', 'mail_storage_unavailable'), 'indeterminate'],
    [new Error('private-network-text'), 'indeterminate'],
  ] as const)('distinguishes rejected intents from uncertain enqueue without displaying raw errors', async (error, status) => {
    const ctrl = createAdminAnnouncementsController(options); mocks.post.mockRejectedValueOnce(error);
    expect(await ctrl.create(payload)).toEqual({ status });
    expect(ctrl.createError).not.toContain('private-'); expect(ctrl.creating).toBe(false); ctrl.dispose();
  });
});
