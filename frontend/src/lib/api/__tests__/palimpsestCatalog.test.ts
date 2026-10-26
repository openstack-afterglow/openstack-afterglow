import { beforeEach, expect, it, vi } from 'vitest';
import { fetchWithAuth } from '$lib/api/client';
import { catalogApi, CATALOG_PAGE_SIZE } from '$lib/api/palimpsestCatalog';
import { ApiError } from '$lib/api/errors';

vi.mock('$lib/api/client', () => ({ fetchWithAuth: vi.fn() }));
const identity = { token: 'original-human-token', userId: 'human-a', projectId: 'project-a' };
beforeEach(() => vi.mocked(fetchWithAuth).mockReset());

it('sends bounded name or digest search to the exact admin source with the original project token', async () => {
  vi.mocked(fetchWithAuth).mockResolvedValue(new Response(JSON.stringify({ source: 'hub', items: [], offset: 81, has_more: false, next_offset: null })));
  const abort = new AbortController();
  await catalogApi.layers(identity, abort.signal, 'hub', ' torch & cuda ', 81);
  const [path, options, token, project] = vi.mocked(fetchWithAuth).mock.calls[0];
  const url = new URL(path as string, 'http://localhost');
  expect(url.pathname).toBe('/api/v1/admin/palimpsest/catalog');
  expect(Object.fromEntries(url.searchParams)).toEqual({ source: 'hub', q: 'torch & cuda', offset: '81', limit: String(CATALOG_PAGE_SIZE) });
  expect(token).toBe('original-human-token');
  expect(project).toBe('project-a');
  expect(options).toMatchObject({ method: 'GET', credentials: 'include', cache: 'no-store', redirect: 'error' });
  abort.abort();
  expect(options?.signal?.aborted).toBe(true);
});

it('encodes canonical digest detail identity without widening to a gateway route', async () => {
  vi.mocked(fetchWithAuth).mockResolvedValue(new Response(JSON.stringify({ id: 'sha256:abcd' })));
  await catalogApi.detail(identity, new AbortController().signal, 'hub', 'sha256:abcd');
  expect(vi.mocked(fetchWithAuth).mock.calls[0][0]).toBe('/api/v1/admin/palimpsest/catalog/sha256%3Aabcd?source=hub');
});

it('preserves service denial and unavailability rather than replacing errors with empty pages', async () => {
  vi.mocked(fetchWithAuth).mockResolvedValueOnce(new Response(JSON.stringify({ detail: { code: 'native_denied', message: 'Native inventory denied' } }), { status: 403 }));
  await expect(catalogApi.layers(identity, new AbortController().signal, 'hub')).rejects.toMatchObject({ status: 403, code: 'native_denied', message: 'Native inventory denied' });
  vi.mocked(fetchWithAuth).mockResolvedValueOnce(new Response('Service unavailable', { status: 503, statusText: 'Unavailable' }));
  await expect(catalogApi.layers(identity, new AbortController().signal, 'managed')).rejects.toBeInstanceOf(ApiError);
});
