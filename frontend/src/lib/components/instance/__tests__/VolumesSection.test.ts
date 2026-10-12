import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import type { Writable } from 'svelte/store';
import type { InstanceDetailController } from '$lib/stores/instanceDetailController.svelte';
import type { Volume } from '$lib/types/volume';
import Wrapper from './_VolumesSectionWrapper.svelte';

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: { get, post }, ApiError: class ApiError extends Error {} }));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token', projectId: 'auth-default' }),
	canWrite: writable(true),
}));
vi.mock('$lib/i18n/ns/instance', () => ({ t: (key: string) => key }));
vi.mock('$lib/i18n/ns/volume', () => ({ t: (key: string) => key }));
import { auth, canWrite } from '$lib/stores/auth';

const volume: Volume = {
	id: 'volume-a', name: 'Actual Cinder disk', status: 'in-use', size: 40, volume_type: null,
	attachments: [{ server_id: 'instance-a', volume_id: 'volume-a' }],
};
function controller(overrides: Partial<InstanceDetailController> = {}): InstanceDetailController {
	return {
		instanceId: 'instance-a', effectiveProjectId: 'target-project',
		instance: { id: 'instance-a', status: 'SHUTOFF' },
		volumes: [{ volume_id: 'volume-a', name: 'Stale row name', size: 20, status: 'in-use', device: '/dev/vda' }],
		availableVolumes: [], actioning: null,
		...overrides,
	} as InstanceDetailController;
}
function deferred<T>() {
	let resolve!: (value: T) => void;
	const promise = new Promise<T>((done) => { resolve = done; });
	return { promise, resolve };
}
function setup(source = controller()) {
	const refresh = vi.fn().mockResolvedValue(undefined);
	return { ...render(Wrapper, { source, refresh }), refresh };
}

beforeEach(() => {
	vi.clearAllMocks();
	auth.set({ token: 'token', projectId: 'auth-default' } as never);
	(canWrite as Writable<boolean>).set(true);
	get.mockImplementation((path: string) => {
		if (path === '/api/v1/volumes/volume-a') return Promise.resolve(volume);
		if (path === '/api/v1/instances/instance-a') return Promise.resolve({ id: 'instance-a', project_id: 'target-project', status: 'SHUTOFF' });
		return Promise.reject(new Error(`Unexpected GET ${path}`));
	});
	post.mockResolvedValue({ ...volume, status: 'extending' });
});

describe('attached volume capacity expansion', () => {
	it('opens the real modal with target-project Cinder details, not the attachment summary', async () => {
		setup();
		await fireEvent.click(screen.getByRole('button', { name: 'volumes.extend' }));
		await screen.findByRole('dialog');
		expect(get).toHaveBeenCalledWith('/api/v1/volumes/volume-a', 'token', 'target-project', { refresh: true });
		expect(screen.getByRole('dialog').textContent).toContain('Actual Cinder disk');
		expect((screen.getByRole('spinbutton') as HTMLInputElement).value).toBe('50');
		expect(post).not.toHaveBeenCalled();
	});

	it('sends a positive expansion only after scoped stopped-owner preflight and refreshes this instance', async () => {
		const view = setup();
		await fireEvent.click(screen.getByRole('button', { name: 'volumes.extend' }));
		await screen.findByRole('dialog');
		await fireEvent.click(screen.getByRole('button', { name: 'extendModal.extend' }));
		await waitFor(() => expect(view.refresh).toHaveBeenCalledWith('instance-a', { silent: true }));
		expect(get).toHaveBeenCalledWith('/api/v1/instances/instance-a', 'token', 'target-project', { refresh: true });
		expect(post).toHaveBeenCalledWith('/api/v1/volumes/volume-a/extend', { new_size: 50 }, 'token', 'target-project');
		expect(screen.queryByRole('dialog')).toBeNull();
	});

	it('communicates the offline requirement and disables ACTIVE expansion', () => {
		setup(controller({ instance: { id: 'instance-a', status: 'ACTIVE' } as never }));
		expect(screen.getByRole('button', { name: 'volumes.extend' }).hasAttribute('disabled')).toBe(true);
		expect(screen.getByText('volumes.extendOfflineRequired')).toBeTruthy();
		expect(get).not.toHaveBeenCalled();
	});

	it.each([
		['read-only', (): void => (canWrite as Writable<boolean>).set(false), controller()],
		['missing target scope', (): void => undefined, controller({ effectiveProjectId: undefined })],
		['stale instance identity', (): void => undefined, controller({ instance: { id: 'old-instance', status: 'SHUTOFF' } as never })],
		['unavailable volume', (): void => undefined, controller({ volumes: [{ volume_id: 'volume-a', status: 'extending', size: 20 }] as never })],
		['invalid capacity', (): void => undefined, controller({ volumes: [{ volume_id: 'volume-a', status: 'in-use', size: 1.5 }] as never })],
		['capacity boundary', (): void => undefined, controller({ volumes: [{ volume_id: 'volume-a', status: 'in-use', size: 2147483647 }] as never })],
	] as const)('disables expansion for %s', (_label, prepare, source) => {
		prepare();
		setup(source);
		expect(screen.getByRole('button', { name: 'volumes.extend' }).hasAttribute('disabled')).toBe(true);
		expect(get).not.toHaveBeenCalled();
	});

	it.each([
		{ ...volume, id: 'wrong-volume' },
		{ ...volume, status: 'extending' },
		{ ...volume, size: 0 },
		{ ...volume, attachments: [] },
		{ ...volume, attachments: [{ server_id: 'other-instance' }] },
	])('rejects unavailable or mismatched authoritative detail %j', async (detail) => {
		get.mockResolvedValue(detail);
		setup();
		await fireEvent.click(screen.getByRole('button', { name: 'volumes.extend' }));
		await screen.findByText('volumes.extendUnavailable');
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(post).not.toHaveBeenCalled();
	});

	it('discards a late detail response after switching target scope', async () => {
		const pending = deferred<Volume>();
		get.mockReturnValue(pending.promise);
		const view = setup();
		await fireEvent.click(screen.getByRole('button', { name: 'volumes.extend' }));
		await view.rerender({ source: controller({ effectiveProjectId: 'project-b' }), refresh: view.refresh });
		pending.resolve(volume);
		await waitFor(() => expect(screen.getByRole('button', { name: 'volumes.extend' }).hasAttribute('disabled')).toBe(false));
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(post).not.toHaveBeenCalled();
	});

	it('discards detail after a credential ABA transition', async () => {
		const pending = deferred<Volume>();
		get.mockReturnValue(pending.promise);
		setup();
		await fireEvent.click(screen.getByRole('button', { name: 'volumes.extend' }));
		auth.set({ token: 'other-token', projectId: 'auth-default' } as never);
		await waitFor(() => expect(screen.getByRole('button', { name: 'volumes.extend' }).hasAttribute('disabled')).toBe(false));
		auth.set({ token: 'token', projectId: 'auth-default' } as never);
		await Promise.resolve();
		pending.resolve(volume);
		await Promise.resolve();
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(post).not.toHaveBeenCalled();
	});

	it('closes an open expansion dialog when the instance starts', async () => {
		const view = setup();
		await fireEvent.click(screen.getByRole('button', { name: 'volumes.extend' }));
		await screen.findByRole('dialog');
		await view.rerender({ source: controller({ instance: { id: 'instance-a', status: 'ACTIVE' } as never }), refresh: view.refresh });
		await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
		expect(post).not.toHaveBeenCalled();
	});
});

it('preserves an open expansion draft across a same-context instance refresh', async () => {
	const view = setup();
	await fireEvent.click(screen.getByRole('button', { name: 'volumes.extend' }));
	await screen.findByRole('dialog');
	await fireEvent.input(screen.getByRole('spinbutton'), { target: { value: '64' } });
	await view.rerender({ source: controller(), refresh: view.refresh });
	expect(screen.getByRole('dialog')).toBeTruthy();
	expect((screen.getByRole('spinbutton') as HTMLInputElement).value).toBe('64');
});
