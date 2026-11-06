import { t } from '$lib/i18n/ns/images-keys';
import type { TableViewState } from '$lib/utils/tableView.svelte';
import { getContext, setContext } from 'svelte';
import { api, ApiError } from '$lib/api/client';
import type { ImageDetail, ImageMember } from '$lib/types/adminImage';
import type { ImageInfo } from '$lib/types/compute';
import { confirmDialog } from '$lib/stores/confirm.svelte';
import { toast } from '$lib/stores/toast';
import { isWindowsSetupAccountValid, windowsSetupChanges, windowsSetupProperties, windowsSetupStatus } from '$lib/utils/windowsImageSetup';
import type { WindowsSetupChange } from '$lib/utils/windowsImageSetup';
import { beginExperienceAction, beginExperienceLoad, experienceApplied, experienceDiscarded, experienceState, type ExperienceContext } from '$lib/utils/experience';

const RESERVED_KEYS = new Set([
	'id', 'name', 'status', 'visibility', 'owner', 'size', 'virtual_size',
	'disk_format', 'container_format', 'checksum', 'os_hash_algo', 'os_hash_value',
	'min_disk', 'min_ram', 'tags', 'self', 'file', 'schema', 'direct_url',
	'locations', 'created_at', 'updated_at', 'protected', 'os_hidden',
]);

export const isReservedKey = (k: string) => RESERVED_KEYS.has(k) || k.startsWith('os_glance_');

export const VISIBILITY_OPTIONS = [
	{ value: 'public',    get label() { return t('detailController.visibility.public'); } },
	{ value: 'private',   get label() { return t('detailController.visibility.private'); } },
	{ value: 'shared',    get label() { return t('detailController.visibility.shared'); } },
	{ value: 'community', get label() { return t('detailController.visibility.community'); } },
];

export interface ImageDetailControllerOpts {
	imageId: () => string;
	token: () => string | undefined;
	projectId: () => string | undefined;
	isAdmin: () => boolean;
	onDelete?: (id: string) => void;
	onClose?: () => void;
}

interface ImageDetailScope {
	imageId: string;
	token: string | undefined;
	projectId: string | undefined;
	isAdmin: boolean;
	generation: number;
}

export function createImageDetailController(opts: ImageDetailControllerOpts): ImageDetailController {
	// Every async result belongs to this exact scope and request generation.
	let generation = 0;
	function captureScope(): ImageDetailScope {
		return { imageId: opts.imageId(), token: opts.token(), projectId: opts.projectId(), isAdmin: opts.isAdmin(), generation };
	}
	let loadedScope = $state<ImageDetailScope | null>(null);
	function sameContext(scope: ImageDetailScope | null): boolean {
		return scope !== null && scope.imageId === opts.imageId() && scope.token === opts.token()
			&& scope.projectId === opts.projectId() && scope.isAdmin === opts.isAdmin();
	}
	function isCurrent(scope: ImageDetailScope): boolean {
		return sameContext(scope) && scope.generation === generation;
	}
	let appliedAssignment = 0;
	function observeApplied(experience: ExperienceContext | undefined, scope: ImageDetailScope) {
		if (!experience) return;
		const assignment = ++appliedAssignment;
		void experienceApplied(experience, {}, () => isCurrent(scope) && assignment === appliedAssignment);
	}
	function imageEndpoint(scope: ImageDetailScope): string {
		return `${scope.isAdmin ? '/api/v1/admin/images' : '/api/v1/images'}/${scope.imageId}`;
	}
	// Domain state
	let image = $state<ImageDetail | null>(null);
	let members = $state<ImageMember[]>([]);
	let loading = $state(true);
	let error = $state('');
	let deleting = $state(false);
	let tableStates = $state<Record<string, { search: string; state: TableViewState }>>({});
	let tableViewScope: Pick<ImageDetailScope, 'imageId' | 'projectId' | 'isAdmin'> | null = null;
	function tableState(key: string) {
		tableViewScope ??= { imageId: opts.imageId(), projectId: opts.projectId(), isAdmin: opts.isAdmin() };
		if (!tableStates[key]) tableStates[key] = { search: '', state: { sort: null, filters: {} } };
		return tableStates[key];
	}

	// Visibility state
	let visibilityValue = $state('');
	let savingVisibility = $state(false);
	let visibilityError = $state('');
	let visibilitySuccess = $state(false);

	// Members state
	let loadingMembers = $state(false);
	let newMemberId = $state('');
	let addingMember = $state(false);
	let memberError = $state('');
	let removingMember = $state<string | null>(null);

	// Properties edit state
	let editingProps = $state(false);
	let propsDraft = $state<Record<string, string>>({});
	let propsRemovedKeys = $state<Set<string>>(new Set());
	let newPropKey = $state('');
	let newPropValue = $state('');
	let savingProps = $state(false);
	let propsError = $state('');

	// Windows setup is a mutually exclusive metadata draft, not a guest operation.
	let windowsEditing = $state(false);
	let windowsSaving = $state(false);
	let windowsError = $state('');
	let windowsSuccess = $state(false);
	let windowsAccount = $state('');
	let windowsWin11 = $state(false);
	let windowsQga = $state(false);
	let windowsConfirmed = $state(false);

	// Derived
	const isOwner = $derived(sameContext(loadedScope) && !!image && !!opts.projectId() && image.owner === opts.projectId());
	const canManageImage = $derived(sameContext(loadedScope) && !!image && !!opts.token() && (isOwner || opts.isAdmin()));
	const canEditMetadata = $derived(canManageImage);
	// Palimpsest exports retain the caller's project token/trust, never the admin executor.
	const canExport = $derived(sameContext(loadedScope) && !!image && (!opts.isAdmin() || isOwner
		|| image.visibility === 'public' || image.visibility === 'community'
		|| (image.visibility === 'shared' && !loadingMembers
			&& members.some(member => member.member_id === opts.projectId() && member.status === 'accepted'))));
	const windowsCurrentProperties = $derived(image && sameContext(loadedScope) ? windowsSetupProperties(image) : {});
	const windowsStatus = $derived(windowsSetupStatus(windowsCurrentProperties));
	const windowsAccountValid = $derived(isWindowsSetupAccountValid(windowsAccount));
	const windowsChanges = $derived(windowsSetupChanges(windowsCurrentProperties, {
		account: windowsAccount, win11: windowsWin11, qga: windowsQga,
	}));
	const canSaveWindowsSetup = $derived(canEditMetadata && windowsEditing && !windowsSaving && !savingProps
		&& !editingProps && windowsConfirmed && windowsAccountValid && windowsChanges.length > 0);

	// Handlers
	async function loadImage() {
		// An explicit reload must not replace an open metadata draft.
		if (sameContext(loadedScope) && (editingProps || windowsEditing || savingProps || windowsSaving
			|| savingVisibility || addingMember || removingMember || deleting)) return;
		if (!sameContext(loadedScope)) {
			const retainTableViews = tableViewScope !== null && tableViewScope.imageId === opts.imageId()
				&& tableViewScope.projectId === opts.projectId() && tableViewScope.isAdmin === opts.isAdmin();
			reset(retainTableViews);
		}
		++generation;
		const scope = captureScope();
		if (!scope.imageId || !scope.token) return;
		const experience = beginExperienceLoad('compute', 'resource.detail');
		experienceState(experience, 'loading');
		loading = true;
		error = '';
		image = null;
		members = [];
		loadedScope = null;
		try {
			const loadedImage = await api.withExperience(experience).get<ImageDetail>(imageEndpoint(scope), scope.token, scope.projectId);
			if (!isCurrent(scope)) { experienceDiscarded(experience, 'stale'); return; }
			visibilityValue = loadedImage.visibility ?? '';
			image = loadedImage;
			loadedScope = scope;
			experienceState(experience, 'ready');
			observeApplied(experience, scope);
			if (loadedImage.visibility === 'shared') void loadMembers(experience);
		} catch (e) {
			if (!isCurrent(scope)) { experienceDiscarded(experience, 'stale'); return; }
			error = e instanceof ApiError ? t('detailController.loadFailed', { status: e.status, message: e.message }) : t('detailController.serverError');
			experienceState(experience, 'error');
			observeApplied(experience, scope);
		} finally {
			if (isCurrent(scope)) loading = false;
		}
	}

	async function loadMembers(experience: ExperienceContext | undefined = beginExperienceLoad('compute', 'resource.detail')) {
		const scope = captureScope();
		if (!sameContext(loadedScope)) return;
		loadingMembers = true;
		memberError = '';
		experienceState(experience, 'loading');
		try {
			const loaded = await api.withExperience(experience).get<ImageMember[]>(`${imageEndpoint(scope)}/members`, scope.token, scope.projectId);
			if (isCurrent(scope)) {
				members = loaded;
				experienceState(experience, members.length ? 'ready' : 'empty');
				observeApplied(experience, scope);
			} else experienceDiscarded(experience, 'stale');
		} catch {
			if (isCurrent(scope)) {
				members = [];
				experienceState(experience, 'error');
				observeApplied(experience, scope);
			} else experienceDiscarded(experience, 'stale');
		} finally {
			if (isCurrent(scope)) loadingMembers = false;
		}
	}

	function reset(retainTableViews = false) {
		if (!retainTableViews) {
			tableStates = {};
			tableViewScope = null;
		}
		++generation;
		loadedScope = null;
		image = null;
		members = [];
		loading = true;
		error = '';
		editingProps = false;
		propsDraft = {};
		propsRemovedKeys = new Set();
		newPropKey = '';
		newPropValue = '';
		savingProps = false;
		propsError = '';
		windowsEditing = false;
		windowsSaving = false;
		windowsError = '';
		windowsSuccess = false;
		windowsAccount = '';
		windowsWin11 = false;
		windowsQga = false;
		windowsConfirmed = false;
		visibilityValue = '';
		savingVisibility = false;
		visibilityError = '';
		visibilitySuccess = false;
		loadingMembers = false;
		newMemberId = '';
		addingMember = false;
		memberError = '';
		removingMember = null;
		deleting = false;
	}

	async function saveVisibility() {
		if (!image || !canManageImage || savingVisibility || editingProps || windowsEditing || savingProps || windowsSaving
			|| visibilityValue === image.visibility) return;
		const scope = captureScope();
		const experience = beginExperienceAction('compute', 'update', 'resource.detail');
		savingVisibility = true;
		visibilityError = '';
		visibilitySuccess = false;
		try {
			const updated = await api.withExperience(experience).patch<ImageInfo>(
				imageEndpoint(scope), { visibility: visibilityValue }, scope.token, scope.projectId
			);
			if (!isCurrent(scope) || !image) { experienceDiscarded(experience, 'stale'); return; }
			// This endpoint returns ImageInfo, unlike the full properties PATCH projection.
			image = { ...image, visibility: updated.visibility ?? image.visibility };
			visibilityValue = image.visibility;
			visibilitySuccess = true;
			experienceState(experience, 'ready');
			observeApplied(experience, scope);
			setTimeout(() => { if (isCurrent(scope)) visibilitySuccess = false; }, 2000);
			if (updated.visibility === 'shared') void loadMembers(experience);
		} catch (e) {
			if (isCurrent(scope)) {
				visibilityError = e instanceof ApiError ? e.message : t('detailController.visibility.saveFailed');
				experienceState(experience, 'error');
				observeApplied(experience, scope);
			} else experienceDiscarded(experience, 'stale');
		} finally {
			if (isCurrent(scope)) savingVisibility = false;
		}
	}

	async function addMember() {
		if (!image || !canManageImage || addingMember || !newMemberId.trim()) return;
		const scope = captureScope();
		const experience = beginExperienceAction('compute', 'attach', 'resource.detail');
		addingMember = true;
		memberError = '';
		try {
			await api.withExperience(experience).post(`${imageEndpoint(scope)}/members`, { member: newMemberId.trim() }, scope.token, scope.projectId);
			if (!isCurrent(scope)) { experienceDiscarded(experience, 'stale'); return; }
			newMemberId = '';
			await loadMembers(experience);
		} catch (e) {
			if (isCurrent(scope)) {
				memberError = e instanceof ApiError ? e.message : t('detailController.members.addFailed');
				experienceState(experience, 'error');
				observeApplied(experience, scope);
			} else experienceDiscarded(experience, 'stale');
		} finally {
			if (isCurrent(scope)) addingMember = false;
		}
	}

	async function removeMember(memberId: string) {
		if (!image || !canManageImage || removingMember) return;
		const scope = captureScope();
		const experience = beginExperienceAction('compute', 'detach', 'resource.detail');
		removingMember = memberId;
		memberError = '';
		try {
			await api.withExperience(experience).delete(`${imageEndpoint(scope)}/members/${memberId}`, scope.token, scope.projectId);
			if (isCurrent(scope)) await loadMembers(experience);
			else experienceDiscarded(experience, 'stale');
		} catch (e) {
			if (isCurrent(scope)) {
				memberError = e instanceof ApiError ? e.message : t('detailController.members.deleteFailed');
				experienceState(experience, 'error');
				observeApplied(experience, scope);
			} else experienceDiscarded(experience, 'stale');
		} finally {
			if (isCurrent(scope)) removingMember = null;
		}
	}

	function startEditProps() {
		if (!image || !canEditMetadata || savingVisibility || editingProps || savingProps || windowsEditing || windowsSaving) return;
		propsDraft = { ...image.properties };
		propsRemovedKeys = new Set();
		newPropKey = '';
		newPropValue = '';
		propsError = '';
		editingProps = true;
	}

	function cancelEditProps() {
		if (savingProps) return;
		editingProps = false;
		propsDraft = {};
		propsRemovedKeys = new Set();
		propsError = '';
	}

	function removeProperty(key: string) {
		if (!canEditMetadata || !editingProps || savingProps || isReservedKey(key)) return;
		delete propsDraft[key];
		propsDraft = { ...propsDraft };
		propsRemovedKeys.add(key);
		propsRemovedKeys = new Set(propsRemovedKeys);
	}

	function addProperty() {
		if (!canEditMetadata || !editingProps || savingProps) return;
		const key = newPropKey.trim();
		const value = newPropValue.trim();
		if (!key) {
			propsError = t('detailController.properties.keyRequired');
			return;
		}
		if (isReservedKey(key)) {
			propsError = t('detailController.properties.reservedKey', { key });
			return;
		}
		propsDraft[key] = value;
		propsDraft = { ...propsDraft };
		propsRemovedKeys.delete(key);
		propsRemovedKeys = new Set(propsRemovedKeys);
		newPropKey = '';
		newPropValue = '';
		propsError = '';
	}

	async function saveProperties() {
		if (!image || !canEditMetadata || !editingProps || savingProps || windowsEditing || windowsSaving) return;
		const pendingKey = newPropKey.trim();
		if (pendingKey && !isReservedKey(pendingKey)) {
			propsDraft[pendingKey] = newPropValue.trim();
			propsDraft = { ...propsDraft };
			propsRemovedKeys.delete(pendingKey);
			propsRemovedKeys = new Set(propsRemovedKeys);
			newPropKey = '';
			newPropValue = '';
		}
		const original = image.properties;
		const setObj: Record<string, string> = {};
		for (const [k, v] of Object.entries(propsDraft)) {
			if (isReservedKey(k)) continue;
			if (original[k] !== v) setObj[k] = v;
		}
		const removeList = Array.from(propsRemovedKeys).filter((k) => !isReservedKey(k));
		if (Object.keys(setObj).length === 0 && removeList.length === 0) {
			editingProps = false;
			return;
		}
		const scope = captureScope();
		const experience = beginExperienceAction('compute', 'update', 'resource.detail');
		savingProps = true;
		propsError = '';
		try {
			const updated = await patchProperties(scope, setObj, removeList, experience);
			if (!isCurrent(scope)) { experienceDiscarded(experience, 'stale'); return; }
			image = updated;
			visibilityValue = updated.visibility ?? '';
			editingProps = false;
			experienceState(experience, 'ready');
			observeApplied(experience, scope);
		} catch (e) {
			if (isCurrent(scope)) {
				propsError = e instanceof ApiError ? e.message : t('detailController.properties.saveFailed');
				experienceState(experience, 'error');
				observeApplied(experience, scope);
			} else experienceDiscarded(experience, 'stale');
		} finally {
			if (isCurrent(scope)) savingProps = false;
		}
	}

	// The existing API returns get_image's full authoritative projection after JSON-Patch.
	function patchProperties(scope: ImageDetailScope, set: Record<string, string>, remove: string[], experience: ExperienceContext | undefined) {
		return api.withExperience(experience).patch<ImageDetail>(`${imageEndpoint(scope)}/properties`, { set, remove }, scope.token, scope.projectId);
	}

	function startWindowsSetup() {
		if (!image || !canEditMetadata || savingVisibility || editingProps || savingProps || windowsEditing || windowsSaving) return;
		windowsAccount = windowsCurrentProperties.os_admin_user || 'Admin';
		windowsWin11 = false;
		windowsQga = false;
		windowsConfirmed = false;
		windowsError = '';
		windowsSuccess = false;
		windowsEditing = true;
	}

	function cancelWindowsSetup() {
		if (windowsSaving) return;
		windowsEditing = false;
		windowsAccount = '';
		windowsWin11 = false;
		windowsQga = false;
		windowsConfirmed = false;
		windowsError = '';
	}

	async function saveWindowsSetup() {
		if (!canSaveWindowsSetup) return;
		// Capture exactly the preview, never merge a full properties snapshot into a write.
		const set = Object.fromEntries(windowsChanges.map(change => [change.key, change.proposed]));
		const scope = captureScope();
		const experience = beginExperienceAction('compute', 'update', 'resource.detail');
		windowsSaving = true;
		windowsError = '';
		windowsSuccess = false;
		try {
			const updated = await patchProperties(scope, set, [], experience);
			if (!isCurrent(scope)) { experienceDiscarded(experience, 'stale'); return; }
			image = updated;
			visibilityValue = updated.visibility ?? '';
			windowsEditing = false;
			windowsConfirmed = false;
			windowsSuccess = true;
			experienceState(experience, 'ready');
			observeApplied(experience, scope);
		} catch (e) {
			if (isCurrent(scope)) {
				windowsError = e instanceof ApiError ? e.message : t('windowsSetup.saveFailed');
				experienceState(experience, 'error');
				observeApplied(experience, scope);
			} else experienceDiscarded(experience, 'stale');
		} finally {
			if (isCurrent(scope)) windowsSaving = false;
		}
	}

	async function deleteImage() {
		if (!image || !canManageImage || deleting || savingProps || windowsSaving) return;
		const scope = captureScope();
		if (!(await confirmDialog(t('detailController.deleteConfirm', { name: image.name }))) || !isCurrent(scope)) return;
		const experience = beginExperienceAction('compute', 'delete', 'resource.detail');
		deleting = true;
		try {
			await api.withExperience(experience).delete(imageEndpoint(scope), scope.token, scope.projectId);
			if (!isCurrent(scope)) { experienceDiscarded(experience, 'stale'); return; }
			opts.onDelete?.(scope.imageId);
			opts.onClose?.();
		} catch (e) {
			if (!isCurrent(scope)) return;
			toast.error(t('detailController.deleteFailed', { message: e instanceof ApiError ? e.message : String(e) }));
			deleting = false;
		}
	}

	return {
		tableState,
		get hasPropertyViewConditions() {
			const table = tableStates.properties;
			return !!table && (!!table.search || table.state.sort !== null || Object.keys(table.state.filters).length > 0);
		},
		// State getters
		get image() { return sameContext(loadedScope) ? image : null; },
		get members() { return sameContext(loadedScope) ? members : []; },
		get loading() { return loading; },
		get error() { return error; },
		get deleting() { return deleting; },
		get visibilityValue() { return visibilityValue; },
		set visibilityValue(v: string) { visibilityValue = v; },
		get savingVisibility() { return savingVisibility; },
		get visibilityError() { return visibilityError; },
		get visibilitySuccess() { return visibilitySuccess; },
		get loadingMembers() { return loadingMembers; },
		get newMemberId() { return newMemberId; },
		set newMemberId(v: string) { newMemberId = v; },
		get addingMember() { return addingMember; },
		get memberError() { return memberError; },
		get removingMember() { return removingMember; },
		get editingProps() { return editingProps; },
		get propsDraft() { return propsDraft; },
		get propsRemovedKeys() { return propsRemovedKeys; },
		get newPropKey() { return newPropKey; },
		set newPropKey(v: string) { newPropKey = v; },
		get newPropValue() { return newPropValue; },
		set newPropValue(v: string) { newPropValue = v; },
		get savingProps() { return savingProps; },
		get propsError() { return propsError; },
		get windowsEditing() { return windowsEditing; },
		get windowsSaving() { return windowsSaving; },
		get windowsError() { return windowsError; },
		get windowsSuccess() { return windowsSuccess; },
		get windowsAccount() { return windowsAccount; },
		set windowsAccount(v: string) { if (!windowsSaving && canEditMetadata) windowsAccount = v; },
		get windowsWin11() { return windowsWin11; },
		set windowsWin11(v: boolean) { if (!windowsSaving && canEditMetadata) windowsWin11 = v; },
		get windowsQga() { return windowsQga; },
		set windowsQga(v: boolean) { if (!windowsSaving && canEditMetadata) windowsQga = v; },
		get windowsConfirmed() { return windowsConfirmed; },
		set windowsConfirmed(v: boolean) { if (!windowsSaving && canEditMetadata) windowsConfirmed = v; },
		get windowsCurrentProperties() { return windowsCurrentProperties; },
		get windowsStatus() { return windowsStatus; },
		get windowsAccountValid() { return windowsAccountValid; },
		get windowsChanges() { return windowsChanges; },
		get canSaveWindowsSetup() { return canSaveWindowsSetup; },
		// Derived getters
		get isOwner() { return isOwner; },
		get canManageImage() { return canManageImage; },
		get canExport() { return canExport; },
		get canEditMetadata() { return canEditMetadata; },
		get isAdmin() { return opts.isAdmin(); },
		// Handlers
		loadImage,
		loadMembers,
		reset,
		saveVisibility,
		addMember,
		removeMember,
		startEditProps,
		cancelEditProps,
		removeProperty,
		addProperty,
		saveProperties,
		deleteImage,
		startWindowsSetup,
		cancelWindowsSetup,
		saveWindowsSetup,
	};
}

export interface ImageDetailController {
	tableState(key: string): { search: string; state: TableViewState };
	readonly hasPropertyViewConditions: boolean;
	readonly image: ImageDetail | null;
	readonly members: ImageMember[];
	readonly loading: boolean;
	readonly error: string;
	readonly deleting: boolean;
	visibilityValue: string;
	readonly savingVisibility: boolean;
	readonly visibilityError: string;
	readonly visibilitySuccess: boolean;
	readonly loadingMembers: boolean;
	newMemberId: string;
	readonly addingMember: boolean;
	readonly memberError: string;
	readonly removingMember: string | null;
	readonly editingProps: boolean;
	readonly propsDraft: Record<string, string>;
	readonly propsRemovedKeys: Set<string>;
	newPropKey: string;
	newPropValue: string;
	readonly savingProps: boolean;
	readonly propsError: string;
	readonly windowsEditing: boolean;
	readonly windowsSaving: boolean;
	readonly windowsError: string;
	readonly windowsSuccess: boolean;
	windowsAccount: string;
	windowsWin11: boolean;
	windowsQga: boolean;
	windowsConfirmed: boolean;
	readonly windowsCurrentProperties: Record<string, string>;
	readonly windowsStatus: 'native' | 'legacy' | 'unconfigured';
	readonly windowsAccountValid: boolean;
	readonly windowsChanges: WindowsSetupChange[];
	readonly canSaveWindowsSetup: boolean;
	readonly isOwner: boolean;
	readonly canManageImage: boolean;
	readonly canExport: boolean;
	readonly canEditMetadata: boolean;
	readonly isAdmin: boolean;
	loadImage(): Promise<void>;
	loadMembers(): Promise<void>;
	reset(retainTableViews?: boolean): void;
	saveVisibility(): Promise<void>;
	addMember(): Promise<void>;
	removeMember(memberId: string): Promise<void>;
	startEditProps(): void;
	cancelEditProps(): void;
	removeProperty(key: string): void;
	addProperty(): void;
	saveProperties(): Promise<void>;
	deleteImage(): Promise<void>;
	startWindowsSetup(): void;
	cancelWindowsSetup(): void;
	saveWindowsSetup(): Promise<void>;
}

const IMAGE_DETAIL_KEY = Symbol('image-detail');

export function provideImageDetailController(store: ImageDetailController) {
	setContext(IMAGE_DETAIL_KEY, store);
}

export function useImageDetailController(): ImageDetailController {
	const store = getContext<ImageDetailController | undefined>(IMAGE_DETAIL_KEY);
	if (!store) throw new Error(t('detailController.contextRequired'));
	return store;
}
