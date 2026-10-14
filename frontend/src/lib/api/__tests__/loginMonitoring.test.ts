import { beforeEach, describe, expect, it, vi } from 'vitest';
import { monitoringRequest } from '../loginMonitoring';

const { fetchWithAuth } = vi.hoisted(() => ({ fetchWithAuth: vi.fn() }));
vi.mock('$lib/api/client', () => ({ fetchWithAuth }));
const authority = { token: 'token-a', userId: 'actor', projectId: 'project-a', admin: true, ready: true };
beforeEach(() => fetchWithAuth.mockReset());

describe('monitoring HTTP boundary', () => {
  it('uses no-store with the captured actor/project and returns only the server result', async () => {
    fetchWithAuth.mockResolvedValue(new Response(JSON.stringify({ user: { id: 'selected' } }), { status: 200 }));
    expect(await monitoringRequest('/api/v1/admin/monitoring/logins/users/selected', authority)).toEqual({ user: { id: 'selected' } });
    expect(fetchWithAuth).toHaveBeenCalledWith('/api/v1/admin/monitoring/logins/users/selected', expect.objectContaining({ cache: 'no-store', credentials: 'include' }), 'token-a', 'project-a');
  });
  it('preserves native-denied separately from platform-admin denied', async () => {
    fetchWithAuth.mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'login_monitoring_native_denied' }), { status: 403 }));
    await expect(monitoringRequest('/api/v1/admin/monitoring/logins/users', authority)).rejects.toMatchObject({ status: 403, code: 'login_monitoring_native_denied' });
    fetchWithAuth.mockResolvedValueOnce(new Response(JSON.stringify({ detail: '관리자 권한이 필요합니다' }), { status: 403 }));
    await expect(monitoringRequest('/api/v1/admin/monitoring/logins/users', authority)).rejects.toMatchObject({ code: 'login_monitoring_admin_denied' });
    expect(authority.admin).toBe(true);
  });
  it('does not display arbitrary provider errors or interpret outage as empty data', async () => {
    fetchWithAuth.mockResolvedValue(new Response(JSON.stringify({ detail: 'token=private-provider-detail' }), { status: 503 }));
    await expect(monitoringRequest('/api/v1/admin/monitoring/logins/users/selected', authority)).rejects.toMatchObject({ code: 'login_monitoring_unavailable', message: 'login_monitoring_unavailable' });
  });
});
