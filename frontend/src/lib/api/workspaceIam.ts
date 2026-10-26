import { api } from './client';
import type { IamSession } from './domainIam';
import type { DomainMonitoring, AdminDomain } from './domains';

export const quotaFields = {
	compute: ['instances', 'cores', 'ram', 'key_pairs', 'server_groups', 'server_group_members', 'injected_files', 'injected_file_content_bytes', 'injected_file_path_bytes', 'metadata_items'],
	volume: ['volumes', 'snapshots', 'gigabytes'],
	network: ['network', 'subnet', 'port', 'router', 'floatingip', 'security_group', 'security_group_rule'],
	file_storage: ['shares', 'share_gigabytes', 'share_snapshots', 'share_snapshot_gigabytes', 'share_networks', 'share_groups', 'share_group_snapshots']
} as const;
export type QuotaSection = keyof typeof quotaFields;
export type QuotaField = (typeof quotaFields)[QuotaSection][number];
export type QuotaMap = Partial<Record<QuotaField, number>>;
export interface QuotaEntry { limit: number; in_use: number; reserved?: number }
export interface ProjectQuotas {
	project_id: string;
	compute: Record<string, QuotaEntry> | null;
	volume: Record<string, QuotaEntry> | null;
	network: Record<string, QuotaEntry> | null;
	file_storage: Record<string, QuotaEntry> | null;
	availability: Partial<Record<QuotaSection, boolean>>;
	errors: Partial<Record<QuotaSection, string>>;
}
export interface QuotaOperation {
	id: string; project_id: string; status: string; requested: QuotaMap; created_at: string;
	sections: Record<string, { status: string; error?: string; observed?: Record<string, number> }>;
}
export interface DomainBudgets {
	domain_id: string; revision: number; ceilings: QuotaMap; defaults: QuotaMap;
	enforcement_scope: 'afterglow_project_allocations'; defaults_future_only: boolean; drift: boolean;
	allocations: Partial<Record<QuotaField, { limit: number | null; status: string; error?: string; within_budget: boolean | null }>>;
	projects: Array<{ id: string; name: string; enabled: boolean }>;
	operations: QuotaOperation[];
	allocation_blocked: boolean; blocking_operation_id: string | null;
}
export interface QuotaResult { domain_id: string; project_id: string; operation_id: string | null; status: string; updated: string[]; errors: Record<string, string> }
export type WorkspaceMetric = DomainMonitoring['resources'][number];
export interface IamResourceWorkspace {
	domain: AdminDomain;
	projects: Array<{ id: string; name: string; enabled: boolean; resources: WorkspaceMetric[]; quotas: ProjectQuotas }>;
	users: Array<{ id: string; name: string; domain_id: string; enabled: boolean; project_ids: string[]; membership_state: string; resources: WorkspaceMetric[] }>;
	resources: WorkspaceMetric[];
	inventory: Array<{ category: string; id: string | null; name: string; project_id: string; user_id: string | null; status: string | null }>;
	coverage: { observed_at: string; partial: boolean; notes: string[] };
}
export interface DomainForecast {
	domain_id: string; observed_at: string; window_days: number; horizon_days: number; source: string;
	entries: Array<{
		metric: string; unit: string; status: string; error: string | null; current: number | null; limit: number | null;
		trend: { current_pct: number | null; slope_per_day: number | null; projected_pct: number | null; days_to_limit: number | null; trend_available: boolean; series: number[] } | null;
	}>;
}
export const quotaBlocked = (snapshot: DomainBudgets) => snapshot.allocation_blocked || snapshot.operations.some(operation => ['applying', 'unknown'].includes(operation.status));
export function nativeQuotaKey(field: QuotaField): string {
	return ({ share_gigabytes: 'gigabytes', share_snapshots: 'snapshots', share_snapshot_gigabytes: 'snapshot_gigabytes' } as Partial<Record<QuotaField, string>>)[field] ?? field;
}

// The console owns revalidation. These fences also cover the interval before unmount.
export function workspaceIam(session: IamSession) {
	const dispatch = async <T>(send: () => Promise<T>, mutation = false): Promise<T> => {
		if (!session.isCurrent() || (mutation && !session.canSubmit())) throw new DOMException('', 'AbortError');
		try {
			const result = await send();
			if (!session.isCurrent()) throw new DOMException('', 'AbortError');
			return result;
		} catch (cause) {
			if (!session.isCurrent()) throw new DOMException('', 'AbortError');
			throw cause;
		}
	};
	const root = '/api/v1/iam';
	return {
		budgets: () => dispatch(() => api.get<DomainBudgets>(root + '/quotas', session.token(), undefined, { cache: 'no-store' })),
		resources: () => dispatch(() => api.get<IamResourceWorkspace>(root + '/monitoring', session.token(), undefined, { cache: 'no-store' })),
		forecast: () => dispatch(() => api.get<DomainForecast>(root + '/monitoring/forecast', session.token(), undefined, { cache: 'no-store' })),
		defaults: (revision: number, defaults: QuotaMap) => dispatch(() => api.put<DomainBudgets>(root + '/quotas/defaults', { revision, defaults }, session.token(), undefined, { replayOnUnauthorized: false }), true),
		project: (projectId: string) => dispatch(() => api.get<ProjectQuotas>(`${root}/projects/${encodeURIComponent(projectId)}/quotas`, session.token(), undefined, { cache: 'no-store' })),
		saveProject: (projectId: string, limits: QuotaMap) => dispatch(() => api.put<QuotaResult>(`${root}/projects/${encodeURIComponent(projectId)}/quotas`, limits, session.token(), undefined, { replayOnUnauthorized: false }), true)
	};
}

export interface BudgetAuthority { token: () => string; projectId: () => string | undefined; isCurrent: () => boolean }
export function adminDomainBudgets(domainId: string, authority: BudgetAuthority) {
	const path = `/api/v1/admin/domains/${encodeURIComponent(domainId)}/quotas`;
	const dispatch = async <T>(send: () => Promise<T>): Promise<T> => {
		if (!authority.isCurrent()) throw new DOMException('', 'AbortError');
		try {
			const result = await send();
			if (!authority.isCurrent()) throw new DOMException('', 'AbortError');
			return result;
		} catch (cause) {
			if (!authority.isCurrent()) throw new DOMException('', 'AbortError');
			throw cause;
		}
	};
	return {
		load: () => dispatch(() => api.get<DomainBudgets>(path, authority.token(), authority.projectId(), { refresh: true })),
		save: (revision: number, ceilings: QuotaMap) => dispatch(() => api.put<DomainBudgets>(path, { revision, ceilings }, authority.token(), authority.projectId(), { replayOnUnauthorized: false })),
		reconcile: (operationId: string) => dispatch(() => api.post<DomainBudgets>(`${path}/operations/${encodeURIComponent(operationId)}/reconcile`, { native_calls_settled: true }, authority.token(), authority.projectId(), { replayOnUnauthorized: false }))
	};
}
