import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/svelte';
import { derived, writable } from 'svelte/store';
import type { Instance } from '$lib/types/compute';
import type { FlavorOption } from '$lib/types/flavor';
import type { InstanceDetailController } from '../instanceDetailController.svelte';
import { t } from '$lib/i18n/ns/instance';

const { mockGet, mockPost, confirmDialog, toastError } = vi.hoisted(() => ({
	mockGet: vi.fn(), mockPost: vi.fn(), confirmDialog: vi.fn(), toastError: vi.fn(),
}));
vi.mock('$lib/stores/auth', () => {
	const auth = writable({ token: 'token', userId: 'user', projectId: 'own-project', roles: ['member'], isSystemAdmin: false });
	return {
		auth,
		canWrite: derived(auth, state => state.isSystemAdmin || state.roles.some(role => ['admin', 'member'].includes(role))),
	};
});
vi.mock('$lib/api/client', () => ({
	api: { get: mockGet, post: mockPost, withExperience() { return this; } },
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
let status = 'SHUTOFF';
function composedFlavor(): FlavorOption {
	return { id: 'composed', name: 'composed', vcpus: 6, ram: 12288, disk: 20, is_public: false,
		eligibility: { selectable: true, blockers: [], requirements: { instances: 0, cores: 4, ram_mb: 8192, gpus: {} }, remaining: { instances: 10, cores: 128, ram_mb: 131072, gpus: {} },
			capacity: { status: 'available', checked_at: '2026-10-31T10:00:00Z', candidate_hosts: 1, cpu_resource_class: 'VCPU', remaining_vcpus: 128, remaining_ram_mb: 131072 } } };
}
let flavorRequest: string;

async function setup(adminMode = false, source = { id: 'vm', projectId: 'target-project', adminMode }): Promise<Controller> {
	if (adminMode) auth.update(state => ({ ...state, isSystemAdmin: true }));
	let controller: Controller | undefined;
	render(Probe, {
		source,
		onReady: value => { controller = value; },
	});
	await vi.waitFor(() => expect(controller).toBeDefined());
	await controller!.fetchInstance('vm');
	return controller!;
}

beforeEach(() => {
	vi.clearAllMocks();
	status = 'SHUTOFF';
	flavorRequest = '';
	auth.update(state => ({ ...state, token: 'token', userId: 'user', projectId: 'own-project', roles: ['member'], isSystemAdmin: false }));
	confirmDialog.mockResolvedValue(true);
	mockGet.mockImplementation((path: string) => {
		if (/^\/api\/v1\/(?:admin\/)?instances\/vm$/.test(path)) return Promise.resolve({
			id: 'vm', name: 'vm', status, flavor_id: 'current', flavor_name: 'current', image_name: null,
			ip_addresses: [], created_at: null, union_libraries: [], union_strategy: null,
		} satisfies Instance);
		if (/^\/api\/v1\/(?:admin\/)?instances\/vm\/resize-flavors$/.test(path)) {
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
		[true, '/api/v1/admin/instances/vm/resize-flavors', '/api/v1/admin/instances/vm', 'own-project'],
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

	it('rejects resize after flavor loading or mutation failures and preserves raw confirm/revert errors', async () => {
		const s = await setup();
		mockGet.mockRejectedValueOnce(new Error('unavailable'));
		await s.loadResizeFlavors();
		expect(await s.doResize('next')).toBe(false);
		await s.loadResizeFlavors();
		mockPost.mockRejectedValueOnce(new Error('Nova offline'));
		expect(await s.doResize('next')).toBe(false);
		expect(s.resizeLoading).toBe(false);
		status = 'VERIFY_RESIZE';
		await s.fetchInstance('vm');
		mockPost.mockRejectedValueOnce(new Error('cannot confirm'));
		await s.confirmResize();
		expect(toastError).toHaveBeenCalledWith(expect.stringContaining('cannot confirm'));
		mockPost.mockRejectedValueOnce(new Error('cannot revert'));
		await s.revertResize();
		expect(toastError).toHaveBeenCalledWith(expect.stringContaining('cannot revert'));
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

	it.each(['ACTIVE', 'SHUTOFF'])('owns resize confirmation and includes running notice only for %s', async nextStatus => {
		status = nextStatus;
		const s = await setup();
		await s.loadResizeFlavors();
		confirmDialog.mockResolvedValueOnce(false);
		expect(await s.doResize('next')).toBe(false);
		const flavorLabel = t('resize.flavorLabel', { name: 'next', vcpus: 4, ram: '8 GB' });
		const message = t('resize.confirmMessage', { flavorLabel });
		expect(confirmDialog).toHaveBeenCalledWith(nextStatus === 'ACTIVE' ? `${message}\n\n${t('resize.runningNotice')}` : message);
		expect(mockPost).not.toHaveBeenCalled();
		expect(s.resizeLoading).toBe(false);
	});

	it.each(['status', 'project', 'mode', 'token', 'permission', 'reload'])('rejects resize confirmation after %s changes even if choices are reloaded', async (change) => {
		const source = { id: 'vm', projectId: 'target-project', adminMode: false };
		const s = await setup(false, source);
		await s.loadResizeFlavors();
		const pending = Promise.withResolvers<boolean>();
		confirmDialog.mockReturnValueOnce(pending.promise);
		const request = s.doResize('next');
		if (change === 'status') {
			status = 'ACTIVE';
			await s.fetchInstance('vm');
		}
		if (change === 'project') source.projectId = 'other-project';
		if (change === 'mode') source.adminMode = true;
		if (change === 'token') auth.update(state => ({ ...state, token: 'other-token' }));
		if (change === 'permission') auth.update(state => ({ ...state, roles: ['reader'] }));
		await s.loadResizeFlavors();
		pending.resolve(true);
		expect(await request).toBe(false);
		expect(mockPost).not.toHaveBeenCalled();
	});

	it.each([
		[false, 'ACTIVE'], [false, 'SHUTOFF'], [true, 'ACTIVE'], [true, 'SHUTOFF'],
	] as const)('loads and submits resize in adminMode=%s with status=%s', async (adminMode, nextStatus) => {
		status = nextStatus;
		const s = await setup(adminMode);
		await s.loadResizeFlavors();
		expect(s.resizeFlavors).toHaveLength(3);
		expect(await s.doResize('next')).toBe(true);
		expect(mockPost).toHaveBeenCalledWith(`/api/v1/${adminMode ? 'admin/' : ''}instances/vm/resize`, { flavor_id: 'next' }, 'token', adminMode ? 'own-project' : 'target-project');
	});

	it.each(['BUILD', 'STOPPED', 'SHELVED', 'SHELVED_OFFLOADED', 'ERROR', 'VERIFY_RESIZE'])('never permits resize for %s', async (nextStatus) => {
		status = nextStatus;
		const s = await setup();
		await s.loadResizeFlavors();
		expect(await s.doResize('next')).toBe(false);
		expect(flavorRequest).toBe('');
		expect(mockPost).not.toHaveBeenCalled();
	});

	it.each(['ACTIVE', 'SHUTOFF'])('accepts an eligible composed readback outside the catalog for %s', async nextStatus => {
		status = nextStatus;
		const s = await setup();
		await s.loadResizeFlavors();
		const composed = composedFlavor();
		expect(s.selectableResizeFlavor(composed.id)).toBe(false);
		expect(s.selectableResizeFlavor(composed.id, composed)).toBe(true);
		expect(await s.doResize(composed.id, composed)).toBe(true);
		expect(mockPost).toHaveBeenCalledWith('/api/v1/instances/vm/resize', { flavor_id: composed.id }, 'token', 'target-project');
	});

	it.each(['identity', 'current', 'eligibility', 'capacity', 'blocker'] as const)('rejects composed resize with invalid %s', async invalid => {
		const s = await setup();
		await s.loadResizeFlavors();
		const composed = composedFlavor();
		if (invalid === 'identity') composed.id = 'different';
		if (invalid === 'current') composed.id = 'current';
		if (invalid === 'eligibility') composed.eligibility = null;
		if (invalid === 'capacity') composed.eligibility!.capacity!.status = 'unavailable';
		if (invalid === 'blocker') composed.eligibility!.blockers = [{ code: 'disk_shrink' }];
		const id = invalid === 'identity' ? 'composed' : composed.id;
		expect(s.selectableResizeFlavor(id, composed)).toBe(false);
		expect(await s.doResize(id, composed)).toBe(false);
		expect(confirmDialog).not.toHaveBeenCalled();
		expect(mockPost).not.toHaveBeenCalled();
	});

	it.each(['BUILD', 'SHELVED_OFFLOADED', 'VERIFY_RESIZE'])('rejects loaded choices after transitioning to %s', async nextStatus => {
		const s = await setup();
		await s.loadResizeFlavors();
		status = nextStatus;
		await s.fetchInstance('vm');
		expect(await s.doResize('next')).toBe(false);
		expect(mockPost).not.toHaveBeenCalled();
	});

	it.each(['instance', 'project', 'mode', 'token', 'caller', 'authProject', 'permission'])('rejects loaded resize choices after a %s switch', async (change) => {
		const source = { id: 'vm', projectId: 'target-project', adminMode: false };
		const s = await setup(false, source);
		await s.loadResizeFlavors();
		if (change === 'instance') source.id = 'other';
		if (change === 'project') source.projectId = 'other-project';
		if (change === 'mode') source.adminMode = true;
		if (change === 'token') auth.update(state => ({ ...state, token: 'other-token' }));
		if (change === 'caller') auth.update(state => ({ ...state, userId: 'other-user' }));
		if (change === 'authProject') auth.update(state => ({ ...state, projectId: 'other-project' }));
		if (change === 'permission') auth.update(state => ({ ...state, roles: ['reader'] }));
		expect(await s.doResize('next')).toBe(false);
		expect(mockPost).not.toHaveBeenCalled();
	});

	it('does not publish resize choices from a late response after scope changes', async () => {
		const source = { id: 'vm', projectId: 'target-project', adminMode: false };
		const s = await setup(false, source);
		const pending = Promise.withResolvers<FlavorOption[]>();
		mockGet.mockReturnValueOnce(pending.promise);
		const loading = s.loadResizeFlavors();
		source.projectId = 'other-project';
		pending.resolve(flavors);
		await loading;
		expect(s.resizeFlavors).toEqual([]);
		expect(s.resizeFlavorsLoading).toBe(false);
		expect(await s.doResize('next')).toBe(false);
	});

	it.each(['confirmResize', 'revertResize'] as const)('rechecks state after a stale %s confirmation', async (action) => {
		status = 'VERIFY_RESIZE';
		const s = await setup();
		const pending = Promise.withResolvers<boolean>();
		confirmDialog.mockReturnValueOnce(pending.promise);
		const request = s[action]();
		status = 'ACTIVE';
		await s.fetchInstance('vm');
		pending.resolve(true);
		await request;
		expect(mockPost).not.toHaveBeenCalled();
	});

	it.each(['confirmResize', 'revertResize'] as const)('does not retarget a pending %s confirmation', async (action) => {
		status = 'VERIFY_RESIZE';
		const source = { id: 'vm', projectId: 'target-project', adminMode: false };
		const s = await setup(false, source);
		const pending = Promise.withResolvers<boolean>();
		confirmDialog.mockReturnValueOnce(pending.promise);
		const request = s[action]();
		source.id = 'other';
		pending.resolve(true);
		await request;
		expect(mockPost).not.toHaveBeenCalled();
	});

	it('reports an accepted resize without waiting for the refresh, even after token rotation', async () => {
		const s = await setup();
		await s.loadResizeFlavors();
		const post = Promise.withResolvers<unknown>();
		mockPost.mockReturnValueOnce(post.promise);
		const refresh = Promise.withResolvers<unknown>();
		const request = s.doResize('next');
		await vi.waitFor(() => expect(mockPost).toHaveBeenCalled());
		auth.update(state => ({ ...state, token: 'rotated' }));
		mockGet.mockImplementationOnce(() => refresh.promise);
		post.resolve({});
		expect(await request).toBe(true);
		expect(s.resizeLoading).toBe(false);
		expect(await s.doResize('next')).toBe(false);
		expect(mockPost).toHaveBeenCalledTimes(1);
		refresh.resolve(undefined);
	});

	it('keeps the loaded instance when a background refresh fails', async () => {
		const s = await setup();
		mockGet.mockImplementationOnce(() => Promise.reject(new DOMException('signal timed out', 'TimeoutError')));
		await s.fetchInstance('vm', { silent: true });
		expect(s.error).toBe('');
		expect(s.instance?.id).toBe('vm');
		expect(s.refreshError).toBe(t('controller.error.refreshFailed', { message: t('controller.error.timeout') }));
		mockGet.mockImplementationOnce(() => Promise.reject(new DOMException('aborted', 'AbortError')));
		await s.fetchInstance('vm', { silent: true });
		await s.fetchInstance('vm', { silent: true });
		expect(s.refreshError).toBe('');
		mockGet.mockImplementationOnce(() => Promise.reject(new DOMException('signal timed out', 'TimeoutError')));
		await s.fetchInstance('vm');
		expect(s.error).toBe(t('controller.error.timeout'));
	});
});
