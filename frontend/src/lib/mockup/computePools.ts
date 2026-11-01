import { ApiError } from '$lib/api/errors';
import { cloneMockup, getMockupState } from './state';
import { computePoolLimit, type ComputePool, type ComputeLimits } from '$lib/api/computePools';
import type { MockupProfileId } from './contracts';
import { parseGpuProfiles, type GpuAutomationProfile } from '$lib/api/flavorAutomation';

// Explicit synthetic tutorial state. This path is never used for authenticated real cloud requests.
export function mockComputePolicy(method: string, path: string, query: URLSearchParams, body: unknown, profile: MockupProfileId): unknown | undefined {
	if (profile === 'admin' && method === 'GET' && path === '/api/v1/admin/gpu-devices') return { devices: [{ vendor_id: '10de', device_id: '2236', vendor_name: 'NVIDIA', name: 'Synthetic A10', is_audio: false, aliases: ['A10'], source: 'builtin' }] };
	if (profile === 'admin' && method === 'GET' && path === '/api/v1/admin/flavors') return { items: [{ id: 'mock-managed-cpu-4', name: 'cpu.4c_8g', vcpus: 4, ram: 8192, disk: 0, is_public: false, description: 'Synthetic managed shape; native publication unverified.', is_gpu: false, gpu_count: 0, gpu_primary_aliases: [], frontend_visible: true, extra_specs: { 'afterglow:managed_by': 'domain-compute-v1', 'afterglow:access_mode': 'domain_quota', 'afterglow:frontend_visible': 'true' } }], count: 1, next_marker: null };
	if (profile === 'admin' && method === 'GET' && path === '/api/v1/admin/flavors/mock-managed-cpu-4/access') return [];
	const admin = path.match(/^\/api\/v1\/admin\/domains\/([^/]+)\/compute-pool(?:\/projects\/([^/]+))?$/);
	const iam = path.match(/^\/api\/v1\/iam\/compute-pool(?:\/projects\/([^/]+))?$/);
	const automation = /^\/api\/v1\/admin\/flavor-automation(?:\/(?:policy|reconcile|discover|hosts\/[^/]+))?$/.test(path);
	if (!admin && !iam && !automation) return undefined;
	if (profile !== 'admin') throw new ApiError(403, 'Tutorial profile has no domain compute management authority.');
	const state = getMockupState();
	const payload = body as { revision?: number; enabled?: boolean; limits?: ComputeLimits; gpu_profiles?: GpuAutomationProfile[]; removed?: boolean } | null;
	if (automation) {
		const policy = state.flavorAutomationPolicy;
		if (path.endsWith('/policy')) {
			if (method === 'GET') return cloneMockup(policy);
			if (method !== 'PUT') throw new ApiError(405, 'Method not allowed.');
			if (payload?.revision !== policy.revision) throw new ApiError(409, 'Policy revision changed.');
			if (!Array.isArray(payload.gpu_profiles)) throw new ApiError(422, 'GPU profiles must be an array.');
			const profiles = parseGpuProfiles(payload.gpu_profiles.map(row => ({ name: row.name, display_name: row.display_name, enabled: row.enabled, resource_class: row.resource_class, resources: JSON.stringify(row.resource_requirements), specs: JSON.stringify(row.extra_specs), aliases: JSON.stringify(row.alias_resource_classes ?? {}) })));
			if (!profiles) throw new ApiError(422, 'Invalid exact GPU templates.');
			policy.gpu_profiles = profiles; policy.revision++; return cloneMockup(policy);
		}
		if (path.endsWith('/discover')) {
			if (method !== 'POST') throw new ApiError(405, 'Method not allowed.');
			policy.revision++; return cloneMockup(policy); // Synthetic observations never contact Nova or reactivate removed hosts.
		}
		const hostId = path.match(/\/hosts\/([^/]+)$/)?.[1];
		if (hostId) {
			if (method !== 'PUT') throw new ApiError(405, 'Method not allowed.');
			if (payload?.revision !== policy.revision) throw new ApiError(409, 'Policy revision changed.');
			if (typeof payload.removed !== 'boolean') throw new ApiError(422, 'removed must be boolean.');
			const host = policy.hosts.find(row => row.id === decodeURIComponent(hostId));
			if (!host) throw new ApiError(404, 'Host not found.');
			host.removed = payload.removed; policy.revision++; return cloneMockup(policy);
		}
		const current = state.flavorAutomation;
		if (method === 'GET' && !path.endsWith('/reconcile')) return cloneMockup(current);
		if (method === 'PUT' && !path.endsWith('/reconcile')) {
			if (payload?.revision !== current.revision) throw new ApiError(409, 'Policy revision changed.');
			if (typeof payload.enabled !== 'boolean') throw new ApiError(422, 'enabled must be boolean.');
			current.revision++; current.enabled = payload.enabled; current.status = current.enabled ? 'idle' : 'disabled';
			return cloneMockup(current);
		}
		if (method === 'POST' && path.endsWith('/reconcile')) {
			if (!current.enabled) throw new ApiError(409, 'Automation is disabled.');
			current.last_run = new Date().toISOString(); current.status = 'complete'; current.error = null;
			return cloneMockup(current);
		}
		throw new ApiError(405, 'Method not allowed.');
	}
	const domain = admin ? decodeURIComponent(admin[1]) : 'mock-domain';
	if (domain !== 'mock-domain' && !state.admin.domains.some(row => row.domain_id === domain)) throw new ApiError(404, 'Domain not found.');
	const projectId = admin?.[2] ? decodeURIComponent(admin[2]) : iam?.[1] ? decodeURIComponent(iam[1]) : '';
	const pool = state.computePools[domain] ??= {
		domain_id: domain, state: 'unmanaged', revision: 0, enabled: false,
		limits: { CPU: 64, MEMORY_MB: 262144 }, project_limits: {},
		usage: { CPU: 12, MEMORY_MB: 24576 },
		available: { CPU: 52, MEMORY_MB: 237568 },
		projects: state.projects.map(row => ({ id: row.id, name: row.name, enabled: true })),
		policy_ready: true, control_scope: 'afterglow', gpu_profiles: []
	} satisfies ComputePool;
	pool.gpu_profiles = state.flavorAutomationPolicy.gpu_profiles.filter(row => row.enabled);
	const approved = new Set(pool.gpu_profiles.map(row => row.resource_class));
	const configuredResources = new Set([...Object.keys(pool.limits), ...Object.values(pool.project_limits).flatMap(Object.keys)]);
	pool.policy_ready = [...configuredResources].every(rc => rc === 'CPU' || rc === 'MEMORY_MB' || approved.has(rc));
	if (method === 'GET' && !projectId) return cloneMockup(pool);
	if (!pool.policy_ready) throw new ApiError(409, 'Afterglow policy unavailable');
	const revision = method === 'DELETE' ? Number(query.get('revision')) : payload?.revision;
	if (revision !== pool.revision) throw new ApiError(409, 'Policy revision changed.');
    if (projectId && !pool.projects.some(row => row.id === projectId && (method === 'DELETE' || row.enabled))) throw new ApiError(404, 'Project not found in this domain.');
	if (method === 'DELETE' && projectId) delete pool.project_limits[projectId];
	else if (method === 'PUT') {
        if (!payload?.limits || Object.entries(payload.limits).some(([key, value]) => !/^(CPU|MEMORY_MB|CUSTOM_PCI_[0-9A-F]{4}_[0-9A-F]{4})$/.test(key) || !Number.isSafeInteger(value) || value < -1 || value > 2_147_483_647)) throw new ApiError(422, 'Invalid compute limits.');
		if (Object.keys(payload.limits).some(rc => rc !== 'CPU' && rc !== 'MEMORY_MB' && !approved.has(rc))) throw new ApiError(409, 'compute_pool_gpu_alias_unverified');
		if (projectId) {
			if (pool.state === 'unmanaged') throw new ApiError(409, 'The domain pool is not configured.');
			if (Object.entries(payload.limits).some(([key, value]) => computePoolLimit(pool.limits, key) !== -1 && (value === -1 || value > computePoolLimit(pool.limits, key)))) throw new ApiError(409, 'Project ceiling exceeds domain pool.');
			pool.project_limits[projectId] = { ...payload.limits };
		} else {
			if (!admin || typeof payload.enabled !== 'boolean') throw new ApiError(403, 'Only system administrators may edit domain limits.');
			if (Object.values(pool.project_limits).some(caps => Object.entries(caps).some(([key, value]) => computePoolLimit(payload.limits!, key) !== -1 && (value === -1 || value > computePoolLimit(payload.limits!, key))))) throw new ApiError(409, 'Existing project ceiling exceeds domain pool.');
			pool.enabled = payload.enabled; pool.state = payload.enabled ? 'active' : 'paused'; pool.limits = { ...payload.limits };
		}
	} else throw new ApiError(405, 'Method not allowed.');
	pool.revision++;
	pool.available = Object.fromEntries([...new Set(['CPU', 'MEMORY_MB', ...Object.keys(pool.limits)])].map(key => { const limit = computePoolLimit(pool.limits, key); return [key, limit === -1 ? -1 : Math.max(0, limit - (pool.usage[key] ?? 0))]; }));
	return cloneMockup(pool);
}
