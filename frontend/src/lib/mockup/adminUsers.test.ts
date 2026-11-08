import { beforeEach, describe, expect, it } from 'vitest';
import { ApiError } from '$lib/api/errors';
import type { DomainAccountResult } from '$lib/types/auth';
import { mockAdminUsers } from './adminUsers';
import { getMockupState, resetMockupState } from './state';

const none = new URLSearchParams();
// The page deletes through domainPath(), which appends the selected domain as domain_id.
const scoped = new URLSearchParams({ domain_id: 'mock-domain' });
const admin = (method: string, path: string, body: unknown = null, params = none) => mockAdminUsers(method, path, params, body, 'admin');
// Exactly the body AdminUsersPage.create() sends for the selected domain.
const form = (overrides: Record<string, unknown> = {}) => ({ domain_id: 'mock-domain', name: 'tut-user', email: 'tut-user@Example.TEST', password: 'practice-pass-1', enabled: true, ...overrides });
const status = (fn: () => unknown) => { try { fn(); } catch (error) { return error instanceof ApiError ? error.status : -1; } return 0; };

describe('mockAdminUsers', () => {
	beforeEach(() => resetMockupState());

	it('creates a listed user in the selected domain without storing the password, then deletes only it', () => {
		const seeds = getMockupState().admin.users.map((user) => user.id);
		const result = admin('POST', '/api/v1/admin/users', form()) as DomainAccountResult & { id: string; email: string };
		expect(result).toMatchObject({ user_id: result.id, email: 'tut-user@example.test', identity_domain_id: 'mock-domain', identity_domain_name: 'Demo', personal_project_id: null, personal_project_deferred: true });
		expect(JSON.stringify(result)).not.toContain('practice-pass-1');
		const listed = getMockupState().admin.users.find((user) => user.id === result.user_id);
		expect(listed).toMatchObject({ name: 'tut-user', domain_id: 'mock-domain', enabled: true, default_project_id: null });
		expect(JSON.stringify(getMockupState())).not.toContain('practice-pass-1');
		expect(seeds).not.toContain(result.user_id);

		expect(admin('DELETE', `/api/v1/admin/users/${result.user_id}`, null, scoped)).toEqual({});
		expect(getMockupState().admin.users.map((user) => user.id)).toEqual(seeds);
		expect(status(() => admin('DELETE', `/api/v1/admin/users/${result.user_id}`, null, scoped))).toBe(404);
	});

	it('rejects invalid creation like the backend', () => {
		expect(status(() => admin('POST', '/api/v1/admin/users', form({ password: 'short' })))).toBe(422);
		expect(status(() => admin('POST', '/api/v1/admin/users', form({ role: 'admin' })))).toBe(422);
		expect(status(() => admin('POST', '/api/v1/admin/users', form({ domain_id: 'other' })))).toBe(404);
		expect(status(() => admin('POST', '/api/v1/admin/users', form({ email: 'not-an-email' })))).toBe(403);
		expect(status(() => admin('POST', '/api/v1/admin/users', form({ email: 'sample-admin@example.test' })))).toBe(409);
		expect(status(() => admin('POST', '/api/v1/admin/users', form({ name: 'sample-admin', email: 'tut-other@example.test' })))).toBe(409);
		expect(getMockupState().adminCreatedUserIds).toEqual([]);
	});

	it('never deletes seed accounts, the signed-in administrator or foreign domains', () => {
		const before = getMockupState().admin.users.length;
		expect(status(() => admin('DELETE', '/api/v1/admin/users/mock-user-2', null, scoped))).toBe(409);
		expect(status(() => admin('DELETE', '/api/v1/admin/users/mock-admin-1', null, scoped))).toBe(409);
		expect(status(() => admin('DELETE', '/api/v1/admin/users/mock-user-2'))).toBe(422);
		expect(status(() => admin('DELETE', '/api/v1/admin/users/mock-user-2', null, new URLSearchParams({ domain_id: 'other' })))).toBe(404);
		expect(getMockupState().admin.users).toHaveLength(before);
		expect(mockAdminUsers('POST', '/api/v1/admin/users', none, form(), 'on')).toBeUndefined();
		expect(admin('GET', '/api/v1/admin/users')).toBeUndefined();
	});
});
