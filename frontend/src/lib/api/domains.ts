import { api } from './client';

export interface AdminDomain {
  id: string;
  name: string;
  enabled: boolean;
  description?: string | null;
}
export interface DomainDraft { name: string; description: string; enabled: boolean }
export interface AdminAuthority { token?: string; projectId?: string }
export type ObservationState = 'ready' | 'partial' | 'unavailable' | 'disabled' | 'denied' | 'unlimited';
export type DomainWindow = '24h' | '7d' | '30d';
export interface DomainMonitoring {
  domain: AdminDomain;
  directory: { users: number; projects: number };
  resources: Array<{ service: string; metric: string; kind: 'count' | 'utilization' | 'allocation'; value: number | null; unit: string; status: ObservationState; error?: string }>;
  requests: { state: ObservationState; window: DomainWindow; total: number | null; errors: number | null; services: Array<{ service: string; requests: number; errors: number }>; timeline: Array<{ at: string; requests: number; errors: number }> | null };
  logins: { state: ObservationState; successes: number | null; recorded_failures: number | null; failure_history: 'not_collected'; timeline: Array<{ at: string; successes: number; recorded_failures: number }> | null };
  sessions: { state: ObservationState; valid_count: number | null; observed_recent_count: number | null; unattributed_count: number | null; online_count: null };
  activity: { state: ObservationState; recent_users: number | null; events: number | null; last_seen: string | null; hour_distribution: Array<{ hour: number; events: number }> | null };
  coverage: { window: DomainWindow; observed_at: string; partial: boolean; notes: string[] };
}
export interface DomainManager {
  user_id: string; user_name: string; user_domain_id: string | null; role_id: string; role_name: string;
}
export interface DomainManagers { items: DomainManager[]; roles: Array<{ id: string; name: string; grantable: boolean }> }
export function domainPath(path: string, domainId: string): string {
  const [pathname, query = ''] = path.split('?');
  const params = new URLSearchParams(query);
  params.set('domain_id', domainId);
  return `${pathname}?${params}`;
}
export const domainsApi = {
  list: ({ token, projectId }: AdminAuthority) => api.get<{ items: AdminDomain[] }>('/api/v1/admin/domains', token, projectId),
  create: (draft: DomainDraft, { token, projectId }: AdminAuthority) => api.post<AdminDomain>('/api/v1/admin/domains', draft, token, projectId),
  update: (id: string, draft: DomainDraft, { token, projectId }: AdminAuthority) => api.patch<AdminDomain>(`/api/v1/admin/domains/${encodeURIComponent(id)}`, draft, token, projectId),
  monitoring: (id: string, window: DomainWindow, { token, projectId }: AdminAuthority) => api.get<DomainMonitoring>(`/api/v1/admin/domains/${encodeURIComponent(id)}/monitoring?window=${window}`, token, projectId),
  managers: (id: string, { token, projectId }: AdminAuthority) => api.get<DomainManagers>(`/api/v1/admin/domains/${encodeURIComponent(id)}/managers`, token, projectId),
  grantManager: (id: string, user_id: string, role_id: string, { token, projectId }: AdminAuthority) => api.post<DomainManagers>(`/api/v1/admin/domains/${encodeURIComponent(id)}/managers`, { user_id, role_id }, token, projectId),
  revokeManager: (id: string, user_id: string, role_id: string, { token, projectId }: AdminAuthority) => api.delete<void>(`/api/v1/admin/domains/${encodeURIComponent(id)}/managers?${new URLSearchParams({ user_id, role_id })}`, token, projectId),
};
