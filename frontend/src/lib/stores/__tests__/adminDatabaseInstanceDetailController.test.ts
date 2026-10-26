import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createAdminDatabaseInstanceDetailController } from '../adminDatabaseInstanceDetailController.svelte';
import { render, screen } from '@testing-library/svelte';
import { ApiError } from '$lib/api/client';
import DbDatabasesSection from '$lib/components/admin/database-instances/id/DbDatabasesSection.svelte';
import DbUsersSection from '$lib/components/admin/database-instances/id/DbUsersSection.svelte';
import DbBackupsSection from '$lib/components/admin/database-instances/id/DbBackupsSection.svelte';

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn(), confirm: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: mocks, ApiError: class extends Error {} }));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: mocks.confirm }));
vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$lib/stores/toast', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

let owner: string | undefined;
const options = { instanceId: () => 'db', token: () => 'token', projectId: () => 'personal' };
beforeEach(() => {
  vi.clearAllMocks(); owner = 'foreign';
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
});
