import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { writable, type Writable } from 'svelte/store';
import { tick } from 'svelte';
import type { Volume } from '$lib/types/volume';
import type { VolumeBackupPolicy, VolumeBackupPolicyInput } from '$lib/types/volumeBackupPolicy';

const { get, post, remove, confirm } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), remove: vi.fn(), confirm: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: { get, post, delete: remove, prefetch: vi.fn() }, ApiError: class ApiError extends Error {} }));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'token-a', projectId: 'project-a', userId: 'member' }), canWrite: writable(true), projectSwitching: writable(false) }));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: confirm }));
vi.mock('$lib/i18n/ns/volume', () => ({ t: (key: string, values?: Record<string, unknown>) => values?.name ? `${key}:${values.name}` : key }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({ createAutoRefresh: () => ({ active: false, intervalSeconds: 15, intervalOptions: [10, 15, 30, 60] }) }));
vi.mock('$app/state', () => ({ page: { url: new URL('http://localhost/dashboard/volumes/backups') } }));

import { auth, canWrite, projectSwitching } from '$lib/stores/auth';
import { page } from '$app/state';
import Page from '../+page.svelte';

const actor = auth as unknown as Writable<{ token: string | null; projectId: string | null; userId: string }>;
const writableAccess = canWrite as Writable<boolean>;
const base = '/api/v1/volumes/backups/auto-backup';
const available: Volume = { id: 'volume-a', name: 'Data', status: 'available', size: 20, volume_type: null, attachments: [] };
const attached: Volume = { ...available, status: 'in-use', attachments: [{ server_id: 'vm-a' }] };
const other: Volume = { ...attached, id: 'volume-b', name: 'Other' };
const saved = (changes: Partial<VolumeBackupPolicy> = {}): VolumeBackupPolicy => ({
	volume_id: available.id, project_id: 'project-a', max_daily: 2, max_weekly: 2, max_monthly: 1, enabled: true,
	schedule_time: '05:30', timezone: 'Asia/Seoul', weekly_day: 2, monthly_day: 12, force: false,
	created_at: '2026-10-12T00:00:00Z', updated_at: '2026-10-12T00:00:00Z', next_run_at: '2026-10-13T20:30:00Z', next_tier: 'daily',
	last_run_at: '2026-10-12T20:30:00Z', last_status: 'available', last_backup_id: 'completed-real-id', last_error: null,
	...changes,
});
function deferred<T>() {
	let resolve!: (value: T) => void;
	const promise = new Promise<T>((done) => { resolve = done; });
	return { promise, resolve };
}
const editor = () => within(screen.getByTestId('auto-backup-policy-editor'));
const saveButton = () => screen.getByRole('button', { name: 'autoPolicy.save' }) as HTMLButtonElement;
async function input(label: string, value: string) { await fireEvent.input(editor().getByLabelText(label), { target: { value } }); }
async function source(value: string) { await fireEvent.change(editor().getByLabelText('autoPolicy.source'), { target: { value } }); }
async function openSettings() {
	await waitFor(() => expect((screen.getByRole('button', { name: 'autoPolicy.settings' }) as HTMLButtonElement).disabled).toBe(false));
	await fireEvent.click(screen.getByRole('button', { name: 'autoPolicy.settings' }));
}

beforeEach(() => {
	actor.set({ token: 'token-a', projectId: 'project-a', userId: 'member' });
	writableAccess.set(true); projectSwitching.set(false);
	page.url.search = '';
	get.mockReset(); post.mockReset(); remove.mockReset(); confirm.mockReset();
	get.mockImplementation((path: string) => Promise.resolve(path === '/api/v1/volumes' ? [available, other] : []));
	post.mockImplementation((path: string, body: VolumeBackupPolicyInput) => Promise.resolve(path === `${base}/configs` ? [] : saved({ ...body, volume_id: decodeURIComponent(path.split('/').at(-1)!) })));
	remove.mockResolvedValue(undefined); confirm.mockResolvedValue(true);
});

describe('scheduled backup settings', () => {
	it('creates a source calendar policy and displays backend next/last/result rather than an immediate backup', async () => {
		render(Page); await openSettings(); await source('volume-a');
		await input('autoPolicy.time', '21:45'); await input('autoPolicy.timezone', 'UTC');
		await input('autoPolicy.daily', '4'); await input('autoPolicy.weekly', '0'); await input('autoPolicy.monthly', '3');
		await fireEvent.change(editor().getByLabelText('autoPolicy.weeklyDay'), { target: { value: '4' } });
		await input('autoPolicy.monthlyDay', '28');
		await fireEvent.click(saveButton());
		await waitFor(() => expect(screen.queryByTestId('auto-backup-policy-editor')).toBeNull());
		expect(post).toHaveBeenCalledWith(`${base}/volume-a`, { max_daily: 4, max_weekly: 0, max_monthly: 3, enabled: true, schedule_time: '21:45', timezone: 'UTC', weekly_day: 4, monthly_day: 28, force: false }, 'token-a', 'project-a');
		expect(screen.getByText('completed-real-id')).toBeTruthy();
		expect(screen.getByText('autoPolicy.status.available')).toBeTruthy();
		expect(screen.getByText('autoPolicy.next').nextElementSibling?.textContent).not.toContain('autoPolicy.noNext');
		expect(post.mock.calls.filter(([path]) => path === '/api/v1/volumes/backups')).toHaveLength(0);
	});

	it('loads a deep-linked saved source, updates schedule/counts and preserves its saved force authorization', async () => {
		page.url.search = '?auto-backup=volume-a';
		get.mockImplementation((path: string) => Promise.resolve(path === '/api/v1/volumes' ? [attached, other] : []));
		post.mockImplementation((path: string, body: VolumeBackupPolicyInput) => Promise.resolve(path === `${base}/configs` ? [saved({ force: true })] : saved({ ...body, last_status: 'skipped', last_error: 'Source not ready', last_backup_id: null })));
		render(Page);
		await screen.findByTestId('auto-backup-policy-editor');
		expect((editor().getByLabelText('autoPolicy.source') as HTMLSelectElement).value).toBe('volume-a');
		expect((editor().getByLabelText('autoPolicy.force') as HTMLInputElement).checked).toBe(true);
		expect((editor().getByLabelText('autoPolicy.time') as HTMLInputElement).value).toBe('05:30');
		await input('autoPolicy.time', '07:10'); await input('autoPolicy.daily', '6');
		await fireEvent.click(saveButton());
		await waitFor(() => expect(screen.queryByTestId('auto-backup-policy-editor')).toBeNull());
		expect(post).toHaveBeenCalledWith(`${base}/volume-a`, expect.objectContaining({ schedule_time: '07:10', max_daily: 6, force: true }), 'token-a', 'project-a');
		expect(screen.getByText('Source not ready')).toBeTruthy(); expect(screen.getByText('autoPolicy.status.skipped')).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: 'autoPolicy.edit:Data' }));
		expect((editor().getByLabelText('autoPolicy.force') as HTMLInputElement).checked).toBe(true);
	});

	it('requires explicit force, resets it for another source and permits saving a paused in-use policy without consent', async () => {
		get.mockImplementation((path: string) => Promise.resolve(path === '/api/v1/volumes' ? [attached, other] : []));
		render(Page); await openSettings(); await source('volume-a');
		expect(saveButton().disabled).toBe(true);
		await fireEvent.click(editor().getByLabelText('autoPolicy.force'));
		expect(saveButton().disabled).toBe(false);
		await source('volume-b');
		expect((editor().getByLabelText('autoPolicy.force') as HTMLInputElement).checked).toBe(false);
		expect(saveButton().disabled).toBe(true);
		await fireEvent.click(editor().getByLabelText('autoPolicy.enabled'));
		expect(saveButton().disabled).toBe(false);
		await fireEvent.click(saveButton());
		await waitFor(() => expect(post).toHaveBeenCalledWith(`${base}/volume-b`, expect.objectContaining({ enabled: false, force: false }), 'token-a', 'project-a'));
	});

	it('saves explicit scheduled force and reuses only that saved policy consent through pause and resume', async () => {
		get.mockImplementation((path: string) => Promise.resolve(path === '/api/v1/volumes' ? [attached] : []));
		render(Page); await openSettings(); await source('volume-a');
		await fireEvent.click(editor().getByLabelText('autoPolicy.force')); await fireEvent.click(saveButton());
		await waitFor(() => expect(screen.queryByTestId('auto-backup-policy-editor')).toBeNull());
		expect(screen.getByText('autoPolicy.forceOn')).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: 'autoPolicy.pause:Data' }));
		await screen.findByRole('button', { name: 'autoPolicy.resume:Data' });
		expect(post).toHaveBeenLastCalledWith(`${base}/volume-a`, expect.objectContaining({ enabled: false, force: true }), 'token-a', 'project-a');
		await fireEvent.click(screen.getByRole('button', { name: 'autoPolicy.resume:Data' }));
		await screen.findByRole('button', { name: 'autoPolicy.pause:Data' });
		expect(post).toHaveBeenLastCalledWith(`${base}/volume-a`, expect.objectContaining({ enabled: true, force: true }), 'token-a', 'project-a');
		await fireEvent.click(screen.getByRole('button', { name: 'autoPolicy.edit:Data' }));
		expect((editor().getByLabelText('autoPolicy.force') as HTMLInputElement).checked).toBe(true);
	});

	it('keeps policy load failures visible and prevents a reader from mutating saved policies', async () => {
		post.mockRejectedValueOnce(new Error('unavailable'));
		render(Page);
		await screen.findByText('autoPolicy.loadFailed');
		expect(screen.queryByText('autoPolicy.empty')).toBeNull();
		post.mockResolvedValue([saved()]);
		await fireEvent.click(screen.getByRole('button', { name: 'autoPolicy.retry' }));
		writableAccess.set(false); await tick();
		await screen.findByText('completed-real-id');
		expect((screen.getByRole('button', { name: 'autoPolicy.settings' }) as HTMLButtonElement).disabled).toBe(true);
		expect((screen.getByRole('button', { name: 'autoPolicy.pause:Data' }) as HTMLButtonElement).disabled).toBe(true);
	});

	it('never transfers a manual-backup acknowledgement into a scheduled source policy', async () => {
		get.mockImplementation((path: string) => Promise.resolve(path === '/api/v1/volumes' ? [attached] : []));
		render(Page);
		await fireEvent.click(screen.getByRole('button', { name: 'backupsPage.create' }));
		await waitFor(() => expect(screen.getByRole('option', { name: 'backupCreateModal.volumeOption:Data' })).toBeTruthy());
		await fireEvent.change(screen.getByRole('combobox', { name: 'backupCreateModal.volumeLabel' }), { target: { value: 'volume-a' } });
		await fireEvent.click(screen.getByRole('checkbox', { name: 'backupForce.enable' }));
		await fireEvent.click(screen.getByRole('button', { name: 'backupCreateModal.cancel' }));
		await openSettings(); await source('volume-a');
		expect((editor().getByLabelText('autoPolicy.force') as HTMLInputElement).checked).toBe(false);
		expect(saveButton().disabled).toBe(true);
	});

	it('opens resume as enabled but blocks an in-use saved policy until force is explicitly authorized', async () => {
		get.mockImplementation((path: string) => Promise.resolve(path === '/api/v1/volumes' ? [attached] : []));
		post.mockImplementation((path: string, body: VolumeBackupPolicyInput) => Promise.resolve(path === `${base}/configs` ? [saved({ enabled: false })] : saved(body)));
		render(Page); await screen.findByRole('button', { name: 'autoPolicy.resume:Data' });
		await fireEvent.click(screen.getByRole('button', { name: 'autoPolicy.resume:Data' }));
		expect((editor().getByLabelText('autoPolicy.enabled') as HTMLInputElement).checked).toBe(true);
		expect(saveButton().disabled).toBe(true);
		await fireEvent.click(editor().getByLabelText('autoPolicy.force'));
		await fireEvent.click(saveButton());
		await waitFor(() => expect(screen.queryByTestId('auto-backup-policy-editor')).toBeNull());
		expect(post).toHaveBeenLastCalledWith(`${base}/volume-a`, expect.objectContaining({ enabled: true, force: true }), 'token-a', 'project-a');
	});

	it('keeps a rejected policy save in the editor without fabricating a saved policy', async () => {
		post.mockImplementation((path: string) => path === `${base}/configs` ? Promise.resolve([]) : Promise.reject(new Error('provider unavailable')));
		render(Page); await openSettings(); await source('volume-a'); await fireEvent.click(saveButton());
		await screen.findByText('autoPolicy.saveFailed');
		expect(screen.getByTestId('auto-backup-policy-editor')).toBeTruthy();
		expect(screen.queryByRole('button', { name: 'autoPolicy.pause:Data' })).toBeNull();
	});

	it('keeps invalid saved metadata and orphan-source errors visible without crashing and allows orphan removal', async () => {
		post.mockResolvedValue([
			saved({ enabled: false, timezone: 'Invalid/Timezone', last_run_at: 'not-a-date', last_status: 'error', last_error: 'Saved policy needs repair.' }),
			saved({ volume_id: 'orphan-volume', enabled: false, source_status: 'missing', source_available: false, source_error: 'Source volume no longer exists.', last_error: null }),
		]);
		render(Page);
		await screen.findByText('Saved policy needs repair.');
		expect(screen.getByText('Source volume no longer exists.')).toBeTruthy();
		expect((screen.getByRole('button', { name: 'autoPolicy.resume:orphan-volume' }) as HTMLButtonElement).disabled).toBe(true);
		const removeOrphan = screen.getByRole('button', { name: 'autoPolicy.remove:orphan-volume' }) as HTMLButtonElement;
		expect(removeOrphan.disabled).toBe(false);
		await fireEvent.click(removeOrphan);
		await waitFor(() => expect(screen.queryByText('Source volume no longer exists.')).toBeNull());
		expect(remove).toHaveBeenCalledWith(`${base}/orphan-volume`, 'token-a', 'project-a');
		expect(screen.getByText('Saved policy needs repair.')).toBeTruthy();
	});

});

describe('policy project/auth transitions', () => {
	it('drops late A→B→A policy results even with the same token and never shows an empty policy area while loading', async () => {
		const old = deferred<VolumeBackupPolicy[]>();
		let lists = 0;
		post.mockImplementation((path: string) => path === `${base}/configs` ? (++lists === 1 ? old.promise : Promise.resolve([saved({ last_backup_id: 'current-run' })])) : Promise.reject(new Error('unexpected mutation')));
		render(Page); await waitFor(() => expect(lists).toBe(1));
		expect(screen.queryByText('autoPolicy.empty')).toBeNull();
		actor.set({ token: 'token-a', projectId: 'project-b', userId: 'member' });
		actor.set({ token: 'token-a', projectId: 'project-a', userId: 'member' });
		await screen.findByText('current-run'); old.resolve([saved({ last_backup_id: 'stale-run' })]); await tick();
		expect(screen.queryByText('stale-run')).toBeNull();
		actor.set({ token: null, projectId: null, userId: 'member' }); await tick();
		expect(screen.queryByText('current-run')).toBeNull();
	});

	it('closes the editor before project rescope and ignores an old save after the new project is ready', async () => {
		const pending = deferred<VolumeBackupPolicy>();
		post.mockImplementation((path: string) => path === `${base}/configs` ? Promise.resolve([]) : pending.promise);
		render(Page); await openSettings(); await source('volume-a'); await fireEvent.click(saveButton());
		projectSwitching.set(true); await tick();
		expect(screen.queryByTestId('auto-backup-policy-editor')).toBeNull();
		actor.set({ token: 'token-b', projectId: 'project-b', userId: 'member' }); projectSwitching.set(false);
		await screen.findByText('autoPolicy.empty'); pending.resolve(saved({ last_backup_id: 'old-save-result' })); await tick();
		expect(screen.queryByText('old-save-result')).toBeNull();
		await openSettings();
		expect((editor().getByLabelText('autoPolicy.source') as HTMLSelectElement).value).toBe('');
		expect((editor().getByLabelText('autoPolicy.force') as HTMLInputElement).checked).toBe(false);
	});
});
