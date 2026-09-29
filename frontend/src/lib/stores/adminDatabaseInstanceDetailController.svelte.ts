import { confirmDialog } from '$lib/stores/confirm.svelte';
import { api, ApiError } from '$lib/api/client';
import { goto } from '$app/navigation';
import type { DbInstance, DbDatabase, DbUser, DbBackup } from '$lib/types/database';
import { toast } from '$lib/stores/toast';

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


  async function loadAll() {
    loading = true;
    await Promise.allSettled([
      api.get<DbInstance>(`/api/v1/database-instances/${id()}`, tok(), pid())
        .then(v => { instance = v; loading = false; })
        .catch(() => { instance = null; loading = false; }),
      api.get<DbDatabase[]>(`/api/v1/database-instances/${id()}/databases`, tok(), pid())
        .then(v => { databases = v; })
        .catch(() => {}),
      api.get<DbUser[]>(`/api/v1/database-instances/${id()}/users`, tok(), pid())
        .then(v => { users = v; })
        .catch(() => {}),
      api.get<DbBackup[]>(`/api/v1/database-instances/${id()}/backups`, tok(), pid())
        .then(v => { backups = v; })
        .catch(() => {}),
    ]);
    loading = false;
  }

  async function deleteInstance() {
    if (!await confirmDialog(`DB 인스턴스 "${instance?.name}"를 삭제하시겠습니까?`)) return;
    deleting = true;
    try {
      await api.delete(`/api/v1/database-instances/${id()}`, tok(), pid());
      goto('/admin/database-instances');
    } catch (e) {
      toast.error('삭제 실패: ' + (e instanceof ApiError ? e.message : String(e)));
      deleting = false;
    }
  }

  async function enableRoot() {
    enablingRoot = true;
    try {
      rootInfo = await api.post<{ name: string; password: string }>(`/api/v1/database-instances/${id()}/root`, {}, tok(), pid());
    } catch (e) {
      toast.error('root 활성화 실패: ' + (e instanceof ApiError ? e.message : String(e)));
    } finally { enablingRoot = false; }
  }

  async function createDb(form: { name: string; character_set: string; collate: string }): Promise<boolean> {
    creatingDb = true; dbError = '';
    try {
      await api.post(`/api/v1/database-instances/${id()}/databases`, form, tok(), pid());
      databases = await api.get<DbDatabase[]>(`/api/v1/database-instances/${id()}/databases`, tok(), pid());
      return true;
    } catch (e) { dbError = e instanceof ApiError ? e.message : '실패'; return false; }
    finally { creatingDb = false; }
  }

  async function deleteDb(name: string) {
    if (!await confirmDialog(`데이터베이스 "${name}"를 삭제하시겠습니까?`)) return;
    deletingDb = name;
    try {
      await api.delete(`/api/v1/database-instances/${id()}/databases/${encodeURIComponent(name)}`, tok(), pid());
      databases = databases.filter(d => d.name !== name);
    } catch (e) { toast.error('삭제 실패: ' + (e instanceof ApiError ? e.message : String(e))); }
    finally { deletingDb = null; }
  }

  async function createUser(form: { name: string; password: string; databases: string }): Promise<boolean> {
    creatingUser = true; userError = '';
    try {
      const dbs = form.databases.split(',').map(s => s.trim()).filter(Boolean);
      await api.post(`/api/v1/database-instances/${id()}/users`, { ...form, databases: dbs }, tok(), pid());
      users = await api.get<DbUser[]>(`/api/v1/database-instances/${id()}/users`, tok(), pid());
      return true;
    } catch (e) { userError = e instanceof ApiError ? e.message : '실패'; return false; }
    finally { creatingUser = false; }
  }

  async function deleteUser(name: string) {
    if (!await confirmDialog(`유저 "${name}"를 삭제하시겠습니까?`)) return;
    deletingUser = name;
    try {
      await api.delete(`/api/v1/database-instances/${id()}/users/${encodeURIComponent(name)}`, tok(), pid());
      users = users.filter(u => u.name !== name);
    } catch (e) { toast.error('삭제 실패: ' + (e instanceof ApiError ? e.message : String(e))); }
    finally { deletingUser = null; }
  }

  async function createBackup(form: { name: string; description: string }): Promise<boolean> {
    creatingBackup = true; backupError = '';
    try {
      await api.post(`/api/v1/database-instances/${id()}/backups`, form, tok(), pid());
      backups = await api.get<DbBackup[]>(`/api/v1/database-instances/${id()}/backups`, tok(), pid());
      return true;
    } catch (e) { backupError = e instanceof ApiError ? e.message : '실패'; return false; }
    finally { creatingBackup = false; }
  }

  async function deleteBackup(backupId: string) {
    if (!await confirmDialog('백업을 삭제하시겠습니까?')) return;
    deletingBackup = backupId;
    try {
      await api.delete(`/api/v1/database-instances/backups/${backupId}`, tok(), pid());
      backups = backups.filter(b => b.id !== backupId);
    } catch (e) { toast.error('삭제 실패: ' + (e instanceof ApiError ? e.message : String(e))); }
    finally { deletingBackup = null; }
  }

  async function restoreBackup(backupId: string) {
    const name = prompt('복원할 새 인스턴스 이름:');
    if (!name) return;
    restoringBackup = backupId;
    try {
      await api.post('/api/v1/database-instances/restore', {
        backup_id: backupId, name,
        flavor_id: instance?.flavor_id ?? '',
        volume_size: instance?.size ?? 5,
      }, tok(), pid());
      toast.success('복원 인스턴스 생성이 시작되었습니다.');
      goto('/admin/database-instances');
    } catch (e) { toast.error('복원 실패: ' + (e instanceof ApiError ? e.message : String(e))); }
    finally { restoringBackup = null; }
  }

  return {
    get instance() { return instance; },
    get databases() { return databases; },
    get users() { return users; },
    get backups() { return backups; },
    get loading() { return loading; },
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
