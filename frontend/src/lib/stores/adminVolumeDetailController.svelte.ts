import { t } from '$lib/i18n/ns/admin-storage';
import { getContext, setContext, untrack } from 'svelte';
import { api, ApiError } from '$lib/api/client';
import type { AdminVolumeDetail, VolumeDeleteDiagnostic, VolumeDeleteRecoveryResult } from '$lib/types/volume';
import { beginExperienceAction, beginExperienceLoad, experienceState, experienceApplied, experienceDiscarded, type ExperienceContext } from '$lib/utils/experience';

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

	// There is no existing mounted/result-generation guard here. Observe the
	// assignments as they occur, without claiming DOM commitment or adding one.
	async function fetchVolume() {
		const experience = beginExperienceLoad('admin', 'resource.detail');
		const request = experience ? api.withExperience(experience) : api;
		experienceState(experience, 'loading');
		try {
			const currentVolume = await request.get<AdminVolumeDetail>(`/api/v1/admin/volumes/${opts.volumeId()}`, opts.token(), opts.projectId());
			volume = currentVolume;
			experienceState(experience, currentVolume ? 'ready' : 'empty');
			void experienceApplied(experience);
			if (diagnosticStatuses[(currentVolume.status || '').toLowerCase()]) {
				await fetchDeleteDiagnosticWithExperience(undefined, experience);
			} else {
				deleteDiagnostic = null;
				diagnosticError = '';
				recoveryResult = null;
			}
		} catch (e) {
			error = e instanceof ApiError ? e.message : t('volumeDetail.loadFailed');
			experienceState(experience, 'error');
			void experienceApplied(experience);
		} finally {
			loading = false;
		}
	}

	async function fetchDeleteDiagnostic(requestOpts?: { refresh?: boolean }): Promise<void> {
		await fetchDeleteDiagnosticWithExperience(requestOpts);
	}

	async function fetchDeleteDiagnosticWithExperience(requestOpts?: { refresh?: boolean }, inherited?: ExperienceContext): Promise<void> {
		const volumeId = opts.volumeId();
		if (!volumeId) { experienceDiscarded(inherited, 'scope_changed'); return; }
		const experience = inherited ?? beginExperienceAction('admin', 'inspect', 'resource.detail');
		const request = experience ? api.withExperience(experience) : api;
		experienceState(experience, 'loading');
		diagnosticLoading = true;
		diagnosticError = '';
		try {
			deleteDiagnostic = await request.get<VolumeDeleteDiagnostic>(
				`/api/v1/admin/volumes/${volumeId}/delete-diagnostics`,
				opts.token(),
				opts.projectId(),
				requestOpts
			);
			experienceState(experience, deleteDiagnostic ? 'ready' : 'empty');
			void experienceApplied(experience);
		} catch (e) {
			diagnosticError = e instanceof ApiError ? e.message : t('diagnostic.loadFailed');
			experienceState(experience, 'error');
			void experienceApplied(experience);
		} finally {
			diagnosticLoading = false;
		}
	}

	async function recoverDelete(): Promise<VolumeDeleteRecoveryResult | null> {
		const volumeId = opts.volumeId();
		if (!volumeId) return null;
		const experience = beginExperienceAction('admin', 'recover', 'resource.detail');
		const request = experience ? api.withExperience(experience) : api;
		experienceState(experience, 'loading');
		recovering = true;
		diagnosticError = '';
		try {
			const result = await request.post<VolumeDeleteRecoveryResult>(
				`/api/v1/admin/volumes/${volumeId}/recover-delete`,
				{},
				opts.token(),
				opts.projectId()
			);
			recoveryResult = result;
			deleteDiagnostic = result.diagnostic;
			experienceState(experience, 'ready');
			void experienceApplied(experience);
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
			diagnosticError = e instanceof ApiError ? e.message : t('diagnostic.recoveryFailed');
			experienceState(experience, 'error');
			void experienceApplied(experience);
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
