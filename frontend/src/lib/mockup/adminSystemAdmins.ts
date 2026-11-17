import { ApiError } from '$lib/api/errors';
import type { MockupProfileId } from './contracts';
import { getMockupState } from './state';

const LIST = '/api/v1/admin/identity/system-roles';

// Synthetic system:all administrator inventory for the tutorial admin profile.
// Grant/revoke mirror the backend guards (unknown user 404, last administrator 409)
// and the list is a plain read of the same state, so a mutation is visible on the next read.
export function mockAdminSystemAdmins(method: string, path: string, body: unknown, profile: MockupProfileId): unknown | undefined {
	if (profile !== 'admin') return undefined;
	const state = getMockupState();
	if (method === 'GET' && path === LIST) {
		return state.admin.systemAdminIds.flatMap((id) => {
			const user = state.admin.users.find((item) => item.id === id);
			return user ? [{ user_id: id, name: user.name, email: user.email, enabled: user.enabled }] : [];
		});
	}
	if (method !== 'POST' || (path !== `${LIST}/grant` && path !== `${LIST}/revoke`)) return undefined;
	const userId = (body as { user_id?: unknown } | null)?.user_id;
	if (typeof userId !== 'string' || !userId) throw new ApiError(422, 'user_id is required');
	if (!state.admin.users.some((item) => item.id === userId)) throw new ApiError(404, 'User not found');
	if (path.endsWith('/grant')) {
		if (!state.admin.systemAdminIds.includes(userId)) state.admin.systemAdminIds.push(userId);
		return { status: 'granted' };
	}
	if (!state.admin.systemAdminIds.includes(userId)) throw new ApiError(404, 'system_admin_grant_not_found');
	if (state.admin.systemAdminIds.length <= 1) throw new ApiError(409, 'Cannot revoke the last system administrator');
	state.admin.systemAdminIds = state.admin.systemAdminIds.filter((id) => id !== userId);
	return { status: 'revoked' };
}
