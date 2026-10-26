import { fetchWithAuth } from '$lib/api/client';
import { ApiError } from '$lib/api/errors';
import type { PackageIdentity } from '$lib/api/palimpsestPackages';

export type CatalogSource = 'managed' | 'hub';
export interface CatalogOrigin {
  kind: 'build' | 'image-export' | 'registered' | 'unknown';
  source: 'hub-build' | 'dockerfile-inline' | 'github-dockerfile' | 'recipe' | 'glance' | 'upload-or-import' | 'unknown';
  evidence: 'recorded' | 'unrecorded';
  build_id: string | null;
  job_id: string | null;
  revision: string | null;
}
export interface CatalogLayer {
  id: string;
  name: string;
  blob_digest: string | null;
  parent_id: string | null;
  parent_digest: string | null;
  kind: string;
  arch: string | null;
  ubuntu_base: string | null;
  size_bytes: number | null;
  created_at: string | null;
  project_id: string | null;
  visibility: 'public' | 'site' | 'project' | 'shared' | 'private';
  chain_complete: boolean;
  origin: CatalogOrigin;
}
export interface CatalogLayerPage {
  source: CatalogSource;
  items: CatalogLayer[];
  offset: number;
  has_more: boolean;
  next_offset: number | null;
}
export interface CatalogLayerDetail extends CatalogLayer {
  ancestors: CatalogLayer[];
  children: CatalogLayer[];
  children_has_more: boolean;
  bundles: string[];
}
export const CATALOG_PAGE_SIZE = 50;
const base = '/api/v1/admin/palimpsest/catalog';
async function request<T>(path: string, identity: PackageIdentity, signal: AbortSignal): Promise<T> {
  const result = await fetchWithAuth(path, {
    method: 'GET', signal: AbortSignal.any([signal, AbortSignal.timeout(30_000)]),
    credentials: 'include', cache: 'no-store', redirect: 'error',
  }, identity.token, identity.projectId);
  if (!result.ok) {
    const envelope = await result.json().catch(() => null);
    const detail = envelope?.error ?? envelope?.detail;
    const message = typeof detail === 'string' ? detail : detail?.message;
    const code = envelope?.code ?? detail?.code;
    throw new ApiError(result.status, typeof message === 'string' ? message : result.statusText, typeof code === 'string' ? code : undefined);
  }
  return result.json();
}
export const catalogApi = {
  layers: (identity: PackageIdentity, signal: AbortSignal, source: CatalogSource, q = '', offset = 0) => {
    const query = new URLSearchParams({ source, q: q.trim(), offset: String(offset), limit: String(CATALOG_PAGE_SIZE) });
    return request<CatalogLayerPage>(`${base}?${query}`, identity, signal);
  },
  detail: (identity: PackageIdentity, signal: AbortSignal, source: CatalogSource, id: string) =>
    request<CatalogLayerDetail>(`${base}/${encodeURIComponent(id)}?${new URLSearchParams({ source })}`, identity, signal),
};
