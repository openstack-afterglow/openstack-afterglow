import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { tick } from 'svelte';
import type { AdminVolumeDetail, VolumeDeleteDiagnostic, VolumeDeleteRecoveryResult } from '$lib/types/volume';

const mocks = vi.hoisted(() => ({
	apiGet: vi.fn(),
	apiPost: vi.fn(),
	confirmDialog: vi.fn(),
}));

vi.mock('$lib/stores/confirm.svelte', () => ({
	confirmDialog: mocks.confirmDialog,
}));

vi.mock('$lib/api/client', () => {
	class ApiError extends Error {
		status: number;

		constructor(status: number, message: string) {
			super(message);
			this.status = status;
		}
	}

	return {
		ApiError,
		api: {
			get: mocks.apiGet,
			post: mocks.apiPost,
		},
	};
});

import AdminVolumeDetailPanel from '../../AdminVolumeDetailPanel.svelte';

const baseVolume: AdminVolumeDetail = {
	id: 'vol-1',
	name: 'critical-volume',
	status: 'error_deleting',
	size: 120,
	volume_type: 'fast-ssd',
	project_id: 'project-1',
	attachments: [],
	created_at: '2026-07-07T00:00:00Z',
	description: 'Important data volume',
	bootable: false,
	encrypted: true,
	multiattach: false,
	metadata: {},
};

const recoverableDiagnostic: VolumeDeleteDiagnostic = {
	volume_id: 'vol-1',
	status: 'error_deleting',
	project_id: 'project-1',
	name: 'critical-volume',
	size_gb: 120,
	backend_host: 'controller@ceph#ceph',
	updated_at: '2026-07-07T00:00:00Z',
	attachments: [],
	dependencies: [],
	messages: [
		{
			id: 'msg-1',
			event_id: 'VOLUME_DELETE_STALLED',
			request_id: 'req-123',
			message_level: 'ERROR',
			resource_uuid: 'vol-1',
			resource_type: 'VOLUME',
			user_message: 'Volume delete is still pending in Cinder.',
			created_at: '2026-07-07T00:00:01Z',
		},
	],
	checks: [
		{ name: 'auth_preflight', state: 'present', detail: null },
		{ name: 'snapshots', state: 'absent', detail: null },
		{ name: 'rbd_header', state: 'present', detail: 'aa11bb22cc33' },
	],
	backend: {
		mode: 'inspected',
		classification: 'consistent',
		pool: 'volumes',
		image_name: 'volume-vol-1',
		image_id: 'aa11bb22cc33',
		size_bytes: 128849018880,
		order: 22,
		parent_spec: null,
	},
	root_cause_code: 'backend_present_consistent',
	confidence: 'high',
	summary: 'Cinder 레코드와 Ceph RBD 이미지가 일관되어 자동 복구할 수 있습니다.',
	evidence: ['status=error_deleting', 'message=Volume delete is still pending in Cinder.'],
	recommended_action: '자동 복구로 force-delete 후 Ceph backend 부재를 검증하세요.',
	recovery_available: true,
};

const blockedDiagnostic: VolumeDeleteDiagnostic = {
	...recoverableDiagnostic,
	dependencies: [
		{
			id: 'snap-1',
			status: 'available',
			name: 'snapshot-one',
			kind: 'snapshot',
		},
	],
	checks: [...recoverableDiagnostic.checks, { name: 'snapshots', state: 'present', detail: 'snapshot:snap-1' }],
	root_cause_code: 'dependent_resource_present',
	summary: '남아 있는 스냅샷 때문에 자동 복구가 차단되었습니다.',
	evidence: ['snapshots=present'],
	recommended_action: '스냅샷을 먼저 삭제하거나 보존 여부를 확인한 뒤 다시 시도하세요.',
	recovery_available: false,
};

const deletedRecoveryResult: VolumeDeleteRecoveryResult = {
	volume_id: 'vol-1',
	status: 'deleted',
	verified_deleted: true,
	final_status: null,
	backend_verification: 'verified',
	quota_verification: 'verified',
	diagnostic: recoverableDiagnostic,
	steps: [
		{ action: 'diagnose', status: 'success', detail: 'backend_present_consistent' },
		{ action: 'recheck_state', status: 'success', detail: 'error_deleting' },
		{ action: 'force_delete', status: 'success', detail: 'force_delete_submitted' },
		{ action: 'verify_after_force_delete', status: 'success', detail: 'deleted' },
		{ action: 'backend_verify', status: 'success', detail: 'backend_absent' },
		{ action: 'quota_verify', status: 'success', detail: 'volumes:10→9,gigabytes:120→0' },
	],
};

const blockedRecoveryResult: VolumeDeleteRecoveryResult = {
	volume_id: 'vol-1',
	status: 'blocked',
	verified_deleted: false,
	final_status: 'error_deleting',
	backend_verification: 'unavailable',
	quota_verification: 'unavailable',
	diagnostic: blockedDiagnostic,
	steps: [{ action: 'diagnose', status: 'success', detail: 'snapshot blocker detected' }],
};

const residueRecoveryResult: VolumeDeleteRecoveryResult = {
	...deletedRecoveryResult,
	status: 'backend_residue',
	verified_deleted: false,
	backend_verification: 'residue',
	quota_verification: 'verified',
};

function mockVolumeGets(volume: AdminVolumeDetail, diagnostic?: VolumeDeleteDiagnostic) {
	mocks.apiGet.mockImplementation((path: string) => {
		if (path === '/api/v1/admin/volumes/vol-1') return Promise.resolve(volume);
		if (path === '/api/v1/admin/volumes/vol-1/delete-diagnostics' && diagnostic) return Promise.resolve(diagnostic);
		return Promise.reject(new Error(`Unexpected path: ${path}`));
	});
}

function renderPanel(overrides: Partial<{ onClose: () => void; onRefresh: () => void }> = {}) {
	return render(AdminVolumeDetailPanel, {
		props: {
			volumeId: 'vol-1',
			token: 'test-token',
			projectId: 'test-project',
			onClose: overrides.onClose ?? vi.fn(),
			onRefresh: overrides.onRefresh ?? vi.fn(),
		},
	});
}

describe('AdminVolumeDeleteDiagnosticSection', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		mockVolumeGets(baseVolume, recoverableDiagnostic);
		mocks.apiPost.mockResolvedValue(deletedRecoveryResult);
		mocks.confirmDialog.mockResolvedValue(false);
	});

	it('fetches volume detail and delete diagnostics exactly once for error_deleting volumes and renders recovery context', async () => {
		renderPanel();

		await waitFor(() => {
			expect(mocks.apiGet.mock.calls.map((call) => call[0])).toEqual([
				'/api/v1/admin/volumes/vol-1',
				'/api/v1/admin/volumes/vol-1/delete-diagnostics',
			]);
		});

		expect(await screen.findByText('삭제 진단 및 자동 복구')).toBeTruthy();
		expect(screen.getByText('backend_present_consistent')).toBeTruthy();
		expect(screen.getByText(/auth_preflight: present/)).toBeTruthy();
		expect(screen.getByText(/inspected \/ consistent/)).toBeTruthy();
		expect(screen.getByText(/pool=volumes/)).toBeTruthy();
		expect(screen.getByText(/status=error_deleting/)).toBeTruthy();
		expect(screen.getByText(/message=Volume delete is still pending in Cinder\./)).toBeTruthy();
		expect(screen.getByText(/req-123/)).toBeTruthy();
		expect(screen.getByRole('button', { name: '강제 삭제 실행' })).toBeTruthy();
		expect((screen.getByRole('button', { name: 'error 상태로 복구' }) as HTMLButtonElement).disabled).toBe(true);
	});

	it('posts recover-delete after confirmation and closes/refetches on deleted result', async () => {
		mocks.confirmDialog.mockResolvedValue(true);
		const onRefresh = vi.fn();
		const onClose = vi.fn();
		renderPanel({ onRefresh, onClose });

		await screen.findByRole('button', { name: '강제 삭제 실행' });
		await fireEvent.click(screen.getByRole('button', { name: '강제 삭제 실행' }));

		await waitFor(() => {
			expect(mocks.apiPost).toHaveBeenCalledWith(
				'/api/v1/admin/volumes/vol-1/recover-delete',
				{ mode: 'force_delete', confirm_volume_id: 'vol-1', expected_status: 'error_deleting' },
				'test-token',
				'test-project'
			);
			expect(onRefresh).toHaveBeenCalledTimes(1);
			expect(onClose).toHaveBeenCalledTimes(1);
		});
		expect(mocks.confirmDialog.mock.calls[0][0]).toContain('critical-volume');
		expect(mocks.confirmDialog.mock.calls[0][0]).toContain(recoverableDiagnostic.summary);
		expect(mocks.confirmDialog.mock.calls[0][0]).toContain('Ceph RBD metadata');
	});

	it('does not request diagnostics or render the section for available volumes', async () => {
		mockVolumeGets({ ...baseVolume, status: 'available' });
		renderPanel();

		await waitFor(() => {
			expect(mocks.apiGet.mock.calls.map((call) => call[0])).toEqual(['/api/v1/admin/volumes/vol-1']);
		});

		expect(await screen.findByText('기본 정보')).toBeTruthy();
		expect(screen.queryByText('삭제 진단 및 자동 복구')).toBeNull();
	});

	it('keeps the panel open and shows the recommended action when recovery is blocked', async () => {
		mocks.confirmDialog.mockResolvedValue(true);
		mocks.apiPost.mockResolvedValue(blockedRecoveryResult);
		const onRefresh = vi.fn();
		const onClose = vi.fn();
		renderPanel({ onRefresh, onClose });

		await screen.findByRole('button', { name: '강제 삭제 실행' });
		await fireEvent.click(screen.getByRole('button', { name: '강제 삭제 실행' }));

		await waitFor(() => {
			expect(screen.getByText('자동 복구 차단')).toBeTruthy();
			expect(screen.getByText(blockedDiagnostic.recommended_action)).toBeTruthy();
		});

		expect(onRefresh).not.toHaveBeenCalled();
		expect(onClose).not.toHaveBeenCalled();
		expect(screen.getByText('삭제 진단 및 자동 복구')).toBeTruthy();
	});

	it('keeps backend residue visible, refreshes data, and does not close the panel', async () => {
		mocks.confirmDialog.mockResolvedValue(true);
		mocks.apiPost.mockResolvedValue(residueRecoveryResult);
		const onRefresh = vi.fn();
		const onClose = vi.fn();
		renderPanel({ onRefresh, onClose });

		await screen.findByRole('button', { name: '강제 삭제 실행' });
		await fireEvent.click(screen.getByRole('button', { name: '강제 삭제 실행' }));

		await waitFor(() => {
			expect(screen.getByText('Ceph backend 잔여물 확인됨')).toBeTruthy();
			expect(screen.getByText('backend_verification=residue')).toBeTruthy();
			expect(screen.getByText('quota_verification=verified')).toBeTruthy();
		});
		expect(onRefresh).toHaveBeenCalledTimes(1);
		expect(onClose).not.toHaveBeenCalled();
	});

	it.each(['creating', 'downloading'])('automatically diagnoses %s and confirms the fresh diagnostic status for reset', async (status) => {
		const diagnostic: VolumeDeleteDiagnostic = {
			...recoverableDiagnostic, status, root_cause_code: 'creation_stalled',
			creation_age_seconds: status === 'creating' ? 1800 : 21600, owner_service_hint: 'palimpsest',
		};
		const refreshedDiagnostic: VolumeDeleteDiagnostic = { ...diagnostic, status: 'error', root_cause_code: 'backend_present_consistent' };
		mockVolumeGets({ ...baseVolume, status }, diagnostic);
		mocks.confirmDialog.mockResolvedValue(true);
		mocks.apiPost.mockImplementation(() => {
			mockVolumeGets({ ...baseVolume, status: 'error' }, refreshedDiagnostic);
			return Promise.resolve({
				...deletedRecoveryResult, status: 'state_reset', previous_status: status, final_status: 'error',
				verified_deleted: false, diagnostic: refreshedDiagnostic,
				steps: [{ action: 'reset_state', status: 'success', detail: `${status}→error` }],
			});
		});
		const onClose = vi.fn();
		const onRefresh = vi.fn();
		renderPanel({ onClose, onRefresh });
		await screen.findByText('creation_stalled');
		expect(screen.getByText(/Palimpsest 관리 볼륨/)).toBeTruthy();
		expect(screen.getByText(/creating은 30분, downloading은 6시간/)).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: 'error 상태로 복구' }));
		await waitFor(() => expect(mocks.apiPost).toHaveBeenCalledWith(
			'/api/v1/admin/volumes/vol-1/recover-delete',
			{ mode: 'recover', confirm_volume_id: 'vol-1', expected_status: status },
			'test-token', 'test-project',
		));
		expect(mocks.confirmDialog).toHaveBeenCalledWith(expect.stringContaining(`UUID: vol-1, 현재 진단 상태: ${status}`), {
			confirmLabel: 'error 상태로 복구', confirmVariant: 'danger',
		});
		await screen.findByText('error 상태 전환 확인됨');
		expect(screen.getByText(new RegExp(`reset_state: success.*${status}→error`))).toBeTruthy();
		await waitFor(() => expect(mocks.apiGet).toHaveBeenCalledWith(
			'/api/v1/admin/volumes/vol-1', 'test-token', 'test-project', { refresh: true },
		));
		expect(onRefresh).toHaveBeenCalledOnce();
		expect(onClose).not.toHaveBeenCalled();
	});

	it('force deletes stalled creation only after explicit UUID/status confirmation', async () => {
		mockVolumeGets({ ...baseVolume, status: 'creating' }, {
			...recoverableDiagnostic, status: 'creating', root_cause_code: 'creation_stalled', creation_age_seconds: 1800,
		});
		mocks.confirmDialog.mockResolvedValue(true);
		renderPanel();
		await fireEvent.click(await screen.findByRole('button', { name: '강제 삭제 실행' }));
		await waitFor(() => expect(mocks.apiPost).toHaveBeenCalledWith(
			'/api/v1/admin/volumes/vol-1/recover-delete',
			{ mode: 'force_delete', confirm_volume_id: 'vol-1', expected_status: 'creating' },
			'test-token', 'test-project',
		));
		expect(mocks.confirmDialog.mock.calls[0][0]).toContain('현재 진단 상태: creating');
		expect(mocks.confirmDialog.mock.calls[0][1]).toEqual({ confirmLabel: '강제 삭제 실행', confirmVariant: 'danger' });
	});

	it.each(['creation_in_progress', 'creation_active_watcher', 'backend_lookup_unknown', 'dependent_resource_present'] as const)(
		'disables both actions for %s while preserving diagnostic retry', async (root_cause_code) => {
			mockVolumeGets({ ...baseVolume, status: 'downloading' }, {
				...recoverableDiagnostic, status: 'downloading', root_cause_code,
				creation_age_seconds: null, recovery_available: false,
			});
			renderPanel();
			await screen.findByText(root_cause_code);
			expect((screen.getByRole('button', { name: 'error 상태로 복구' }) as HTMLButtonElement).disabled).toBe(true);
			expect((screen.getByRole('button', { name: '강제 삭제 실행' }) as HTMLButtonElement).disabled).toBe(true);
			expect((screen.getByRole('button', { name: '진단 다시 실행' }) as HTMLButtonElement).disabled).toBe(false);
			expect(mocks.apiPost).not.toHaveBeenCalled();
			if (root_cause_code === 'creation_active_watcher') expect(screen.getByText(/client\/c-vol\/image-copy 작업/)).toBeTruthy();
		},
	);

	it('does not allow a watcher blocker even if recovery availability is inconsistent', async () => {
		mockVolumeGets({ ...baseVolume, status: 'creating' }, {
			...recoverableDiagnostic, status: 'creating', root_cause_code: 'creation_active_watcher',
			recovery_available: true,
		});
		renderPanel();
		await screen.findByText('creation_active_watcher');
		await fireEvent.click(screen.getByRole('button', { name: '강제 삭제 실행' }));
		expect(mocks.confirmDialog).not.toHaveBeenCalled();
		expect(mocks.apiPost).not.toHaveBeenCalled();
	});

	it('shows unconfigured backend risk and Afterglow ownership without exposing metadata values', async () => {
		mockVolumeGets({ ...baseVolume, status: 'creating' }, {
			...recoverableDiagnostic, status: 'creating', root_cause_code: 'creation_stalled',
			owner_service_hint: 'afterglow', backend: { ...recoverableDiagnostic.backend, mode: 'unavailable', classification: 'not_inspected' },
		});
		renderPanel();
		await screen.findByText(/Afterglow 관리 볼륨/);
		expect(screen.getByText(/Ceph 검사가 설정되지 않아/)).toBeTruthy();
		expect((screen.getByRole('button', { name: 'error 상태로 복구' }) as HTMLButtonElement).disabled).toBe(false);
	});

	it('cancels without mutation and disables all actions during confirmation', async () => {
		const confirmation = Promise.withResolvers<boolean>();
		mocks.confirmDialog.mockReturnValue(confirmation.promise);
		renderPanel();
		await fireEvent.click(await screen.findByRole('button', { name: '강제 삭제 실행' }));
		expect((screen.getByRole('button', { name: '강제 삭제 실행' }) as HTMLButtonElement).disabled).toBe(true);
		expect((screen.getByRole('button', { name: '진단 다시 실행' }) as HTMLButtonElement).disabled).toBe(true);
		confirmation.resolve(false);
		await waitFor(() => expect((screen.getByRole('button', { name: '강제 삭제 실행' }) as HTMLButtonElement).disabled).toBe(false));
		expect(mocks.apiPost).not.toHaveBeenCalled();
	});

	it('blocks mutation while diagnostics are refreshing and after refresh failure', async () => {
		const refresh = Promise.withResolvers<VolumeDeleteDiagnostic>();
		renderPanel();
		await screen.findByText('backend_present_consistent');
		mocks.apiGet.mockReturnValueOnce(refresh.promise);
		await fireEvent.click(screen.getByRole('button', { name: '진단 다시 실행' }));
		expect((screen.getByRole('button', { name: '강제 삭제 실행' }) as HTMLButtonElement).disabled).toBe(true);
		refresh.reject(new Error('offline'));
		await screen.findByText('볼륨 삭제 진단 실패');
		expect((screen.getByRole('button', { name: '강제 삭제 실행' }) as HTMLButtonElement).disabled).toBe(true);
		expect(mocks.apiPost).not.toHaveBeenCalled();
	});

	it('does not close an unverified deleted response', async () => {
		mocks.confirmDialog.mockResolvedValue(true);
		mocks.apiPost.mockResolvedValue({ ...deletedRecoveryResult, verified_deleted: false });
		const onClose = vi.fn();
		renderPanel({ onClose });
		await fireEvent.click(await screen.findByRole('button', { name: '강제 삭제 실행' }));
		await screen.findByText('verified_deleted=false');
		expect(onClose).not.toHaveBeenCalled();
	});

	it('keeps error reset idempotent and never substitutes error_deleting for error', async () => {
		mockVolumeGets({ ...baseVolume, status: 'error' }, { ...recoverableDiagnostic, status: 'error' });
		mocks.confirmDialog.mockResolvedValue(true);
		mocks.apiPost.mockResolvedValue({
			...deletedRecoveryResult, status: 'state_reset', previous_status: 'error', final_status: 'error',
			verified_deleted: false, diagnostic: { ...recoverableDiagnostic, status: 'error' },
			steps: [{ action: 'reset_state', status: 'success', detail: 'already_error' }],
		});
		renderPanel();
		await screen.findByText('backend_present_consistent');
		expect((screen.getByRole('button', { name: 'error 상태로 복구' }) as HTMLButtonElement).disabled).toBe(false);
		await fireEvent.click(screen.getByRole('button', { name: 'error 상태로 복구' }));
		await waitFor(() => expect(mocks.apiPost).toHaveBeenCalledWith(
			'/api/v1/admin/volumes/vol-1/recover-delete',
			{ mode: 'recover', confirm_volume_id: 'vol-1', expected_status: 'error' },
			'test-token', 'test-project',
		));
	});

	it('does not mutate after its confirmation owner unmounts', async () => {
		const confirmation = Promise.withResolvers<boolean>();
		mocks.confirmDialog.mockReturnValue(confirmation.promise);
		const panel = renderPanel();
		await fireEvent.click(await screen.findByRole('button', { name: '강제 삭제 실행' }));
		panel.unmount();
		confirmation.resolve(true);
		await waitFor(() => expect(mocks.confirmDialog).toHaveBeenCalledOnce());
		expect(mocks.apiPost).not.toHaveBeenCalled();
	});

	it('warns and refreshes when native force delete changes stalled creation to available without deleting', async () => {
		const diagnostic: VolumeDeleteDiagnostic = { ...recoverableDiagnostic, status: 'creating', root_cause_code: 'creation_stalled' };
		mockVolumeGets({ ...baseVolume, status: 'creating' }, diagnostic);
		mocks.confirmDialog.mockResolvedValue(true);
		mocks.apiPost.mockImplementation(() => {
			mockVolumeGets({ ...baseVolume, status: 'available' });
			return Promise.resolve({
				...deletedRecoveryResult, status: 'failed', verified_deleted: false, final_status: 'available',
				diagnostic: { ...diagnostic, status: 'available', root_cause_code: 'not_recoverable_status', recovery_available: false },
				steps: [{ action: 'verify_after_force_delete', status: 'failed', detail: 'creation_delete_state_changed:available' }],
			});
		});
		const onClose = vi.fn();
		const onRefresh = vi.fn();
		renderPanel({ onClose, onRefresh });
		await fireEvent.click(await screen.findByRole('button', { name: '강제 삭제 실행' }));
		await screen.findByText(/provider가 볼륨 상태를 available/);
		expect(screen.getByText(/이미지가 불완전할 수 있으므로/)).toBeTruthy();
		expect(screen.getByText(/watcher가 사라진 뒤 진단을 다시 실행/)).toBeTruthy();
		await waitFor(() => expect(mocks.apiGet).toHaveBeenCalledWith(
			'/api/v1/admin/volumes/vol-1', 'test-token', 'test-project', { refresh: true },
		));
		expect(mocks.apiPost).toHaveBeenCalledOnce();
		expect(onRefresh).toHaveBeenCalledOnce();
		expect(onClose).not.toHaveBeenCalled();
	});
	it('refreshes metadata and list after a reset succeeds but deletion fails', async () => {
		const diagnostic: VolumeDeleteDiagnostic = { ...recoverableDiagnostic, status: 'creating', root_cause_code: 'creation_stalled' };
		mockVolumeGets({ ...baseVolume, status: 'creating' }, diagnostic);
		mocks.confirmDialog.mockResolvedValue(true);
		mocks.apiPost.mockImplementation(() => {
			mockVolumeGets({ ...baseVolume, status: 'error' });
			return Promise.resolve({
				...deletedRecoveryResult, status: 'failed', verified_deleted: false, final_status: 'error',
				diagnostic: { ...recoverableDiagnostic, status: 'error' },
				steps: [
					{ action: 'reset_state', status: 'success', detail: 'error' },
					{ action: 'force_delete', status: 'failed', detail: 'RuntimeError' },
				],
			});
		});
		const onClose = vi.fn();
		const onRefresh = vi.fn();
		renderPanel({ onClose, onRefresh });
		await fireEvent.click(await screen.findByRole('button', { name: '강제 삭제 실행' }));
		await waitFor(() => expect(mocks.apiGet).toHaveBeenCalledWith(
			'/api/v1/admin/volumes/vol-1', 'test-token', 'test-project', { refresh: true },
		));
		expect(onRefresh).toHaveBeenCalledOnce();
		expect(onClose).not.toHaveBeenCalled();
		expect(screen.getByText('reset_state: success — error')).toBeTruthy();
	});

	it('clears pending creation diagnostics when the mounted panel switches to an available volume', async () => {
		const pending = Promise.withResolvers<VolumeDeleteDiagnostic>();
		mocks.apiGet.mockImplementation((path: string) => {
			if (path === '/api/v1/admin/volumes/vol-1') return Promise.resolve({ ...baseVolume, status: 'creating' });
			if (path === '/api/v1/admin/volumes/vol-1/delete-diagnostics') return pending.promise;
			if (path === '/api/v1/admin/volumes/vol-2') return Promise.resolve({ ...baseVolume, id: 'vol-2', name: 'second-volume', status: 'available' });
			return Promise.reject(new Error(`Unexpected path: ${path}`));
		});
		const panel = renderPanel();
		await waitFor(() => expect(mocks.apiGet.mock.calls.some(([path]) => path === '/api/v1/admin/volumes/vol-1/delete-diagnostics')).toBe(true));
		await panel.rerender({ volumeId: 'vol-2', token: 'test-token', projectId: 'test-project' });
		await screen.findByText('기본 정보');
		expect(screen.queryByText('삭제 진단 및 자동 복구')).toBeNull();
		pending.resolve({ ...recoverableDiagnostic, status: 'creating', root_cause_code: 'creation_stalled' });
		await tick();
		expect(screen.queryByText('삭제 진단 및 자동 복구')).toBeNull();
		expect(screen.queryByRole('button', { name: 'error 상태로 복구' })).toBeNull();
		expect(mocks.apiPost).not.toHaveBeenCalled();
	});
});
