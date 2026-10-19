import { beforeEach, describe, expect, it, vi } from 'vitest';
import { credentialRequest } from '../adminCredentials';
const { fetchAuth } = vi.hoisted(() => ({ fetchAuth: vi.fn() }));
vi.mock('$lib/api/client', () => ({ fetchWithAuth: fetchAuth }));
const authority = { token: 'caller-token', userId: 'caller', projectId: 'project', admin: true, ready: true };
const domainId = 'selected-domain';
beforeEach(() => fetchAuth.mockReset());

describe('sensitive credential transport', () => {
  it('fetches explicit blob details anew, preserving filters and overriding stale domain query values', async () => {
    fetchAuth.mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ id: 'credential', blob: 'sensitive' }), { status: 200 })));
    const path = '/api/v1/admin/user-credentials/credential?sensitive=true&domain_id=old-domain';
    const first = await credentialRequest(path, domainId, authority);
    const second = await credentialRequest(path, domainId, authority);
    expect(first).toEqual(second); expect(fetchAuth).toHaveBeenCalledTimes(2);
    for (const [url, options, token, project] of fetchAuth.mock.calls) {
      const query = new URL(url, 'https://afterglow.test').searchParams;
      expect(query.getAll('domain_id')).toEqual([domainId]); expect(query.get('sensitive')).toBe('true');
      expect(options.cache).toBe('no-store'); expect(token).toBe('caller-token'); expect(project).toBe('project');
    }
  });
  it('refuses an absent domain before transport rather than falling back to the caller domain', async () => {
    await expect(credentialRequest('/api/v1/admin/user-credentials', '', authority)).rejects.toMatchObject({ code: 'credential_scope_denied' });
    await expect(credentialRequest('/api/v1/admin/users?limit=100', '  ', authority)).rejects.toMatchObject({ code: 'credential_scope_denied' });
    expect(fetchAuth).not.toHaveBeenCalled();
  });
  it('preserves native denial separately without displaying arbitrary upstream content', async () => {
    fetchAuth.mockResolvedValue(new Response(JSON.stringify({ detail: 'credential_native_denied' }), { status: 403 }));
    await expect(credentialRequest('/api/v1/admin/user-credentials', domainId, authority)).rejects.toMatchObject({ status: 403, code: 'credential_native_denied' });
    fetchAuth.mockResolvedValue(new Response(JSON.stringify({ detail: 'provider-secret-or-token' }), { status: 503 }));
    await expect(credentialRequest('/api/v1/admin/user-credentials', domainId, authority)).rejects.toMatchObject({ status: 503, message: 'credential_unavailable' });
  });
  it('does not infer platform-admin revocation from an unclassified native 403', async () => {
    fetchAuth.mockResolvedValue(new Response('Forbidden', { status: 403 }));
    await expect(credentialRequest('/api/v1/admin/users', domainId, authority)).rejects.toMatchObject({ status: 403, code: 'credential_native_denied' });
  });
  it('scopes delete and patch without reading a delete body or altering native JSON string blobs', async () => {
    fetchAuth.mockResolvedValue(new Response(null, { status: 204 }));
    expect(await credentialRequest('/api/v1/admin/user-credentials/id', domainId, authority, 'DELETE')).toBeUndefined();
    fetchAuth.mockResolvedValue(new Response('{}', { status: 200 }));
    await credentialRequest('/api/v1/admin/user-credentials/id', domainId, authority, 'PATCH', { blob: '{"access":"a","secret":"s"}' });
    const last = fetchAuth.mock.calls.at(-1)!;
    expect(JSON.parse(last[1].body).blob).toBe('{"access":"a","secret":"s"}');
    for (const [url] of fetchAuth.mock.calls) expect(new URL(url, 'https://afterglow.test').searchParams.get('domain_id')).toBe(domainId);
  });
});
