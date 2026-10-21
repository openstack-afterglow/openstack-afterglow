import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createAdminAnnouncementsController } from '../adminAnnouncementsController.svelte';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { ApiError } from '$lib/api/errors';
import type * as ClientModule from '$lib/api/client';
import type * as DomainsModule from '$lib/api/domains';
const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), list: vi.fn() }));
vi.mock('$lib/api/client', async (importOriginal) => ({ ...(await importOriginal<typeof ClientModule>()), api: mocks }));
vi.mock('$lib/api/domains', async (importOriginal) => ({ ...(await importOriginal<typeof DomainsModule>()), domainsApi: { list: mocks.list } }));
const options = { token: () => 'token', projectId: () => 'project' };
beforeEach(() => {
  vi.resetAllMocks(); initLocale('en');
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
    expect(await ctrl.create(payload)).toBe(true);
    expect(mocks.post).toHaveBeenCalledWith('/api/v1/admin/announcements', payload, 'token', 'project');
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
    expect(await ctrl.create({ title: 'Maintenance', body: 'Notice', severity: 'info', target_type: 'project', target_id: 'project-a', starts_at: null, ends_at: null })).toBe(false);
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
    expect(await saving).toBe(false); expect(ctrl.allProjects).toEqual([]); ctrl.dispose();
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
    expect(await saving).toBe(false); expect(ctrl.announcements).toEqual([]); expect(ctrl.error).toBe(''); ctrl.dispose();
  });
});
