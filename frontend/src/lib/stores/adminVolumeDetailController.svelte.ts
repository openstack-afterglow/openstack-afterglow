import { t } from '$lib/i18n/ns/admin-storage';
import { getContext, onDestroy, setContext, untrack } from 'svelte';
import { api, ApiError } from '$lib/api/client';
import type { AdminVolumeDetail, VolumeDeleteDiagnostic, VolumeDeleteRecoveryResult, VolumeDeleteRecoveryMode } from '$lib/types/volume';
import { beginExperienceAction, beginExperienceLoad, experienceState, experienceApplied, experienceDiscarded, type ExperienceContext } from '$lib/utils/experience';

interface Options {
	volumeId: () => string;
	token: () => string | undefined;
	projectId: () => string | undefined;
	onClose?: () => void;
	onRefresh?: () => void;
}

const diagnosticStatuses: Record<string, true> = {
	creating: true,
	downloading: true,
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
	let diagnosticScope = '';
	let mounted = true;
	onDestroy(() => { mounted = false; });
	const currentScope = () => JSON.stringify([mounted, opts.volumeId(), opts.token(), opts.projectId()]);
	let recovering = $state(false);
	let lastVolumeId = '';

	$effect(() => {
		const volumeId = opts.volumeId();
		opts.token();
		opts.projectId();
		diagnosticLoading = false;
		diagnosticScope = '';
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

	// Keep diagnostics and confirmed mutations bound to the selected volume and request scope.
	async function fetchVolume() {
		const scope = currentScope();
		const experience = beginExperienceLoad('admin', 'resource.detail');
		const request = experience ? api.withExperience(experience) : api;
		experienceState(experience, 'loading');
		try {
			const currentVolume = await request.get<AdminVolumeDetail>(`/api/v1/admin/volumes/${opts.volumeId()}`, opts.token(), opts.projectId());
			if (scope !== currentScope()) { experienceDiscarded(experience, 'scope_changed'); return; }
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
			if (scope !== currentScope()) { experienceDiscarded(experience, 'scope_changed'); return; }
			error = e instanceof ApiError ? e.message : t('volumeDetail.loadFailed');
			experienceState(experience, 'error');
			void experienceApplied(experience);
		} finally {
			if (scope === currentScope()) loading = false;
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
		const scope = currentScope();
		try {
			const diagnostic = await request.get<VolumeDeleteDiagnostic>(
				`/api/v1/admin/volumes/${volumeId}/delete-diagnostics`,
				opts.token(),
				opts.projectId(),
				requestOpts
			);
			if (scope !== currentScope()) return;
			deleteDiagnostic = diagnostic;
			diagnosticScope = scope;
			experienceState(experience, deleteDiagnostic ? 'ready' : 'empty');
			void experienceApplied(experience);
		} catch (e) {
			if (scope !== currentScope()) { experienceDiscarded(experience, 'scope_changed'); return; }
			diagnosticScope = '';
			diagnosticError = e instanceof ApiError ? e.message : t('diagnostic.loadFailed');
			experienceState(experience, 'error');
			void experienceApplied(experience);
		} finally {
			if (scope === currentScope()) diagnosticLoading = false;
		}
	}

	async function recoverDelete(mode: VolumeDeleteRecoveryMode = 'force_delete', confirmedDiagnostic = deleteDiagnostic): Promise<VolumeDeleteRecoveryResult | null> {
		const volumeId = opts.volumeId();
		if (!volumeId || recovering || diagnosticLoading || diagnosticError || !confirmedDiagnostic
			|| confirmedDiagnostic !== deleteDiagnostic || confirmedDiagnostic.volume_id !== volumeId
			|| diagnosticScope !== currentScope() || volume?.id !== volumeId
			|| !confirmedDiagnostic.status || !confirmedDiagnostic.recovery_available
			|| confirmedDiagnostic.root_cause_code === 'creation_active_watcher'
			|| (mode === 'recover' && confirmedDiagnostic.root_cause_code !== 'creation_stalled' && confirmedDiagnostic.status !== 'error')) return null;
		const scope = currentScope();
		const experience = beginExperienceAction('admin', 'recover', 'resource.detail');
		const request = experience ? api.withExperience(experience) : api;
		experienceState(experience, 'loading');
		recovering = true;
		diagnosticError = '';
		try {
			const result = await request.post<VolumeDeleteRecoveryResult>(
				`/api/v1/admin/volumes/${volumeId}/recover-delete`,
				{ mode, confirm_volume_id: volumeId, expected_status: confirmedDiagnostic.status },
				opts.token(),
				opts.projectId()
			);
			if (scope !== currentScope()) { experienceDiscarded(experience, 'scope_changed'); return null; }
			const creationStateChanged = result.steps.some(step => step.detail?.startsWith('creation_delete_state_changed:'));
			const stateReset = result.steps.some(step => step.action === 'reset_state' && step.status === 'success');
			recoveryResult = result;
			deleteDiagnostic = result.diagnostic;
			experienceState(experience, 'ready');
			void experienceApplied(experience);
			if ((result.status === 'deleted' || result.status === 'already_deleted') && result.verified_deleted) {
				opts.onRefresh?.();
				opts.onClose?.();
			} else if (
				result.status === 'state_reset' ||
				result.status === 'delete_submitted' ||
				result.status === 'backend_residue' ||
				result.status === 'backend_unverified' || creationStateChanged || stateReset
			) {
				opts.onRefresh?.();
				if (result.status === 'state_reset' || creationStateChanged || stateReset) {
					// Refresh metadata without replacing the returned diagnostic or its action timeline.
					try {
						const refreshed = await request.get<AdminVolumeDetail>(`/api/v1/admin/volumes/${volumeId}`, opts.token(), opts.projectId(), { refresh: true });
						if (scope !== currentScope()) { experienceDiscarded(experience, 'scope_changed'); return null; }
						volume = refreshed;
					} catch (e) {
						if (scope !== currentScope()) { experienceDiscarded(experience, 'scope_changed'); return null; }
						diagnosticError = e instanceof ApiError ? e.message : t('volumeDetail.loadFailed');
					}
				}
			}
			return result;
		} catch (e) {
			if (scope !== currentScope()) { experienceDiscarded(experience, 'scope_changed'); return null; }
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
