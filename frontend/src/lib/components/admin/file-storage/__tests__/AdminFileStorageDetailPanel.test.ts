import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { Mock } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/svelte';
import type { AccessRule, FileStorage, FileStorageDeleteDiagnostic } from '$lib/types/fileStorage';

const mocks = vi.hoisted(() => ({
	apiGet: vi.fn(),
	apiDelete: vi.fn(),
	apiPost: vi.fn(),
	apiMut: vi.fn((_label: string, fn: () => Promise<unknown>) => fn()),
	confirmDialog: vi.fn(),
	createAutoRefresh: vi.fn(() => ({
		active: true,
		intervalSeconds: 15,
		intervalOptions: [10, 15, 30, 60],
	})),
}));

vi.mock('$env/dynamic/public', () => ({
	env: { PUBLIC_API_BASE: 'http://backend.test' },
}));

vi.mock('$lib/stores/auth', () => ({
	auth: {
		subscribe: (run: (value: { token: string; projectId: string }) => void) => {
			run({ token: 'test-token', projectId: 'test-project' });
			return () => {};
		},
	},
}));

vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: mocks.createAutoRefresh,
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
			delete: mocks.apiDelete,
			post: mocks.apiPost,
		},
	};
});

vi.mock('$lib/api/mutations', () => ({
	apiMut: mocks.apiMut,
}));

import AdminFileStorageDetailPanel from '../AdminFileStorageDetailPanel.svelte';

const fileStorage: FileStorage = {
	id: 'share-1',
	name: 'share-one',
	status: 'available',
	size: 20,
	share_proto: 'CEPHFS',
	export_locations: ['10.0.0.10:/volumes/share-one'],
	metadata: { union_type: 'dynamic' },
	project_id: 'test-project',
	created_at: '2026-06-01T00:00:00Z',
	is_public: false,
	library_name: null,
	library_version: null,
	built_at: null,
	progress: '100%',
	user_id: 'user-1',
	user_name: 'User One',
	access_rules_status: 'active',
	host: 'host@backend#pool',
	availability_zone: 'az-one',
	share_type_name: 'cephfs-rw',
	share_network_id: 'share-network-1',
	export_location_details: [
		{
			path: '10.0.0.10:/volumes/share-one',
			preferred: true,
			share_instance_id: 'instance-1',
		},
	],
};

const accessRule: AccessRule = {
	id: 'rule-1',
	access_to: '10.0.0.0/24',
	access_level: 'rw',
	access_type: 'ip',
	state: 'active',
	access_key: 'secret-access-key-value',
};

const deleteDiagnostic: FileStorageDeleteDiagnostic = {
	file_storage_id: 'share-1',
	status: 'error_deleting',
	share_proto: 'NFS',
	share_type_name: 'nfstype',
	share_network_id: 'share-network-1',
	share_instance_ids: ['inst-1'],
	root_cause_code: 'dhss_false_share_network_mismatch',
	confidence: 'high',
	summary: 'DHSS=False share type에 share_network_id가 포함되어 Manila 드라이버가 작업을 거부한 것으로 판단됩니다.',
	evidence: ['share_type_name=nfstype', 'driver_handles_share_servers=False', 'share_network_id=share-network-1'],
	recommended_action: '관리자 강제 삭제로 Manila share/instance DB 레코드를 제거하세요.',
	force_delete_available: true,
};

const errorDeletingFileStorage: FileStorage = {
	...fileStorage,
	status: 'error_deleting',
	share_proto: 'NFS',
	share_type_name: 'nfstype',
	share_network_id: 'share-network-1',
};

function mockSuccessfulGets(storage: FileStorage = fileStorage, diagnostic: FileStorageDeleteDiagnostic = deleteDiagnostic) {
	mocks.apiGet.mockImplementation((path: string) => {
		if (path === '/api/v1/admin/file-storage/share-1') return Promise.resolve(storage);
		if (path === '/api/v1/admin/file-storage/share-1/access-rules') return Promise.resolve([accessRule]);
		if (path === '/api/v1/admin/file-storage/share-1/delete-diagnostics') return Promise.resolve(diagnostic);
		return Promise.reject(new Error(`Unexpected path: ${path}`));
	});
}

function renderPanel(overrides: Partial<{ onClose: () => void; onDeleted: () => void | Promise<void> }> = {}) {
	return render(AdminFileStorageDetailPanel, {
		props: {
			fileStorageId: 'share-1',
			onClose: overrides.onClose ?? vi.fn(),
			onDeleted: overrides.onDeleted ?? vi.fn(),
		},
	});
}

describe('AdminFileStorageDetailPanel', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		mockSuccessfulGets();
		mocks.apiDelete.mockResolvedValue(undefined);
		mocks.apiPost.mockResolvedValue({ file_storage_id: 'share-1', status: 'force_delete_submitted', diagnostic: deleteDiagnostic });
		mocks.confirmDialog.mockResolvedValue(false);
		Object.defineProperty(navigator, 'clipboard', {
			value: { writeText: vi.fn().mockResolvedValue(undefined) },
			configurable: true,
		});
	});

	it('loads file storage details and read-only access rules', async () => {
		renderPanel();

		await waitFor(() => {
			expect(mocks.apiGet).toHaveBeenCalledWith('/api/v1/admin/file-storage/share-1', 'test-token', 'test-project', undefined);
			expect(mocks.apiGet).toHaveBeenCalledWith('/api/v1/admin/file-storage/share-1/access-rules', 'test-token', 'test-project', undefined);
		});

		expect(await screen.findByText('host@backend#pool')).toBeTruthy();
		await Promise.resolve();
		await Promise.resolve();
		expect(mocks.apiGet).toHaveBeenCalledTimes(2);
		expect(mocks.createAutoRefresh).toHaveBeenCalledWith(
			expect.any(Function),
			expect.objectContaining({ invokeOnMount: false })
		);
		expect(screen.getByText('share-network-1')).toBeTruthy();
		expect(screen.getByText('접근 규칙 (읽기 전용)')).toBeTruthy();
		expect(screen.getByText('내부 데이터')).toBeTruthy();
		expect(screen.queryByText('+ 추가')).toBeNull();
	});

	it('reads foreign-project storage without offering caller-owned delete', async () => {
		mockSuccessfulGets({ ...fileStorage, project_id: 'foreign-project' });
		renderPanel();
		expect(await screen.findByText('host@backend#pool')).toBeTruthy();
		expect(screen.queryByRole('button', { name: '파일 스토리지 삭제' })).toBeNull();
		expect(mocks.apiGet.mock.calls.every(call => String(call[0]).startsWith('/api/v1/admin/'))).toBe(true);
		expect(mocks.apiDelete).not.toHaveBeenCalled();
	});

	it('copies raw internal JSON', async () => {
		renderPanel();

		await screen.findByText('내부 데이터');
		await fireEvent.click(screen.getByRole('button', { name: 'Raw JSON 복사' }));

		const writeText = navigator.clipboard.writeText as Mock;
		expect(writeText).toHaveBeenCalledTimes(1);
		const copiedJson = writeText.mock.calls[0][0] as string;
		expect(copiedJson).toContain('share-1');
		expect(copiedJson).toContain('rule-1');
	});

	it('deletes through the existing file-storage endpoint and closes on success', async () => {
		mocks.confirmDialog.mockResolvedValue(true);
		const onDeleted = vi.fn().mockResolvedValue(undefined);
		const onClose = vi.fn();
		renderPanel({ onDeleted, onClose });

		await screen.findByText('파일 스토리지 삭제');
		await fireEvent.click(screen.getByRole('button', { name: '파일 스토리지 삭제' }));

		await waitFor(() => {
			expect(mocks.apiDelete).toHaveBeenCalledWith('/api/v1/file-storage/share-1', 'test-token', 'test-project');
			expect(onDeleted).toHaveBeenCalledTimes(1);
			expect(onClose).toHaveBeenCalledTimes(1);
		});
	});

	it('loads and renders delete diagnostics for error_deleting shares', async () => {
		mockSuccessfulGets(errorDeletingFileStorage);
		renderPanel();

		await waitFor(() => {
			expect(mocks.apiGet.mock.calls.map((call) => call[0])).toEqual([
				'/api/v1/admin/file-storage/share-1',
				'/api/v1/admin/file-storage/share-1/access-rules',
				'/api/v1/admin/file-storage/share-1/delete-diagnostics',
			]);
		});

		expect(await screen.findByText('삭제 진단 및 복구 시나리오')).toBeTruthy();
		expect(screen.getByText('driver_handles_share_servers=False')).toBeTruthy();
		expect(screen.getByText('share_network_id=share-network-1')).toBeTruthy();
		expect(screen.getByRole('button', { name: '강제 삭제' })).toBeTruthy();
	});

	it('force-deletes through the admin repair endpoint and closes on success', async () => {
		mockSuccessfulGets(errorDeletingFileStorage);
		mocks.confirmDialog.mockResolvedValue(true);
		const onDeleted = vi.fn().mockResolvedValue(undefined);
		const onClose = vi.fn();
		renderPanel({ onDeleted, onClose });

		await screen.findByRole('button', { name: '강제 삭제' });
		await fireEvent.click(screen.getByRole('button', { name: '강제 삭제' }));

		await waitFor(() => {
			expect(mocks.apiPost).toHaveBeenCalledWith(
				'/api/v1/admin/file-storage/share-1/force-delete',
				{},
				'test-token',
				'test-project'
			);
			expect(onDeleted).toHaveBeenCalledTimes(1);
			expect(onClose).toHaveBeenCalledTimes(1);
		});
		expect(mocks.confirmDialog.mock.calls[0][0]).toContain('share-one');
		expect(mocks.confirmDialog.mock.calls[0][0]).toContain(deleteDiagnostic.summary);
	});

	it('does not request diagnostics or show force-delete for available shares', async () => {
		renderPanel();

		await waitFor(() => {
			expect(mocks.apiGet).toHaveBeenCalledWith('/api/v1/admin/file-storage/share-1', 'test-token', 'test-project', undefined);
			expect(mocks.apiGet).toHaveBeenCalledWith('/api/v1/admin/file-storage/share-1/access-rules', 'test-token', 'test-project', undefined);
		});

		expect(mocks.apiGet.mock.calls.map((call) => call[0])).not.toContain('/api/v1/admin/file-storage/share-1/delete-diagnostics');
		expect(screen.queryByText('삭제 진단 및 복구 시나리오')).toBeNull();
		expect(screen.queryByRole('button', { name: '강제 삭제' })).toBeNull();
	});
});
