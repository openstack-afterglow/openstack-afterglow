import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/svelte';
import { derived, writable } from 'svelte/store';
import type { Instance } from '$lib/types/compute';
import type { InstanceDetailController } from '../instanceDetailController.svelte';
import { t } from '$lib/i18n/ns/instance';

const { mockGet, mockPost, mockPut, mockPatch, mockDelete, confirmDialog, toastError, MockApiError } = vi.hoisted(() => {
	class MockApiError extends Error {
		constructor(public status: number, message: string, public code?: string) { super(message); }
	}
	return {
		mockGet: vi.fn(), mockPost: vi.fn(), mockPut: vi.fn(), mockPatch: vi.fn(), mockDelete: vi.fn(),
		confirmDialog: vi.fn(), toastError: vi.fn(), MockApiError,
	};
});
vi.mock('$lib/stores/auth', () => {
	const auth = writable({ token: 'token', userId: 'user', projectId: 'own-project', roles: ['member'], isSystemAdmin: false });
	return { auth, canWrite: derived(auth, state => state.isSystemAdmin || state.roles.includes('member')) };
});
vi.mock('$lib/api/client', () => ({
	api: { get: mockGet, post: mockPost, put: mockPut, patch: mockPatch, delete: mockDelete, withExperience() { return this; } },
	ApiError: MockApiError,
}));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog }));
vi.mock('$lib/stores/toast', () => ({ toast: { error: toastError, info: vi.fn() } }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({ active: false, intervalSeconds: 30, intervalOptions: [15, 30, 60], setBoost: vi.fn() }),
}));

import { auth } from '$lib/stores/auth';
import Probe from './_InstanceDetailControllerProbe.svelte';

let status = 'SHUTOFF';
let waygateManaged = true;

async function setup(adminMode = false): Promise<InstanceDetailController> {
	let controller: InstanceDetailController | undefined;
	render(Probe, { source: { id: 'vm', projectId: 'target-project', adminMode }, onReady: value => { controller = value; } });
	await vi.waitFor(() => expect(controller).toBeDefined());
	await controller!.fetchInstance('vm');
	return controller!;
}

function expectNoMutation() {
	expect(confirmDialog).not.toHaveBeenCalled();
	expect(mockPost).not.toHaveBeenCalled();
	expect(mockPut).not.toHaveBeenCalled();
	expect(mockPatch).not.toHaveBeenCalled();
	expect(mockDelete).not.toHaveBeenCalled();
}

beforeEach(() => {
	vi.clearAllMocks();
	status = 'SHUTOFF';
	waygateManaged = true;
	auth.update(state => ({ ...state, token: 'token', userId: 'user', projectId: 'own-project', roles: ['member'], isSystemAdmin: false }));
	confirmDialog.mockResolvedValue(true);
	mockPost.mockResolvedValue({});
	mockPut.mockResolvedValue({});
	mockPatch.mockResolvedValue({});
	mockDelete.mockResolvedValue({});
	mockGet.mockImplementation((path: string) => {
		if (/^\/api\/v1\/(?:admin\/)?instances\/vm$/.test(path)) return Promise.resolve({
			id: 'vm', name: 'gateway', status, flavor_id: 'current', flavor_name: 'current', image_name: null,
			ip_addresses: [], created_at: null, union_libraries: [], union_strategy: null,
			project_id: 'target-project', user_id: 'user', waygate_managed: waygateManaged,
		} satisfies Instance);
		if (path.endsWith('/security-groups')) return Promise.resolve({ ports: [], security_groups: [] });
		if (path.endsWith('/owner')) return Promise.resolve({ display: '' });
		return Promise.resolve([]);
	});
});

describe('Waygate-managed instance detail guards', () => {
	it('refuses every locked project mutation without a confirmation or network call', async () => {
		const s = await setup();
		expect(s.waygateLocked).toBe(true);
		mockGet.mockClear();
		await s.performAction('shelve');
		await s.deleteInstance();
		await s.assignFloatingIp('port');
		await s.releaseFloatingIp('fip');
		await s.attachVolume('volume');
		await s.createAndAttachVolume('data', 10);
		await s.detachVolume('volume');
		await s.setDeleteOnTermination('volume', true);
		await s.attachInterface('network');
		await s.detachInterface('port');
		await s.saveSgEdit('port', []);
		await s.loadResizeFlavors();
		expect(await s.doResize('bigger')).toBe(false);
		s.openRename();
		expect(s.renameOpen).toBe(false);
		expectNoMutation();
		expect(mockGet).not.toHaveBeenCalled();
		expect(s.actioning).toBeNull();
	});

	it('keeps start, stop and reboot available for a gateway in project mode', async () => {
		const s = await setup();
		await s.performAction('start');
		expect(mockPost).toHaveBeenCalledWith('/api/v1/instances/vm/start', {}, 'token', 'own-project');
		status = 'ACTIVE';
		await s.fetchInstance('vm');
		await s.performAction('stop');
		await s.performAction('reboot');
		expect(mockPost).toHaveBeenCalledWith('/api/v1/instances/vm/stop', {}, 'token', 'own-project');
		expect(mockPost).toHaveBeenCalledWith('/api/v1/instances/vm/reboot', {}, 'token', 'own-project');
	});

	it('leaves the administrator surface unrestricted for a gateway', async () => {
		auth.update(state => ({ ...state, isSystemAdmin: true }));
		const s = await setup(true);
		expect(s.waygateLocked).toBe(false);
		await s.performAction('shelve');
		await s.deleteInstance();
		await s.detachInterface('port');
		expect(mockPost).toHaveBeenCalledWith('/api/v1/admin/instances/vm/shelve', {}, 'token', 'own-project');
		expect(mockDelete).toHaveBeenCalledWith('/api/v1/admin/instances/vm', 'token', 'own-project');
		expect(mockDelete).toHaveBeenCalledWith('/api/v1/admin/instances/vm/interfaces/port', 'token', 'own-project');
	});

	it('does not lock an ordinary project instance', async () => {
		waygateManaged = false;
		const s = await setup();
		expect(s.waygateLocked).toBe(false);
		await s.deleteInstance();
		expect(mockDelete).toHaveBeenCalledWith('/api/v1/instances/vm', 'token', 'own-project');
	});

	it('shows the localized Waygate note instead of the backend English refusal', async () => {
		waygateManaged = false;
		const s = await setup();
		mockPost.mockRejectedValueOnce(new MockApiError(409, 'This resource is managed by Waygate; change it through Waygate', 'waygate_managed_resource'));
		await s.performAction('shelve');
		expect(toastError).toHaveBeenCalledExactlyOnceWith(t('controller.action.failed', { action: 'shelve', message: t('waygate.managedNote') }));
		mockDelete.mockRejectedValueOnce(new MockApiError(409, 'This resource is managed by Waygate; change it through Waygate', 'waygate_managed_resource'));
		await s.deleteInstance();
		expect(toastError).toHaveBeenLastCalledWith(t('controller.delete.failed', { message: t('waygate.managedNote') }));
		mockDelete.mockRejectedValueOnce(new MockApiError(500, 'Nova failed'));
		await s.detachVolume('volume');
		expect(toastError).toHaveBeenLastCalledWith(t('controller.volume.detachFailed', { message: 'Nova failed' }));
	});
});
