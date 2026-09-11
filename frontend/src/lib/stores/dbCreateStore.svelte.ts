import { setContext, getContext } from 'svelte';
import { get } from 'svelte/store';
import { auth } from '$lib/stores/auth';
import { api, ApiError } from '$lib/api/client';
import { toast } from '$lib/stores/toast';
import type { DbFlavor, DbInstance, DbBackup } from '$lib/types/database';

interface DbDatastore {
	id: string;
	name: string;
	versions: { id: string; name: string }[];
}
interface DbNetwork {
	id: string;
	name: string;
	is_external: boolean;
	is_shared: boolean;
}
interface DbAZ {
	name: string;
}
interface DbVolumeType {
	id: string;
	name: string;
}
interface DbConfiguration {
	id: string;
	name: string;
	datastore_name: string;
}
export interface UserDraft {
	name: string;
	password: string;
	host: string;
}

export const DB_TABS = ['상세 정보', '네트워킹', 'DB 접근', '초기화', '진보된'] as const;

interface DbCreateOpts {
	open: () => boolean;
	setOpen: (v: boolean) => void;
	onCreated: () => void;
	databaseBackupsEnabled?: () => boolean;
}

const DB_CREATE_KEY = Symbol('db-create');

export type DbCreateStore = ReturnType<typeof createDbCreateStore>;

export function provideDbCreate(store: DbCreateStore) {
	setContext(DB_CREATE_KEY, store);
}

export function useDbCreate(): DbCreateStore {
	return getContext<DbCreateStore>(DB_CREATE_KEY);
}

export function createDbCreateStore(opts: DbCreateOpts) {
	// auth 브릿지 (Svelte 4 store → $state)
	let authState = $state(get(auth));
	$effect(() => auth.subscribe((v) => { authState = v; }));

	const token = $derived(authState.token ?? undefined);
	const projectId = $derived(authState.projectId ?? undefined);

	const databaseBackupsOn = () => opts.databaseBackupsEnabled?.() ?? true;

	// 메타데이터
	let flavors = $state<DbFlavor[]>([]);
	let datastores = $state<DbDatastore[]>([]);
	let networks = $state<DbNetwork[]>([]);
	let availabilityZones = $state<DbAZ[]>([]);
	let volumeTypes = $state<DbVolumeType[]>([]);
	let configurations = $state<DbConfiguration[]>([]);
	let instances = $state<DbInstance[]>([]);
	let backups = $state<DbBackup[]>([]);
	let loading = $state(false);
	let error = $state('');

	// UI 상태
	let activeTab = $state(0);
	let creating = $state(false);
	let createError = $state('');

	// 폼 — Step 1
	let name = $state('');
	let availabilityZone = $state('');
	let volumeSize = $state(5);
	let volumeType = $state('');
	let datastoreType = $state('');
	let datastoreVersion = $state('');
	let flavorId = $state('');
	let locality = $state('');

	// 폼 — Step 2
	let selectedNics = $state<string[]>([]);

	// 폼 — Step 3
	let isPublic = $state(false);
	let allowedCidrs = $state('');

	// 폼 — Step 4
	let initDatabases = $state('');
	let users = $state<UserDraft[]>([]);
	let userDraft = $state<UserDraft>({ name: '', password: '', host: '%' });

	// 폼 — Step 5
	let configurationId = $state('');
	let restoreBackupId = $state('');
	let replicaOf = $state('');
	let replicaCount = $state(1);

	// derived
	const selectedDs = $derived(datastores.find((d) => d.name === datastoreType));

	const step1Error = $derived.by(() => {
		if (!name.trim()) return '인스턴스 이름을 입력하세요.';
		if (!datastoreType) return '데이터스토어를 선택하세요.';
		if (!datastoreVersion) return '버전을 선택하세요.';
		if (!flavorId) return '플레이버를 선택하세요.';
		if (!volumeSize || volumeSize < 1) return '볼륨 크기를 입력하세요.';
		return '';
	});

	const canCreate = $derived(!step1Error);

	$effect(() => {
		if (!databaseBackupsOn()) restoreBackupId = '';
	});

	// 스타일 상수 (서브 컴포넌트에서 공유)
	const inputCls =
		'w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-amber-500';
	const labelCls = 'block text-xs text-gray-400 mb-1';

	function resetForm() {
		activeTab = 0;
		name = '';
		availabilityZone = '';
		volumeSize = 5;
		volumeType = '';
		datastoreType = '';
		datastoreVersion = '';
		flavorId = '';
		locality = '';
		selectedNics = [];
		isPublic = false;
		allowedCidrs = '';
		initDatabases = '';
		users = [];
		userDraft = { name: '', password: '', host: '%' };
		configurationId = '';
		restoreBackupId = '';
		replicaOf = '';
		replicaCount = 1;
		error = '';
		createError = '';
	}

	async function loadMetadata() {
		loading = true;
		error = '';
		const t = token;
		const p = projectId;
		try {
			[flavors, datastores] = await Promise.all([
				api.get<DbFlavor[]>('/api/v1/database-instances/flavors', t, p),
				api.get<DbDatastore[]>('/api/v1/database-instances/datastores', t, p),
			]);
			if (flavors.length) flavorId = String(flavors[0].id);
			if (datastores.length) {
				datastoreType = datastores[0].name;
				datastoreVersion = datastores[0].versions[0]?.name ?? '';
			}
		} catch {
			error = '필수 메타데이터(플레이버/데이터스토어) 조회 실패';
		}
		await Promise.allSettled([
			api
				.get<DbNetwork[]>('/api/v1/networks', t, p)
				.then((v) => (networks = v.filter((n) => !n.is_external && !n.is_shared)))
				.catch(() => {}),
			api
				.get<DbAZ[]>('/api/v1/instances/availability-zones', t, p)
				.then((v) => (availabilityZones = v))
				.catch(() => {}),
			api
				.get<DbVolumeType[]>('/api/v1/database-instances/volume-types', t, p)
				.then((v) => (volumeTypes = v))
				.catch(() => {}),
			api
				.get<DbConfiguration[]>('/api/v1/database-instances/configurations', t, p)
				.then((v) => (configurations = v))
				.catch(() => {}),
			api
				.get<DbInstance[]>('/api/v1/database-instances', t, p)
				.then((v) => (instances = v))
				.catch(() => {}),
			databaseBackupsOn()
				? api
					.get<DbBackup[]>('/api/v1/database-instances/backups', t, p)
					.then((v) => (backups = v))
					.catch(() => {})
				: Promise.resolve().then(() => { backups = []; restoreBackupId = ''; }),
		]);
		loading = false;
	}

	// open 전이 시 자동 초기화 + 로드 (원본 $effect와 동일 동작)
	$effect(() => {
		if (!opts.open()) return;
		resetForm();
		loadMetadata();
	});

	function selectDatastore(dsName: string) {
		datastoreType = dsName;
		const ds = datastores.find((d) => d.name === dsName);
		datastoreVersion = ds?.versions[0]?.name ?? '';
	}

	function toggleNic(id: string) {
		if (selectedNics.includes(id)) {
			selectedNics = selectedNics.filter((n) => n !== id);
		} else {
			selectedNics = [...selectedNics, id];
		}
	}

	function addUser() {
		if (!userDraft.name.trim() || !userDraft.password) return;
		users = [...users, { ...userDraft }];
		userDraft = { name: '', password: '', host: '%' };
	}

	function removeUser(i: number) {
		users = users.filter((_, idx) => idx !== i);
	}

	async function createInstance() {
		if (!canCreate) return;
		creating = true;
		createError = '';
		const t = token;
		const p = projectId;
		const dbs = initDatabases
			.split(',')
			.map((s) => s.trim())
			.filter(Boolean);
		const cidrs = allowedCidrs
			.split(',')
			.map((s) => s.trim())
			.filter(Boolean);
		const body = {
			name: name.trim(),
			flavor_id: flavorId,
			volume_size: volumeSize,
			datastore_type: datastoreType,
			datastore_version: datastoreVersion,
			availability_zone: availabilityZone || null,
			volume_type: volumeType || null,
			nics: selectedNics,
			locality: replicaOf ? locality || null : null,
			databases: dbs,
			users: users.map((u) => ({ name: u.name, password: u.password, host: u.host })),
			is_public: isPublic,
			allowed_cidrs: cidrs,
			configuration_id: configurationId || null,
			restore_backup_id: databaseBackupsOn() ? restoreBackupId || null : null,
			replica_of: replicaOf || null,
			replica_count: replicaOf && replicaCount > 1 ? replicaCount : null,
		};
		try {
			await api.post('/api/v1/database-instances', body, t, p);
			opts.setOpen(false);
			opts.onCreated();
			if (isPublic) {
				toast.success(
					'DB 인스턴스 생성 요청 완료. Floating IP는 백그라운드에서 자동 할당됩니다. (1~10분 소요)'
				);
			}
		} catch (e) {
			createError = e instanceof ApiError ? e.message : 'DB 인스턴스 생성 실패';
		} finally {
			creating = false;
		}
	}

	return {
		// 메타데이터 (읽기 전용)
		get flavors() { return flavors; },
		get datastores() { return datastores; },
		get networks() { return networks; },
		get availabilityZones() { return availabilityZones; },
		get volumeTypes() { return volumeTypes; },
		get configurations() { return configurations; },
		get instances() { return instances; },
		get backups() { return backups; },
		get loading() { return loading; },
		get error() { return error; },

		// UI
		get activeTab() { return activeTab; },
		set activeTab(v: number) { activeTab = v; },
		get creating() { return creating; },
		get createError() { return createError; },

		// derived
		get selectedDs() { return selectedDs; },
		get step1Error() { return step1Error; },
		get canCreate() { return canCreate; },
		get databaseBackupsEnabled() { return databaseBackupsOn(); },

		// 스타일 상수
		inputCls,
		labelCls,

		// 폼 — Step 1
		get name() { return name; },
		set name(v: string) { name = v; },
		get availabilityZone() { return availabilityZone; },
		set availabilityZone(v: string) { availabilityZone = v; },
		get volumeSize() { return volumeSize; },
		set volumeSize(v: number) { volumeSize = v; },
		get volumeType() { return volumeType; },
		set volumeType(v: string) { volumeType = v; },
		get datastoreType() { return datastoreType; },
		get datastoreVersion() { return datastoreVersion; },
		set datastoreVersion(v: string) { datastoreVersion = v; },
		get flavorId() { return flavorId; },
		set flavorId(v: string) { flavorId = v; },
		get locality() { return locality; },
		set locality(v: string) { locality = v; },
		selectDatastore,

		// 폼 — Step 2
		get selectedNics() { return selectedNics; },
		toggleNic,

		// 폼 — Step 3
		get isPublic() { return isPublic; },
		set isPublic(v: boolean) { isPublic = v; },
		get allowedCidrs() { return allowedCidrs; },
		set allowedCidrs(v: string) { allowedCidrs = v; },

		// 폼 — Step 4
		get initDatabases() { return initDatabases; },
		set initDatabases(v: string) { initDatabases = v; },
		get users() { return users; },
		get userDraft() { return userDraft; },
		addUser,
		removeUser,

		// 폼 — Step 5
		get configurationId() { return configurationId; },
		set configurationId(v: string) { configurationId = v; },
		get restoreBackupId() { return restoreBackupId; },
		set restoreBackupId(v: string) { restoreBackupId = v; },
		get replicaOf() { return replicaOf; },
		set replicaOf(v: string) { replicaOf = v; },
		get replicaCount() { return replicaCount; },
		set replicaCount(v: number) { replicaCount = v; },

		// 액션
		createInstance,
		close: () => opts.setOpen(false),
	};
}
