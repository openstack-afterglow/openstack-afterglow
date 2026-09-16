import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
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
		expect(screen.getByRole('button', { name: '자동 복구 실행' })).toBeTruthy();
	});

	it('posts recover-delete after confirmation and closes/refetches on deleted result', async () => {
		mocks.confirmDialog.mockResolvedValue(true);
		const onRefresh = vi.fn();
		const onClose = vi.fn();
		renderPanel({ onRefresh, onClose });

		await screen.findByRole('button', { name: '자동 복구 실행' });
		await fireEvent.click(screen.getByRole('button', { name: '자동 복구 실행' }));

		await waitFor(() => {
			expect(mocks.apiPost).toHaveBeenCalledWith(
				'/api/v1/admin/volumes/vol-1/recover-delete',
				{},
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

		await screen.findByRole('button', { name: '자동 복구 실행' });
		await fireEvent.click(screen.getByRole('button', { name: '자동 복구 실행' }));

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

		await screen.findByRole('button', { name: '자동 복구 실행' });
		await fireEvent.click(screen.getByRole('button', { name: '자동 복구 실행' }));

		await waitFor(() => {
			expect(screen.getByText('Ceph backend 잔여물 확인됨')).toBeTruthy();
			expect(screen.getByText('backend_verification=residue')).toBeTruthy();
			expect(screen.getByText('quota_verification=verified')).toBeTruthy();
		});
		expect(onRefresh).toHaveBeenCalledTimes(1);
		expect(onClose).not.toHaveBeenCalled();
	});
});
