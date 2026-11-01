import { beforeEach, describe, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }));
vi.mock('./client', () => ({ api: mocks }));
import { gpuQuotaRequests } from './gpuQuotaRequests';
const authority = () => ({ token: () => 'manager-token', projectId: () => undefined, isCurrent: () => true, canSubmit: () => true });
beforeEach(() => vi.resetAllMocks());

describe('GPU request wire authority', () => {
	it('uses exact manager targets without accepting a domain and never writes quota', async () => {
		const client = gpuQuotaRequests(false, authority());
		const body = { project_id: 'exact-project', resource_class: 'CUSTOM_PCI_10DE_2684', additional: 2, reason: 'More work' };
		await client.list('all', 'cursor/id'); await client.create(body);
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/iam/gpu-quota-requests?status=all&cursor=cursor%2Fid', 'manager-token', undefined, { cache: 'no-store' });
		expect(mocks.post).toHaveBeenCalledWith('/api/v1/iam/gpu-quota-requests', body, 'manager-token', undefined, expect.objectContaining({ replayOnUnauthorized: false }));
		expect(mocks.put).not.toHaveBeenCalled();
	});
	it('resolves only through the admin review endpoint with fresh bearer and no replay', async () => {
		let token = 'first';
		const client = gpuQuotaRequests(true, { ...authority(), token: () => token, projectId: () => 'working-project' });
		await client.list('pending'); token = 'rotated'; await client.resolve('exact/id', 'fulfilled', 'Manually adjusted');
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/admin/gpu-quota-requests?status=pending', 'first', 'working-project', { cache: 'no-store' });
		expect(mocks.post).toHaveBeenCalledExactlyOnceWith('/api/v1/admin/gpu-quota-requests/exact%2Fid/resolve', { status: 'fulfilled', note: 'Manually adjusted' }, 'rotated', 'working-project', expect.objectContaining({ replayOnUnauthorized: false }));
		expect(mocks.put).not.toHaveBeenCalled();
	});
	it('refuses cross-role operations and revoked write authority before dispatch', async () => {
		await expect(gpuQuotaRequests(false, authority()).resolve('request', 'rejected', '')).rejects.toMatchObject({ name: 'AbortError' });
		await expect(gpuQuotaRequests(true, authority()).create({ project_id: 'p', resource_class: 'r', additional: 1, reason: '' })).rejects.toMatchObject({ name: 'AbortError' });
		await expect(gpuQuotaRequests(false, { ...authority(), canSubmit: () => false }).create({ project_id: 'p', resource_class: 'r', additional: 1, reason: '' })).rejects.toMatchObject({ name: 'AbortError' });
		expect(mocks.post).not.toHaveBeenCalled();
	});
	it('checks the last dispatch boundary and discards stale replies', async () => {
		let current = true;
		const client = gpuQuotaRequests(true, { ...authority(), isCurrent: () => current });
		mocks.post.mockImplementation(async (_path, _body, _token, _project, options) => { current = false; options.beforeDispatch(); });
		await expect(client.resolve('request', 'rejected', '')).rejects.toMatchObject({ name: 'AbortError' });
		current = true;
		const pending = Promise.withResolvers<unknown>(); mocks.get.mockReturnValue(pending.promise);
		const result = client.list('all'); current = false; pending.resolve({ items: [], next_cursor: null });
		await expect(result).rejects.toMatchObject({ name: 'AbortError' });
	});
});
