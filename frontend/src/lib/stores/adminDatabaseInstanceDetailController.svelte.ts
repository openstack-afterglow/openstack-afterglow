import { t as tr } from '$lib/i18n/ns/database';
import { confirmDialog } from '$lib/stores/confirm.svelte';
import { api, ApiError } from '$lib/api/client';
import { goto } from '$app/navigation';
import type { DbInstance, DbDatabase, DbUser, DbBackup } from '$lib/types/database';
import { toast } from '$lib/stores/toast';
import { beginExperienceAction, beginExperienceLoad, experienceState, experienceApplied, experienceDiscarded, type ExperienceAction } from '$lib/utils/experience';

export interface AdminDbInstanceDetailOpts {
  instanceId: () => string;
  token: () => string | undefined;
  projectId: () => string | undefined;
}

export function createAdminDatabaseInstanceDetailController(opts: AdminDbInstanceDetailOpts) {
  let instance = $state<DbInstance | null>(null);
  let databases = $state<DbDatabase[]>([]);
  let users = $state<DbUser[]>([]);
  let backups = $state<DbBackup[]>([]);
  let loading = $state(true);
  let loadError = $state('');
  let databasesReadError = $state('');
  let usersReadError = $state('');
  let backupsReadError = $state('');
  let rootInfo = $state<{ name: string; password: string } | null>(null);
  let enablingRoot = $state(false);
  let creatingDb = $state(false);
  let dbError = $state('');
  let deletingDb = $state<string | null>(null);
  let creatingUser = $state(false);
  let userError = $state('');
  let deletingUser = $state<string | null>(null);
  let creatingBackup = $state(false);
  let backupError = $state('');
  let deletingBackup = $state<string | null>(null);
  let restoringBackup = $state<string | null>(null);
  let deleting = $state(false);

  const id = opts.instanceId;
  const tok = opts.token;
  const pid = opts.projectId;

  const canMutate = $derived(instance?.id === id() && !!instance?.project_id && instance.project_id === pid());

  // No mounted/generation owner exists here: record actual assignment, not DOM commit.
  // The collector still fences the captured authenticated owner.
  function observe(action: ExperienceAction) {
    const experience = action === 'load'
      ? beginExperienceLoad('admin', 'resource.detail')
      : beginExperienceAction('admin', action, 'resource.detail');
    return {
      experience,
      request: experience ? api.withExperience(experience) : api,
      applied(state: 'ready' | 'empty' | 'error') {
        experienceState(experience, state);
        void experienceApplied(experience);
      },
    };
  }

  async function loadAll() {
    const observation = observe('load');
    loading = true;
    experienceState(observation.experience, 'loading');
    await Promise.allSettled([
      observation.request.get<DbInstance>(`/api/v1/admin/database-instances/${id()}`, tok(), pid())
        .then(v => { instance = v; loadError = ''; })
        .catch(e => { instance = null; loadError = e instanceof ApiError ? e.message : tr('errors.failed'); }),
      observation.request.get<DbDatabase[]>(`/api/v1/admin/database-instances/${id()}/databases`, tok(), pid())
        .then(v => { databases = v; databasesReadError = ''; })
        .catch(e => { databases = []; databasesReadError = e instanceof ApiError ? e.message : tr('errors.failed'); }),
      observation.request.get<DbUser[]>(`/api/v1/admin/database-instances/${id()}/users`, tok(), pid())
        .then(v => { users = v; usersReadError = ''; })
        .catch(e => { users = []; usersReadError = e instanceof ApiError ? e.message : tr('errors.failed'); }),
      observation.request.get<DbBackup[]>(`/api/v1/admin/database-instances/${id()}/backups`, tok(), pid())
        .then(v => { backups = v; backupsReadError = ''; })
        .catch(e => { backups = []; backupsReadError = e instanceof ApiError ? e.message : tr('errors.failed'); }),
    ]);
    loading = false;
    observation.applied(loadError || databasesReadError || usersReadError || backupsReadError ? 'error' : instance ? 'ready' : 'empty');
  }

  async function deleteInstance() {
    if (!canMutate) return;
    const observation = observe('delete');
    if (!await confirmDialog(tr('instances.deleteConfirm', { name: String(instance?.name) }))) { experienceDiscarded(observation.experience, 'aborted'); return; }
    deleting = true;
    experienceState(observation.experience, 'loading');
    try {
      await observation.request.delete(`/api/v1/database-instances/${id()}`, tok(), pid());
      goto('/admin/database-instances');
    } catch (e) {
      toast.error(tr('errors.delete', { error: e instanceof ApiError ? e.message : String(e) }));
      deleting = false;
      observation.applied('error');
    }
  }

  async function enableRoot() {
    if (!canMutate) return;
    const observation = observe('update');
    enablingRoot = true;
    experienceState(observation.experience, 'loading');
    try {
      rootInfo = await observation.request.post<{ name: string; password: string }>(`/api/v1/database-instances/${id()}/root`, {}, tok(), pid());
      observation.applied('ready');
    } catch (e) {
      toast.error(tr('errors.root', { error: e instanceof ApiError ? e.message : String(e) }));
      observation.applied('error');
    } finally { enablingRoot = false; }
  }

  async function createDb(form: { name: string; character_set: string; collate: string }): Promise<boolean> {
    if (!canMutate) return false;
    const observation = observe('create');
    creatingDb = true; dbError = '';
    experienceState(observation.experience, 'loading');
    try {
      await observation.request.post(`/api/v1/database-instances/${id()}/databases`, form, tok(), pid());
      databases = await observation.request.get<DbDatabase[]>(`/api/v1/admin/database-instances/${id()}/databases`, tok(), pid());
      observation.applied(databases.length ? 'ready' : 'empty');
      return true;
    } catch (e) { dbError = e instanceof ApiError ? e.message : tr('errors.failed'); observation.applied('error'); return false; }
    finally { creatingDb = false; }
  }

  async function deleteDb(name: string) {
    if (!canMutate) return;
    const observation = observe('delete');
    if (!await confirmDialog(tr('databases.deleteConfirm', { name: name }))) { experienceDiscarded(observation.experience, 'aborted'); return; }
    deletingDb = name;
    experienceState(observation.experience, 'loading');
    try {
      await observation.request.delete(`/api/v1/database-instances/${id()}/databases/${encodeURIComponent(name)}`, tok(), pid());
      databases = databases.filter(d => d.name !== name);
      observation.applied(databases.length ? 'ready' : 'empty');
    } catch (e) { toast.error(tr('errors.delete', { error: e instanceof ApiError ? e.message : String(e) })); observation.applied('error'); }
    finally { deletingDb = null; }
  }

  async function createUser(form: { name: string; password: string; databases: string }): Promise<boolean> {
    if (!canMutate) return false;
    const observation = observe('create');
    creatingUser = true; userError = '';
    experienceState(observation.experience, 'loading');
    try {
      const dbs = form.databases.split(',').map(s => s.trim()).filter(Boolean);
      await observation.request.post(`/api/v1/database-instances/${id()}/users`, { ...form, databases: dbs }, tok(), pid());
      users = await observation.request.get<DbUser[]>(`/api/v1/admin/database-instances/${id()}/users`, tok(), pid());
      observation.applied(users.length ? 'ready' : 'empty');
      return true;
    } catch (e) { userError = e instanceof ApiError ? e.message : tr('errors.failed'); observation.applied('error'); return false; }
    finally { creatingUser = false; }
  }

  async function deleteUser(name: string) {
    if (!canMutate) return;
    const observation = observe('delete');
    if (!await confirmDialog(tr('users.deleteConfirm', { name: name }))) { experienceDiscarded(observation.experience, 'aborted'); return; }
    deletingUser = name;
    experienceState(observation.experience, 'loading');
    try {
      await observation.request.delete(`/api/v1/database-instances/${id()}/users/${encodeURIComponent(name)}`, tok(), pid());
      users = users.filter(u => u.name !== name);
      observation.applied(users.length ? 'ready' : 'empty');
    } catch (e) { toast.error(tr('errors.delete', { error: e instanceof ApiError ? e.message : String(e) })); observation.applied('error'); }
    finally { deletingUser = null; }
  }

  async function createBackup(form: { name: string; description: string }): Promise<boolean> {
    if (!canMutate) return false;
    const observation = observe('create');
    creatingBackup = true; backupError = '';
    experienceState(observation.experience, 'loading');
    try {
      await observation.request.post(`/api/v1/database-instances/${id()}/backups`, form, tok(), pid());
      backups = await observation.request.get<DbBackup[]>(`/api/v1/admin/database-instances/${id()}/backups`, tok(), pid());
      observation.applied(backups.length ? 'ready' : 'empty');
      return true;
    } catch (e) { backupError = e instanceof ApiError ? e.message : tr('errors.failed'); observation.applied('error'); return false; }
    finally { creatingBackup = false; }
  }

  async function deleteBackup(backupId: string) {
    if (!canMutate) return;
    const observation = observe('delete');
    if (!await confirmDialog(tr('backups.deleteConfirm'))) { experienceDiscarded(observation.experience, 'aborted'); return; }
    deletingBackup = backupId;
    experienceState(observation.experience, 'loading');
    try {
      await observation.request.delete(`/api/v1/database-instances/backups/${backupId}`, tok(), pid());
      backups = backups.filter(b => b.id !== backupId);
      observation.applied(backups.length ? 'ready' : 'empty');
    } catch (e) { toast.error(tr('errors.delete', { error: e instanceof ApiError ? e.message : String(e) })); observation.applied('error'); }
    finally { deletingBackup = null; }
  }

  async function restoreBackup(backupId: string) {
    if (!canMutate) return;
    const name = prompt(tr('restore.namePrompt'));
    if (!name) return;
    const observation = observe('create');
    restoringBackup = backupId;
    experienceState(observation.experience, 'loading');
    try {
      await observation.request.post('/api/v1/database-instances/restore', {
        backup_id: backupId, name,
        flavor_id: instance?.flavor_id ?? '',
        volume_size: instance?.size ?? 5,
      }, tok(), pid());
      toast.success(tr('restore.started'));
      observation.applied('ready');
      goto('/admin/database-instances');
    } catch (e) { toast.error(tr('errors.restore', { error: e instanceof ApiError ? e.message : String(e) })); observation.applied('error'); }
    finally { restoringBackup = null; }
  }

  return {
    get instance() { return instance; },
    get databases() { return databases; },
    get users() { return users; },
    get backups() { return backups; },
    get loading() { return loading; },
    get loadError() { return loadError; },
    get databasesReadError() { return databasesReadError; },
    get usersReadError() { return usersReadError; },
    get backupsReadError() { return backupsReadError; },
    get canMutate() { return canMutate; },
    get rootInfo() { return rootInfo; },
    get enablingRoot() { return enablingRoot; },
    get creatingDb() { return creatingDb; },
    get dbError() { return dbError; },
    get deletingDb() { return deletingDb; },
    get creatingUser() { return creatingUser; },
    get userError() { return userError; },
    get deletingUser() { return deletingUser; },
    get creatingBackup() { return creatingBackup; },
    get backupError() { return backupError; },
    get deletingBackup() { return deletingBackup; },
    get restoringBackup() { return restoringBackup; },
    get deleting() { return deleting; },
    loadAll,
    deleteInstance,
    enableRoot,
    createDb,
    deleteDb,
    createUser,
    deleteUser,
    createBackup,
    deleteBackup,
    restoreBackup,
  };
}
