import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/svelte';
import { derived, writable } from 'svelte/store';
import type { Instance } from '$lib/types/compute';
import type { InstanceDetailController } from '../instanceDetailController.svelte';
import { t } from '$lib/i18n/ns/instance';

const { mockGet, mockPost, mockDelete, confirmDialog } = vi.hoisted(() => ({
	mockGet: vi.fn(), mockPost: vi.fn(), mockDelete: vi.fn(), confirmDialog: vi.fn(),
}));
vi.mock('$lib/stores/auth', () => {
	const auth = writable({ token: 'token', userId: 'user', projectId: 'own-project', roles: ['member'], isSystemAdmin: false });
	return { auth, canWrite: derived(auth, state => state.isSystemAdmin || state.roles.includes('member')) };
});
vi.mock('$lib/api/client', () => ({
	api: { get: mockGet, post: mockPost, delete: mockDelete },
	ApiError: class ApiError extends Error { status = 409; },
}));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog }));
vi.mock('$lib/stores/toast', () => ({ toast: { error: vi.fn() } }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({ active: false, intervalSeconds: 30, intervalOptions: [15, 30, 60], setBoost: vi.fn() }),
}));

import { auth } from '$lib/stores/auth';
import Probe from './_InstanceDetailControllerProbe.svelte';

let status = 'ACTIVE';
async function setup(source = { id: 'vm', projectId: 'target-project', adminMode: false }): Promise<InstanceDetailController> {
	let controller: InstanceDetailController | undefined;
	render(Probe, { source, onReady: value => { controller = value; } });
	await vi.waitFor(() => expect(controller).toBeDefined());
	await controller!.fetchInstance(source.id);
	return controller!;
}

beforeEach(() => {
	vi.clearAllMocks();
	status = 'ACTIVE';
	auth.update(state => ({ ...state, token: 'token', userId: 'user', projectId: 'own-project', roles: ['member'], isSystemAdmin: false }));
	confirmDialog.mockResolvedValue(true);
	mockPost.mockResolvedValue({});
	mockDelete.mockResolvedValue({});
	mockGet.mockImplementation((path: string) => {
		if (/^\/api\/v1\/instances\/[^/]+$/.test(path)) return Promise.resolve({
			id: path.split('/').at(-1)!, name: 'vm', status, flavor_id: 'current', flavor_name: 'current', image_name: null,
			ip_addresses: [], created_at: null, union_libraries: [], union_strategy: null,
		} satisfies Instance);
		if (path.endsWith('/security-groups')) return Promise.resolve({ ports: [], security_groups: [] });
		if (path.endsWith('/owner')) return Promise.resolve({ display: '' });
		return Promise.resolve([]);
	});
});

describe('instance lifecycle action admission', () => {
	it.each([false, true])('blocks live archive and deletion, then permits SHUTOFF in adminMode=%s', async (adminMode) => {
		const s = await setup({ id: 'vm', projectId: 'target-project', adminMode });
		await s.performAction('shelve');
		await s.deleteInstance();
		expect(confirmDialog).not.toHaveBeenCalled();
		expect(mockPost).not.toHaveBeenCalled();
		expect(mockDelete).not.toHaveBeenCalled();
		status = 'SHUTOFF';
		await s.fetchInstance('vm');
		await s.performAction('shelve');
		await s.deleteInstance();
		expect(mockPost).toHaveBeenCalledWith('/api/v1/instances/vm/shelve', {}, 'token', 'own-project');
		expect(mockDelete).toHaveBeenCalledWith('/api/v1/instances/vm', 'token', 'own-project');
	});

	it.each(['STOPPED', 'SHELVED', 'SHELVED_OFFLOADED', 'ERROR', 'VERIFY_RESIZE'])('does not treat %s as SHUTOFF for archive/delete', async (nextStatus) => {
		status = nextStatus;
		const s = await setup();
		await s.performAction('shelve');
		await s.deleteInstance();
		expect(confirmDialog).not.toHaveBeenCalled();
		expect(mockPost).not.toHaveBeenCalled();
		expect(mockDelete).not.toHaveBeenCalled();
	});

	it.each([
		['ACTIVE', 'stop'], ['ACTIVE', 'reboot'], ['SHUTOFF', 'start'],
		['SHELVED', 'unshelve'], ['SHELVED_OFFLOADED', 'unshelve'],
	] as const)('retains %s/%s lifecycle behavior', async (nextStatus, action) => {
		status = nextStatus;
		const s = await setup();
		await s.performAction(action);
		expect(mockPost).toHaveBeenCalledWith(`/api/v1/instances/vm/${action}`, {}, 'token', 'own-project');
		if (action === 'stop') expect(confirmDialog).toHaveBeenCalledWith(expect.stringContaining(t('panel.stoppedQuotaWarning')));
	});

	it.each(['shelve', 'delete'] as const)('rechecks SHUTOFF after a stale %s confirmation', async (action) => {
		status = 'SHUTOFF';
		const s = await setup();
		const pending = Promise.withResolvers<boolean>();
		confirmDialog.mockReturnValueOnce(pending.promise);
		const request = action === 'delete' ? s.deleteInstance() : s.performAction(action);
		status = 'ACTIVE';
		await s.fetchInstance('vm');
		pending.resolve(true);
		await request;
		expect(mockPost).not.toHaveBeenCalled();
		expect(mockDelete).not.toHaveBeenCalled();
	});

	it.each(['instance', 'project', 'mode', 'token', 'caller', 'authProject', 'permission'])('rejects pending deletion after a %s switch', async (change) => {
		status = 'SHUTOFF';
		const source = { id: 'vm', projectId: 'target-project', adminMode: false };
		const s = await setup(source);
		const pending = Promise.withResolvers<boolean>();
		confirmDialog.mockReturnValueOnce(pending.promise);
		const request = s.deleteInstance();
		if (change === 'instance') source.id = 'other';
		if (change === 'project') source.projectId = 'other-project';
		if (change === 'mode') source.adminMode = true;
		if (change === 'token') auth.update(state => ({ ...state, token: 'other-token' }));
		if (change === 'caller') auth.update(state => ({ ...state, userId: 'other-user' }));
		if (change === 'authProject') auth.update(state => ({ ...state, projectId: 'other-project' }));
		if (change === 'permission') auth.update(state => ({ ...state, roles: ['reader'] }));
		pending.resolve(true);
		await request;
		expect(mockDelete).not.toHaveBeenCalled();
	});

	it('does not retarget a pending stop when the selected instance changes', async () => {
		const source = { id: 'vm', projectId: 'target-project', adminMode: false };
		const s = await setup(source);
		const pending = Promise.withResolvers<boolean>();
		confirmDialog.mockReturnValueOnce(pending.promise);
		const request = s.performAction('stop');
		source.id = 'other';
		await s.fetchInstance('other');
		pending.resolve(true);
		await request;
		expect(mockPost).not.toHaveBeenCalled();
	});

	it('keeps read-only callers and concurrent mutations blocked', async () => {
		status = 'SHUTOFF';
		const s = await setup();
		auth.update(state => ({ ...state, roles: ['reader'] }));
		await s.performAction('start');
		await s.deleteInstance();
		expect(confirmDialog).not.toHaveBeenCalled();
		auth.update(state => ({ ...state, roles: ['member'] }));
		const pending = Promise.withResolvers<object>();
		mockPost.mockReturnValueOnce(pending.promise);
		const starting = s.performAction('start');
		await vi.waitFor(() => expect(s.actioning).toBe('start'));
		await s.deleteInstance();
		await s.performAction('shelve');
		expect(confirmDialog).toHaveBeenCalledTimes(1);
		expect(mockDelete).not.toHaveBeenCalled();
		pending.resolve({});
		await starting;
	});
});
