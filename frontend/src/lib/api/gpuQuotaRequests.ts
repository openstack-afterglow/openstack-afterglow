import { api } from './client';
import type { ComputeAuthority } from './computePools';

export type GpuQuotaRequestStatus = 'pending' | 'fulfilled' | 'rejected';
export type GpuQuotaRequestFilter = GpuQuotaRequestStatus | 'all';
export interface GpuQuotaRequest {
	id: string;
	domain_id: string;
	project_id: string;
	requester_id: string;
	gpu_profile_name: string;
	resource_class: string;
	additional: number;
	baseline_limit: number;
	target_limit: number;
	pool_revision: number;
	reason: string;
	status: GpuQuotaRequestStatus;
	created_at: string;
	reviewer_id: string | null;
	reviewed_at: string | null;
	note: string;
}
export interface GpuQuotaRequestPage { items: GpuQuotaRequest[]; next_cursor: string | null }
export interface GpuQuotaRequestCreate { project_id: string; resource_class: string; additional: number; reason: string }

export function gpuQuotaRequests(adminMode: boolean, authority: ComputeAuthority) {
	const root = `/api/v1/${adminMode ? 'admin' : 'iam'}/gpu-quota-requests`;
	const guard = (write = false) => {
		if (!authority.isCurrent() || (write && !authority.canSubmit())) throw new DOMException('', 'AbortError');
	};
	const dispatch = async <T>(send: () => Promise<T>, write = false): Promise<T> => {
		guard(write);
		try { const result = await send(); guard(); return result; }
		catch (cause) { guard(); throw cause; }
	};
	const options = { replayOnUnauthorized: false, beforeDispatch: () => guard(true) };
	return {
		list: (status: GpuQuotaRequestFilter, cursor?: string) => dispatch(() => api.get<GpuQuotaRequestPage>(`${root}?status=${status}${cursor === undefined ? '' : `&cursor=${encodeURIComponent(cursor)}`}`, authority.token(), authority.projectId(), { cache: 'no-store' })),
		create: (body: GpuQuotaRequestCreate) => {
			if (adminMode) return Promise.reject<GpuQuotaRequest>(new DOMException('', 'AbortError'));
			return dispatch(() => api.post<GpuQuotaRequest>(root, body, authority.token(), authority.projectId(), options), true);
		},
		resolve: (id: string, status: Exclude<GpuQuotaRequestStatus, 'pending'>, note: string) => {
			if (!adminMode) return Promise.reject<GpuQuotaRequest>(new DOMException('', 'AbortError'));
			return dispatch(() => api.post<GpuQuotaRequest>(`${root}/${encodeURIComponent(id)}/resolve`, { status, note }, authority.token(), authority.projectId(), options), true);
		},
	};
}
