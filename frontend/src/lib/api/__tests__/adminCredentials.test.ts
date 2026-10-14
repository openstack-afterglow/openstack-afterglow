import { beforeEach, describe, expect, it, vi } from 'vitest';
import { credentialRequest } from '../adminCredentials';
const { fetchAuth } = vi.hoisted(() => ({ fetchAuth: vi.fn() }));
vi.mock('$lib/api/client', () => ({ fetchWithAuth: fetchAuth }));
const authority = { token: 'caller-token', userId: 'caller', projectId: 'project', admin: true, ready: true };
beforeEach(() => fetchAuth.mockReset());

describe('sensitive credential transport', () => {
  it('fetches explicit blob details anew and never uses an ordinary cached GET', async () => {
    fetchAuth.mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ id: 'credential', blob: 'sensitive' }), { status: 200 })));
    const first = await credentialRequest('/api/v1/admin/user-credentials/credential?sensitive=true', authority);
    const second = await credentialRequest('/api/v1/admin/user-credentials/credential?sensitive=true', authority);
    expect(first).toEqual(second); expect(fetchAuth).toHaveBeenCalledTimes(2);
    for (const [, options, token, project] of fetchAuth.mock.calls) {
      expect(options.cache).toBe('no-store'); expect(token).toBe('caller-token'); expect(project).toBe('project');
    }
  });
  it('preserves native denied separately without displaying arbitrary upstream content', async () => {
    fetchAuth.mockResolvedValue(new Response(JSON.stringify({ detail: 'credential_native_denied' }), { status: 403 }));
    await expect(credentialRequest('/api/v1/admin/user-credentials', authority)).rejects.toMatchObject({ status: 403, code: 'credential_native_denied' });
    fetchAuth.mockResolvedValue(new Response(JSON.stringify({ detail: 'provider-secret-or-token' }), { status: 503 }));
    await expect(credentialRequest('/api/v1/admin/user-credentials', authority)).rejects.toMatchObject({ status: 503, message: 'credential_unavailable' });
  });
  it('does not read a delete response body and sends native JSON string blobs unchanged', async () => {
    fetchAuth.mockResolvedValue(new Response(null, { status: 204 }));
    expect(await credentialRequest('/api/v1/admin/user-credentials/id', authority, 'DELETE')).toBeUndefined();
    fetchAuth.mockResolvedValue(new Response('{}', { status: 200 }));
    await credentialRequest('/api/v1/admin/user-credentials/id', authority, 'PATCH', { blob: '{"access":"a","secret":"s"}' });
    const last = fetchAuth.mock.calls.at(-1)!;
    expect(JSON.parse(last[1].body).blob).toBe('{"access":"a","secret":"s"}');
  });
});
