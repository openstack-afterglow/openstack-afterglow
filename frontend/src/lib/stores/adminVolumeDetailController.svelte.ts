import { getContext, setContext, untrack } from 'svelte';
import { api, ApiError } from '$lib/api/client';
import type { AdminVolumeDetail, VolumeDeleteDiagnostic, VolumeDeleteRecoveryResult } from '$lib/types/volume';

interface Options {
	volumeId: () => string;
	token: () => string | undefined;
	projectId: () => string | undefined;
	onClose?: () => void;
	onRefresh?: () => void;
}

const diagnosticStatuses: Record<string, true> = {
	error: true,
	error_deleting: true,
	deleting: true,
	error_extending: true,
	error_restoring: true,
	error_managing: true,
};

function createAdminVolumeDetailController(opts: Options) {
	let volume = $state<AdminVolumeDetail | null>(null);
	let loading = $state(true);
	let error = $state('');
	let deleteDiagnostic = $state<VolumeDeleteDiagnostic | null>(null);
	let diagnosticLoading = $state(false);
	let diagnosticError = $state('');
	let recoveryResult = $state<VolumeDeleteRecoveryResult | null>(null);
	let recovering = $state(false);
	let lastVolumeId = '';

	$effect(() => {
		const volumeId = opts.volumeId();
		opts.token();
		opts.projectId();
		if (!volumeId) return;
		if (volumeId !== lastVolumeId) {
			lastVolumeId = volumeId;
			deleteDiagnostic = null;
			diagnosticError = '';
			recoveryResult = null;
		}
		loading = true;
		error = '';
		volume = null;
		untrack(() => { void fetchVolume(); });
	});

	async function fetchVolume() {
		try {
			const currentVolume = await api.get<AdminVolumeDetail>(`/api/v1/admin/volumes/${opts.volumeId()}`, opts.token(), opts.projectId());
			volume = currentVolume;
			if (diagnosticStatuses[(currentVolume.status || '').toLowerCase()]) {
				await fetchDeleteDiagnostic();
			} else {
				deleteDiagnostic = null;
				diagnosticError = '';
				recoveryResult = null;
			}
		} catch (e) {
			error = e instanceof ApiError ? e.message : '볼륨 조회 실패';
		} finally {
			loading = false;
		}
	}

	async function fetchDeleteDiagnostic(requestOpts?: { refresh?: boolean }): Promise<void> {
		const volumeId = opts.volumeId();
		if (!volumeId) return;
		diagnosticLoading = true;
		diagnosticError = '';
		try {
			deleteDiagnostic = await api.get<VolumeDeleteDiagnostic>(
				`/api/v1/admin/volumes/${volumeId}/delete-diagnostics`,
				opts.token(),
				opts.projectId(),
				requestOpts
			);
		} catch (e) {
			diagnosticError = e instanceof ApiError ? e.message : '볼륨 삭제 진단 실패';
		} finally {
			diagnosticLoading = false;
		}
	}

	async function recoverDelete(): Promise<VolumeDeleteRecoveryResult | null> {
		const volumeId = opts.volumeId();
		if (!volumeId) return null;
		recovering = true;
		diagnosticError = '';
		try {
			const result = await api.post<VolumeDeleteRecoveryResult>(
				`/api/v1/admin/volumes/${volumeId}/recover-delete`,
				{},
				opts.token(),
				opts.projectId()
			);
			recoveryResult = result;
			deleteDiagnostic = result.diagnostic;
			if (result.status === 'deleted' || result.status === 'already_deleted') {
				opts.onRefresh?.();
				opts.onClose?.();
			} else if (
				result.status === 'delete_submitted' ||
				result.status === 'backend_residue' ||
				result.status === 'backend_unverified'
			) {
				opts.onRefresh?.();
			}
			return result;
		} catch (e) {
			diagnosticError = e instanceof ApiError ? e.message : '볼륨 삭제 복구 실패';
			return null;
		} finally {
			recovering = false;
		}
	}

	return {
		get volume() { return volume; },
		get loading() { return loading; },
		get error() { return error; },
		get deleteDiagnostic() { return deleteDiagnostic; },
		get diagnosticLoading() { return diagnosticLoading; },
		get diagnosticError() { return diagnosticError; },
		get recoveryResult() { return recoveryResult; },
		get recovering() { return recovering; },
		fetchVolume,
		fetchDeleteDiagnostic,
		recoverDelete,
	};
}

export type AdminVolumeDetailController = ReturnType<typeof createAdminVolumeDetailController>;
export { createAdminVolumeDetailController };

const ADMIN_VOLUME_DETAIL_KEY = Symbol('admin-volume-detail');

export function provideAdminVolumeDetailController(store: AdminVolumeDetailController) {
	setContext(ADMIN_VOLUME_DETAIL_KEY, store);
}

export function useAdminVolumeDetailController(): AdminVolumeDetailController {
	const store = getContext<AdminVolumeDetailController | undefined>(ADMIN_VOLUME_DETAIL_KEY);
	if (!store) throw new Error('useAdminVolumeDetailController must be called within AdminVolumeDetailPanel');
	return store;
}
