import { waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushSync, tick } from 'svelte';
import type { ExperienceContext } from '$lib/utils/experience';
import { captureFlowExperience } from './experienceFlowHarness';
import { createFileStorageDetailController } from '../fileStorageDetailController.svelte';
import { createFileStorageWizardStore } from '../fileStorageWizardStore.svelte';
import { createDbCreateStore } from '../dbCreateStore.svelte';
import { createDbInstanceDetailController } from '../dbInstanceDetailController.svelte';
import { createObjectBrowserStore } from '../objectBrowser.svelte';

const transport = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() }));
const requests = vi.hoisted(() => [] as { method: string; context?: ExperienceContext; options?: Record<string, unknown> }[]);
vi.mock('$lib/api/client', () => ({
	ApiError: class ApiError extends Error {},
	api: {
		...transport,
		withExperience(context?: ExperienceContext) {
			return {
				get<T>(path: string, token?: string, project?: string, options?: Record<string, unknown>): Promise<T> {
					requests.push({ method: 'get', context, options });
					return transport.get(path, token, project, { ...options, experience: context });
				},
				post<T>(path: string, body: unknown, token?: string, project?: string): Promise<T> {
					requests.push({ method: 'post', context });
					return transport.post(path, body, token, project);
				},
				put<T>(path: string, body: unknown, token?: string, project?: string): Promise<T> {
					requests.push({ method: 'put', context });
					return transport.put(path, body, token, project);
				},
				delete<T>(path: string, token?: string, project?: string): Promise<T> {
					requests.push({ method: 'delete', context });
					return transport.delete(path, token, project);
				},
			};
		},
	},
	fetchWithAuth: vi.fn(), getBaseUrl: () => '',
}));
vi.mock('$lib/stores/auth', async () => {
	// Hoisted module factory must initialize its own store before static application imports.
	const { writable } = await import('svelte/store');
	return { auth: writable({ token: 'TOKEN_CANARY', projectId: 'project-a' }), authReady: writable(true), projectSwitching: writable(false) };
});
vi.mock('$lib/stores/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: vi.fn(async () => true) }));
vi.mock('$lib/api/mutations', () => ({ apiMut: async (_label: string, mutation: () => Promise<unknown>) => mutation() }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({ createAutoRefresh: () => ({}) }));

const owner = { token: 'TOKEN_CANARY', userId: 'user-a', projectId: 'project-a', domainId: 'domain-a' };
const cleanups: (() => void)[] = [];
function mount<T>(factory: () => T): T {
	let value!: T;
	cleanups.push($effect.root(() => { value = factory(); }));
	flushSync();
	return value;
}
function deferred<T>() {
	return Promise.withResolvers<T>();
}
function capture(route: string) {
	const flow = captureFlowExperience(route, () => owner);
	cleanups.push(flow.collector.destroy);
	return flow;
}
beforeEach(() => {
	vi.clearAllMocks(); requests.length = 0;
	transport.get.mockResolvedValue([]);
	transport.post.mockResolvedValue({});
	transport.put.mockResolvedValue({});
	transport.delete.mockResolvedValue(undefined);
});
afterEach(() => {
	for (const cleanup of cleanups.splice(0).reverse()) cleanup();
	vi.restoreAllMocks();
});

describe('storage experience actual owner assignments', () => {
	it('records both late and newer actual assignments without inventing a request-start stale fence', async () => {
		const flow = capture('/dashboard/file-storage');
		const first = deferred<unknown>();
		const second = deferred<unknown>();
		let detailReads = 0;
		transport.get.mockImplementation((path: string) => path.endsWith('/access-rules')
			? Promise.resolve([]) : (++detailReads === 1 ? first.promise : second.promise));
		const store = createFileStorageDetailController({ fileStorageId: () => 'share-a', token: () => owner.token, projectId: () => owner.projectId });
		const oldRead = store.fetchAll({ refresh: true });
		const newRead = store.fetchAll({ refresh: true });
		second.resolve({ id: 'share-a', name: 'NEW_NAME_CANARY', status: 'available' });
		await newRead;
		first.resolve({ id: 'share-a', name: 'OLD_NAME_CANARY', status: 'creating' });
		await oldRead;
		await tick();
		const events = await flow.flush();
		expect(store.fileStorage?.name).toBe('OLD_NAME_CANARY');
		expect(events.filter((event) => event.event_type === 'action.started')).toHaveLength(0);
		expect(events.filter((event) => event.event_type === 'result.applied')).toHaveLength(4);
		expect(requests[0].context?.traceId).toBeTruthy();
		expect(requests[0].context?.traceId).toBe(requests[1].context?.traceId);
		expect(requests[2].context?.traceId).toBe(requests[3].context?.traceId);
		expect(requests[0].context?.spanId).not.toBe(requests[1].context?.spanId);
		expect(requests[2].context?.spanId).not.toBe(requests[3].context?.spanId);
		expect(requests[0].context?.traceId).not.toBe(requests[2].context?.traceId);
		expect(requests.every((request) => request.options?.refresh === true)).toBe(true);
		expect(JSON.stringify(events)).not.toMatch(/OLD_NAME_CANARY|NEW_NAME_CANARY|TOKEN_CANARY|share-a/);
	});

	it('keeps independent detail and rule fanout assignments under one action with an unknown DOM tail', async () => {
		const flow = capture('/dashboard/file-storage');
		transport.get.mockImplementation(async (path: string) => path.endsWith('/access-rules') ? [] : { id: 'share-a', status: 'creating' });
		const store = createFileStorageDetailController({ fileStorageId: () => 'share-a', token: () => owner.token, projectId: () => owner.projectId });
		await store.fetchAll();
		await tick();
		const events = await flow.flush();
		expect(events.filter((event) => event.event_type === 'result.applied')).toHaveLength(2);
		expect(events.filter((event) => event.event_type === 'result.committed')).toHaveLength(0);
		expect(events.some((event) => event.event_type === 'result.discarded')).toBe(false);
		expect(events.some((event) => event.payload.state === 'empty')).toBe(true);
	});

	it('observes accepted file creation before its follow-up read, without asserting availability or retaining metadata', async () => {
		const flow = capture('/dashboard/file-storage');
		const rules = deferred<unknown[]>();
		transport.post.mockResolvedValue({ id: 'SHARE_ID_CANARY', status: 'creating' });
		transport.get.mockReturnValue(rules.promise);
		const store = mount(() => createFileStorageWizardStore({ open: () => true, setOpen: () => {}, onCreated: () => {} }));
		store.fsForm = { name: 'SHARE_NAME_CANARY', size_gb: 10, share_type: '', share_proto: 'CEPHFS' };
		store.metaEntries = [{ key: 'META_KEY_CANARY', value: 'META_VALUE_CANARY' }];
		const pending = store.createFileStorage();
		await waitFor(() => expect(store.createdFs?.status).toBe('creating'));
		let events = await flow.flush();
		expect(events.some((event) => event.event_type === 'result.applied')).toBe(true);
		rules.resolve([]); await pending; await tick();
		events = await flow.flush();
		expect(requests[0].context?.action).toBe('create');
		expect(requests[1].context).toBe(requests[0].context);
		expect(events.some((event) => event.action_id === requests[0].context?.actionId && event.payload.state === 'ready')).toBe(false);
		expect(JSON.stringify(events)).not.toMatch(/SHARE_ID_CANARY|SHARE_NAME_CANARY|META_KEY_CANARY|META_VALUE_CANARY|available|succeeded/);
	});

	it('uses one explicit database metadata context for all fanout requests and a separate accepted-create action', async () => {
		const flow = capture('/dashboard/database');
		let open = true;
		transport.get.mockImplementation(async (path: string) => {
			if (path.endsWith('/flavors')) return [{ id: 'FLAVOR_CANARY' }];
			if (path.endsWith('/datastores')) return [{ id: 'DS_CANARY', name: 'mysql', versions: [{ name: '8' }] }];
			return [];
		});
		const created = vi.fn();
		const store = mount(() => createDbCreateStore({ open: () => open, setOpen: (value) => { open = value; }, onCreated: created }));
		await waitFor(() => expect(store.loading).toBe(false));
		store.name = 'DATABASE_NAME_CANARY';
		await store.createInstance(); await tick();
		const events = await flow.flush();
		const metadata = requests.filter((request) => request.method === 'get');
		expect(metadata).toHaveLength(8);
		expect(new Set(metadata.map((request) => request.context?.traceId)).size).toBe(1);
		expect(metadata.every((request) => request.context && !request.context.actionId)).toBe(true);
		expect(new Set(metadata.map((request) => request.context?.spanId)).size).toBe(7);
		expect(events.some((event) => event.event_type === 'result.discarded')).toBe(false);
		const creation = requests.find((request) => request.method === 'post');
		expect(creation?.context?.action).toBe('create');
		expect(creation?.context?.actionId).not.toBe(metadata[0].context?.actionId);
		expect(open).toBe(false); expect(created).toHaveBeenCalledOnce();
		expect(events.some((event) => event.action_id === creation?.context?.actionId && event.event_type === 'result.applied')).toBe(true);
		expect(events.some((event) => event.action_id === creation?.context?.actionId && event.payload.state === 'ready')).toBe(false);
		expect(JSON.stringify(events)).not.toMatch(/DATABASE_NAME_CANARY|FLAVOR_CANARY|DS_CANARY|TOKEN_CANARY|available|succeeded/);
	});

	it('links database user mutation readback without serializing credentials or returned users', async () => {
		const flow = capture('/dashboard/database');
		transport.get.mockResolvedValue([{ name: 'USERNAME_CANARY', password: 'RETURNED_SECRET_CANARY', host: '%' }]);
		const store = mount(() => createDbInstanceDetailController({ instanceId: () => 'INSTANCE_ID_CANARY', token: () => owner.token, projectId: () => owner.projectId }));
		expect(await store.createUser({ name: 'USERNAME_CANARY', password: 'PASSWORD_CANARY', host: '%', dbNames: ['DB_NAME_CANARY'] })).toBe(true);
		await tick();
		const events = await flow.flush();
		expect(store.users).toHaveLength(1);
		expect(requests.map((request) => request.method)).toEqual(['post', 'get']);
		expect(requests[1].context).toBe(requests[0].context);
		expect(events.some((event) => event.event_type === 'result.applied')).toBe(true);
		expect(events.some((event) => event.action_id === requests[0].context?.actionId && event.payload.state === 'ready')).toBe(false);
		expect(JSON.stringify(events)).not.toMatch(/USERNAME_CANARY|PASSWORD_CANARY|RETURNED_SECRET_CANARY|DB_NAME_CANARY|INSTANCE_ID_CANARY/);
	});

	it('retains the existing object bulk scope discard and never starts a follow-up in the newer scope', async () => {
		const flow = capture('/dashboard/object-storage');
		let project = 'project-a';
		const store = mount(() => createObjectBrowserStore({ mode: () => 'admin', containerName: () => 'CONTAINER_CANARY', token: () => owner.token, projectId: () => project, ownerKey: () => project }));
		await Promise.resolve(); await Promise.resolve(); await tick();
		await flow.flush();
		flow.events.length = 0; requests.length = 0;
		const deletion = deferred<unknown>();
		transport.post.mockReturnValue(deletion.promise);
		store.selected = new Set(['OBJECT_PATH_CANARY/SECRET_KEY_CANARY']);
		const pending = store.bulkDelete();
		await Promise.resolve();
		project = 'project-b';
		deletion.resolve({ deleted: ['OBJECT_PATH_CANARY/SECRET_KEY_CANARY'], failed: [] });
		await pending; await tick();
		const events = await flow.flush();
		expect(requests.map((request) => request.method)).toEqual(['post']);
		expect(store.selected.size).toBe(1);
		expect(events.some((event) => event.event_type === 'result.discarded' && event.payload.reason === 'stale')).toBe(true);
		expect(events.some((event) => event.event_type === 'result.applied')).toBe(false);
		expect(JSON.stringify(events)).not.toMatch(/CONTAINER_CANARY|OBJECT_PATH_CANARY|SECRET_KEY_CANARY|TOKEN_CANARY/);
	});

	it('retains an actual object assignment but discards its DOM tail after the existing disposal hook', async () => {
		const flow = capture('/dashboard/object-storage');
		const store = mount(() => createObjectBrowserStore({ mode: () => 'admin', containerName: () => 'CONTAINER_CANARY', token: () => owner.token, projectId: () => owner.projectId, ownerKey: () => owner.projectId }));
		await Promise.resolve(); await Promise.resolve(); await tick();
		await flow.flush(); flow.events.length = 0;
		const listing = deferred<unknown[]>();
		transport.get.mockReturnValueOnce(listing.promise);
		const pending = store.load();
		listing.resolve([{ name: 'OBJECT_CANARY', bytes: 1 }]);
		await Promise.resolve();
		store.disposeThumbnails();
		await pending; await tick();
		const events = await flow.flush();
		expect(store.objects).toHaveLength(1);
		expect(events.filter((event) => event.event_type === 'result.applied')).toHaveLength(1);
		expect(events.some((event) => event.event_type === 'result.discarded' && event.payload.stage === 'dom')).toBe(true);
		expect(events.some((event) => event.event_type === 'result.committed')).toBe(false);
		expect(events.some((event) => event.event_type === 'action.started')).toBe(false);
		expect(JSON.stringify(events)).not.toMatch(/CONTAINER_CANARY|OBJECT_CANARY|TOKEN_CANARY/);
	});
});
