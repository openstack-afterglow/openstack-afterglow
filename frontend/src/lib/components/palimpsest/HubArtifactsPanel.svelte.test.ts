import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import type { Writable } from 'svelte/store';
import type * as SvelteStore from 'svelte/store';
import HubArtifactsPanel from './HubArtifactsPanel.svelte';
import { projectPermissions } from '$lib/stores/servicePermissions';
import type { ProjectPermissions } from '$lib/stores/servicePermissions';
import type * as HubModule from '$lib/api/palimpsestHub';
import { HUB_PAGE_SIZE, hubApi, type HubLayer } from '$lib/api/palimpsestHub';
import { getLocale, initLocale } from '$lib/i18n/runtime.svelte';
import { t as commonText } from '$lib/i18n/ns/common';
import { t as hubText } from '$lib/i18n/ns/palimpsest-hub';

vi.mock('$lib/stores/servicePermissions', async () => {
  const { writable } = await vi.importActual<typeof SvelteStore>('svelte/store');
  return {
    projectPermissions: writable({ permissions: null, loading: true, error: '' }),
    serviceCapabilities: writable(() => true),
  };
});
vi.mock('$lib/api/palimpsestHub', async (original) => {
  const module = await original<typeof HubModule>();
  return { ...module, hubApi: {
    me: async () => ({ user_id: 'user-a', project_id: 'project-a', project_name: 'Verified Hub actor', roles: ['member'], is_system_admin: false, capabilities: { inventory: true, download: true, upload: false, delete: false, build: false } }),
    layers: async () => [], builds: async () => [], exports: async () => [],
  } };
});
const permissions = projectPermissions as Writable<{ permissions: ProjectPermissions | null; loading: boolean; error: string }>;
const initialLocale = getLocale();
afterEach(() => { cleanup(); initLocale(initialLocale); vi.restoreAllMocks(); vi.unstubAllEnvs(); });

it('shows the verified caller after initial permission loading and masks it during a later outage', async () => {
  initLocale('en');
  permissions.set({ permissions: null, loading: true, error: '' });
  render(HubArtifactsPanel, { identity: { token: 'browser-jwt', projectId: 'project-a', userId: 'user-a' } });
  expect(screen.queryByText(/Verified Hub actor/)).toBeNull();
  permissions.set({ permissions: { is_owner: false, is_manager: false, can_write: true, service_permissions: { palimpsest: ['palimpsest-inventory_reader'] } }, loading: false, error: '' });
  await screen.findByText(/Verified Hub actor/);
  expect(screen.getByText('project-a')).toBeTruthy();
  expect(screen.getByText('user-a')).toBeTruthy();
  permissions.set({ permissions: null, loading: false, error: 'Directory unavailable' });
  await tick();
  expect(screen.queryByText(/Verified Hub actor/)).toBeNull();
});

it('localizes native UTC job times without shifting explicit offsets or observation epochs', async () => {
  initLocale('en');
  vi.spyOn(Date, 'now').mockReturnValue(Date.UTC(2026, 9, 15, 4));
  vi.spyOn(hubApi, 'exports').mockResolvedValue([{
    id: 'native-utc-export', source_image_id: 'source', source_name: 'Native UTC export',
    source_disk_format: 'qcow2', source_size_bytes: 1024, target_disk_format: 'raw',
    status: 'complete', progress_pct: 100, error_code: null, error_message: null,
    blob_digest: null, size_bytes: null, filename: null, download_path: null,
    created_at: '2026-10-15T00:00:00.123456',
    started_at: '2026-10-15T01:00:00Z',
    completed_at: '2026-10-15T12:00:00+09:00',
  }]);
  permissions.set({ permissions: { is_owner: false, is_manager: false, can_write: true, service_permissions: { palimpsest: ['palimpsest-inventory_reader'] } }, loading: false, error: '' });
  render(HubArtifactsPanel, { identity: { token: 'browser-jwt', projectId: 'project-a', userId: 'user-a' } });
  const job = (await screen.findByText('Native UTC export')).closest('li')!;
  const displayed = [...job.querySelectorAll('details dd')].slice(0, 3).map(node => node.textContent);
  // vitest.config.ts pins TZ before the worker starts; hard-code the zone so a
  // naive-local implementation cannot pass by sharing the host default.
  const localTime = (hour: number) => new Date(Date.UTC(2026, 9, 15, hour)).toLocaleString('en-US', { timeZone: 'Asia/Seoul' });
  expect(displayed).toEqual([localTime(0), localTime(1), localTime(3)]);
  expect(job.closest('section')!.querySelector(':scope > p')?.textContent).toContain(localTime(4));
});

it('keeps native scalar header facets global, resets their offset and retains regex through refresh', async () => {
  initLocale('en');
  const rows: HubLayer[] = Array.from({ length: HUB_PAGE_SIZE + 1 }, (_, index) => ({
    blob_digest: `sha256:${index.toString(16).padStart(64, '0')}`, size_bytes: 1024,
    media_type: 'application/octet-stream', disk_format: 'raw', arch: 'x86_64',
    os_variant: null, config_digest: `sha256:${'a'.repeat(64)}`, chain_id: null,
    parent_digest: null, base_image_digest: null, name: `layer-${index}`, kind: 'cloud-image',
    ubuntu_base: '24.04', python_version: null, config_json: {}, project_id: 'project-a',
    is_published: false, created_by: 'user-a', created_at: '2026-10-15T00:00:00Z',
  }));
  const layers = vi.spyOn(hubApi, 'layers').mockResolvedValue(rows);
  permissions.set({ permissions: { is_owner: false, is_manager: false, can_write: true, service_permissions: { palimpsest: ['palimpsest-inventory_reader'] } }, loading: false, error: '' });
  render(HubArtifactsPanel, { identity: { token: 'browser-jwt', projectId: 'project-a', userId: 'user-a' } });
  await screen.findByText('layer-0');
  const search = document.getElementById('hub-artifact-regex') as HTMLInputElement;
  await fireEvent.input(search, { target: { value: '^layer-(0|1)$' } });
  expect(screen.queryByText('layer-2')).toBeNull();
  expect(layers).toHaveBeenCalledOnce();
  await fireEvent.click(screen.getByRole('button', { name: hubText('next') }));
  await waitFor(() => expect(layers).toHaveBeenLastCalledWith(expect.anything(), expect.any(AbortSignal), {}, HUB_PAGE_SIZE));
  await screen.findByText('layer-0');
  await fireEvent.click(screen.getByRole('button', { name: commonText('table.filterColumn', { column: hubText('filter.kind') }) }));
  const kindMenu = within(screen.getByRole('dialog', { name: commonText('table.filterColumn', { column: hubText('filter.kind') }) }));
  await fireEvent.click(kindMenu.getByRole('checkbox', { name: 'squashfs' }));
  await waitFor(() => expect(layers).toHaveBeenLastCalledWith(expect.anything(), expect.any(AbortSignal), { kind: 'squashfs' }, 0));
  if (screen.queryByRole('dialog')) await fireEvent.click(kindMenu.getByRole('button', { name: commonText('actions.close') }));
  await screen.findByText('layer-0');
  await fireEvent.click(screen.getByRole('button', { name: commonText('table.filterColumn', { column: hubText('filter.arch') }) }));
  const archMenu = within(screen.getByRole('dialog', { name: commonText('table.filterColumn', { column: hubText('filter.arch') }) }));
  await fireEvent.click(archMenu.getByRole('checkbox', { name: 'aarch64' }));
  await waitFor(() => expect(layers).toHaveBeenLastCalledWith(expect.anything(), expect.any(AbortSignal), { kind: 'squashfs', arch: 'aarch64' }, 0));
  if (screen.queryByRole('dialog')) await fireEvent.click(archMenu.getByRole('button', { name: commonText('actions.close') }));
  await screen.findByText('layer-0');
  expect(search.value).toBe('^layer-(0|1)$');
  await fireEvent.click(screen.getAllByRole('button', { name: hubText('refresh') })[0]);
  await waitFor(() => expect(layers).toHaveBeenLastCalledWith(expect.anything(), expect.any(AbortSignal), { kind: 'squashfs', arch: 'aarch64' }, 0));
  expect(search.value).toBe('^layer-(0|1)$');
  expect(screen.getByText('layer-0')).toBeTruthy();
});

it('sorts and facets offset-free native UTC and explicit-offset activity times by the same instant', async () => {
  initLocale('en');
  const details: Omit<HubModule.HubExport, 'id' | 'source_name' | 'created_at'> = {
    source_image_id: 'source', source_disk_format: 'qcow2', source_size_bytes: 1024,
    target_disk_format: 'raw', status: 'complete', progress_pct: 100, error_code: null,
    error_message: null, blob_digest: null, size_bytes: 1024, filename: null, download_path: null,
    started_at: null, completed_at: null,
  };
  vi.spyOn(hubApi, 'exports').mockResolvedValue([
    { ...details, id: 'native', source_name: 'native-later', created_at: '2026-10-15T10:00:00' },
    { ...details, id: 'earlier', source_name: 'explicit-earlier', created_at: '2026-10-15T05:00:00Z' },
    { ...details, id: 'same', source_name: 'explicit-same', created_at: '2026-10-15T19:00:00+09:00' },
  ]);
  permissions.set({ permissions: { is_owner: false, is_manager: false, can_write: true, service_permissions: { palimpsest: ['palimpsest-inventory_reader'] } }, loading: false, error: '' });
  render(HubArtifactsPanel, { identity: { token: 'browser-jwt', projectId: 'project-a', userId: 'user-a' } });
  await screen.findByText('native-later');
  const exports = within(screen.getByRole('region', { name: hubText('exports') }));
  await fireEvent.click(exports.getByRole('button', { name: commonText('table.sortColumn', { column: hubText('jobs.created'), direction: commonText('table.none') }) }));
  expect(exports.getAllByRole('listitem').map(item => within(item).getByText(/^(native-later|explicit-earlier|explicit-same)$/).textContent))
    .toEqual(['explicit-earlier', 'native-later', 'explicit-same']);
  await fireEvent.click(exports.getByRole('button', { name: commonText('table.filterColumn', { column: hubText('jobs.created') }) }));
  const menu = within(screen.getByRole('dialog', { name: commonText('table.filterColumn', { column: hubText('jobs.created') }) }));
  expect(menu.getAllByRole('checkbox')).toHaveLength(2);
});
