import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import type { Writable } from 'svelte/store';
import type * as SvelteStore from 'svelte/store';
import HubArtifactsPanel from './HubArtifactsPanel.svelte';
import { projectPermissions } from '$lib/stores/servicePermissions';
import type { ProjectPermissions } from '$lib/stores/servicePermissions';
import type * as HubModule from '$lib/api/palimpsestHub';
import { hubApi } from '$lib/api/palimpsestHub';
import { getLocale, initLocale } from '$lib/i18n/runtime.svelte';

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
  vi.stubEnv('TZ', 'Asia/Seoul');
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
  const localTime = (hour: number) => new Date(Date.UTC(2026, 9, 15, hour)).toLocaleString('en-US', { timeZone: 'Asia/Seoul' });
  expect(displayed).toEqual([localTime(0), localTime(1), localTime(3)]);
  expect(job.closest('section')!.querySelector(':scope > p')?.textContent).toContain(localTime(4));
});
