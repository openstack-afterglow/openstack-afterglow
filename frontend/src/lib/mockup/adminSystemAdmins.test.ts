import { beforeEach, describe, expect, it } from 'vitest';
import { ApiError } from '$lib/api/errors';
import { mockAdminSystemAdmins } from './adminSystemAdmins';
import { resetMockupState } from './state';

const LIST = '/api/v1/admin/identity/system-roles';
const admin = (method: string, path: string, body: unknown = null) => mockAdminSystemAdmins(method, path, body, 'admin');
const status = (fn: () => unknown) => { try { fn(); } catch (error) { return error instanceof ApiError ? error.status : -1; } return 0; };

describe('mockAdminSystemAdmins', () => {
	beforeEach(() => resetMockupState());

	it('reads the same state a grant and a revoke change', () => {
		expect(admin('GET', LIST)).toEqual([expect.objectContaining({ user_id: 'mock-admin-1' })]);
		expect(admin('POST', `${LIST}/grant`, { user_id: 'mock-user-2' })).toEqual({ status: 'granted' });
		expect((admin('GET', LIST) as { user_id: string }[]).map((row) => row.user_id)).toEqual(['mock-admin-1', 'mock-user-2']);
		expect(admin('POST', `${LIST}/revoke`, { user_id: 'mock-user-2' })).toEqual({ status: 'revoked' });
		expect((admin('GET', LIST) as unknown[]).length).toBe(1);
	});

	it('keeps backend guards', () => {
		expect(status(() => admin('POST', `${LIST}/grant`, {}))).toBe(422);
		expect(status(() => admin('POST', `${LIST}/grant`, { user_id: 'unknown' }))).toBe(404);
		expect(status(() => admin('POST', `${LIST}/revoke`, { user_id: 'mock-user-2' }))).toBe(404);
		expect(status(() => admin('POST', `${LIST}/revoke`, { user_id: 'mock-admin-1' }))).toBe(409);
		expect(mockAdminSystemAdmins('GET', LIST, null, 'on')).toBeUndefined();
	});
});
