import { t as tr } from '$lib/i18n/ns/database';
import { getContext, setContext } from 'svelte';
import { api, ApiError } from '$lib/api/client';
import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
import { confirmDialog } from '$lib/stores/confirm.svelte';
import { toast } from '$lib/stores/toast';
import type { DbInstance, DbFlavor, DbDatabase, DbUser, DbBackup } from '$lib/types/database';
import type { FloatingIp } from '$lib/types/networks';
import { beginExperienceAction, beginExperienceLoad, experienceRequest, experienceState, experienceApplied, type ExperienceAction, type ExperienceContext } from '$lib/utils/experience';
import { intlLocale } from '$lib/i18n/runtime.svelte';
import { createTableView } from '$lib/utils/tableView.svelte';
import { dbBackupColumns, dbDatabaseColumns, dbUserColumns } from '$lib/utils/databaseTableColumns';

export interface DbInstanceDetailControllerOpts {
	instanceId: () => string;
	token: () => string | undefined;
	projectId: () => string | undefined;
	onDeleted?: () => void;
}

export function createDbInstanceDetailController(opts: DbInstanceDetailControllerOpts) {
	// Domain state
	let instance = $state<DbInstance | null>(null);
	let instanceReadError = $state('');
	let databases = $state<DbDatabase[]>([]);
	let users = $state<DbUser[]>([]);
	let backups = $state<DbBackup[]>([]);
	let flavors = $state<DbFlavor[]>([]);
	let floatingIps = $state<FloatingIp[]>([]);
	let rootInfo = $state<{ name: string; password: string } | null>(null);
	let loading = $state(true);
	let enablingRoot = $state(false);
	let deleting = $state(false);
	let attachingFip = $state(false);
	let detachingFip = $state(false);
	let fipError = $state('');

	// Database sub-resource state
	let creatingDb = $state(false);
	let dbError = $state('');
	let deletingDb = $state<string | null>(null);

	// User sub-resource state
	let creatingUser = $state(false);
	let userError = $state('');
	let deletingUser = $state<string | null>(null);

	// Backup sub-resource state
	let creatingBackup = $state(false);
	let backupError = $state('');
	let deletingBackup = $state<string | null>(null);
	let restoringBackup = $state<string | null>(null);

	// Auto-backup state
	interface AutoBackupConfig {
		enabled: boolean;
		max_daily: number;
		max_weekly: number;
		max_monthly: number;
	}
	let autoBackupConfig = $state<AutoBackupConfig | null>(null);
	let loadingAutoBackup = $state(false);
	let savingAutoBackup = $state(false);
	let backupSearch = $state('');
	let userSearch = $state('');
	let databaseSearch = $state('');
	const backupView = createTableView({
		rows: () => backups, columns: () => dbBackupColumns(), search: () => backupSearch,
		searchable: (row) => [row.name, row.id, row.status, String(row.size ?? ''), row.created_at, row.description ?? ''], locale: intlLocale,
	});
	const userView = createTableView({
		rows: () => users, columns: dbUserColumns, search: () => userSearch, locale: intlLocale,
	});
	const databaseView = createTableView({
		rows: () => databases, columns: dbDatabaseColumns, search: () => databaseSearch, locale: intlLocale,
	});
	function observe(action: ExperienceAction, parent?: ExperienceContext) {
		const ctx = parent ? experienceRequest(parent).context ?? parent : (action === 'load' ? beginExperienceLoad('database', 'resource.detail') : beginExperienceAction('database', action, 'resource.detail'));
		return {
			ctx, client: api.withExperience(ctx),
			applied(state: 'ready' | 'empty' | 'error') {
				if (!ctx) return;
				if (ctx.action !== 'create' || state === 'error') experienceState(ctx, state);
				// Preserve actual assignments; this controller has no mounted-result guard.
				void experienceApplied(ctx);
			},
		};
	}

	// Derived
	const instanceFips = $derived.by(() => {
		const ips = instance?.ips ?? [];
		return floatingIps.filter(f => f.fixed_ip_address && ips.includes(f.fixed_ip_address));
	});
	const dsType = $derived(instance?.datastore?.type ?? '');
	const flavorDisplay = $derived.by(() => {
		const inst = instance;
		if (!inst?.flavor_id) return '-';
		const f = flavors.find(x => String(x.id) === String(inst.flavor_id));
		if (f) return `${f.name} (${f.vcpus}vCPU / ${f.ram}MB)`;
		const ramVcpu = inst.flavor_vcpus || inst.flavor_ram
			? ` (${inst.flavor_vcpus}vCPU / ${inst.flavor_ram}MB)` : '';
		return `${inst.flavor_id}${ramVcpu}`;
	});
	const dbPort = $derived(
		dsType === 'postgresql' ? '5432' :
		dsType === 'redis' ? '6379' :
		dsType === 'mongodb' ? '27017' : '3306'
	);
	const connectHost = $derived(
		instance ? (instance.ips?.[0] || instance.hostname || '<host>') : '<host>'
	);
	const connectCmd = $derived(
		instance
			? dsType === 'postgresql'
				? `psql -h ${connectHost} -p ${dbPort} -U <user> -d <database>`
				: dsType === 'redis'
				? `redis-cli -h ${connectHost} -p ${dbPort}`
				: `mysql -h ${connectHost} -P ${dbPort} -u <user> -p`
			: ''
	);

	async function loadAutoBackupConfig() {
		const observation = observe('load');
		const id = opts.instanceId();
		const tok = opts.token();
		const proj = opts.projectId();
		loadingAutoBackup = true;
		try {
			const cfg = await observation.client.get<AutoBackupConfig>(`/api/v1/database-instances/${id}/auto-backup`, tok, proj);
			autoBackupConfig = cfg;
			observation.applied('ready');
		} catch {
			autoBackupConfig = null;
			observation.applied('error');
		} finally {
			loadingAutoBackup = false;
		}
	}

	async function saveAutoBackupConfig(max_daily: number, max_weekly: number, max_monthly: number) {
		const observation = observe('update');
		const id = opts.instanceId();
		const tok = opts.token();
		const proj = opts.projectId();
		savingAutoBackup = true;
		try {
			const cfg = await observation.client.put<AutoBackupConfig>(
				`/api/v1/database-instances/${id}/auto-backup`,
				{ max_daily, max_weekly, max_monthly },
				tok, proj
			);
			autoBackupConfig = cfg;
			observation.applied('ready');
			toast.success(tr('auto.saved'));
		} catch (e) {
			toast.error(tr('errors.autoSave', { error: e instanceof ApiError ? e.message : String(e) }));
			observation.applied('error');
		} finally {
			savingAutoBackup = false;
		}
	}

	async function disableAutoBackup() {
		const observation = observe('delete');
		const id = opts.instanceId();
		const tok = opts.token();
		const proj = opts.projectId();
		savingAutoBackup = true;
		try {
			await observation.client.delete(`/api/v1/database-instances/${id}/auto-backup`, tok, proj);
			autoBackupConfig = null;
			observation.applied('empty');
			toast.success(tr('auto.disabled'));
		} catch (e) {
			toast.error(tr('errors.autoDisable', { error: e instanceof ApiError ? e.message : String(e) }));
			observation.applied('error');
		} finally {
			savingAutoBackup = false;
		}
	}

	// AutoRefresh
	const ar = createAutoRefresh(() => loadAll(), {
		storageKey: 'dashboard-db-instance-detail',
		invokeOnMount: false,
		defaultActive: true,
		defaultInterval: 15,
		intervalOptions: [10, 15, 30, 60],
	});

	// Handlers
	async function loadAll(parent?: ExperienceContext) {
		const ctx = parent ?? beginExperienceLoad('database', 'resource.detail');
		const detail = observe('load', ctx);
		const dbs = observe('load', ctx);
		const userList = observe('load', ctx);
		const backupList = observe('load', ctx);
		const floating = observe('load', ctx);
		const auto = observe('load', ctx);
		const flavorList = observe('load', ctx);
		experienceState(ctx, 'loading');
		const id = opts.instanceId();
		const tok = opts.token();
		const proj = opts.projectId();
		instanceReadError = '';
		loading = true;
		await Promise.allSettled([
			detail.client.get<DbInstance>(`/api/v1/database-instances/${id}`, tok, proj)
				.then(v => { instance = v; instanceReadError = ''; loading = false; detail.applied(v ? 'ready' : 'empty'); })
				.catch((error) => {
					instance = null;
					instanceReadError = error instanceof ApiError && error.status === 404 ? '' : tr('instances.loadFailed');
					loading = false;
					detail.applied(instanceReadError ? 'error' : 'empty');
				}),
			dbs.client.get<DbDatabase[]>(`/api/v1/database-instances/${id}/databases`, tok, proj)
				.then(v => { databases = v; dbs.applied(v.length ? 'ready' : 'empty'); })
				.catch(() => {}),
			userList.client.get<DbUser[]>(`/api/v1/database-instances/${id}/users`, tok, proj)
				.then(v => { users = v; userList.applied(v.length ? 'ready' : 'empty'); })
				.catch(() => {}),
			backupList.client.get<DbBackup[]>(`/api/v1/database-instances/${id}/backups`, tok, proj)
				.then(v => { backups = v; backupList.applied(v.length ? 'ready' : 'empty'); })
				.catch(() => {}),
			flavors.length === 0
				? flavorList.client.get<DbFlavor[]>('/api/v1/database-instances/flavors', tok, proj)
					.then(v => { flavors = v; flavorList.applied(v.length ? 'ready' : 'empty'); })
					.catch(() => {})
				: Promise.resolve(),
			floating.client.get<FloatingIp[]>('/api/v1/networks/floating-ips', tok, proj)
				.then(v => { floatingIps = v; floating.applied(v.length ? 'ready' : 'empty'); })
				.catch(() => {}),
			auto.client.get<AutoBackupConfig>(`/api/v1/database-instances/${id}/auto-backup`, tok, proj)
				.then(v => { autoBackupConfig = v; auto.applied('ready'); })
				.catch(() => { autoBackupConfig = null; auto.applied('error'); }),
		]);
		loading = false;
	}

	function reset() {
		instance = null;
		instanceReadError = '';
		databases = [];
		users = [];
		backups = [];
		rootInfo = null;
		loading = true;
		backupSearch = '';
		userSearch = '';
		databaseSearch = '';
		backupView.reset();
		userView.reset();
		databaseView.reset();
	}

	async function attachFip() {
		const observation = observe('attach');
		const id = opts.instanceId();
		const tok = opts.token();
		const proj = opts.projectId();
		attachingFip = true; fipError = '';
		try {
			await observation.client.post(`/api/v1/database-instances/${id}/floating-ip`, {}, tok, proj);
			floatingIps = await observation.client.get<FloatingIp[]>('/api/v1/networks/floating-ips', tok, proj);
			observation.applied(floatingIps.length ? 'ready' : 'empty');
		} catch (e) { fipError = e instanceof ApiError ? e.message : tr('errors.failed'); observation.applied('error'); }
		finally { attachingFip = false; }
	}

	async function detachFip(deleteFip: boolean) {
		const id = opts.instanceId();
		const tok = opts.token();
		const proj = opts.projectId();
		if (!(await confirmDialog(deleteFip ? tr('connection.deleteConfirm') : tr('connection.detachConfirm')))) return;
		const observation = observe('detach');
		detachingFip = true; fipError = '';
		try {
			await observation.client.delete(
				`/api/v1/database-instances/${id}/floating-ip${deleteFip ? '?delete=true' : ''}`,
				tok, proj
			);
			floatingIps = await observation.client.get<FloatingIp[]>('/api/v1/networks/floating-ips', tok, proj);
			observation.applied(floatingIps.length ? 'ready' : 'empty');
		} catch (e) { fipError = e instanceof ApiError ? e.message : tr('errors.failed'); observation.applied('error'); }
		finally { detachingFip = false; }
	}

	async function deleteInstance() {
		const id = opts.instanceId();
		const tok = opts.token();
		const proj = opts.projectId();
		if (!(await confirmDialog(tr('instances.deleteConfirm', { name: String(instance?.name) })))) return;
		const observation = observe('delete');
		deleting = true;
		try {
			await observation.client.delete(`/api/v1/database-instances/${id}`, tok, proj);
			opts.onDeleted?.();
		} catch (e) {
			toast.error(tr('errors.delete', { error: e instanceof ApiError ? e.message : String(e) }));
			deleting = false;
			observation.applied('error');
		}
	}

	async function enableRoot() {
		const observation = observe('update');
		const id = opts.instanceId();
		const tok = opts.token();
		const proj = opts.projectId();
		enablingRoot = true;
		try {
			rootInfo = await observation.client.post<{ name: string; password: string }>(
				`/api/v1/database-instances/${id}/root`, {}, tok, proj
			);
			observation.applied('ready');
		} catch (e) {
			toast.error(tr('errors.root', { error: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			enablingRoot = false;
		}
	}

	async function createDb(name: string) {
		const observation = observe('create');
		const id = opts.instanceId();
		const tok = opts.token();
		const proj = opts.projectId();
		creatingDb = true; dbError = '';
		try {
			const isMysqlLike = dsType.match(/^(mysql|mariadb|percona)/i);
			const payload = isMysqlLike
				? { name, character_set: 'utf8mb4', collate: 'utf8mb4_unicode_ci' }
				: { name };
			await observation.client.post(`/api/v1/database-instances/${id}/databases`, payload, tok, proj);
			databases = await observation.client.get<DbDatabase[]>(`/api/v1/database-instances/${id}/databases`, tok, proj);
			observation.applied(databases.length ? 'ready' : 'empty');
			return true;
		} catch (e) { dbError = e instanceof ApiError ? e.message : tr('errors.failed'); observation.applied('error'); return false; }
		finally { creatingDb = false; }
	}

	async function deleteDb(name: string) {
		const id = opts.instanceId();
		const tok = opts.token();
		const proj = opts.projectId();
		if (!(await confirmDialog(tr('databases.deleteConfirm', { name: name })))) return;
		const observation = observe('delete');
		deletingDb = name;
		try {
			await observation.client.delete(`/api/v1/database-instances/${id}/databases/${encodeURIComponent(name)}`, tok, proj);
			databases = databases.filter(d => d.name !== name);
			observation.applied(databases.length ? 'ready' : 'empty');
		} catch (e) { toast.error(tr('errors.delete', { error: e instanceof ApiError ? e.message : String(e) })); }
		finally { deletingDb = null; }
	}

	async function createUser(newUser: { name: string; password: string; host: string; dbNames: string[] }) {
		const observation = observe('create');
		const id = opts.instanceId();
		const tok = opts.token();
		const proj = opts.projectId();
		creatingUser = true; userError = '';
		try {
			await observation.client.post(`/api/v1/database-instances/${id}/users`, {
				name: newUser.name,
				password: newUser.password,
				host: newUser.host || '%',
				databases: newUser.dbNames,
			}, tok, proj);
			users = await observation.client.get<DbUser[]>(`/api/v1/database-instances/${id}/users`, tok, proj);
			observation.applied(users.length ? 'ready' : 'empty');
			return true;
		} catch (e) { userError = e instanceof ApiError ? e.message : tr('errors.failed'); observation.applied('error'); return false; }
		finally { creatingUser = false; }
	}

	async function deleteUser(u: DbUser) {
		const id = opts.instanceId();
		const tok = opts.token();
		const proj = opts.projectId();
		const host = u.host || '%';
		const label = host !== '%' ? `${u.name}@${host}` : u.name;
		if (!(await confirmDialog(tr('users.deleteConfirm', { name: label })))) return;
		const observation = observe('delete');
		deletingUser = label;
		try {
			const url = `/api/v1/database-instances/${id}/users/${encodeURIComponent(u.name)}`
				+ `?host=${encodeURIComponent(host)}`;
			await observation.client.delete(url, tok, proj);
			users = users.filter(x => !(x.name === u.name && x.host === u.host));
			observation.applied(users.length ? 'ready' : 'empty');
		} catch (e) { toast.error(tr('errors.delete', { error: e instanceof ApiError ? e.message : String(e) })); }
		finally { deletingUser = null; }
	}

	async function createBackup(name: string, description: string) {
		const observation = observe('create');
		const id = opts.instanceId();
		const tok = opts.token();
		const proj = opts.projectId();
		creatingBackup = true; backupError = '';
		try {
			await observation.client.post(`/api/v1/database-instances/${id}/backups`, { name, description }, tok, proj);
			backups = await observation.client.get<DbBackup[]>(`/api/v1/database-instances/${id}/backups`, tok, proj);
			observation.applied(backups.length ? 'ready' : 'empty');
			return true;
		} catch (e) {
			// POST가 타임아웃 등으로 실패해도 Trove에 백업이 실제로 생성됐을 수 있음.
			// 목록을 재조회해 해당 이름의 백업이 존재하면 성공으로 처리한다.
			try {
				const refreshed = await observation.client.get<DbBackup[]>(`/api/v1/database-instances/${id}/backups`, tok, proj);
				backups = refreshed;
				observation.applied(backups.length ? 'ready' : 'empty');
				if (refreshed.some(b => b.name === name)) {
					// 백업이 Trove에 실제로 생성됨 — 오류 표시 없이 성공 반환
					return true;
				}
			} catch { /* 목록 재조회 실패 시 아래 에러 표시로 진행 */ }
			backupError = e instanceof ApiError
				? e.message
				: tr('backups.timeout');
			observation.applied('error');
			return false;
		} finally { creatingBackup = false; }
	}

	async function deleteBackup(backupId: string) {
		const isLast = backups.length === 1;
		const msg = isLast
			? tr('backups.deleteLast')
			: tr('backups.deleteConfirm');
		if (!(await confirmDialog(msg))) return;
		const observation = observe('delete');
		const tok = opts.token();
		const proj = opts.projectId();
		deletingBackup = backupId;
		try {
			await observation.client.delete(`/api/v1/database-instances/backups/${backupId}`, tok, proj);
			backups = backups.filter(b => b.id !== backupId);
			observation.applied(backups.length ? 'ready' : 'empty');
		} catch (e) { toast.error(tr('errors.delete', { error: e instanceof ApiError ? e.message : String(e) })); }
		finally { deletingBackup = null; }
	}

	async function restoreBackup(backupId: string, name: string, flavorId: string, volumeSize: number) {
		const observation = observe('create');
		const tok = opts.token();
		const proj = opts.projectId();
		restoringBackup = backupId;
		let rejected = false;
		try {
			await observation.client.post('/api/v1/database-instances/restore', {
				backup_id: backupId, name,
				flavor_id: flavorId,
				volume_size: volumeSize,
			}, tok, proj);
			toast.success(tr('restore.started'));
			opts.onDeleted?.();
		} catch (e) { rejected = true; toast.error(tr('errors.restore', { error: e instanceof ApiError ? e.message : String(e) })); }
		finally {
			restoringBackup = null;
			// The restore form is idle after acceptance; the restored instance is not proven ready.
			observation.applied(rejected ? 'error' : 'ready');
		}
	}

	return {
		// AutoRefresh (직접 바인딩용)
		get ar() { return ar; },
		backupView,
		userView,
		databaseView,
		get backupSearch() { return backupSearch; },
		set backupSearch(value: string) { backupSearch = value; },
		get userSearch() { return userSearch; },
		set userSearch(value: string) { userSearch = value; },
		get databaseSearch() { return databaseSearch; },
		set databaseSearch(value: string) { databaseSearch = value; },

		// State getters
		get instance() { return instance; },
		get instanceReadError() { return instanceReadError; },
		get databases() { return databases; },
		get users() { return users; },
		get backups() { return backups; },
		get flavors() { return flavors; },
		get floatingIps() { return floatingIps; },
		get rootInfo() { return rootInfo; },
		get loading() { return loading; },
		get enablingRoot() { return enablingRoot; },
		get deleting() { return deleting; },
		get attachingFip() { return attachingFip; },
		get detachingFip() { return detachingFip; },
		get fipError() { return fipError; },
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
		get autoBackupConfig() { return autoBackupConfig; },
		get loadingAutoBackup() { return loadingAutoBackup; },
		get savingAutoBackup() { return savingAutoBackup; },

		// Derived getters
		get instanceFips() { return instanceFips; },
		get dsType() { return dsType; },
		get flavorDisplay() { return flavorDisplay; },
		get dbPort() { return dbPort; },
		get connectHost() { return connectHost; },
		get connectCmd() { return connectCmd; },

		// Setters (서브 컴포넌트에서 에러 초기화용)
		set dbError(v: string) { dbError = v; },
		set userError(v: string) { userError = v; },
		set backupError(v: string) { backupError = v; },

		// Handlers
		loadAll,
		reset,
		loadAutoBackupConfig,
		saveAutoBackupConfig,
		disableAutoBackup,
		attachFip,
		detachFip,
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

export type DbInstanceDetailController = ReturnType<typeof createDbInstanceDetailController>;

const DB_INSTANCE_DETAIL_KEY = Symbol('db-instance-detail');

export function provideDbInstanceDetailController(store: DbInstanceDetailController) {
	setContext(DB_INSTANCE_DETAIL_KEY, store);
}

export function useDbInstanceDetailController(): DbInstanceDetailController {
	const store = getContext<DbInstanceDetailController | undefined>(DB_INSTANCE_DETAIL_KEY);
	if (!store) throw new Error('useDbInstanceDetailController must be called within DbInstanceDetailPanel');
	return store;
}
