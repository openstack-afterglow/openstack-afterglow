import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { get } from 'svelte/store';
import type * as SvelteStore from 'svelte/store';
import { auth, authReady, projectSwitching, logoutInProgress } from '$lib/stores/auth';
import { catalogApi, type CatalogLayer, type CatalogLayerDetail, type CatalogLayerPage } from '$lib/api/palimpsestCatalog';
import { ApiError } from '$lib/api/errors';
import { getLocale, initLocale } from '$lib/i18n/runtime.svelte';
import PalimpsestCatalogPanel from '../PalimpsestCatalogPanel.svelte';

vi.mock('$lib/stores/auth', async () => {
  const { writable } = await vi.importActual<typeof SvelteStore>('svelte/store');
  return {
    auth: writable({ token: 'token-a', userId: 'user-a', projectId: 'project-a', domainId: 'domain-a', sessionId: 'session-a', isSystemAdmin: true }),
    authReady: writable(true), projectSwitching: writable(false), logoutInProgress: writable(false),
  };
});
vi.mock('$lib/api/palimpsestCatalog', () => ({ catalogApi: { layers: vi.fn(), detail: vi.fn() } }));
const originalLocale = getLocale();
const digest = `sha256:${'a'.repeat(64)}`;
const parentDigest = `sha256:${'b'.repeat(64)}`;
const childDigest = `sha256:${'c'.repeat(64)}`;
const row: CatalogLayer = {
  id: '42', name: 'torch-runtime', blob_digest: digest, parent_id: '41', parent_digest: parentDigest,
  kind: 'squashfs', arch: 'x86_64', ubuntu_base: '24.04', size_bytes: 2048,
  created_at: '2026-10-25T01:00:00', project_id: 'project-a', visibility: 'public', chain_complete: false,
  origin: { kind: 'registered', source: 'upload-or-import', evidence: 'unrecorded', build_id: null, job_id: null, revision: null },
};
function page(items: CatalogLayer[] = [row], source: 'managed' | 'hub' = 'managed', offset = 0): CatalogLayerPage {
  return { source, items, offset, has_more: false, next_offset: null };
}
beforeEach(() => {
  initLocale('en');
  auth.set({ ...get(auth), token: 'token-a', userId: 'user-a', projectId: 'project-a', domainId: 'domain-a', sessionId: 'session-a', isSystemAdmin: true });
  authReady.set(true); projectSwitching.set(false); logoutInProgress.set(false);
  vi.mocked(catalogApi.layers).mockReset().mockResolvedValue(page());
  vi.mocked(catalogApi.detail).mockReset();
});
afterEach(() => { cleanup(); initLocale(originalLocale); });

it('searches the server by trimmed name or digest and follows bounded server offsets', async () => {
  vi.mocked(catalogApi.layers).mockImplementation(async (_identity, _signal, source, q, offset) => {
    if (q === 'torch' && offset === 0) return { ...page([row], source), has_more: true, next_offset: 81 };
    return page([{ ...row, name: offset === 81 ? 'later-result' : 'initial-result' }], source, offset);
  });
  render(PalimpsestCatalogPanel);
  await screen.findByText('initial-result');
  await fireEvent.input(screen.getByLabelText('Search name or digest'), { target: { value: '  torch  ' } });
  await fireEvent.submit(screen.getByLabelText('Search name or digest').closest('form')!);
  await screen.findByText('torch-runtime');
  expect(catalogApi.layers).toHaveBeenLastCalledWith(expect.objectContaining({ userId: 'user-a', projectId: 'project-a' }), expect.any(AbortSignal), 'managed', 'torch', 0);
  await fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
  await screen.findByText('later-result');
  expect(catalogApi.layers).toHaveBeenLastCalledWith(expect.anything(), expect.anything(), 'managed', 'torch', 81);
  await fireEvent.click(screen.getByRole('button', { name: 'Previous page' }));
  await screen.findByText('torch-runtime');
  expect(catalogApi.layers).toHaveBeenLastCalledWith(expect.anything(), expect.anything(), 'managed', 'torch', 0);
});

it('distinguishes a native service outage from a successfully empty managed catalog', async () => {
  vi.mocked(catalogApi.layers).mockImplementation(async (_identity, _signal, source) => {
    if (source === 'hub') throw new ApiError(503, 'Native catalog unavailable');
    return page([], source);
  });
  render(PalimpsestCatalogPanel);
  await screen.findByText('No layers recorded in this source.');
  await fireEvent.click(screen.getByRole('button', { name: 'Palimpsest Hub' }));
  await screen.findByText(/The catalog service is unavailable, not empty/);
  expect(screen.queryByText('No layers recorded in this source.')).toBeNull();
  await fireEvent.click(screen.getByRole('button', { name: 'Afterglow managed' }));
  await screen.findByText('No layers recorded in this source.');
  expect(screen.queryByText(/The catalog service is unavailable/)).toBeNull();
});

it('shows full identity, recorded relations and honest unrecorded origin without inventing a build', async () => {
  const parent = { ...row, id: '41', name: 'base-layer', blob_digest: parentDigest, parent_id: null, parent_digest: null, chain_complete: true };
  const child = { ...row, id: '43', name: 'child-layer', blob_digest: childDigest, parent_id: '42', parent_digest: digest };
  vi.mocked(catalogApi.detail).mockImplementation(async (_identity, _signal, _source, id) => ({
    ...(id === '43' ? child : row), ancestors: [parent], children: id === '43' ? [] : [child], children_has_more: true, bundles: ['published-torch'],
  }));
  const onbundle = vi.fn();
  render(PalimpsestCatalogPanel, { onbundle });
  await screen.findByText('torch-runtime');
  await fireEvent.click(screen.getByRole('button', { name: 'Layer details' }));
  const inspector = await screen.findByTestId('palimpsest-catalog-inspector');
  await within(inspector).findByText(digest);
  expect(within(inspector).getByText(/No durable creation evidence/)).toBeTruthy();
  expect(within(inspector).getByText(/The chain is incomplete or unverified/)).toBeTruthy();
  expect(within(inspector).queryByText('Recorded build')).toBeNull();
  expect(within(inspector).getAllByText(parentDigest)).toHaveLength(2);
  expect(within(inspector).getByText(childDigest)).toBeTruthy();
  expect(within(inspector).getByText(/More direct children exist/)).toBeTruthy();
  const bundle = within(inspector).getByRole('link', { name: 'published-torch' });
  expect(bundle.getAttribute('href')).toBe('#palimpsest-managed-profiles');
  await fireEvent.click(bundle);
  expect(onbundle).toHaveBeenCalledWith('published-torch');
  await fireEvent.click(within(inspector).getByRole('button', { name: 'child-layer' }));
  await within(inspector).findByRole('heading', { name: 'child-layer' });
  expect(catalogApi.detail).toHaveBeenLastCalledWith(expect.anything(), expect.any(AbortSignal), 'managed', '43');
});

it('aborts stale detail on a source change and never publishes its late result', async () => {
  const pending = Promise.withResolvers<CatalogLayerDetail>();
  vi.mocked(catalogApi.detail).mockReturnValue(pending.promise);
  vi.mocked(catalogApi.layers).mockImplementation(async (_identity, _signal, source) => page([{ ...row, name: `${source}-layer` }], source));
  render(PalimpsestCatalogPanel);
  await screen.findByText('managed-layer');
  await fireEvent.click(screen.getByRole('button', { name: 'Layer details' }));
  const signal = vi.mocked(catalogApi.detail).mock.calls[0][1];
  await fireEvent.click(screen.getByRole('button', { name: 'Palimpsest Hub' }));
  await screen.findByText('hub-layer');
  expect(signal.aborted).toBe(true);
  pending.resolve({ ...row, name: 'stale-private-detail', ancestors: [], children: [], children_has_more: false, bundles: [] });
  await tick();
  expect(screen.queryByText('stale-private-detail')).toBeNull();
  expect(screen.queryByTestId('palimpsest-catalog-inspector')).toBeNull();
});

it('fences same-tick workspace ABA and masks inventory during authority verification', async () => {
  const pending = Promise.withResolvers<CatalogLayerPage>();
  vi.mocked(catalogApi.layers).mockReturnValueOnce(pending.promise).mockResolvedValue(page([{ ...row, name: 'fresh-layer' }]));
  render(PalimpsestCatalogPanel);
  await tick();
  expect(screen.queryByText(/No layers recorded/)).toBeNull();
  const oldSignal = vi.mocked(catalogApi.layers).mock.calls[0][1];
  projectSwitching.set(true); projectSwitching.set(false);
  await screen.findByText('fresh-layer');
  expect(oldSignal.aborted).toBe(true);
  pending.resolve(page([{ ...row, name: 'stale-layer' }]));
  await tick();
  expect(screen.queryByText('stale-layer')).toBeNull();
  authReady.set(false);
  await screen.findByText('Verified current administrator authentication is required.');
  expect(screen.queryByText('fresh-layer')).toBeNull();
  const before = vi.mocked(catalogApi.layers).mock.calls.length;
  auth.set({ ...get(auth), isSystemAdmin: false }); authReady.set(true);
  await tick();
  expect(catalogApi.layers).toHaveBeenCalledTimes(before);
});

it('separates authority denial and missing detail from empty inventory', async () => {
  vi.mocked(catalogApi.layers).mockRejectedValueOnce(new ApiError(403, 'Native denied'));
  render(PalimpsestCatalogPanel);
  await screen.findByText(/The current caller cannot read this inventory/);
  expect(screen.queryByText(/No layers recorded/)).toBeNull();
  await fireEvent.click(screen.getByRole('button', { name: 'Retry read' }));
  await screen.findByText('torch-runtime');
  vi.mocked(catalogApi.detail).mockRejectedValueOnce(new ApiError(404, 'Missing'));
  await fireEvent.click(screen.getByRole('button', { name: 'Layer details' }));
  await screen.findByText('The selected layer was not found. Refresh the inventory.');
  expect(screen.getByText('torch-runtime')).toBeTruthy();
});

it.each(['token', 'userId', 'projectId', 'sessionId', 'isSystemAdmin'] as const)('discards an old inventory after same-tick %s ABA', async field => {
  const pending = Promise.withResolvers<CatalogLayerPage>();
  vi.mocked(catalogApi.layers).mockReturnValueOnce(pending.promise).mockResolvedValue(page([{ ...row, name: 'current-identity-layer' }]));
  render(PalimpsestCatalogPanel);
  await tick();
  const initial = get(auth);
  const oldSignal = vi.mocked(catalogApi.layers).mock.calls[0][1];
  auth.set({ ...initial, [field]: field === 'isSystemAdmin' ? false : 'other-identity' });
  auth.set(initial);
  await screen.findByText('current-identity-layer');
  pending.resolve(page([{ ...row, name: 'old-identity-layer' }]));
  await tick();
  expect(oldSignal.aborted).toBe(true);
  expect(screen.queryByText('old-identity-layer')).toBeNull();
});
