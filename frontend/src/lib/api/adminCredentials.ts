import { fetchWithAuth } from '$lib/api/client';
import { ApiError } from '$lib/api/errors';
import type { CredentialAuthority } from '$lib/types/adminCredential';

/** Bypass the ordinary GET cache: even explicit sensitive details stay ephemeral.
 * Native Keystone 403 is not evidence that platform system-admin was revoked.
 */
export async function credentialRequest<T>(path: string, authority: CredentialAuthority, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetchWithAuth(path, {
    method, cache: 'no-store', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(30_000),
  }, authority.token, authority.projectId);
  if (!response.ok) {
    // Do not display arbitrary upstream error payloads in a sensitive surface.
    const data = await response.json().catch(() => null);
    const code = typeof data?.detail === 'string' && /^credential_[a-z_]+$/.test(data.detail)
      ? data.detail : response.status === 403 ? 'credential_admin_denied' : 'credential_unavailable';
    throw new ApiError(response.status, code, code);
  }
  return response.status === 204 ? undefined as T : response.json();
}
