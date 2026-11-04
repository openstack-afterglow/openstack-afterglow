import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createAdminDatabaseInstanceDetailController } from '../adminDatabaseInstanceDetailController.svelte';
import { render, screen } from '@testing-library/svelte';
import { ApiError } from '$lib/api/client';
import DbDatabasesSection from '$lib/components/admin/database-instances/id/DbDatabasesSection.svelte';
import DbUsersSection from '$lib/components/admin/database-instances/id/DbUsersSection.svelte';
import DbBackupsSection from '$lib/components/admin/database-instances/id/DbBackupsSection.svelte';
import type * as ExperienceModule from '$lib/utils/experience';

const mocks = vi.hoisted(() => ({
  get: vi.fn(), post: vi.fn(), delete: vi.fn(), confirm: vi.fn(), withExperience: vi.fn(),
  begin: vi.fn(), state: vi.fn(), applied: vi.fn(), discarded: vi.fn(),
}));
vi.mock('$lib/api/client', () => ({ api: mocks, ApiError: class extends Error {} }));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: mocks.confirm }));
vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$lib/stores/toast', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('$lib/utils/experience', async (importOriginal) => ({
  ...(await importOriginal<typeof ExperienceModule>()),
  beginExperienceAction: mocks.begin, beginExperienceLoad: mocks.begin, experienceState: mocks.state, experienceApplied: mocks.applied,
  experienceDiscarded: mocks.discarded,
}));

let owner: string | undefined;
const options = { instanceId: () => 'db', token: () => 'token', projectId: () => 'personal' };
beforeEach(() => {
  vi.clearAllMocks(); owner = 'foreign';
  mocks.begin.mockReturnValue(undefined); mocks.withExperience.mockReturnValue(mocks); mocks.applied.mockReset();
  mocks.confirm.mockResolvedValue(true); mocks.post.mockResolvedValue({});
  mocks.get.mockImplementation((path: string) => Promise.resolve(path === '/api/v1/admin/database-instances/db'
    ? { id: 'db', name: 'DB', project_id: owner } : []));
});

describe('administrator database detail transport', () => {
  it('loads all foreign-project reads through explicit admin routes and guards every caller-native action', async () => {
    const controller = createAdminDatabaseInstanceDetailController(options);
    await controller.loadAll();
    expect(mocks.get.mock.calls.map(call => call[0])).toEqual([
      '/api/v1/admin/database-instances/db', '/api/v1/admin/database-instances/db/databases',
      '/api/v1/admin/database-instances/db/users', '/api/v1/admin/database-instances/db/backups',
    ]);
    expect(controller.instance?.project_id).toBe('foreign');
    expect(controller.canMutate).toBe(false);
    await controller.deleteInstance(); await controller.enableRoot();
    expect(await controller.createDb({ name: 'db', character_set: '', collate: '' })).toBe(false);
    await controller.deleteDb('db');
    expect(await controller.createUser({ name: 'user', password: 'pass', databases: '' })).toBe(false);
    await controller.deleteUser('user');
    expect(await controller.createBackup({ name: 'backup', description: '' })).toBe(false);
    await controller.deleteBackup('backup'); await controller.restoreBackup('backup');
    expect(mocks.post).not.toHaveBeenCalled(); expect(mocks.delete).not.toHaveBeenCalled();
    expect(mocks.confirm).not.toHaveBeenCalled();
  });

  it('keeps same-project writes caller-native and refreshes only administrator reads', async () => {
    owner = 'personal';
    const controller = createAdminDatabaseInstanceDetailController(options);
    await controller.loadAll();
    expect(controller.canMutate).toBe(true);
    expect(await controller.createDb({ name: 'new', character_set: '', collate: '' })).toBe(true);
    expect(await controller.createUser({ name: 'user', password: 'pass', databases: 'new' })).toBe(true);
    expect(await controller.createBackup({ name: 'backup', description: '' })).toBe(true);
    expect(mocks.post.mock.calls.map(call => call[0])).toEqual([
      '/api/v1/database-instances/db/databases', '/api/v1/database-instances/db/users', '/api/v1/database-instances/db/backups',
    ]);
    expect(mocks.get.mock.calls.every(call => String(call[0]).startsWith('/api/v1/admin/'))).toBe(true);
    expect(mocks.post.mock.calls.every(call => call[2] === 'token' && call[3] === 'personal')).toBe(true);
  });

  it('exposes child denials as section alerts instead of successful empty lists', async () => {
    mocks.get.mockImplementation((path: string) => path === '/api/v1/admin/database-instances/db'
      ? Promise.resolve({ id: 'db', project_id: 'foreign' }) : Promise.reject(new ApiError(502, 'native child unavailable')));
    const controller = createAdminDatabaseInstanceDetailController(options);
    await controller.loadAll();
    const shared = { addError: '', creating: false, canMutate: false, onAdd: vi.fn(), onDelete: vi.fn() };
    render(DbDatabasesSection, { props: { ...shared, databases: [], deletingDb: null, loadError: controller.databasesReadError } });
    render(DbUsersSection, { props: { ...shared, users: [], deletingUser: null, loadError: controller.usersReadError } });
    render(DbBackupsSection, { props: { ...shared, backups: [], deletingBackup: null, restoringBackup: null, onRestore: vi.fn(), loadError: controller.backupsReadError } });
    expect(screen.getAllByRole('alert')).toHaveLength(3);
    expect(controller.databasesReadError).not.toBe('');
    expect(controller.usersReadError).not.toBe('');
    expect(controller.backupsReadError).not.toBe('');
  });

  it('missing owner never enables native writes', async () => {
    owner = undefined;
    const controller = createAdminDatabaseInstanceDetailController(options);
    await controller.loadAll();
    expect(controller.canMutate).toBe(false);
    await controller.enableRoot(); expect(mocks.post).not.toHaveBeenCalled();
  });

  it('keeps partial read failures as error observations after the assigned section state', async () => {
    const experience = { actionId: 'read-action' };
    mocks.begin.mockReturnValue(experience);
    mocks.get.mockImplementation((path: string) => path.endsWith('/users')
      ? Promise.reject(new Error('private-native-error'))
      : Promise.resolve(path.endsWith('/db') ? { id: 'db', project_id: 'personal' } : []));
    const controller = createAdminDatabaseInstanceDetailController(options);
    const assignedErrors: string[] = [];
    mocks.applied.mockImplementation(() => { assignedErrors.push(controller.usersReadError); });
    await controller.loadAll();
    expect(mocks.withExperience).toHaveBeenCalledWith(experience);
    expect(mocks.state).toHaveBeenLastCalledWith(experience, 'error');
    expect(assignedErrors.at(-1)).toBe(controller.usersReadError);
    expect(mocks.applied).toHaveBeenCalledOnce();
    expect(controller.usersReadError).not.toBe('');
    // No mounted/current-result guard exists, so no DOM commitment is asserted.
    expect(mocks.applied.mock.calls.every(call => call.length === 1)).toBe(true);
    expect(JSON.stringify([mocks.state.mock.calls, mocks.applied.mock.calls])).not.toContain('private-native-error');
  });

  it('keeps a user creation and its administrator readback on one context without serializing credentials', async () => {
    owner = 'personal';
    const controller = createAdminDatabaseInstanceDetailController(options);
    await controller.loadAll();
    vi.clearAllMocks();
    const experience = { actionId: 'create-action' };
    mocks.begin.mockReturnValue(experience); mocks.withExperience.mockReturnValue(mocks);
    mocks.get.mockResolvedValue([{ name: 'private-user' }]);
    const snapshots: unknown[] = [];
    mocks.applied.mockImplementation(() => { snapshots.push(controller.users.map(user => user.name)); });
    expect(await controller.createUser({ name: 'private-user', password: 'private-password', databases: 'private-db' })).toBe(true);
    expect(mocks.begin).toHaveBeenCalledExactlyOnceWith('admin', 'create', 'resource.detail');
    expect(mocks.withExperience).toHaveBeenCalledExactlyOnceWith(experience);
    expect(snapshots).toEqual([['private-user']]);
    expect(mocks.state).toHaveBeenLastCalledWith(experience, 'ready');
    const telemetry = JSON.stringify([mocks.begin.mock.calls, mocks.state.mock.calls, mocks.applied.mock.calls]);
    expect(telemetry).not.toMatch(/private-user|private-password|private-db/);
  });

  it('does not invent a stale discard or DOM commitment for existing unguarded same-owner assignments', async () => {
    const experience = { actionId: 'old-detail' };
    mocks.begin.mockReturnValue(experience);
    let instanceId = 'db';
    const pending = Promise.withResolvers<unknown>();
    mocks.get.mockReturnValue(pending.promise);
    const controller = createAdminDatabaseInstanceDetailController({ ...options, instanceId: () => instanceId });
    const loading = controller.loadAll();
    instanceId = 'next-db';
    pending.resolve([]);
    await loading;
    expect(mocks.applied).toHaveBeenCalledWith(experience);
    expect(mocks.applied.mock.calls.every(call => call.length === 1)).toBe(true);
  });

  it('captures delete intent before confirmation and discards the same context on cancellation', async () => {
    owner = 'personal';
    const controller = createAdminDatabaseInstanceDetailController(options);
    await controller.loadAll(); vi.clearAllMocks();
    const experience = { actionId: 'confirmed-handler' };
    mocks.begin.mockReturnValue(experience);
    const confirmation = Promise.withResolvers<boolean>();
    mocks.confirm.mockReturnValueOnce(confirmation.promise);
    const deleting = controller.deleteDb('private-database');
    expect(mocks.state).not.toHaveBeenCalled();
    expect(mocks.begin).toHaveBeenCalledExactlyOnceWith('admin', 'delete', 'resource.detail');
    mocks.begin.mockReturnValue({ actionId: 'unrelated-action' });
    confirmation.resolve(false); await deleting;
    expect(mocks.discarded).toHaveBeenCalledExactlyOnceWith(experience, 'aborted');
    expect(mocks.state).not.toHaveBeenCalled();
    expect(mocks.delete).not.toHaveBeenCalled();
    expect(JSON.stringify(mocks.discarded.mock.calls)).not.toContain('private-database');
  });
});
