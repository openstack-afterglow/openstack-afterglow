import { fetchWithAuth } from './client';
import { ApiError } from './errors';
import type { InfrastructureTopologySnapshot, TopologyAuthority, TopologyTrace } from '$lib/types/infrastructureTopology';
import type { ExperienceContext } from '$lib/utils/experience';

const base = '/api/v1/admin/infrastructure-topology';
async function request<T>(path: string, authority: TopologyAuthority, signal: AbortSignal, body?: unknown, experience?: ExperienceContext): Promise<T> {
	const response = await fetchWithAuth(path, {
		method: body === undefined ? 'GET' : 'POST',
		cache: 'no-store', credentials: 'include',
		headers: { 'Content-Type': 'application/json' },
		body: body === undefined ? undefined : JSON.stringify(body),
		signal: AbortSignal.any([signal, AbortSignal.timeout(30_000)]),
	}, authority.token, authority.projectId, { experience });
	if (!response.ok) {
		const data = await response.json().catch(() => null);
		const detail = typeof data?.detail === 'string' ? data.detail : '';
		const code = /^(trace|topology|observer)_[a-z_]+$/.test(detail) ? detail : 'topology_request_failed';
		throw new ApiError(response.status, code, code);
	}
	return response.json();
}
export function getInfrastructureTopology(authority: TopologyAuthority, signal: AbortSignal, experience?: ExperienceContext) {
	return request<InfrastructureTopologySnapshot>(base, authority, signal, undefined, experience);
}
export function submitInfrastructureTrace(hostId: string, target: string, authority: TopologyAuthority, signal: AbortSignal, experience?: ExperienceContext) {
	return request<Omit<TopologyTrace, 'result'>>(`${base}/hosts/${encodeURIComponent(hostId)}/traces`, authority, signal, { target }, experience);
}
