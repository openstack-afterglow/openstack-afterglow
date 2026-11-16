import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import { SvelteURL } from 'svelte/reactivity';
import type { Volume, VolumeBackup, VolumeSnapshot } from '$lib/types/volume';

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), goto: vi.fn(), url: null as URL | null, refresh: null as (() => Promise<void>) | null }));
vi.mock('$app/state', () => ({ page: { get url() { return mocks.url; }, data: {} } }));
vi.mock('$app/navigation', () => ({ goto: mocks.goto }));
vi.mock('$lib/api/client', () => ({ api: { get: mocks.get, prefetch: vi.fn(), post: mocks.post, delete: vi.fn(), withExperience: () => ({ get: mocks.get }) }, ApiError: class ApiError extends Error {} }));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'token', projectId: 'project-a', userId: 'me', domainId: 'domain-a', canWrite: true, roles: ['member'] }), canWrite: writable(true), projectSwitching: writable(false), isMockAuthActive: () => false }));
vi.mock('$lib/stores/authDisplayContext', () => ({ authDisplayContext: writable({ key: 'owner-a', ready: true }) }));
vi.mock('$lib/stores/betaFeatures', () => ({ betaFeatures: writable({ volumeSnapshots: true }) }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({ createAutoRefresh: (refresh: () => Promise<void>) => { mocks.refresh = refresh; return { active: false, intervalSeconds: 15, intervalOptions: [15] }; } }));
vi.mock('$lib/utils/experience', () => ({ beginExperienceAction: vi.fn(), beginExperienceLoad: vi.fn(), experienceApplied: vi.fn(), experienceDiscarded: vi.fn(), experienceState: vi.fn() }));
vi.mock('$lib/i18n/ns/volume', () => ({ t: (key: string, params?: Record<string, unknown>) => key + (params ? JSON.stringify(params) : '') }));
// Vitest hoists this factory before static component bindings; load the UI stub inside that factory.
vi.mock('$lib/tutorial/TutorialStartButton.svelte', async () => ({ default: (await import('$lib/components/ui/EmptyState.svelte')).default }));

import BackupPage from '../../../../routes/dashboard/volumes/backups/+page.svelte';
import SnapshotPage from '../../../../routes/dashboard/volumes/snapshots/+page.svelte';
import BackupCreate from '../backups/VolumeBackupCreateModal.svelte';
import SnapshotCreate from '../snapshots/VolumeSnapshotCreateModal.svelte';
import { groupRecoveryPoints, hasFullBackup, recoveryCreator, recoveryOrigin, recoveryVolumeName, recoveryVolumeUrl } from '../recoveryPoints';

const volume: Volume = { id: 'volume-a', name: 'Research data', size: 20, status: 'available', attachments: [], volume_type: null };
const full: VolumeBackup = { id: 'full-a', volume_id: volume.id, name: 'Full copy', size: 20, status: 'available', created_at: '2026-11-15T03:00:00Z', description: '', is_incremental: false, has_dependent_backups: false, user_id: 'me', origin: 'manual' };
const daily: VolumeBackup = { ...full, id: 'daily-a', name: 'Automatic daily', is_incremental: true, origin: 'auto', auto_tier: 'daily', user_id: 'system-secret-id', created_at: '2026-11-16T03:00:00Z' };
const snapshot: VolumeSnapshot = { ...full, id: 'snapshot-a', name: 'Snapshot copy', description: '' };

beforeEach(() => {
 cleanup();
 mocks.url = new SvelteURL('http://localhost/dashboard/volumes/backups');
 mocks.goto.mockReset().mockImplementation(async (url: URL) => { mocks.url!.search = url.search; });
 mocks.post.mockReset().mockResolvedValue({ ...full, id: 'created-a' });
 mocks.get.mockReset().mockImplementation(async (path: string) => {
  if (path === '/api/v1/volumes') return [volume];
  if (path.endsWith('/configs')) return [];
  if (path.endsWith('/members')) return { items: [{ user_id: 'other-user', username: 'Alice' }] };
  if (path === '/api/v1/volumes/backups') return [full, daily];
  if (path === '/api/v1/volume-snapshots') return [snapshot];
  throw new Error(path);
 });
});

describe('source volume recovery groups', () => {
 it('groups deleted volumes, retains zero-point volumes and sorts latest points newest first', () => {
  const deleted = { ...full, id: 'orphan-a', volume_id: 'deleted-volume' };
  const groups = groupRecoveryPoints([volume, { ...volume, id: 'empty-volume' }], [full, deleted, daily]);
  expect(groups.find(group => group.id === volume.id)?.points.map(point => point.id)).toEqual(['daily-a', 'full-a']);
  expect(groups.find(group => group.id === volume.id)?.latest).toBe(daily.created_at);
  const orphan = groups.find(group => group.id === 'deleted-volume')!;
  expect(orphan.volume).toBeNull();
  expect(orphan.points).toHaveLength(1);
  expect(recoveryVolumeName(orphan)).toContain('backupGroups.deletedVolume');
  expect(recoveryVolumeName(orphan, false)).toContain('backupGroups.unknownVolume');
  expect(groups.find(group => group.id === 'empty-volume')?.points).toEqual([]);
 });
 it('labels origin and creator without exposing an automatic system identity', () => {
  expect(recoveryOrigin(daily)).toContain('backupGroups.automaticTier');
  expect(recoveryOrigin(full)).toBe('backupGroups.manual');
  expect(recoveryCreator(daily, 'me')).not.toContain('system-secret-id');
  expect(recoveryCreator(full, 'me')).toBe('backupGroups.me');
  expect(recoveryCreator({ user_id: 'other-user' }, 'me', { 'other-user': 'Alice' })).toBe('Alice');
  expect(recoveryCreator({ user_id: 'unknown-user' }, 'me')).toBe('unknown-');
 });
 it('preserves unrelated query state and clears only recovery selection on back', () => {
  const initial = new URL('https://example.test/dashboard/volumes/backups?sort=name&auto-backup=old');
  const detail = recoveryVolumeUrl(initial, 'volume / a');
  expect(detail.searchParams.get('volume')).toBe('volume / a');
  expect(detail.searchParams.get('auto-backup')).toBeNull();
  expect(recoveryVolumeUrl(detail, null).search).toBe('?sort=name');
  expect(initial.searchParams.get('auto-backup')).toBe('old');
 });
});

describe('explicit creation methods', () => {
 it('preselects volume and disables incremental until an available full backup exists for that exact volume', async () => {
  const props = { open: true, volumes: [volume], initialVolumeId: volume.id, onCreate: vi.fn().mockResolvedValue(true) };
  const view = render(BackupCreate, { ...props, backups: [daily, { ...full, volume_id: 'other' }] });
  const incremental = () => screen.getByRole('radio', { name: 'backupListTable.incremental' }) as HTMLInputElement;
  expect((screen.getByRole('combobox') as HTMLSelectElement).value).toBe(volume.id);
  expect(incremental().disabled).toBe(true);
  expect(screen.getByText('backupGroups.fullRequired')).toBeTruthy();
  expect(hasFullBackup([{ ...full, status: 'creating' }], volume.id)).toBe(false);
  await view.rerender({ ...props, backups: [full, daily] });
  expect(incremental().disabled).toBe(false);
  await fireEvent.click(incremental());
  await fireEvent.input(screen.getByRole('textbox', { name: 'backupCreateModal.nameLabel' }), { target: { value: 'Changes' } });
  await fireEvent.click(screen.getByRole('button', { name: 'backupCreateModal.create' }));
  expect(props.onCreate).toHaveBeenCalledWith(expect.objectContaining({ volume_id: volume.id, incremental: true }));
 });
 it('explains CoW and links to a full backup for the selected volume', () => {
  render(SnapshotCreate, { open: true, volumes: [volume], initialVolumeId: volume.id, onCreate: vi.fn() });
  expect(screen.getByText('snapshotGroups.methodHelp')).toBeTruthy();
  expect(screen.getByRole('link', { name: 'snapshotGroups.fullBackup' }).getAttribute('href')).toBe('/dashboard/volumes/backups?volume=volume-a');
 });
});

it.each([['backup', BackupPage], ['snapshot', SnapshotPage]] as const)('%s starts with volumes and opens only selected volume rows through URL state', async (kind, Page) => {
 render(Page);
 await screen.findByRole('button', { name: volume.name });
 expect(screen.queryByText('Full copy')).toBeNull();
 expect(screen.queryByText('Snapshot copy')).toBeNull();
 await fireEvent.click(screen.getByRole('button', { name: volume.name }));
 await waitFor(() => expect(mocks.url!.searchParams.get('volume')).toBe(volume.id));
 await screen.findAllByText(kind === 'backup' ? 'Full copy' : 'Snapshot copy');
 const rows = screen.getAllByRole('row');
 expect(within(rows[0]).getByText('backupGroups.creator')).toBeTruthy();
 expect(screen.getAllByText('backupGroups.me').length).toBeGreaterThan(0);
 if (kind === 'backup') {
  expect(screen.getAllByText('backupListTable.full').length).toBeGreaterThan(0);
  expect(screen.getAllByText('backupListTable.incremental').length).toBeGreaterThan(0);
  expect(screen.queryByText('system-secret-id')).toBeNull();
 } else expect(screen.getAllByText('snapshotGroups.method').length).toBeGreaterThan(0);
 await fireEvent.click(screen.getByRole('button', { name: 'backupGroups.back' }));
 await screen.findByRole('button', { name: volume.name });
 expect(mocks.url!.searchParams.has('volume')).toBe(false);
});

it.each([['backup', BackupPage], ['snapshot', SnapshotPage]] as const)('%s opens direct volume URLs after refresh', async (kind, Page) => {
 mocks.url!.search = '?volume=volume-a';
 render(Page);
 await screen.findAllByText(kind === 'backup' ? 'Full copy' : 'Snapshot copy');
 expect(screen.queryByRole('button', { name: volume.name })).toBeNull();
 expect(screen.getByRole('button', { name: 'backupGroups.back' })).toBeTruthy();
});

it.each([['backup', BackupPage], ['snapshot', SnapshotPage]] as const)('%s creation opens its source detail so tutorial delete anchors stay reachable', async (kind, Page) => {
 render(Page);
 await screen.findByRole('button', { name: volume.name });
 await fireEvent.click(screen.getByRole('button', { name: kind === 'backup' ? 'backupsPage.create' : 'snapshotsPage.create' }));
 const prefix = kind === 'backup' ? 'backupCreateModal' : 'snapshotCreateModal';
 await fireEvent.change(screen.getByRole('combobox', { name: `${prefix}.volumeLabel` }), { target: { value: volume.id } });
 await fireEvent.input(screen.getByRole('textbox', { name: `${prefix}.nameLabel` }), { target: { value: 'New recovery point' } });
 await fireEvent.click(screen.getByRole('button', { name: `${prefix}.create` }));
 await waitFor(() => expect(mocks.url!.searchParams.get('volume')).toBe(volume.id));
 expect(mocks.post).toHaveBeenCalledWith(kind === 'backup' ? '/api/v1/volumes/backups' : '/api/v1/volume-snapshots', expect.objectContaining({ volume_id: volume.id }), 'token', 'project-a');
 await screen.findAllByText(kind === 'backup' ? 'Full copy' : 'Snapshot copy');
});

it.each([['backup', BackupPage], ['snapshot', SnapshotPage]] as const)('%s retains settled policy and deleted-volume labels during background refresh', async (kind, Page) => {
 const orphan = { ...full, id: 'orphan', volume_id: 'deleted-volume' };
 const baseGet = mocks.get.getMockImplementation()!;
 const policy = { volume_id: volume.id, project_id: 'project-a', enabled: true };
 mocks.get.mockImplementation(async (path: string) => path.endsWith('/configs') ? [policy] : path === (kind === 'backup' ? '/api/v1/volumes/backups' : '/api/v1/volume-snapshots') ? [full, orphan] : baseGet(path));
 render(Page);
 await screen.findByText('backupGroups.policyActive');
 const deletedName = 'backupGroups.deletedVolume' + JSON.stringify({ id: 'deleted-' });
 expect(screen.getByRole('button', { name: deletedName })).toBeTruthy();
 const { promise: pending, resolve: finish } = Promise.withResolvers<unknown[]>();
 mocks.get.mockImplementation((path: string) => path.endsWith('/configs') ? pending : Promise.resolve(path === (kind === 'backup' ? '/api/v1/volumes/backups' : '/api/v1/volume-snapshots') ? [full, orphan] : baseGet(path)));
 const refresh = mocks.refresh!();
 await waitFor(() => expect(mocks.get).toHaveBeenCalledWith(expect.stringContaining('/configs'), 'token', 'project-a'));
 expect(screen.getByText('backupGroups.policyActive')).toBeTruthy();
 expect(screen.queryByText('backupGroups.policyUnknown')).toBeNull();
 expect(screen.getByRole('button', { name: deletedName })).toBeTruthy();
 finish([policy]);
 await refresh;
});
