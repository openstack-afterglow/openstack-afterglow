import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
import { auth } from '$lib/stores/auth';
import { adminInventoryScope, setAdminInventoryScope } from '$lib/stores/adminInventoryScope';
import { createAdminInventoryApi } from '../adminInventoryScope';

const mocks = vi.hoisted(() => ({ get: vi.fn(), prefetch: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: mocks }));
const initial = get(auth);
beforeEach(() => {
	vi.resetAllMocks();
	auth.set({ ...initial, token: 'token', sessionId: 'session', userId: 'operator', projectId: 'workspace', domainId: 'home', isSystemAdmin: true });
	setAdminInventoryScope('', '');
	mocks.get.mockResolvedValue([]); mocks.prefetch.mockResolvedValue(undefined); mocks.post.mockResolvedValue({ ok: true });
});

afterEach(() => { auth.set(initial); });

describe('scoped administrator requests', () => {
	it('passes domain and project intersection with a marker to inventory and prefetch without changing authentication scope', async () => {
		setAdminInventoryScope('domain-a', 'project-a');
		const scoped = createAdminInventoryApi();
		await scoped.get('/api/v1/admin/all-instances?limit=20&marker=previous', 'token', 'workspace');
		await scoped.prefetch('/api/v1/admin/all-instances?limit=20&marker=next', 'token', 'workspace');
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/admin/all-instances?limit=20&marker=previous&domain_id=domain-a&project_id=project-a', 'token', 'workspace');
		expect(mocks.prefetch).toHaveBeenCalledWith('/api/v1/admin/all-instances?limit=20&marker=next&domain_id=domain-a&project_id=project-a', 'token', 'workspace');
		expect(get(auth).projectId).toBe('workspace');
	});

	it('filters administrator Swift accounts without applying inventory scope to the consumer list', async () => {
		setAdminInventoryScope('domain-a', 'project-a');
		const scoped = createAdminInventoryApi();
		await scoped.get('/api/v1/admin/object-storage?include_quarantine=true&include_trash=true&include_deleted=true', 'token', undefined);
		await scoped.get('/api/v1/object-storage', 'token', 'workspace');
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/admin/object-storage?include_quarantine=true&include_trash=true&include_deleted=true&domain_id=domain-a&project_id=project-a', 'token', undefined);
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/object-storage', 'token', 'workspace');
	});

	it('leaves exact details, directory IAM and mutation targets untouched', async () => {
		setAdminInventoryScope('domain-a', 'project-a');
		const scoped = createAdminInventoryApi();
		await scoped.get('/api/v1/admin/users?domain_id=identity-domain', 'token', 'workspace');
		await scoped.get('/api/v1/admin/instances/vm-id', 'token', 'workspace');
		await scoped.post('/api/v1/admin/volumes/volume-id/transfer', { target_project_id: 'foreign-project' }, 'token', 'workspace');
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/admin/users?domain_id=identity-domain', 'token', 'workspace');
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/admin/instances/vm-id', 'token', 'workspace');
		expect(mocks.post).toHaveBeenCalledWith('/api/v1/admin/volumes/volume-id/transfer', { target_project_id: 'foreign-project' }, 'token', 'workspace');
	});

	it('invalidates old responses and old mutation closures across A→B→A, but not same-session bearer refresh', async () => {
		setAdminInventoryScope('domain-a', 'project-a');
		const scoped = createAdminInventoryApi();
		const pending = Promise.withResolvers<string[]>();
		mocks.get.mockReturnValueOnce(pending.promise);
		const request = scoped.get<string[]>('/api/v1/admin/all-volumes', 'token', 'workspace');
		const rejected = expect(request).rejects.toMatchObject({ name: 'AbortError' });
		const revision = get(adminInventoryScope).revision;
		auth.update(state => ({ ...state, token: 'refreshed-token' }));
		expect(get(adminInventoryScope).revision).toBe(revision);
		setAdminInventoryScope('domain-b', 'project-b'); setAdminInventoryScope('domain-a', 'project-a');
		pending.resolve(['old-volume']);
		await rejected;
		expect(() => scoped.post('/api/v1/instances/bulk-action', { instance_ids: ['old-vm'] }, 'refreshed-token', 'workspace')).toThrow();
		expect(mocks.post).not.toHaveBeenCalled();
	});

	it('does not present stored cluster aggregate history as filtered history', async () => {
		setAdminInventoryScope('domain-a', '');
		const scoped = createAdminInventoryApi();
		await expect(scoped.get('/api/v1/admin/timeseries/instances?range=7d', 'token', 'workspace')).rejects.toMatchObject({ name: 'AbortError' });
		expect(mocks.get).not.toHaveBeenCalled();
	});

	it('revokes pending reads and confirmation closures when their route is disposed', async () => {
		const scoped = createAdminInventoryApi();
		const pending = Promise.withResolvers<string[]>();
		mocks.get.mockReturnValueOnce(pending.promise);
		const rejected = expect(scoped.get('/api/v1/admin/all-instances', 'token', 'workspace')).rejects.toMatchObject({ name: 'AbortError' });
		scoped.dispose();
		pending.resolve(['stale']);
		await rejected;
		expect(scoped.isCurrent()).toBe(false);
		expect(() => scoped.delete('/api/v1/admin/volumes/stale', 'token', 'workspace')).toThrow();
		expect(mocks.delete).not.toHaveBeenCalled();
	});
});
