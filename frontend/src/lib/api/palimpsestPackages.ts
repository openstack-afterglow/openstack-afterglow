import { fetchWithAuth, ApiError } from '$lib/api/client';

export interface PackageIdentity { token: string; projectId: string; userId: string }
export interface ProjectContext {
  project_id: string;
  project_name: string;
  namespace: string | null;
  package_authority: string | null;
  capabilities: { packages_read: boolean; packages_download: boolean; packages_write: boolean; keys_issue: boolean; keys_revoke: boolean };
}
export interface Platform { os: string; architecture: string; variant?: string }
export interface PackageSummary {
  package_id: string;
  project_id: string;
  namespace: string;
  name: string;
  package_type: 'oci-image' | 'runtime-bundle';
  visibility: 'project';
  tags: { tag: string; digest: string }[];
  platforms: Platform[];
  version_count: number;
  latest_pushed_at: string | null;
  latest_pushed_by: string | null;
}
export interface PackageVersion {
  project_id: string;
  namespace: string;
  package: string;
  root_digest: string;
  root_media_type: string;
  root_descriptor: { digest: string; mediaType: string; size: number };
  graph: Record<string, { media_type: string; size_bytes: number }>;
  platforms: Platform[];
  archive_digest: string;
  archive_size_bytes: number;
  total_bytes: number;
  provenance: Record<string, unknown>;
  pushed_by: string;
  pushed_key_id: string;
  pushed_at: string;
}
export interface ScopedPage<T> { project_id: string; namespace: string; items: T[]; next_cursor: string | null }
export interface VersionPage extends ScopedPage<PackageVersion> { package: string }
export interface KeyList { project_id: string; namespace: string; items: PackageKey[] }
export type KeyAction = 'packages:inventory' | 'packages:read' | 'packages:write' | 'cache:read' | 'cache:write';
export type KeyScope = { packages: string[]; all_packages?: never } | { all_packages: true; packages?: never };
export interface PackageKey {
  key_id: string;
  name: string;
  owner_user_id: string;
  project_id: string;
  namespace: string;
  scope: KeyScope;
  actions: KeyAction[];
  created_at: string;
  expires_at: string;
  revoked_at: string | null;
}
export interface CreatePackageKey { name: string; scope: KeyScope; actions: KeyAction[]; expires_in_days: number }
export interface IssuedPackageKey { key: PackageKey; secret: string }
export interface PackageResolution { project_id: string; namespace: string; package: string; tag: string; digest: string }

const packages = '/api/v1/palimpsest/packages';
const keys = '/api/v1/palimpsest/package-keys';
function query(values: Record<string, string | undefined>) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) if (value !== undefined) params.set(key, value);
  return `?${params}`;
}
async function response(path: string, identity: PackageIdentity, signal: AbortSignal, method = 'GET', body?: unknown, timeoutMs = 30_000) {
  const result = await fetchWithAuth(path, {
    method, signal: AbortSignal.any([signal, AbortSignal.timeout(timeoutMs)]),
    credentials: 'include', cache: 'no-store', redirect: 'error',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  }, identity.token, identity.projectId);
  if (!result.ok) {
    const envelope = await result.json().catch(() => null);
    const message = envelope?.error?.message ?? envelope?.detail ?? result.statusText;
    throw new ApiError(result.status, typeof message === 'string' ? message : result.statusText);
  }
  return result;
}
async function json<T>(path: string, identity: PackageIdentity, signal: AbortSignal, method?: string, body?: unknown): Promise<T> {
  const result = await response(path, identity, signal, method, body);
  return result.status === 204 ? undefined as T : result.json();
}
export const packageApi = {
  context: (identity: PackageIdentity, signal: AbortSignal) => json<ProjectContext>(`${packages}/context`, identity, signal),
  register: (identity: PackageIdentity, signal: AbortSignal) => json<ProjectContext>(`${packages}/namespace`, identity, signal, 'PUT'),
  inventory: (identity: PackageIdentity, signal: AbortSignal, cursor?: string) => json<ScopedPage<PackageSummary>>(`${packages}${query({ limit: '50', cursor })}`, identity, signal),
  detail: (identity: PackageIdentity, signal: AbortSignal, name: string) => json<PackageSummary>(`${packages}/detail${query({ package: name })}`, identity, signal),
  versions: (identity: PackageIdentity, signal: AbortSignal, name: string, cursor?: string, limit = 50) => json<VersionPage>(`${packages}/versions${query({ package: name, limit: String(limit), cursor })}`, identity, signal),
  version: (identity: PackageIdentity, signal: AbortSignal, name: string, digest: string) => json<PackageVersion>(`${packages}/versions/${encodeURIComponent(digest)}${query({ package: name })}`, identity, signal),
  resolve: (identity: PackageIdentity, signal: AbortSignal, name: string, tag: string) => json<PackageResolution>(`${packages}/resolve${query({ package: name, tag })}`, identity, signal),
  keys: (identity: PackageIdentity, signal: AbortSignal) => json<KeyList>(keys, identity, signal),
  issue: (identity: PackageIdentity, signal: AbortSignal, body: CreatePackageKey) => json<IssuedPackageKey>(keys, identity, signal, 'POST', body),
  revoke: (identity: PackageIdentity, signal: AbortSignal, id: string) => json<void>(`${keys}/${encodeURIComponent(id)}`, identity, signal, 'DELETE'),
  download: async (identity: PackageIdentity, signal: AbortSignal, name: string, digest: string) => {
    const result = await response(`${packages}/versions/${encodeURIComponent(digest)}/download${query({ package: name })}`, identity, signal, 'GET', undefined, 300_000);
    return result.blob();
  },
};
export function samePackageIdentity(a: PackageIdentity | null, b: PackageIdentity | null) {
  return a === b || !!a && !!b && a.projectId === b.projectId && a.userId === b.userId;
}
