import { get } from 'svelte/store';
import { fetchWithAuth, ApiError } from '$lib/api/client';
import { auth } from '$lib/stores/auth';
import type { PackageIdentity, PackageSummary, PackageVersion, ProjectContext, ScopedPage } from './palimpsestPackages';
import { HubClientError } from './palimpsestHub';

export interface AssetIdentity extends PackageIdentity { sessionId?: string }
export function sameAssetActor(a: AssetIdentity | null, b: AssetIdentity | null): boolean {
  return a === b || !!a && !!b && a.projectId === b.projectId && a.userId === b.userId && a.sessionId === b.sessionId;
}
export interface ReusableAsset {
  id: string;
  name: string;
  kind: 'layer-bundle' | 'cloud-image';
  blob_digest: string;
  chain_id: string | null;
  arch: string | null;
  ubuntu_base: string | null;
  size_bytes: number | null;
  created_at: string | null;
  visibility: 'public' | 'site' | 'project' | 'shared';
  layer_count: number;
  chain_complete: boolean;
  download_allowed: boolean;
  base_image_digest: string | null;
  local_supported: boolean;
  local_reason: string | null;
}
export interface CloudEnvironment extends ReusableAsset {
  source: 'managed';
  revision: string;
  cloud_supported: boolean;
  cloud_reason: string | null;
}
export interface AssetPage<T> { items: T[]; offset: number; has_more: boolean; next_offset: number | null }
export interface ConsumeResult {
  consume_id: number;
  server_id: string | null;
  status: string;
  ready: boolean;
  revision: string;
  project_id: string;
}
export interface CloudRequest {
  revision: string;
  flavor_id: string;
  network_id: string;
  key_name: string;
  server_name: string;
  ssh_username: string;
}
export interface CloudResources {
  flavors: { id: string; name: string; vcpus: number; ram: number }[];
  networks: { id: string; name: string; external?: boolean }[];
  keys: { name: string }[];
}
const root = '/api/v1/palimpsest/catalog';
const digestPattern = /^sha256:[0-9a-f]{64}$/;
export function actorIsCurrent(identity: PackageIdentity): boolean {
  const state = get(auth);
  return !!state.token && identity.projectId === state.projectId && identity.userId === state.userId;
}
async function request<T>(identity: PackageIdentity, signal: AbortSignal, path: string, body: unknown, read: (response: Response, signal: AbortSignal) => Promise<T>, method?: 'DELETE'): Promise<T> {
  signal.throwIfAborted();
  if (!actorIsCurrent(identity)) throw new DOMException('Asset actor changed', 'AbortError');
  const changed = new AbortController();
  const session = get(auth).sessionId;
  const stop = auth.subscribe((state) => { if (!actorIsCurrent(identity) || state.sessionId !== session) changed.abort(); });
  const bounded = AbortSignal.any([signal, changed.signal, AbortSignal.timeout(300_000)]);
  try {
    const result = await fetchWithAuth(path, {
      method: method ?? (body === undefined ? 'GET' : 'POST'), credentials: 'include', redirect: 'error', cache: 'no-store',
      signal: bounded,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    }, identity.token, identity.projectId);
    if (!result.ok) {
      const value = await result.json().catch(() => null);
      const message = value?.error?.message ?? value?.detail?.message ?? value?.detail ?? result.statusText;
      throw new ApiError(result.status, typeof message === 'string' ? message : result.statusText);
    }
    const value = await read(result, bounded);
    signal.throwIfAborted();
    if (!actorIsCurrent(identity) || changed.signal.aborted) throw new DOMException('Asset actor changed', 'AbortError');
    return value;
  } finally { stop(); }
}
async function json<T>(identity: PackageIdentity, signal: AbortSignal, path: string, body?: unknown): Promise<T> {
  return request(identity, signal, path, body, (response) => response.json());
}
function searchQuery(q: string, offset: number) {
  return new URLSearchParams({ q, limit: '20', offset: String(offset) });
}

export const MAX_ASSET_DOWNLOAD_BYTES = 64 * 1024 * 1024;
async function boundedBlob(response: Response, signal: AbortSignal): Promise<Blob> {
  const reader = response.body?.getReader();
  if (!reader) throw new HubClientError('response');
  const chunks: Uint8Array<ArrayBuffer>[] = [];
  let total = 0;
  const cancel = () => { void reader.cancel().catch(() => {}); };
  signal.addEventListener('abort', cancel, { once: true });
  try {
    const length = response.headers.get('content-length');
    if (length !== null && (!/^\d+$/.test(length) || Number(length) > MAX_ASSET_DOWNLOAD_BYTES)) throw new HubClientError('too-large');
    while (true) {
      signal.throwIfAborted();
      const { value, done } = await reader.read();
      signal.throwIfAborted();
      if (done) break;
      total += value.byteLength;
      if (total > MAX_ASSET_DOWNLOAD_BYTES) throw new HubClientError('too-large');
      chunks.push(value);
    }
    return new Blob(chunks, { type: response.headers.get('content-type') ?? 'application/octet-stream' });
  } finally {
    signal.removeEventListener('abort', cancel);
    await reader.cancel().catch(() => {}); reader.releaseLock();
  }
}
export const assetApi = {
  hub: (identity: PackageIdentity, signal: AbortSignal, q: string, offset = 0) =>
    json<AssetPage<ReusableAsset>>(identity, signal, `${root}/assets?${searchQuery(q, offset)}`),
  environments: (identity: PackageIdentity, signal: AbortSignal, q: string, offset = 0) =>
    json<AssetPage<CloudEnvironment>>(identity, signal, `${root}/environments?${searchQuery(q, offset)}`),
  context: (identity: PackageIdentity, signal: AbortSignal) =>
    json<ProjectContext>(identity, signal, '/api/v1/palimpsest/packages/context'),
  packages: (identity: PackageIdentity, signal: AbortSignal, q: string, cursor?: string) => {
    const params = new URLSearchParams({ q, limit: '20' });
    if (cursor) params.set('cursor', cursor);
    return json<ScopedPage<PackageSummary>>(identity, signal, `/api/v1/palimpsest/packages?${params}`);
  },
  versions: (identity: PackageIdentity, signal: AbortSignal, name: string, cursor?: string) => {
    const params = new URLSearchParams({ package: name, limit: '20' });
    if (cursor) params.set('cursor', cursor);
    return json<ScopedPage<PackageVersion>>(identity, signal, `/api/v1/palimpsest/packages/versions?${params}`);
  },
  bundle: async (identity: PackageIdentity, signal: AbortSignal, digest: string): Promise<Blob> => {
    if (!digestPattern.test(digest)) throw new Error('Invalid asset digest');
    return request(identity, signal, '/api/v1/palimpsest/hub/bundles', { refs: [digest], include_base_image: true }, boundedBlob);
  },
  packageDownload: async (identity: PackageIdentity, signal: AbortSignal, name: string, digest: string): Promise<Blob> => {
    if (!digestPattern.test(digest)) throw new Error('Invalid package digest');
    return request(identity, signal, `/api/v1/palimpsest/packages/versions/${encodeURIComponent(digest)}/download?${new URLSearchParams({ package: name })}`, undefined, boundedBlob);
  },
  consume: (identity: PackageIdentity, signal: AbortSignal, id: string, body: CloudRequest) =>
    json<ConsumeResult>(identity, signal, `${root}/environments/${encodeURIComponent(id)}/consume`, body),
  consumeStatus: (identity: PackageIdentity, signal: AbortSignal, id: number) =>
    json<ConsumeResult>(identity, signal, `${root}/environments/consumes/${id}`),
  cleanup: (identity: PackageIdentity, signal: AbortSignal, id: number) =>
    request<ConsumeResult>(identity, signal, `${root}/environments/consumes/${id}`, undefined, (response) => response.json(), 'DELETE'),
  resources: async (identity: PackageIdentity, signal: AbortSignal): Promise<CloudResources> => {
    const [flavors, networks, keys] = await Promise.all([
      json<{ id: string; name: string; vcpus: number; ram: number }[]>(identity, signal, '/api/v1/flavors'),
      json<{ id: string; name: string; external?: boolean }[]>(identity, signal, '/api/v1/networks'),
      json<{ name: string }[]>(identity, signal, '/api/v1/keypairs'),
    ]);
    return { flavors, networks, keys };
  },
};

/** Only canonical digest-derived paths enter commands, never resource display names. */
export function localAssetCommands(kind: 'runtime-bundle' | 'oci-image', filename: string): string {
  const identity = /^palimpsest-(?:runtime|image)-([0-9a-f]{64})\.oci\.tar$/.exec(filename);
  if (!identity || identity[0] !== filename) throw new Error('Unsupported local asset filename');
  if (kind === 'oci-image') return `palimpsest run ./${filename} --runtime-kind oci-root --name palimpsest-app`;
  const directory = `palimpsest-bundle-${identity[1]}`;
  return `palimpsest bundle unpack ./${filename} --output ./${directory} &&\npalimpsest run ./${directory} --name palimpsest-app`;
}

export function hubAssetCommands(digest: string): string {
  if (digest.length !== 71 || !digestPattern.test(digest)) throw new Error('Invalid asset digest');
  const directory = `palimpsest-bundle-${digest.slice(7)}`;
  return `palimpsest bundle pull ${digest} --include-base --output ./${directory} &&\npalimpsest run ./${directory} --name palimpsest-app`;
}

export function packageAssetCommands(authority: string | null, namespace: string, name: string, digest: string, kind: 'runtime-bundle' | 'oci-image', filename: string): string {
  const component = /^[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*$/;
  if (!authority || !/^[A-Za-z0-9.\[\]:-]{1,255}$/.test(authority) || authority.trim() !== authority
    || namespace.length > 63 || namespace.trim() !== namespace || !component.test(namespace)
    || name.length > 253 || name.trim() !== name || !name.split('/').every((part) => component.test(part))
    || digest.length !== 71 || !digestPattern.test(digest)) return '';
  if (filename !== `palimpsest-${kind === 'oci-image' ? 'image' : 'runtime'}-${digest.slice(7)}.oci.tar`) return '';
  return `palimpsest pull '${authority}/${namespace}/${name}@${digest}' --output ./${filename} &&\n${localAssetCommands(kind, filename)}`;
}
