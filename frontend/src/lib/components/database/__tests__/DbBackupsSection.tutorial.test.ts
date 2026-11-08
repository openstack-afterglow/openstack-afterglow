import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type * as ClientModule from '$lib/api/client';
import type * as AuthModule from '$lib/stores/auth';
import { t } from '$lib/i18n/ns/database';
import DbInstanceDetailPanel from '../DbInstanceDetailPanel.svelte';

const session = vi.hoisted(() => ({ mockup: false }));
const transport = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('$app/state', () => ({ page: { get data() { return { mockup: { active: session.mockup } }; } } }));
vi.mock('$lib/stores/auth', async (importOriginal) => {
	const actual = await importOriginal<typeof AuthModule>();
	return { ...actual, isMockAuthActive: () => session.mockup };
});
vi.mock('$lib/api/client', async (importOriginal) => {
	const actual = await importOriginal<typeof ClientModule>();
	return { ...actual, api: { get: transport.get, post: transport.post, withExperience() { return this; } } };
});
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({ active: false, intervalSeconds: 15, intervalOptions: [10, 15, 30, 60] }),
}));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: vi.fn() }));
vi.mock('$lib/stores/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const INSTANCE = { id: 'db-a', name: 'sample-customer-mysql', status: 'ACTIVE', datastore: { type: 'mysql', version: '8.0' }, flavor_id: '101', size: 20, created_at: '2026-07-09T00:00:00Z' };

beforeEach(() => {
	vi.clearAllMocks();
	transport.get.mockImplementation((path: string) => {
		if (path === '/api/v1/database-instances/db-a') return Promise.resolve(INSTANCE);
		if (path.endsWith('/auto-backup')) return Promise.reject(new Error('none'));
		return Promise.resolve([]);
	});
	transport.post.mockResolvedValue({ id: 'backup-new', name: 'created', status: 'NEW', size: 0, created_at: '2026-07-09T00:00:00Z' });
});

async function openBackupForm(): Promise<HTMLInputElement> {
	render(DbInstanceDetailPanel, { instanceId: 'db-a', token: 'token-a', projectId: 'project-a' });
	await fireEvent.click(await screen.findByRole('button', { name: t('actions.createBackup') }));
	return screen.getByPlaceholderText(t('backups.namePlaceholder', { name: INSTANCE.name })) as HTMLInputElement;
}

function postedName(): string {
	const [path, body] = transport.post.mock.calls[0] as [string, { name: string }];
	expect(path).toBe('/api/v1/database-instances/db-a/backups');
	return body.name;
}

describe('database backup tutorial naming', () => {
	it('prefills and creates a tut- backup in tutorial sessions, even when the name is cleared', async () => {
		session.mockup = true;
		const input = await openBackupForm();
		expect(input.value).toMatch(/^tut-sample-customer-mysql-\d{8}-\d{6}$/);
		await fireEvent.input(input, { target: { value: '' } });
		await fireEvent.click(screen.getByRole('button', { name: t('actions.backup') }));
		await waitFor(() => expect(transport.post).toHaveBeenCalledTimes(1));
		expect(postedName()).toMatch(/^tut-sample-customer-mysql-\d{8}-\d{6}$/);
	});

	it('keeps the ordinary generated name outside tutorial sessions', async () => {
		session.mockup = false;
		const input = await openBackupForm();
		expect(input.value).toBe('');
		await fireEvent.click(screen.getByRole('button', { name: t('actions.backup') }));
		await waitFor(() => expect(transport.post).toHaveBeenCalledTimes(1));
		expect(postedName()).toMatch(/^sample-customer-mysql-\d{8}-\d{6}$/);
	});
});
