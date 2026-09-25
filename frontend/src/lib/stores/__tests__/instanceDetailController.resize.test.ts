import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/svelte';
import { derived, writable } from 'svelte/store';
import type { Instance } from '$lib/types/compute';
import type { FlavorOption } from '$lib/types/flavor';
import type { InstanceDetailController } from '../instanceDetailController.svelte';

const { mockGet, mockPost, confirmDialog, toastError } = vi.hoisted(() => ({
	mockGet: vi.fn(), mockPost: vi.fn(), confirmDialog: vi.fn(), toastError: vi.fn(),
}));
vi.mock('$lib/stores/auth', () => {
	const auth = writable({ token: 'token', projectId: 'own-project', roles: ['member'], isSystemAdmin: false });
	return {
		auth,
		canWrite: derived(auth, state => state.isSystemAdmin || state.roles.some(role => ['admin', 'member'].includes(role))),
	};
});
vi.mock('$lib/api/client', () => ({
	api: { get: mockGet, post: mockPost },
	ApiError: class ApiError extends Error { status = 409; },
}));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog }));
vi.mock('$lib/stores/toast', () => ({ toast: { error: toastError } }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({ active: false, intervalSeconds: 30, intervalOptions: [15, 30, 60], setBoost: vi.fn() }),
}));

import { auth } from '$lib/stores/auth';
import Probe from './_InstanceDetailControllerProbe.svelte';

type Controller = InstanceDetailController;
const flavors: FlavorOption[] = [
	{ id: 'current', name: 'current', vcpus: 2, ram: 4096, disk: 20, is_public: true },
	{ id: 'next', name: 'next', vcpus: 4, ram: 8192, disk: 20, is_public: true },
	{ id: 'blocked', name: 'blocked', vcpus: 8, ram: 16384, disk: 20, is_public: true,
		eligibility: { selectable: false, blockers: [{ code: 'disk_shrink' }], requirements: { instances: 0, cores: 0, ram_mb: 0, gpus: {} }, remaining: { instances: 0, cores: 0, ram_mb: 0, gpus: {} } } },
];
let status = 'ACTIVE';
let flavorRequest: string;

async function setup(adminMode = false): Promise<Controller> {
	let controller: Controller | undefined;
	render(Probe, {
		source: { id: 'vm', projectId: 'target-project', adminMode },
		onReady: value => { controller = value; },
	});
	await vi.waitFor(() => expect(controller).toBeDefined());
	await controller!.fetchInstance('vm');
	return controller!;
}

beforeEach(() => {
	vi.clearAllMocks();
	status = 'ACTIVE';
	flavorRequest = '';
	auth.update(state => ({ ...state, token: 'token', projectId: 'own-project', roles: ['member'], isSystemAdmin: false }));
	confirmDialog.mockResolvedValue(true);
	mockGet.mockImplementation((path: string) => {
		if (path === '/api/v1/instances/vm') return Promise.resolve({
			id: 'vm', name: 'vm', status, flavor_id: 'current', flavor_name: 'current', image_name: null,
			ip_addresses: [], created_at: null, union_libraries: [], union_strategy: null,
		} satisfies Instance);
		if (path === '/api/v1/instances/vm/resize-flavors') {
			flavorRequest = path;
			return Promise.resolve(flavors);
		}
		if (path.endsWith('/security-groups')) return Promise.resolve({ ports: [], security_groups: [] });
		if (path.endsWith('/owner')) return Promise.resolve({ display: '' });
		return Promise.resolve([]);
	});
	mockPost.mockResolvedValue({});
});

describe('instance detail resize routing', () => {
	it.each([
		[false, '/api/v1/instances/vm/resize-flavors', '/api/v1/instances/vm', 'target-project'],
		[true, '/api/v1/instances/vm/resize-flavors', '/api/v1/admin/instances/vm', 'own-project'],
	] as const)('loads eligible flavors and performs resize/confirm/revert for adminMode=%s', async (adminMode, getPath, actionBase, projectId) => {
		const s = await setup(adminMode);
		await s.loadResizeFlavors();
		expect(flavorRequest).toBe(getPath);
		expect(mockGet).toHaveBeenCalledWith(getPath, 'token', projectId);
		expect(await s.doResize('current')).toBe(false);
		expect(await s.doResize('blocked')).toBe(false);
		expect(mockPost).not.toHaveBeenCalled();
		expect(await s.doResize('next')).toBe(true);
		expect(mockPost).toHaveBeenCalledWith(`${actionBase}/resize`, { flavor_id: 'next' }, 'token', projectId);

		status = 'VERIFY_RESIZE';
		await s.fetchInstance('vm');
		await s.confirmResize();
		await s.revertResize();
		expect(confirmDialog).toHaveBeenCalledWith('리사이즈를 확인하시겠습니까?');
		expect(confirmDialog).toHaveBeenCalledWith('리사이즈를 취소하고 이전 플레이버로 복귀하시겠습니까?');
		expect(mockPost).toHaveBeenCalledWith(`${actionBase}/confirm-resize`, {}, 'token', projectId);
		expect(mockPost).toHaveBeenCalledWith(`${actionBase}/revert-resize`, {}, 'token', projectId);
	});

	it('never requests flavors or posts resize actions for a reader, even when invoked directly', async () => {
		auth.update(state => ({ ...state, roles: ['reader'] }));
		const s = await setup();
		await s.loadResizeFlavors();
		expect(flavorRequest).toBe('');
		expect(await s.doResize('next')).toBe(false);
		status = 'VERIFY_RESIZE';
		await s.fetchInstance('vm');
		await s.confirmResize();
		await s.revertResize();
		expect(confirmDialog).not.toHaveBeenCalled();
		expect(mockPost).not.toHaveBeenCalled();
	});

	it('surfaces flavor loading and mutation errors and preserves the selection for retry', async () => {
		const s = await setup();
		mockGet.mockRejectedValueOnce(new Error('unavailable'));
		await s.loadResizeFlavors();
		expect(s.resizeError).toBe('플레이버 목록을 가져올 수 없습니다');
		expect(await s.doResize('next')).toBe(false);
		await s.loadResizeFlavors();
		mockPost.mockRejectedValueOnce(new Error('Nova offline'));
		expect(await s.doResize('next')).toBe(false);
		expect(s.resizeError).toBe('리사이즈 실패');
		expect(s.resizeLoading).toBe(false);
		status = 'VERIFY_RESIZE';
		await s.fetchInstance('vm');
		mockPost.mockRejectedValueOnce(new Error('cannot confirm'));
		await s.confirmResize();
		expect(toastError).toHaveBeenCalledWith('리사이즈 확인 실패: Error: cannot confirm');
		mockPost.mockRejectedValueOnce(new Error('cannot revert'));
		await s.revertResize();
		expect(toastError).toHaveBeenCalledWith('리사이즈 취소 실패: Error: cannot revert');
	});

	it('does not POST when confirmation is declined', async () => {
		const s = await setup();
		status = 'VERIFY_RESIZE';
		await s.fetchInstance('vm');
		confirmDialog.mockResolvedValue(false);
		await s.confirmResize();
		await s.revertResize();
		expect(mockPost).not.toHaveBeenCalled();
	});
});
