import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/svelte';
import { derived, writable } from 'svelte/store';
import type { InstanceDetailController } from '../instanceDetailController.svelte';

const { get, post, remove, patch } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), remove: vi.fn(), patch: vi.fn() }));
vi.mock('$lib/stores/auth', () => {
	const auth = writable({ token: 'token', userId: 'actor', projectId: 'personal', roles: ['member'], isSystemAdmin: true });
	return { auth, canWrite: derived(auth, state => state.isSystemAdmin || state.roles.includes('member')) };
});
vi.mock('$lib/api/client', () => ({ api: { get, post, delete: remove, patch }, ApiError: class ApiError extends Error {} }));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: vi.fn().mockResolvedValue(true) }));
vi.mock('$lib/stores/toast', () => ({ toast: { error: vi.fn(), info: vi.fn() } }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({ createAutoRefresh: () => ({ active: false, setBoost: vi.fn() }) }));

import Probe from './_InstanceDetailControllerProbe.svelte';
import { auth } from '$lib/stores/auth';

async function mount(adminMode = true) {
	const source = { id: 'vm', projectId: 'foreign', adminMode };
	let controller: InstanceDetailController | undefined;
	render(Probe, { source, onReady: value => { controller = value; } });
	await vi.waitFor(() => expect(controller).toBeDefined());
	await controller!.fetchInstance('vm');
	return { controller: controller!, source };
}

beforeEach(() => {
	vi.clearAllMocks();
	auth.update(state => ({ ...state, token: 'token', isSystemAdmin: true, projectId: 'personal' }));
	get.mockImplementation(async (path: string) => {
		if (/\/instances\/vm$/.test(path)) return { id: 'vm', project_id: 'foreign', name: 'vm', status: 'ACTIVE', ip_addresses: [] };
		if (path.endsWith('/security-groups')) return { ports: [], security_groups: [] };
		if (path.endsWith('/owner')) return { display: 'Creator' };
		if (path.includes('/log?')) return { output: 'foreign serial log' };
		if (path.endsWith('/console')) return { url: 'https://console.example.test/exact-vm' };
		if (path.endsWith('/precheck')) return { supported: true, server_status: 'ACTIVE' };
		return [];
	});
	post.mockResolvedValue({});
	remove.mockResolvedValue(undefined);
	patch.mockResolvedValue(undefined);
});

describe('administrator instance detail transport', () => {
	it('reads every subordinate view through explicit parent-bound admin routes, without target project headers', async () => {
		const { controller } = await mount();
		await vi.waitFor(() => expect(controller.ownerDisplay).toBe('Creator'));
		for (const suffix of ['', '/interfaces', '/volumes', '/security-groups', '/floating-ips', '/available-volumes', '/networks', '/owner']) {
			expect(get.mock.calls.some(([path, token, project]) => path === `/api/v1/admin/instances/vm${suffix}` && token === 'token' && project === 'personal')).toBe(true);
		}
		const open = vi.spyOn(window, 'open').mockReturnValue(null);
		await controller.loadConsoleLog();
		await controller.openConsole();
		expect(get).toHaveBeenCalledWith('/api/v1/admin/instances/vm/log?length=200', 'token', 'personal');
		expect(get).toHaveBeenCalledWith('/api/v1/admin/instances/vm/console', 'token', 'personal');
		expect(open).toHaveBeenCalledWith('https://console.example.test/exact-vm', '_blank', 'noopener,noreferrer');
		expect(get.mock.calls.some(([path]) => /^\/api\/v1\/(?:instances|networks|volumes)(?:\/|$)/.test(path))).toBe(false);
		open.mockRestore();
	});

	it('keeps ordinary detail and console paths unchanged', async () => {
		const { controller } = await mount(false);
		await controller.loadConsoleLog();
		expect(get).toHaveBeenCalledWith('/api/v1/instances/vm', 'token', 'foreign');
		expect(get).toHaveBeenCalledWith('/api/v1/instances/vm/log?length=200', 'token', 'personal');
		expect(get.mock.calls.some(([path]) => path.startsWith('/api/v1/admin/'))).toBe(false);
	});

	it('sends existing attachment, security-group and Floating IP actions to administrator endpoints', async () => {
		const { controller } = await mount();
		await controller.attachVolume('volume');
		await controller.attachInterface('network');
		await controller.saveSgEdit('port', ['group']);
		await controller.releaseFloatingIp('floating');
		expect(post).toHaveBeenCalledWith('/api/v1/admin/instances/vm/volumes', { volume_id: 'volume' }, 'token', 'personal');
		expect(post).toHaveBeenCalledWith('/api/v1/admin/instances/vm/interfaces', { net_id: 'network' }, 'token', 'personal');
		expect(post).toHaveBeenCalledWith('/api/v1/admin/instances/vm/ports/port/security-groups', { security_group_ids: ['group'] }, 'token', 'personal');
		expect(remove).toHaveBeenCalledWith('/api/v1/admin/instances/vm/floating-ips/floating', 'token', 'personal');
		expect(post.mock.calls.some(([path]) => path.includes('/networks/floating-ips/'))).toBe(false);
	});

	it.each(['selection', 'mode', 'logout'] as const)('discards late console URLs and serial logs after %s changes', async change => {
		const { controller, source } = await mount();
		const pendingLog = Promise.withResolvers<{ output: string }>();
		const pendingConsole = Promise.withResolvers<{ url: string }>();
		get.mockImplementation((path: string) => path.includes('/log?') ? pendingLog.promise : pendingConsole.promise);
		const open = vi.spyOn(window, 'open').mockReturnValue(null);
		const logging = controller.loadConsoleLog();
		const opening = controller.openConsole();
		if (change === 'selection') source.id = 'other';
		if (change === 'mode') source.adminMode = false;
		if (change === 'logout') auth.update(state => ({ ...state, token: '' }));
		pendingLog.resolve({ output: 'stale secret serial output' });
		pendingConsole.resolve({ url: 'https://console.example.test/stale-token' });
		await Promise.all([logging, opening]);
		expect(controller.consoleLog).not.toContain('stale secret');
		expect(open).not.toHaveBeenCalled();
		open.mockRestore();
	});
});
