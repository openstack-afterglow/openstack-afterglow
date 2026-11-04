import { api } from './client';
import type { FlavorComposition, FlavorComposerSnapshot, FlavorOption } from '$lib/types/flavor';
import type { ExperienceContext } from '$lib/utils/experience';

export interface FlavorComposerAuthority {
	token: string;
	projectId: string;
	targetProjectId: string;
	admin: boolean;
	/** Resize: evaluate the increase over this instance's current allocation. */
	instanceId?: string | null;
}
function path(authority: FlavorComposerAuthority, kind: 'options' | 'compositions', operationId?: string, readback = false) {
	const base = authority.admin ? '/api/v1/admin/instances' : '/api/v1/flavors';
	const leaf = authority.admin ? (kind === 'options' ? 'flavor-composer-options' : 'flavor-compositions') : (kind === 'options' ? 'composer-options' : 'compositions');
	const params = new URLSearchParams();
	if (authority.admin) params.set('project_id', authority.targetProjectId);
	if (authority.instanceId) params.set('instance_id', authority.instanceId);
	if (operationId && !readback) params.set('operation_id', operationId);
	return `${base}/${leaf}${readback ? `/operations/${encodeURIComponent(operationId!)}` : ''}${params.size ? `?${params}` : ''}`;
}
export const flavorComposerApi = {
	options: (authority: FlavorComposerAuthority, signal: AbortSignal) => api.get<FlavorComposerSnapshot>(path(authority, 'options'), authority.token, authority.projectId, { signal, cache: 'no-store' }),
	history: (authority: FlavorComposerAuthority, signal: AbortSignal, experience?: ExperienceContext) => api.get<{ items: FlavorOption[] }>(path(authority, 'compositions'), authority.token, authority.projectId, { signal, cache: 'no-store', ...(experience ? { experience } : {}) }),
	// Publication is shielded server-side and performs fresh native fences; a normal
	// catalog deadline must not abandon a valid, still-running mutation at 30s.
	save: (authority: FlavorComposerAuthority, composition: FlavorComposition, operationId: string, signal: AbortSignal, beforeDispatch: () => void) => api.post<FlavorOption>(path(authority, 'compositions', operationId), composition, authority.token, authority.projectId, { signal, timeoutMs: 120_000, replayOnUnauthorized: false, beforeDispatch }),
	resolve: (authority: FlavorComposerAuthority, operationId: string, signal: AbortSignal) => api.get<FlavorOption | null>(path(authority, 'compositions', operationId, true), authority.token, authority.projectId, { signal, cache: 'no-store' }),
};
