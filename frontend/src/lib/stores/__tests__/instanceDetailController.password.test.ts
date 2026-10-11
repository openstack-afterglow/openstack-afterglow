import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/svelte';
import { derived, writable } from 'svelte/store';
import type { Instance } from '$lib/types/compute';
import type { InstanceDetailController, PasswordPrecheck } from '../instanceDetailController.svelte';
import { t } from '$lib/i18n/ns/instance';
import { initLocale } from '$lib/i18n/runtime.svelte';

const { mockGet, mockPost } = vi.hoisted(() => ({ mockGet: vi.fn(), mockPost: vi.fn() }));
vi.mock('$lib/stores/auth', () => {
	const auth = writable({ token: 'token', userId: 'creator', projectId: 'project', roles: ['member'], isSystemAdmin: false });
	return { auth, canWrite: derived(auth, value => value.isSystemAdmin || value.roles.includes('member')) };
});
vi.mock('$lib/api/client', () => ({
	api: { get: mockGet, post: mockPost },
	ApiError: class ApiError extends Error { status = 503; },
}));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({ active: false, intervalSeconds: 30, intervalOptions: [15, 30], setBoost: vi.fn() }),
}));

import { auth } from '$lib/stores/auth';
import Probe from './_InstanceDetailControllerProbe.svelte';

const supported: PasswordPrecheck = { supported: true, reason: null, os_admin_user: 'Administrator', server_status: 'ACTIVE' };
const unsupported: PasswordPrecheck = { supported: false, reason: 'Guest agent unavailable', os_admin_user: null, server_status: 'ACTIVE' };
const instance = (id: string, creator = 'creator', projectId = 'project'): Instance => ({
	id, name: id, status: 'ACTIVE', user_id: creator, project_id: projectId,
	image_name: null, flavor_name: null, ip_addresses: [], created_at: null, union_libraries: [], union_strategy: null,
});

async function setup(source = { id: 'vm', projectId: 'project', adminMode: false }): Promise<InstanceDetailController> {
	let controller: InstanceDetailController | undefined;
	render(Probe, { source, onReady: value => { controller = value; } });
	await vi.waitFor(() => expect(controller).toBeDefined());
	await controller!.fetchInstance(source.id);
	return controller!;
}

beforeEach(() => {
	vi.clearAllMocks();
	initLocale('ko');
	auth.update(value => ({ ...value, token: 'token', userId: 'creator', projectId: 'project', roles: ['member'], isSystemAdmin: false }));
	mockPost.mockResolvedValue(undefined);
	mockGet.mockImplementation((path: string) => {
		if (path.endsWith('/admin-password/precheck')) return Promise.resolve(supported);
		if (/^\/api\/v1\/instances\/[^/]+$/.test(path)) return Promise.resolve(instance(path.split('/').at(-1)!));
		if (path.endsWith('/security-groups')) return Promise.resolve({ ports: [], security_groups: [] });
		if (path.endsWith('/owner')) return Promise.resolve({ display: '' });
		return Promise.resolve([]);
	});
});

describe('instance password capability', () => {
	it.each([
		{ creator: 'creator', adminMode: false, systemAdmin: false, allowed: true },
		{ creator: 'peer', adminMode: false, systemAdmin: false, allowed: false },
		{ creator: '', adminMode: false, systemAdmin: false, allowed: false },
		{ creator: 'peer', adminMode: true, systemAdmin: true, allowed: true },
		{ creator: 'peer', adminMode: true, systemAdmin: false, allowed: false },
		{ creator: 'peer', adminMode: false, systemAdmin: true, allowed: false },
	])('limits mode and native creator access: $creator/$adminMode/$systemAdmin', async ({ creator, adminMode, systemAdmin, allowed }) => {
		auth.update(value => ({ ...value, isSystemAdmin: systemAdmin }));
		mockGet.mockImplementationOnce(() => Promise.resolve(instance('vm', creator)));
		const controller = await setup({ id: 'vm', projectId: 'project', adminMode });
		expect(controller.canChangePassword).toBe(allowed);
		if (allowed) {
			await vi.waitFor(() => expect(controller.passwordPrecheck?.supported).toBe(true));
		} else {
			expect(controller.passwordPrecheck).toBeNull();
			expect(await controller.doSetPassword('Valid-password123!')).not.toBeNull();
			expect(mockPost).not.toHaveBeenCalled();
		}
	});

	it.each([
		{ adminMode: false, systemAdmin: false, reason: 'Image hw_qemu_guest_agent=yes is required' },
		{ adminMode: false, systemAdmin: true, reason: 'Only ACTIVE instances support password changes' },
		{ adminMode: false, systemAdmin: false, reason: null },
		{ adminMode: true, systemAdmin: true, reason: 'Image hw_qemu_guest_agent=yes is required' },
	])('distinguishes unsupported feedback by detail mode: $adminMode/$systemAdmin/$reason', async ({ adminMode, systemAdmin, reason }) => {
		auth.update(value => ({ ...value, isSystemAdmin: systemAdmin }));
		const implementation = mockGet.getMockImplementation()!;
		mockGet.mockImplementation((path: string) => path.endsWith('/admin-password/precheck')
			? Promise.resolve({ ...unsupported, reason }) : implementation(path));
		const controller = await setup({ id: 'vm', projectId: 'project', adminMode });
		await vi.waitFor(() => expect(controller.passwordPrecheck?.supported).toBe(false));
		expect(controller.passwordPrecheck?.reason).toBe(reason);
		expect(controller.passwordPrecheckReason).toBe(adminMode ? reason : t('password.unsupportedInstance'));
		expect(await controller.doSetPassword('Valid-password123!')).toBe(adminMode ? reason : t('password.unsupportedInstance'));
		expect(mockPost).not.toHaveBeenCalled();
	});

	it('updates consumer feedback with locale and clears unsupported state on a supported refresh', async () => {
		const implementation = mockGet.getMockImplementation()!;
		let result = unsupported;
		mockGet.mockImplementation((path: string) => path.endsWith('/admin-password/precheck')
			? Promise.resolve(result) : implementation(path));
		const controller = await setup();
		await vi.waitFor(() => expect(controller.passwordPrecheck?.supported).toBe(false));
		initLocale('en');
		expect(await controller.doSetPassword('Valid-password123!')).toBe(t('password.unsupportedInstance'));
		expect(mockPost).not.toHaveBeenCalled();
		result = supported;
		await controller.fetchInstance('vm');
		await vi.waitFor(() => expect(controller.passwordPrecheck?.supported).toBe(true));
		expect(controller.passwordPrecheckReason).toBeNull();
		expect(await controller.doSetPassword('Valid-password123!')).toBeNull();
		expect(mockPost).toHaveBeenCalledWith('/api/v1/instances/vm/admin-password', { new_password: 'Valid-password123!' }, 'token', 'project');
	});

	it('does not label a pending or failed refresh as an unsupported instance', async () => {
		const implementation = mockGet.getMockImplementation()!;
		const pending = Promise.withResolvers<PasswordPrecheck>();
		let refreshing = false;
		mockGet.mockImplementation((path: string) => path.endsWith('/admin-password/precheck')
			? refreshing ? pending.promise : Promise.resolve(unsupported) : implementation(path));
		const controller = await setup();
		await vi.waitFor(() => expect(controller.passwordPrecheck?.supported).toBe(false));
		refreshing = true;
		await controller.fetchInstance('vm');
		expect(controller.passwordPrecheckLoading).toBe(true);
		expect(controller.passwordPrecheckReason).toBeNull();
		expect(await controller.doSetPassword('Valid-password123!')).toBe(t('controller.password.unavailable'));
		pending.reject(new Error('offline'));
		await vi.waitFor(() => expect(controller.passwordPrecheckLoading).toBe(false));
		expect(controller.passwordPrecheckReason).toBeNull();
		expect(controller.passwordPrecheckError).toBe(t('controller.password.precheckFailed'));
		expect(await controller.doSetPassword('Valid-password123!')).toBe(t('controller.password.precheckFailed'));
		expect(mockPost).not.toHaveBeenCalled();
	});

	it('revokes permission immediately when the creator loses project write access', async () => {
		const controller = await setup();
		await vi.waitFor(() => expect(controller.passwordPrecheck?.supported).toBe(true));
		auth.update(value => ({ ...value, roles: ['reader'] }));
		expect(controller.canChangePassword).toBe(false);
		expect(await controller.doSetPassword('Valid-password123!')).not.toBeNull();
		expect(mockPost).not.toHaveBeenCalled();
	});

	it('does not use a late positive precheck from a previously selected instance', async () => {
		const oldResult = Promise.withResolvers<PasswordPrecheck>();
		const implementation = mockGet.getMockImplementation()!;
		mockGet.mockImplementation((path: string) => path === '/api/v1/instances/old/admin-password/precheck'
			? oldResult.promise : path === '/api/v1/instances/new/admin-password/precheck'
				? Promise.resolve(unsupported) : implementation(path));
		const source = { id: 'old', projectId: 'project', adminMode: false };
		const controller = await setup(source);
		source.id = 'new';
		await controller.fetchInstance('new');
		await vi.waitFor(() => expect(controller.passwordPrecheck?.supported).toBe(false));
		oldResult.resolve(supported);
		await Promise.resolve();
		expect(controller.passwordPrecheck?.supported).toBe(false);
		expect(await controller.doSetPassword('Valid-password123!')).not.toBeNull();
		expect(mockPost).not.toHaveBeenCalled();
	});

	it('does not regain capability from a precheck completed after logout', async () => {
		const pending = Promise.withResolvers<PasswordPrecheck>();
		const implementation = mockGet.getMockImplementation()!;
		mockGet.mockImplementation((path: string) => path.endsWith('/admin-password/precheck') ? pending.promise : implementation(path));
		const controller = await setup();
		auth.update(value => ({ ...value, token: '' }));
		pending.resolve(supported);
		await Promise.resolve();
		expect(controller.canChangePassword).toBe(false);
		expect(controller.passwordPrecheck).toBeNull();
		expect(await controller.doSetPassword('Valid-password123!')).not.toBeNull();
		expect(mockPost).not.toHaveBeenCalled();
	});

	it('keeps a failed precheck closed and prevents a password mutation', async () => {
		const implementation = mockGet.getMockImplementation()!;
		mockGet.mockImplementation((path: string) => path.endsWith('/admin-password/precheck')
			? Promise.reject(new Error('offline')) : implementation(path));
		const controller = await setup();
		await vi.waitFor(() => expect(controller.passwordPrecheckLoading).toBe(false));
		expect(controller.passwordPrecheck).toBeNull();
		expect(await controller.doSetPassword('Valid-password123!')).not.toBeNull();
		expect(mockPost).not.toHaveBeenCalled();
	});
});
