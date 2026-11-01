import { api } from './client';
import type { GpuAutomationProfile } from './flavorAutomation';

export type ComputeLimits = Record<string, number>;
export interface ComputePool {
	domain_id: string;
	state: 'unmanaged' | 'active' | 'paused';
	revision: number;
	enabled: boolean;
	limits: ComputeLimits;
	project_limits: Record<string, ComputeLimits>;
	usage: Record<string, number | null>;
	available: Record<string, number | null>;
	projects: Array<{ id: string; name: string; enabled: boolean }>;
	policy_ready: boolean;
	control_scope: 'afterglow';
	gpu_profiles?: Array<Pick<GpuAutomationProfile, 'name' | 'display_name' | 'resource_class' | 'resource_requirements'>>;
	stale_project_caps?: string[];
	projection_unavailable?: boolean;
}
export interface ComputeAuthority {
	token: () => string;
	projectId: () => string | undefined;
	isCurrent: () => boolean;
	canSubmit: () => boolean;
}
export function computePools(domainId: string, adminMode: boolean, authority: ComputeAuthority) {
	const root = adminMode ? `/api/v1/admin/domains/${encodeURIComponent(domainId)}/compute-pool` : '/api/v1/iam/compute-pool';
	const dispatch = async <T>(send: () => Promise<T>, mutation = false): Promise<T> => {
		if (!authority.isCurrent() || (mutation && !authority.canSubmit())) throw new DOMException('', 'AbortError');
		try {
			const result = await send();
			if (!authority.isCurrent()) throw new DOMException('', 'AbortError');
			return result;
		} catch (cause) {
			if (!authority.isCurrent()) throw new DOMException('', 'AbortError');
			throw cause;
		}
	};
	const beforeDispatch = () => {
		if (!authority.isCurrent() || !authority.canSubmit()) throw new DOMException('', 'AbortError');
	};
	return {
		load: () => dispatch(() => api.get<ComputePool>(root, authority.token(), authority.projectId(), { cache: 'no-store' })),
		save: (revision: number, enabled: boolean, limits: ComputeLimits) => dispatch(() => api.put<ComputePool>(root, { revision, enabled, limits }, authority.token(), authority.projectId(), { replayOnUnauthorized: false, beforeDispatch }), true),
		saveProject: (project: string, revision: number, limits: ComputeLimits) => dispatch(() => api.put<ComputePool>(`${root}/projects/${encodeURIComponent(project)}`, { revision, limits }, authority.token(), authority.projectId(), { replayOnUnauthorized: false, beforeDispatch }), true),
		removeProject: (project: string, revision: number) => dispatch(() => api.delete<ComputePool>(`${root}/projects/${encodeURIComponent(project)}?revision=${revision}`, authority.token(), authority.projectId(), { replayOnUnauthorized: false, beforeDispatch }), true)
	};
}

export const isManagedFlavor = (flavor: { cpu_automation_managed?: boolean; extra_specs?: Record<string, string> }) =>
	flavor.extra_specs?.['afterglow:managed_by'] === 'domain-compute-v1'
	|| flavor.cpu_automation_managed === true;

export function computePoolLimit(limits: ComputeLimits, resource: string): number {
	return limits[resource] ?? (resource === 'CPU' || resource === 'MEMORY_MB' ? -1 : 0);
}
export function parseComputeLimits(draft: Record<string, string>, ceilings?: ComputeLimits): ComputeLimits | null {
	const result: ComputeLimits = {};
	for (const [resource, text] of Object.entries(draft)) {
		if (!text.trim()) continue;
		if (!/^-?\d+$/.test(text.trim())) return null;
		const value = Number(text);
		if (!Number.isSafeInteger(value) || value < -1 || value > 2_147_483_647) return null;
		const ceiling = ceilings ? computePoolLimit(ceilings, resource) : -1;
		if (ceilings && ceiling !== -1 && (value === -1 || value > ceiling)) return null;
		result[resource] = value;
	}
	return result;
}
