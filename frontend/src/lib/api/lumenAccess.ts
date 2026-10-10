import { get } from 'svelte/store';
import { auth } from '$lib/stores/auth';
import { serviceCapabilities } from '$lib/stores/servicePermissions';
import { ApiError } from './errors';
import { permissionReason } from './lumenPermissions';

/** UI preflight; server ownership and action checks remain authoritative. */
export function requireLumenCapability(leaf: string, token?: string, projectId?: string): void {
	const identity = get(auth);
	if (!token || !projectId || token !== identity.token || projectId !== identity.projectId) throw new ApiError(403, 'Lumen request scope changed.');
	if (!get(serviceCapabilities)(leaf)) throw new ApiError(403, permissionReason(leaf));
}
