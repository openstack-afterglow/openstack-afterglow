import { webcrypto } from 'node:crypto';
import { get } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { HubFilters, HubLayer } from '../palimpsestHub';

vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
const fetchMock = vi.fn();
const identity = { token: 'browser-jwt-original', projectId: 'project-original', userId: 'user-original' };
const abcDigest = 'sha256:ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad';
const bytes = new Uint8Array([97, 98, 99]);
const layer: HubLayer = {
  blob_digest: abcDigest, blob_md5: null, size_bytes: 3, media_type: 'application/vnd.palimpsest.layer.squashfs',
  disk_format: null, arch: 'x86_64', os_variant: null, config_digest: `sha256:${'1'.repeat(64)}`,
  chain_id: null, parent_digest: null, base_image_digest: null, name: 'python+cpu', kind: 'squashfs',
  ubuntu_base: null, python_version: '3.13', config_json: {}, project_id: null,
  is_published: true, created_by: null, created_at: null,
};
const me = {
  user_id: identity.userId, project_id: identity.projectId, project_name: 'Original project', roles: ['member'],
  is_system_admin: false, capabilities: { inventory: true, download: true, upload: false, delete: false, build: false },
};
const signal = () => new AbortController().signal;

beforeEach(() => {
  vi.resetModules();
  localStorage.clear();
  sessionStorage.clear();
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
  vi.stubGlobal('crypto', webcrypto);
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

async function consumer() {
  const store = await import('$lib/stores/auth');
  // Real shared transport and auth stores; only the browser's fetch is mocked.
  // No refresh clock or random session ID is involved in these requests.
  store.auth.set({ ...get(store.auth), token: identity.token, userId: identity.userId,
    projectId: identity.projectId, domainId: 'domain-original', sessionId: 'session-original',
    refreshToken: null, accessExpiresAt: null });
  return { ...await import('../palimpsestHub'), ...store };
}
function urlOfCall(index = 0): URL { return new URL(fetchMock.mock.calls[index][0], 'https://afterglow.example'); }
function blobResponse(chunks: Uint8Array[] = [bytes], headers: HeadersInit = {}): Response {
  return new Response(new ReadableStream<Uint8Array>({
    start(controller) { for (const chunk of chunks) controller.enqueue(chunk); controller.close(); },
  }), { status: 200, headers });
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

describe('Hub GET consumer boundary', () => {
  it('forwards the original JWT/project in headers, uses strict request options, and never puts tokens in URLs', async () => {
    const { hubApi } = await consumer();
    fetchMock.mockResolvedValueOnce(Response.json(me));
    expect(await hubApi.me(identity, signal())).toEqual(me);
    const [url, options] = fetchMock.mock.calls[0];
    expect(urlOfCall().pathname).toBe('/api/v1/palimpsest/hub/me');
    expect(url).not.toContain(identity.token);
    expect(urlOfCall().search).toBe('');
    expect(new Headers(options.headers).get('authorization')).toBe(`Bearer ${identity.token}`);
    expect(new Headers(options.headers).get('x-project-id')).toBe(identity.projectId);
    expect(options).toMatchObject({ method: 'GET', credentials: 'include', redirect: 'error', cache: 'no-store' });
    expect(options.signal.aborted).toBe(false);
  });

  it('preserves a native 403 denial instead of substituting inventory or credentials', async () => {
    const { hubApi } = await consumer();
    fetchMock.mockResolvedValueOnce(Response.json({ detail: 'Original actor denied' }, { status: 403 }));
    await expect(hubApi.layers(identity, signal())).rejects.toMatchObject({ status: 403, message: 'Original actor denied' });
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it.each([
    { ...me, user_id: 'foreign-user' }, { ...me, project_id: 'foreign-project' },
    { ...me, capabilities: { ...me.capabilities, download: 'true' } },
  ])('rejects a mismatched or malformed me response', async (body) => {
    const { hubApi } = await consumer();
    fetchMock.mockResolvedValueOnce(Response.json(body));
    await expect(hubApi.me(identity, signal())).rejects.toMatchObject({ code: 'response' });
  });

  it('requests one lookahead row and preserves shared/public native visibility without inventing a total', async () => {
    const { hubApi, HUB_PAGE_SIZE } = await consumer();
    const rows = Array.from({ length: 51 }, () => ({ ...layer, project_id: 'shared-project' }));
    fetchMock.mockResolvedValueOnce(Response.json(rows));
    const result = await hubApi.layers(identity, signal(), {}, 50);
    expect(result).toEqual(rows);
    expect(HUB_PAGE_SIZE).toBe(50);
    expect(urlOfCall().searchParams.get('limit')).toBe('51');
    expect(urlOfCall().searchParams.get('offset')).toBe('50');
    expect(result).not.toHaveProperty('total');
  });

  it('encodes exact names and canonical hex-prefix filters without substring or query injection', async () => {
    const { hubApi } = await consumer();
    fetchMock.mockResolvedValueOnce(Response.json([]));
    await hubApi.layers(identity, signal(), { name: 'python+cpu', digest_prefix: ' SHA256:ABCD ',
      kind: 'cloud-image', arch: 'aarch64', disk_format: 'qcow2' });
    const params = urlOfCall().searchParams;
    expect(params.get('name')).toBe('python+cpu');
    expect(params.get('digest_prefix')).toBe('abcd');
    expect(params.get('kind')).toBe('cloud-image');
    expect(params.get('arch')).toBe('aarch64');
    expect(params.get('disk_format')).toBe('qcow2');
    expect(urlOfCall().search).toContain('name=python%2Bcpu');
    expect(params.has('q')).toBe(false);
  });

  it.each([
    { name: 'partial*' }, { name: 'name&limit=2000' }, { name: 'contains space' }, { name: '' }, { name: 'a'.repeat(65) },
    { digest_prefix: 'abc' }, { digest_prefix: 'abcdz' }, { digest_prefix: 'a'.repeat(65) },
    { kind: 'unknown' }, { arch: 'amd64' }, { disk_format: 'iso' },
  ])('rejects unsupported filters before sending (%j)', async (filters) => {
    const { hubApi } = await consumer();
    await expect(async () => hubApi.layers(identity, signal(), filters as HubFilters)).rejects.toMatchObject({ code: 'query' });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each([[-1, 51], [0.5, 51], [Number.MAX_SAFE_INTEGER, 51], [0, 0], [0, 201], [0, 1.5], [NaN, 51]])(
    'rejects pagination offset=%s limit=%s before sending', async (offset, limit) => {
      const { hubApi } = await consumer();
      await expect(async () => hubApi.layers(identity, signal(), {}, offset, limit)).rejects.toMatchObject({ code: 'query' });
      expect(fetchMock).not.toHaveBeenCalled();
    });

  it('permits the native limit boundary 200 and rejects a response exceeding requested lookahead', async () => {
    const { hubApi } = await consumer();
    fetchMock.mockResolvedValueOnce(Response.json([]));
    await hubApi.layers(identity, signal(), {}, 200, 200);
    expect(urlOfCall().searchParams.get('limit')).toBe('200');
    fetchMock.mockResolvedValueOnce(Response.json(Array.from({ length: 52 }, () => layer)));
    await expect(hubApi.layers(identity, signal())).rejects.toMatchObject({ code: 'response' });
  });

  it('uses encoded canonical digests for detail/ancestors and returns the native root-to-self array', async () => {
    const { hubApi } = await consumer();
    const detail = { ...layer, ancestors: [], chain_complete: true };
    fetchMock.mockResolvedValueOnce(Response.json(detail));
    expect(await hubApi.detail(identity, signal(), abcDigest)).toEqual(detail);
    expect(fetchMock.mock.calls[0][0]).toContain(`/layers/${encodeURIComponent(abcDigest)}`);
    fetchMock.mockResolvedValueOnce(Response.json([layer]));
    expect(await hubApi.ancestors(identity, signal(), abcDigest)).toEqual([layer]);
    expect(urlOfCall(1).pathname).toContain('/ancestors');
    await expect(async () => hubApi.ancestors(identity, signal(), 'sha256:abcd/../me')).rejects.toMatchObject({ code: 'response' });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('uses native builds and image-export schemas and independently requests only recent 20', async () => {
    const { hubApi } = await consumer();
    const build = { id: 'b1', name: 'image', recipe_digest: abcDigest, base_digest: abcDigest,
      layer_digests: [abcDigest], status: 'complete', output_digest: abcDigest, output_size_bytes: 3,
      error_code: null, created_at: '2026-10-14T00:00:00Z', started_at: null, completed_at: null };
    const exported = { id: 'e1', source_image_id: 'image-1', source_name: 'image', source_disk_format: 'raw',
      source_size_bytes: 3, target_disk_format: 'qcow2', status: 'complete', progress_pct: 100,
      error_code: null, error_message: null, blob_digest: abcDigest, size_bytes: 3, filename: 'image.qcow2',
      download_path: '/hub/image-exports/e1/blob', created_at: '2026-10-14T00:00:00Z', started_at: null, completed_at: null };
    fetchMock.mockResolvedValueOnce(Response.json([build]));
    expect(await hubApi.builds(identity, signal())).toEqual([build]);
    fetchMock.mockResolvedValueOnce(Response.json([exported]));
    expect(await hubApi.exports(identity, signal())).toEqual([exported]);
    expect(urlOfCall().pathname).toBe('/api/v1/palimpsest/hub/builds');
    expect(urlOfCall(1).pathname).toBe('/api/v1/palimpsest/hub/image-exports');
    expect(urlOfCall().search).toBe('?limit=20');
    expect(urlOfCall(1).search).toBe('?limit=20');
    expect(fetchMock).toHaveBeenCalledTimes(2); // download_path was not followed.
  });

  it('rejects an absent/stale original actor before fetch, including changed credentials', async () => {
    const { hubApi, auth } = await consumer();
    await expect(hubApi.me({ ...identity, token: 'old-jwt' }, signal())).rejects.toMatchObject({ name: 'AbortError' });
    auth.update((state) => ({ ...state, userId: null }));
    await expect(hubApi.me(identity, signal())).rejects.toMatchObject({ name: 'AbortError' });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('fences a late response across actor ABA transitions', async () => {
    const { hubApi, auth } = await consumer();
    const pending = deferred<Response>();
    fetchMock.mockReturnValueOnce(pending.promise);
    const request = hubApi.me(identity, signal());
    const rejected = expect(request).rejects.toMatchObject({ name: 'AbortError' });
    const original = get(auth);
    auth.set({ ...original, token: 'other-token', userId: 'other-user' });
    auth.set(original);
    pending.resolve(Response.json(me));
    await rejected;
    expect(fetchMock.mock.calls[0][1].signal.aborted).toBe(true);
    expect(fetchMock).toHaveBeenCalledOnce();
  });
  it.each(['builds', 'exports'] as const)('rejects oversized recent %s responses', async (lane) => {
    const { hubApi } = await consumer();
    fetchMock.mockResolvedValueOnce(Response.json(Array.from({ length: 21 }, () => ({ id: 'job' }))));
    await expect(hubApi[lane](identity, signal())).rejects.toMatchObject({ code: 'response' });
  });

  it('rejects an object envelope where native layers requires an array', async () => {
    const { hubApi } = await consumer();
    fetchMock.mockResolvedValueOnce(Response.json({ items: [layer] }));
    await expect(hubApi.layers(identity, signal())).rejects.toMatchObject({ code: 'response' });
  });
});

describe('explicit bounded layer download', () => {
  it('performs no automatic blob fetch; explicit download returns only length/digest-verified bytes', async () => {
    const { hubApi } = await consumer();
    fetchMock.mockResolvedValueOnce(Response.json({ ...layer, ancestors: [], chain_complete: true }));
    await hubApi.detail(identity, signal(), abcDigest);
    expect(fetchMock).toHaveBeenCalledOnce();
    fetchMock.mockResolvedValueOnce(blobResponse([bytes.subarray(0, 1), bytes.subarray(1)], { 'content-length': '3' }));
    const result = await hubApi.download(identity, signal(), layer);
    expect(result.size).toBe(3);
    expect(result.type).toBe(layer.media_type);
    expect(urlOfCall(1).pathname).toContain('/blob');
    expect(fetchMock.mock.calls[1][0]).not.toContain(identity.token);
  });

  it('verifies streaming bytes even when Content-Length is absent', async () => {
    const { hubApi } = await consumer();
    fetchMock.mockResolvedValueOnce(blobResponse());
    expect((await hubApi.download(identity, signal(), layer)).size).toBe(3);
  });

  it.each([-1, 1.5, NaN, Infinity])('rejects invalid metadata length %s before fetch', async (size) => {
    const { hubApi } = await consumer();
    await expect(hubApi.download(identity, signal(), { ...layer, size_bytes: size })).rejects.toMatchObject({ code: 'length' });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('permits exactly 64 MiB through metadata/header guards (then requires a real stream)', async () => {
    const { hubApi, MAX_HUB_DOWNLOAD_BYTES } = await consumer();
    fetchMock.mockResolvedValueOnce(new Response(null, { headers: { 'content-length': String(MAX_HUB_DOWNLOAD_BYTES) } }));
    await expect(hubApi.download(identity, signal(), { ...layer, size_bytes: MAX_HUB_DOWNLOAD_BYTES })).rejects.toMatchObject({ code: 'unsupported' });
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it('refuses metadata greater than 64 MiB before fetch', async () => {
    const { hubApi, MAX_HUB_DOWNLOAD_BYTES } = await consumer();
    expect(MAX_HUB_DOWNLOAD_BYTES).toBe(64 * 1024 * 1024);
    await expect(hubApi.download(identity, signal(), { ...layer, size_bytes: MAX_HUB_DOWNLOAD_BYTES + 1 })).rejects.toMatchObject({ code: 'too-large' });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('rejects a header exceeding 64 MiB before reading and cancels its body', async () => {
    const { hubApi, MAX_HUB_DOWNLOAD_BYTES } = await consumer();
    const cancel = vi.fn();
    fetchMock.mockResolvedValueOnce(new Response(new ReadableStream({ cancel }), {
      headers: { 'content-length': String(MAX_HUB_DOWNLOAD_BYTES + 1) },
    }));
    await expect(hubApi.download(identity, signal(), layer)).rejects.toMatchObject({ code: 'too-large' });
    expect(cancel).toHaveBeenCalledOnce();
  });

  it.each(['2', '4', '-1', '3.5', 'not-a-length', '9007199254740993'])('rejects invalid/mismatched header %s', async (length) => {
    const { hubApi } = await consumer();
    fetchMock.mockResolvedValueOnce(blobResponse([bytes], { 'content-length': length }));
    await expect(hubApi.download(identity, signal(), layer)).rejects.toMatchObject({ code: 'length' });
  });

  it.each([new Uint8Array([97, 98]), new Uint8Array([97, 98, 99, 100])])('rejects truncated/overlong streaming bytes', async (chunk) => {
    const { hubApi } = await consumer();
    fetchMock.mockResolvedValueOnce(blobResponse([chunk]));
    await expect(hubApi.download(identity, signal(), layer)).rejects.toMatchObject({ code: 'length' });
  });

  it('enforces the stream cap independently of the header and advertised metadata', async () => {
    const { hubApi, MAX_HUB_DOWNLOAD_BYTES } = await consumer();
    fetchMock.mockResolvedValueOnce(blobResponse([new Uint8Array(MAX_HUB_DOWNLOAD_BYTES + 1)]));
    await expect(hubApi.download(identity, signal(), layer)).rejects.toMatchObject({ code: 'too-large' });
  });

  it('rejects equal-length corrupted bytes instead of trusting metadata, MD5 or headers', async () => {
    const { hubApi } = await consumer();
    fetchMock.mockResolvedValueOnce(blobResponse([new Uint8Array([97, 98, 100])], { 'content-length': '3' }));
    await expect(hubApi.download(identity, signal(), layer)).rejects.toMatchObject({ code: 'digest' });
  });

  it('honestly reports unsupported integrity when crypto is unavailable, without fetching unverified bytes', async () => {
    const { hubApi } = await consumer();
    vi.stubGlobal('crypto', undefined);
    await expect(hubApi.download(identity, signal(), layer)).rejects.toMatchObject({ code: 'unsupported' });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('reports unsupported when crypto rejects instead of claiming integrity success', async () => {
    const { hubApi } = await consumer();
    vi.stubGlobal('crypto', { subtle: { digest: vi.fn().mockRejectedValue(new Error('Unavailable')) } });
    fetchMock.mockResolvedValueOnce(blobResponse());
    await expect(hubApi.download(identity, signal(), layer)).rejects.toMatchObject({ code: 'unsupported' });
  });

  it('refuses partial responses and unavailable streaming bodies', async () => {
    const { hubApi } = await consumer();
    fetchMock.mockResolvedValueOnce(new Response(bytes, { status: 206 }));
    await expect(hubApi.download(identity, signal(), layer)).rejects.toMatchObject({ code: 'response' });
    fetchMock.mockResolvedValueOnce(new Response(null));
    await expect(hubApi.download(identity, signal(), layer)).rejects.toMatchObject({ code: 'unsupported' });
  });

  it('aborts a stalled stream, cancels the reader, and returns no Blob', async () => {
    const { hubApi } = await consumer();
    const reading = deferred<void>();
    const cancel = vi.fn();
    fetchMock.mockResolvedValueOnce(new Response(new ReadableStream<Uint8Array>({
      pull() { reading.resolve(); }, cancel,
    }, { highWaterMark: 0 })));
    const controller = new AbortController();
    const request = hubApi.download(identity, controller.signal, layer);
    const rejected = expect(request).rejects.toMatchObject({ name: 'AbortError' });
    await reading.promise;
    controller.abort();
    await rejected;
    expect(cancel).toHaveBeenCalledOnce();
  });

  it('discards bytes when the token rotates during SHA-256 verification', async () => {
    const { hubApi, auth } = await consumer();
    const hashing = deferred<void>();
    const hash = deferred<ArrayBuffer>();
    vi.stubGlobal('crypto', { subtle: { digest: vi.fn(() => { hashing.resolve(); return hash.promise; }) } });
    fetchMock.mockResolvedValueOnce(blobResponse());
    const request = hubApi.download(identity, signal(), layer);
    const rejected = expect(request).rejects.toMatchObject({ name: 'AbortError' });
    await hashing.promise;
    auth.update((state) => ({ ...state, token: 'rotated-jwt' }));
    hash.resolve(await webcrypto.subtle.digest('SHA-256', bytes));
    await rejected;
  });

  it('rejects pre-aborted download without fetch', async () => {
    const { hubApi } = await consumer();
    const controller = new AbortController();
    controller.abort();
    await expect(hubApi.download(identity, controller.signal, layer)).rejects.toMatchObject({ name: 'AbortError' });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe('source-proven native download commands', () => {
  it('uses layer pull for SquashFS and image pull for cloud images with a DIRECTORY output', async () => {
    const { hubDownloadCommand } = await consumer();
    // Native cli.py parser: 647–649 and 703–712. Actual handlers: 2342–2371,
    // 2425–2449 append HEX.{format} to --output, so a filename here is incorrect.
    expect(hubDownloadCommand(layer)).toBe(`palimpsest layer pull ${abcDigest} --output ./palimpsest-downloads`);
    expect(hubDownloadCommand({ ...layer, kind: 'cloud-image' })).toBe(`palimpsest image pull ${abcDigest} --output ./palimpsest-downloads`);
    const untrusted = { ...layer, name: "bad'; echo hacked", project_id: identity.token };
    expect(hubDownloadCommand(untrusted)).not.toContain(identity.token);
  });
  it('does not guess commands for unsupported kinds or shell-injected digests', async () => {
    const { hubDownloadCommand } = await consumer();
    expect(() => hubDownloadCommand({ ...layer, kind: 'buildkit-cache' })).toThrowError(expect.objectContaining({ code: 'unsupported' }));
    expect(() => hubDownloadCommand({ ...layer, blob_digest: `${abcDigest};echo hacked` })).toThrowError(expect.objectContaining({ code: 'response' }));
  });
});
