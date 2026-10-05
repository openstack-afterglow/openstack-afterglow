import { t } from '$lib/i18n/ns/file-storage';
import { getContext, setContext } from 'svelte';
import { api, ApiError } from '$lib/api/client';
import { confirmDialog } from '$lib/stores/confirm.svelte';
import { toast } from '$lib/stores/toast';
import type { FileStorage, AccessRule } from '$lib/types/fileStorage';

export const statusColor: Record<string, string> = {
	available: 'text-green-400 bg-green-900/30',
	creating: 'text-yellow-400 bg-yellow-900/30',
	deleting: 'text-orange-400 bg-orange-900/30',
	error: 'text-red-400 bg-red-900/30',
};

interface Options {
	fileStorageId: () => string;
	token: () => string | undefined;
	projectId: () => string | undefined;
	onDeleted?: () => void | Promise<void>;
	onClose?: () => void;
	onMutated?: () => Promise<void>;
}

function createFileStorageDetailController(opts: Options) {
	let fileStorage = $state<FileStorage | null>(null);
	let loading = $state(true);
	let error = $state('');
	let deleting = $state(false);
	let copiedIndex = $state<number | null>(null);

	let accessRules = $state<AccessRule[]>([]);
	let accessLoading = $state(false);
	let accessError = $state('');
	let showAddRule = $state(false);
	let ruleForm = $state({ access_to: '', access_level: 'ro' });
	let addingRule = $state(false);
	let ruleError = $state('');
	let revokingId = $state<string | null>(null);
	let copiedKey = $state<string | null>(null);

	async function fetchFileStorage(requestOpts?: { refresh?: boolean }) {
		// 초기 로드일 때만 스켈레톤 표시 — 이미 데이터가 있으면 백그라운드 새로고침
		if (fileStorage === null) loading = true;
		error = '';
		try {
			fileStorage = await api.get<FileStorage>(
				`/api/v1/file-storage/${opts.fileStorageId()}`,
				opts.token(),
				opts.projectId(),
				requestOpts
			);
		} catch (e) {
			error = e instanceof ApiError ? t('detail.loadFailedWithMessage', { status: e.status, message: e.message }) : t('errors.server');
		} finally {
			loading = false;
		}
	}

	async function fetchAccessRules(requestOpts?: { refresh?: boolean }) {
		// 초기 로드일 때만 로딩 표시 — 이미 규칙이 있으면 백그라운드 새로고침
		if (accessRules.length === 0) accessLoading = true;
		accessError = '';
		try {
			accessRules = await api.get<AccessRule[]>(
				`/api/v1/file-storage/${opts.fileStorageId()}/access-rules`,
				opts.token(),
				opts.projectId(),
				requestOpts
			);
		} catch (e) {
			accessRules = [];
			accessError = e instanceof ApiError ? t('detail.accessLoadFailedWithMessage', { status: e.status, message: e.message }) : t('detail.accessLoadFailed');
		} finally {
			accessLoading = false;
		}
	}

	async function fetchAll(requestOpts?: { refresh?: boolean }) {
		await Promise.allSettled([fetchFileStorage(requestOpts), fetchAccessRules(requestOpts)]);
	}

	async function addAccessRule() {
		if (!fileStorage || !ruleForm.access_to.trim()) return;
		addingRule = true;
		ruleError = '';
		const access_type = fileStorage.share_proto === 'NFS' ? 'ip' : 'cephx';
		try {
			await api.post(
				`/api/v1/file-storage/${fileStorage.id}/access-rules`,
				{ access_to: ruleForm.access_to.trim(), access_level: ruleForm.access_level, access_type },
				opts.token(),
				opts.projectId()
			);
			ruleForm = { access_to: '', access_level: 'ro' };
			showAddRule = false;
			if (opts.onMutated) await opts.onMutated();
			else await fetchAccessRules();
		} catch (e) {
			ruleError = e instanceof ApiError ? e.message : t('errors.create');
		} finally {
			addingRule = false;
		}
	}

	async function revokeAccessRule(accessId: string) {
		if (!fileStorage) return;
		if (!(await confirmDialog(t('detail.revokeConfirm')))) return;
		revokingId = accessId;
		try {
			await api.delete(
				`/api/v1/file-storage/${fileStorage.id}/access-rules/${accessId}`,
				opts.token(),
				opts.projectId()
			);
			if (opts.onMutated) await opts.onMutated();
			else await fetchAccessRules();
		} catch (e) {
			toast.error(t('errors.deleteWithMessage', { message: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			revokingId = null;
		}
	}

	async function copyPath(path: string, index: number) {
		await navigator.clipboard.writeText(path);
		copiedIndex = index;
		setTimeout(() => (copiedIndex = null), 2000);
	}

	async function copyKey(key: string, id: string) {
		await navigator.clipboard.writeText(key);
		copiedKey = id;
		setTimeout(() => (copiedKey = null), 2000);
	}

	async function deleteFileStorage() {
		if (!fileStorage) return;
		if (!(await confirmDialog(t('detail.deleteConfirm', { name: fileStorage.name || fileStorage.id })))) return;
		deleting = true;
		try {
			await api.delete(`/api/v1/file-storage/${fileStorage.id}`, opts.token(), opts.projectId());
			await opts.onDeleted?.();
			opts.onClose?.();
		} catch (e) {
			toast.error(t('errors.deleteWithMessage', { message: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			deleting = false;
		}
	}

	return {
		get fileStorage() { return fileStorage; },
		get loading() { return loading; },
		get error() { return error; },
		get deleting() { return deleting; },
		get copiedIndex() { return copiedIndex; },
		get accessRules() { return accessRules; },
		get accessLoading() { return accessLoading; },
		get accessError() { return accessError; },
		get showAddRule() { return showAddRule; },
		set showAddRule(v: boolean) { showAddRule = v; },
		get ruleForm() { return ruleForm; },
		get addingRule() { return addingRule; },
		get ruleError() { return ruleError; },
		get revokingId() { return revokingId; },
		get copiedKey() { return copiedKey; },
		fetchAll,
		addAccessRule,
		revokeAccessRule,
		copyPath,
		copyKey,
		deleteFileStorage,
	};
}

export type FileStorageDetailController = ReturnType<typeof createFileStorageDetailController>;
export { createFileStorageDetailController };

const FS_DETAIL_KEY = Symbol('fs-detail');

export function provideFileStorageDetailController(store: FileStorageDetailController) {
	setContext(FS_DETAIL_KEY, store);
}

export function useFileStorageDetailController(): FileStorageDetailController {
	const store = getContext<FileStorageDetailController | undefined>(FS_DETAIL_KEY);
	if (!store) throw new Error('useFileStorageDetailController must be called within FileStorageDetailPanel');
	return store;
}
