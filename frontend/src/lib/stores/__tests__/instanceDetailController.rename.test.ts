import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import { writable, type Writable } from 'svelte/store';
import type { Instance } from '$lib/types/compute';
import type { InstanceDetailController } from '../instanceDetailController.svelte';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/instance';

const { mockGet, mockPut } = vi.hoisted(() => ({ mockGet: vi.fn(), mockPut: vi.fn() }));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token', userId: 'actor', projectId: 'project', isSystemAdmin: false, sessionId: 'session' }),
	canWrite: writable(true),
}));
vi.mock('$lib/api/client', () => ({
	api: { get: mockGet, put: mockPut },
	ApiError: class ApiError extends Error { status = 400; },
}));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({ active: false, intervalSeconds: 30, intervalOptions: [15, 30], setBoost: vi.fn() }),
}));

import { auth, canWrite } from '$lib/stores/auth';
import Probe from './_InstanceRenameProbe.svelte';
import { invalidateInstanceDetailSelection } from '../instanceDetailController.svelte';
const permission = canWrite as Writable<boolean>;

const instance = (id = 'vm', projectId = 'project'): Instance => ({
	id, name: id, status: 'ACTIVE', user_id: 'peer', project_id: projectId,
	image_name: null, flavor_name: null, ip_addresses: [], created_at: null, union_libraries: [], union_strategy: null,
});

async function setup(source = { id: 'vm', projectId: 'project', adminMode: false }) {
	let controller: InstanceDetailController | undefined;
	const updated = vi.fn();
	const view = render(Probe, { source, onReady: value => { controller = value; }, onUpdated: updated });
	await vi.waitFor(() => expect(controller).toBeDefined());
	await controller!.fetchInstance(source.id);
	await tick();
	return { controller: controller!, updated, source, view };
}

beforeEach(() => {
	vi.clearAllMocks();
	initLocale('ko');
	auth.update(value => ({ ...value, token: 'token', userId: 'actor', projectId: 'project', isSystemAdmin: false, sessionId: 'session' }));
	permission.set(true);
	mockPut.mockImplementation((_path: string, body: { name: string }) => Promise.resolve({ id: 'vm', name: body.name, project_id: 'project' }));
	mockGet.mockImplementation((path: string) => {
		if (/^\/api\/v1\/instances\/[^/]+$/.test(path)) return Promise.resolve(instance(path.split('/').at(-1)!));
		if (path.endsWith('/security-groups')) return Promise.resolve({ ports: [], security_groups: [] });
		if (path.endsWith('/owner')) return Promise.resolve({ display: '' });
		return Promise.resolve([]);
	});
});
afterEach(cleanup);

describe('shared instance rename', () => {
	it.each([false, true])('saves from accessible detail controls in admin mode %s', async adminMode => {
		auth.update(value => ({ ...value, isSystemAdmin: adminMode }));
		const { controller, updated } = await setup({ id: 'vm', projectId: 'project', adminMode });
		await fireEvent.click(screen.getByRole('button', { name: t('rename.title') }));
		const input = screen.getByRole('textbox', { name: t('rename.name') });
		expect(document.getElementById(input.getAttribute('aria-describedby')!)?.textContent).toBe(t('rename.invalidName'));
		await fireEvent.input(input, { target: { value: '  new name  ' } });
		await fireEvent.click(screen.getByRole('button', { name: t('rename.submit') }));
		await vi.waitFor(() => expect(controller.instance?.name).toBe('new-name'));
		expect(mockPut).toHaveBeenCalledExactlyOnceWith(`/api/v1/${adminMode ? 'admin/' : ''}instances/vm/name`, { name: 'new-name' }, 'token', 'project', { replayOnUnauthorized: false });
		expect(updated).toHaveBeenCalledTimes(1);
		expect(screen.queryByRole('dialog')).toBeNull();
	});

	it('reader and nonadministrator admin mode cannot open or submit', async () => {
		const { controller, source } = await setup();
		permission.set(false);
		controller.openRename();
		expect(controller.renameOpen).toBe(false);
		permission.set(true);
		source.adminMode = true;
		controller.openRename();
		await controller.submitRename();
		expect(controller.renameOpen).toBe(false);
		expect(mockPut).not.toHaveBeenCalled();
	});

	it('rejects empty, invalid and overlong drafts and skips unchanged names', async () => {
		const { controller } = await setup();
		for (const name of ['', '  ', 'a'.repeat(64), '-invalid', 'bad\nname']) {
			controller.openRename();
			controller.renameDraft = name;
			await controller.submitRename();
			expect(controller.renameError).toBe(t('rename.invalidName'));
		}
		controller.renameDraft = ' vm ';
		await controller.submitRename();
		expect(mockPut).not.toHaveBeenCalled();
		expect(controller.renameOpen).toBe(false);
	});

	it.each([false, true])('saving an untouched spaced name is a no-op in admin mode %s', async adminMode => {
		auth.update(value => ({ ...value, isSystemAdmin: adminMode }));
		mockGet.mockImplementationOnce(() => Promise.resolve({ ...instance(), name: 'web server' }));
		const { controller, updated } = await setup({ id: 'vm', projectId: 'project', adminMode });
		await fireEvent.click(screen.getByRole('button', { name: t('rename.title') }));
		expect((screen.getByRole('textbox', { name: t('rename.name') }) as HTMLInputElement).value).toBe('web server');
		await fireEvent.click(screen.getByRole('button', { name: t('rename.submit') }));
		expect(controller.instance?.name).toBe('web server');
		expect(controller.renameOpen).toBe(false);
		expect(mockPut).not.toHaveBeenCalled();
		expect(updated).not.toHaveBeenCalled();
	});

	it('polling retains draft and provider failure leaves the accepted name unchanged', async () => {
		const { controller, updated } = await setup();
		controller.openRename();
		controller.renameDraft = 'new-name';
		await controller.fetchInstance('vm', { silent: true });
		expect(controller.renameDraft).toBe('new-name');
		mockPut.mockRejectedValueOnce(new Error('provider failure'));
		await controller.submitRename();
		expect(controller.instance?.name).toBe('vm');
		expect(controller.renameDraft).toBe('new-name');
		expect(controller.renameError).toBe(t('rename.failed'));
		expect(updated).not.toHaveBeenCalled();
	});

	it('duplicate submits send once and response metadata must match target and name', async () => {
		const pending = Promise.withResolvers<{ id: string; name: string; project_id: string }>();
		mockPut.mockReturnValueOnce(pending.promise);
		const { controller, updated } = await setup();
		controller.openRename();
		controller.renameDraft = 'new-name';
		const first = controller.submitRename();
		await controller.submitRename();
		expect(mockPut).toHaveBeenCalledTimes(1);
		pending.resolve({ id: 'other', name: 'new-name', project_id: 'project' });
		await first;
		expect(controller.instance?.name).toBe('vm');
		expect(controller.renameError).toBe(t('rename.failed'));
		expect(updated).not.toHaveBeenCalled();
	});

	it.each(['token', 'user', 'project', 'session', 'permission', 'admin', 'close', 'unmount', 'target'])('discards success after %s replacement including same-tick ABA', async change => {
		const pending = Promise.withResolvers<{ id: string; name: string; project_id: string }>();
		mockPut.mockReturnValueOnce(pending.promise);
		const { controller, updated, source, view } = await setup();
		controller.openRename();
		controller.renameDraft = 'new-name';
		const operation = controller.submitRename();
		if (change === 'token') { auth.update(value => ({ ...value, token: 'other' })); auth.update(value => ({ ...value, token: 'token' })); }
		if (change === 'user') { auth.update(value => ({ ...value, userId: 'other' })); auth.update(value => ({ ...value, userId: 'actor' })); }
		if (change === 'project') { auth.update(value => ({ ...value, projectId: 'other' })); auth.update(value => ({ ...value, projectId: 'project' })); }
		if (change === 'session') { auth.update(value => ({ ...value, sessionId: 'other' })); auth.update(value => ({ ...value, sessionId: 'session' })); }
		if (change === 'permission') { permission.set(false); permission.set(true); }
		if (change === 'admin') {
			invalidateInstanceDetailSelection(); source.adminMode = true;
			invalidateInstanceDetailSelection(); source.adminMode = false;
		}
		if (change === 'close') controller.closeRename();
		if (change === 'unmount') view.unmount();
		if (change === 'target') {
			invalidateInstanceDetailSelection(); source.id = 'other';
			invalidateInstanceDetailSelection(); source.id = 'vm';
		}
		pending.resolve({ id: 'vm', name: 'new-name', project_id: 'project' });
		await operation;
		expect(controller.instance?.name).toBe('vm');
		expect(updated).not.toHaveBeenCalled();
		expect(controller.renameError).toBe('');
		if (change === 'admin' || change === 'target') {
			expect(controller.renameOpen).toBe(false);
			expect(controller.renameDraft).toBe('');
		}
	});

	it('late error from closed form cannot overwrite a newly opened draft', async () => {
		const pending = Promise.withResolvers<never>();
		mockPut.mockReturnValueOnce(pending.promise);
		const { controller } = await setup();
		controller.openRename(); controller.renameDraft = 'first';
		const operation = controller.submitRename();
		controller.closeRename(); controller.openRename(); controller.renameDraft = 'second';
		pending.reject(new Error('old failure'));
		await operation;
		expect(controller.renameDraft).toBe('second');
		expect(controller.renameError).toBe('');
	});

	it('a poll started before the accepted write cannot restore the old name', async () => {
		const { controller } = await setup();
		const old = Promise.withResolvers<Instance>();
		mockGet.mockImplementationOnce(() => old.promise);
		const poll = controller.fetchInstance('vm', { silent: true });
		controller.openRename(); controller.renameDraft = 'new-name';
		await controller.submitRename();
		old.resolve(instance());
		await poll;
		expect(controller.instance?.name).toBe('new-name');
	});
});
