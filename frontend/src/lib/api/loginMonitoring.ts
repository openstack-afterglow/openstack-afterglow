import { fetchWithAuth } from '$lib/api/client';
import { ApiError } from '$lib/api/errors';
import type { MonitoringAuthority } from '$lib/types/loginMonitoring';

/** Raw response ownership preserves native directory denial without platform-admin demotion. */
export async function monitoringRequest<T>(path: string, authority: MonitoringAuthority): Promise<T> {
  const response = await fetchWithAuth(path, { cache: 'no-store', credentials: 'include', signal: AbortSignal.timeout(30_000) }, authority.token, authority.projectId);
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    const code = typeof data?.detail === 'string' && /^login_monitoring_[a-z_]+$/.test(data.detail)
      ? data.detail : response.status === 403 ? 'login_monitoring_admin_denied' : 'login_monitoring_unavailable';
    throw new ApiError(response.status, code, code);
  }
  return response.json();
}
