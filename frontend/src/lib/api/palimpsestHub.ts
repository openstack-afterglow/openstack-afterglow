import { get } from 'svelte/store';
import { fetchWithAuth, ApiError } from '$lib/api/client';
import { auth } from '$lib/stores/auth';
import type { PackageIdentity } from '$lib/api/palimpsestPackages';

export interface HubMe {
  user_id: string;
  project_id: string;
  project_name: string;
  roles: string[];
  is_system_admin: boolean;
  capabilities: { inventory: boolean; download: boolean; upload: boolean; delete: boolean; build: boolean };
}
export type HubDiskFormat = 'raw' | 'qcow2' | 'vmdk' | 'vdi' | 'vhd' | 'vhdx';
export interface HubLayer {
  blob_digest: string;
  blob_md5?: string | null;
  size_bytes: number;
  media_type: string;
  disk_format: string | null;
  arch: string | null;
  os_variant: string | null;
  config_digest: string;
  chain_id: string | null;
  parent_digest: string | null;
  base_image_digest: string | null;
  name: string;
  kind: string;
  ubuntu_base: string | null;
  python_version: string | null;
  config_json: Record<string, unknown>;
  project_id: string | null;
  is_published: boolean;
  created_by: string | null;
  created_at: string | null;
}
export interface HubLayerDetail extends HubLayer { ancestors: string[]; chain_complete: boolean }
export interface HubBuild {
  id: string;
  name: string;
  recipe_digest: string;
  base_digest: string;
  layer_digests: string[];
  status: string;
  output_digest: string | null;
  output_size_bytes: number | null;
  error_code: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}
export interface HubExport {
  id: string;
  source_image_id: string;
  source_name: string;
  source_disk_format: string;
  source_size_bytes: number;
  target_disk_format: string;
  status: 'queued' | 'downloading' | 'converting' | 'finalizing' | 'complete' | 'error';
  progress_pct: number;
  error_code: string | null;
  error_message: string | null;
  blob_digest: string | null;
  size_bytes: number | null;
  filename: string | null;
  download_path: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}
export interface HubFilters {
  name?: string;
  digest_prefix?: string;
  kind?: 'cloud-image' | 'squashfs';
  arch?: 'x86_64' | 'aarch64';
  disk_format?: HubDiskFormat;
}

export const HUB_PAGE_SIZE = 50;
export const MAX_HUB_DOWNLOAD_BYTES = 64 * 1024 * 1024;
export type HubClientErrorCode = 'response' | 'query' | 'too-large' | 'unsupported' | 'length' | 'digest';
export class HubClientError extends Error {
  constructor(public readonly code: HubClientErrorCode, message: string = code) {
    super(message);
    this.name = 'HubClientError';
  }
}

const root = '/api/v1/palimpsest/hub';
const formats: readonly string[] = ['raw', 'qcow2', 'vmdk', 'vdi', 'vhd', 'vhdx'];
export function sameHubIdentity(a: PackageIdentity | null, b: PackageIdentity | null): boolean {
  return a === b || !!a && !!b && a.token === b.token && a.userId === b.userId && a.projectId === b.projectId;
}
function currentIdentity(): PackageIdentity | null {
  const actor = get(auth);
  return actor.token && actor.userId && actor.projectId
    ? { token: actor.token, userId: actor.userId, projectId: actor.projectId } : null;
}
function digestPath(digest: string): string {
  if (!/^sha256:[0-9a-f]{64}$/.test(digest)) throw new HubClientError('response', 'Expected a canonical SHA-256 digest');
  return `${root}/layers/${encodeURIComponent(digest)}`;
}

// The subscription is a sticky fence: an A→B→A transition still invalidates A's
// in-flight bytes. A refresh also invalidates them; the consumer starts anew.
async function scoped<T>(identity: PackageIdentity, signal: AbortSignal, timeoutMs: number,
  operation: (signal: AbortSignal) => Promise<T>): Promise<T> {
  signal.throwIfAborted();
  if (!identity.token || !identity.userId || !identity.projectId || !sameHubIdentity(identity, currentIdentity())) {
    throw new DOMException('Hub actor is no longer current', 'AbortError');
  }
  const snapshot = { ...identity };
  const changed = new AbortController();
  const unsubscribe = auth.subscribe(() => {
    if (!sameHubIdentity(snapshot, currentIdentity())) changed.abort(new DOMException('Hub actor changed', 'AbortError'));
  });
  const bounded = AbortSignal.any([signal, changed.signal, AbortSignal.timeout(timeoutMs)]);
  try {
    bounded.throwIfAborted();
    const value = await operation(bounded);
    bounded.throwIfAborted();
    return value;
  } finally {
    unsubscribe();
  }
}
async function response(path: string, identity: PackageIdentity, signal: AbortSignal): Promise<Response> {
  const result = await fetchWithAuth(path, {
    method: 'GET', signal, credentials: 'include', cache: 'no-store', redirect: 'error',
  }, identity.token, identity.projectId);
  signal.throwIfAborted();
  if (!result.ok) {
    const envelope = await result.json().catch(() => null);
    signal.throwIfAborted();
    const message = envelope?.error?.message ?? envelope?.detail ?? result.statusText;
    throw new ApiError(result.status, typeof message === 'string' ? message : result.statusText);
  }
  return result;
}
function json<T>(path: string, identity: PackageIdentity, signal: AbortSignal): Promise<T> {
  return scoped(identity, signal, 30_000, async (bounded) => (await response(path, identity, bounded)).json());
}
function layerQuery(filters: HubFilters, offset: number, limit: number): string {
  if (!Number.isSafeInteger(offset) || offset < 0 || offset > Number.MAX_SAFE_INTEGER - limit
    || !Number.isInteger(limit) || limit < 1 || limit > 200) {
    throw new HubClientError('query', 'Invalid Hub pagination bounds');
  }
  const params = new URLSearchParams();
  if (filters.name !== undefined) {
    if (!/^[a-z0-9][a-z0-9.+-]{0,63}$/.test(filters.name)) throw new HubClientError('query', 'Invalid exact layer name');
    params.set('name', filters.name);
  }
  if (filters.digest_prefix !== undefined) {
    const prefix = filters.digest_prefix.trim().toLowerCase().replace(/^sha256:/, '');
    if (!/^[0-9a-f]{4,64}$/.test(prefix)) throw new HubClientError('query', 'Digest prefix must contain 4–64 hexadecimal characters');
    params.set('digest_prefix', prefix);
  }
  if (filters.kind !== undefined) {
    if (!['cloud-image', 'squashfs'].includes(filters.kind)) throw new HubClientError('query');
    params.set('kind', filters.kind);
  }
  if (filters.arch !== undefined) {
    if (!['x86_64', 'aarch64'].includes(filters.arch)) throw new HubClientError('query');
    params.set('arch', filters.arch);
  }
  if (filters.disk_format !== undefined) {
    if (!formats.includes(filters.disk_format)) throw new HubClientError('query');
    params.set('disk_format', filters.disk_format);
  }
  params.set('limit', String(limit));
  params.set('offset', String(offset));
  return `?${params}`;
}
async function list<T>(path: string, identity: PackageIdentity, signal: AbortSignal, limit?: number): Promise<T[]> {
  const rows = await json<T[]>(path, identity, signal);
  if (!Array.isArray(rows) || (limit !== undefined && rows.length > limit)) throw new HubClientError('response');
  return rows;
}

/** Native CLI output is a directory, not a file. Uses the caller's local login;
 * no dashboard credentials, URLs, names or server-provided paths enter a shell.
 * Source: palimpsest_local/cli.py parser 647–649, 703–712 and handlers 2342–2371, 2425–2449.
 */
export function hubDownloadCommand(layer: Pick<HubLayer, 'blob_digest' | 'kind'>): string {
  digestPath(layer.blob_digest);
  if (layer.kind !== 'squashfs' && layer.kind !== 'cloud-image') throw new HubClientError('unsupported');
  const command = layer.kind === 'cloud-image' ? 'image' : 'layer';
  return `palimpsest ${command} pull ${layer.blob_digest} --output ./palimpsest-downloads`;
}

async function download(identity: PackageIdentity, signal: AbortSignal,
  layer: Pick<HubLayer, 'blob_digest' | 'size_bytes' | 'media_type'>): Promise<Blob> {
  const path = `${digestPath(layer.blob_digest)}/blob`;
  // Capture metadata before awaiting; a mutable consumer cannot change integrity expectations.
  const { blob_digest: digest, size_bytes: expectedSize, media_type: mediaType } = layer;
  if (!Number.isSafeInteger(expectedSize) || expectedSize < 0) throw new HubClientError('length');
  if (expectedSize > MAX_HUB_DOWNLOAD_BYTES) throw new HubClientError('too-large');
  const subtle = globalThis.crypto?.subtle;
  if (!subtle || typeof subtle.digest !== 'function') throw new HubClientError('unsupported', 'SHA-256 verification is unavailable; use the native CLI');
  return scoped(identity, signal, 300_000, async (bounded) => {
    const result = await response(path, identity, bounded);
    let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
    try {
      if (result.status !== 200) throw new HubClientError('response', 'Expected a complete blob response');
      const header = result.headers.get('content-length');
      if (header !== null) {
        if (!/^\d+$/.test(header) || !Number.isSafeInteger(Number(header))) throw new HubClientError('length');
        const length = Number(header);
        if (length > MAX_HUB_DOWNLOAD_BYTES) throw new HubClientError('too-large');
        if (length !== expectedSize) throw new HubClientError('length');
      }
      if (!result.body) throw new HubClientError('unsupported', 'A bounded streaming response is unavailable');
      reader = result.body.getReader();
      const activeReader = reader;
      const abort = () => { void activeReader.cancel(bounded.reason).catch(() => {}); };
      bounded.addEventListener('abort', abort, { once: true });
      try {
        bounded.throwIfAborted();
        const bytes = new Uint8Array(expectedSize);
        let received = 0;
        while (true) {
          const chunk = await activeReader.read();
          bounded.throwIfAborted();
          if (chunk.done) break;
          const next = received + chunk.value.byteLength;
          if (next > MAX_HUB_DOWNLOAD_BYTES) throw new HubClientError('too-large');
          if (next > expectedSize) throw new HubClientError('length');
          bytes.set(chunk.value, received);
          received = next;
        }
        if (received !== expectedSize) throw new HubClientError('length');
        let hash: ArrayBuffer;
        try { hash = await subtle.digest('SHA-256', bytes); }
        catch { bounded.throwIfAborted(); throw new HubClientError('unsupported', 'SHA-256 verification failed to execute'); }
        bounded.throwIfAborted();
        const actual = `sha256:${Array.from(new Uint8Array(hash), (byte) => byte.toString(16).padStart(2, '0')).join('')}`;
        if (actual !== digest) throw new HubClientError('digest');
        return new Blob([bytes], { type: mediaType || 'application/octet-stream' });
      } finally {
        bounded.removeEventListener('abort', abort);
      }
    } finally {
      if (reader) {
        await reader.cancel().catch(() => {});
        reader.releaseLock();
      } else {
        await result.body?.cancel().catch(() => {});
      }
    }
  });
}

export const hubApi = {
  me: async (identity: PackageIdentity, signal: AbortSignal): Promise<HubMe> => {
    const me = await json<HubMe>(`${root}/me`, identity, signal);
    if (!me || me.user_id !== identity.userId || me.project_id !== identity.projectId
      || typeof me.project_name !== 'string' || typeof me.is_system_admin !== 'boolean'
      || !Array.isArray(me.roles) || !me.roles.every((role) => typeof role === 'string')
      || !me.capabilities || !['inventory', 'download', 'upload', 'delete', 'build'].every(
        (key) => typeof me.capabilities[key as keyof HubMe['capabilities']] === 'boolean')) {
      throw new HubClientError('response', 'Hub identity does not match the original actor');
    }
    return me;
  },
  // Raw lookahead (51 by default). Consumer displays 50 and uses row 51 only for
  // next-page availability; loaded rows are never an all-project total.
  layers: (identity: PackageIdentity, signal: AbortSignal, filters: HubFilters = {}, offset = 0, limit = HUB_PAGE_SIZE + 1) =>
    list<HubLayer>(`${root}/layers${layerQuery(filters, offset, limit)}`, identity, signal, limit),
  detail: async (identity: PackageIdentity, signal: AbortSignal, digest: string): Promise<HubLayerDetail> => {
    const layer = await json<HubLayerDetail>(digestPath(digest), identity, signal);
    if (!layer || layer.blob_digest !== digest) throw new HubClientError('response');
    return layer;
  },
  ancestors: (identity: PackageIdentity, signal: AbortSignal, digest: string) =>
    list<HubLayer>(`${digestPath(digest)}/ancestors`, identity, signal),
  builds: (identity: PackageIdentity, signal: AbortSignal) => list<HubBuild>(`${root}/builds?limit=20`, identity, signal, 20),
  exports: (identity: PackageIdentity, signal: AbortSignal) => list<HubExport>(`${root}/image-exports?limit=20`, identity, signal, 20),
  download,
};
