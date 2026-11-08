import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { ApiError } from '$lib/api/errors';
import type { Group, GroupMember } from '$lib/types/adminGroup';
import { mockAdminGroups } from './adminGroups';
import { maybeMockJson } from './transport';
import { resetMockupState } from './state';

// The page always appends the DomainScope selection; the tutorial administrator's own domain is mock-domain.
const scoped = new URLSearchParams({ domain_id: 'mock-domain' });
const admin = (method: string, path: string, body: unknown = null, params = scoped) => mockAdminGroups(method, path, params, body, 'admin');
const list = () => admin('GET', '/api/v1/admin/groups') as Group[];
const status = (run: () => unknown) => { try { run(); } catch (error) { return error instanceof ApiError ? error.status : -1; } return 0; };

describe('mockAdminGroups', () => {
	beforeEach(() => {
		resetMockupState();
		// The query activation is read on every request, so the static transport import needs no module reset.
		window.history.replaceState({}, '', '/admin/groups?tutorial=admin&domain_id=mock-domain');
	});
	afterEach(() => window.history.replaceState({}, '', '/'));

	it('creates a group in the selected domain, lists it first and deletes only it', () => {
		const before = list();
		expect(before.map((group) => group.name)).toEqual(['sample-researchers', 'sample-operators']);
		const created = admin('POST', '/api/v1/admin/groups', { name: 'tut-group', description: null, domain_id: 'mock-domain' }) as Group;
		expect(created).toEqual({ id: expect.any(String), name: 'tut-group', description: '', domain_id: 'mock-domain' });
		expect(list().map((group) => group.id)).toEqual([created.id, ...before.map((group) => group.id)]);
		expect(list()[0]).toMatchObject({ name: 'tut-group', domain_id: 'mock-domain', created_at: expect.any(String) });
		expect(admin('GET', `/api/v1/admin/groups/${created.id}/users`)).toEqual([]);
		expect(admin('DELETE', `/api/v1/admin/groups/${created.id}`)).toEqual({});
		expect(list()).toEqual(before);
		expect(status(() => admin('DELETE', `/api/v1/admin/groups/${created.id}`))).toBe(404);
	});

	it('serves the exact request the page sends through the transport', async () => {
		const created = await maybeMockJson<Group>('POST', '/api/v1/admin/groups?domain_id=mock-domain', { name: 'tut-group', description: null, domain_id: 'mock-domain' }, 'mock-token-admin', 'mock-admin-project') as Group;
		const listed = await maybeMockJson<Group[]>('GET', '/api/v1/admin/groups?domain_id=mock-domain', undefined, 'mock-token-admin', 'mock-admin-project') as Group[];
		expect(listed[0].id).toBe(created.id);
		expect(listed.every((group) => group.domain_id === 'mock-domain')).toBe(true);
		await maybeMockJson('DELETE', `/api/v1/admin/groups/${encodeURIComponent(created.id)}?domain_id=mock-domain`, undefined, 'mock-token-admin', 'mock-admin-project');
		const after = await maybeMockJson<Group[]>('GET', '/api/v1/admin/groups?domain_id=mock-domain', undefined, 'mock-token-admin', 'mock-admin-project') as Group[];
		expect(after.some((group) => group.id === created.id)).toBe(false);
	});

	it('keeps seed groups, rejects invalid input and foreign domains', async () => {
		expect(admin('DELETE', '/api/v1/admin/groups/mock-group-operators')).toBeUndefined();
		await expect(maybeMockJson('DELETE', '/api/v1/admin/groups/mock-group-operators?domain_id=mock-domain', undefined, 'mock-token-admin', 'mock-admin-project')).rejects.toMatchObject({ status: 409 });
		expect(list()).toHaveLength(2);
		expect((admin('GET', '/api/v1/admin/groups/mock-group-researchers/users') as GroupMember[]).map((user) => user.id)).toEqual(['mock-user-2']);
		expect(status(() => admin('POST', '/api/v1/admin/groups', { name: 'sample-operators', domain_id: 'mock-domain' }))).toBe(409);
		expect(status(() => admin('POST', '/api/v1/admin/groups', { name: '', domain_id: 'mock-domain' }))).toBe(400);
		expect(status(() => admin('POST', '/api/v1/admin/groups', { name: 'tut-group' }))).toBe(422);
		expect(status(() => admin('POST', '/api/v1/admin/groups', { name: 'tut-group', domain_id: 'other' }))).toBe(404);
		expect(status(() => admin('GET', '/api/v1/admin/groups', null, new URLSearchParams()))).toBe(422);
		expect(status(() => admin('GET', '/api/v1/admin/groups', null, new URLSearchParams({ domain_id: 'other' })))).toBe(404);
		expect(status(() => admin('DELETE', '/api/v1/admin/groups/mock-group-operators', null, new URLSearchParams({ domain_id: 'other' })))).toBe(404);
		expect(admin('PUT', '/api/v1/admin/groups/mock-group-operators/users/mock-user-2')).toBeUndefined();
		expect(mockAdminGroups('GET', '/api/v1/admin/groups', scoped, null, 'on')).toBeUndefined();
		expect(list()).toHaveLength(2);
	});
});
