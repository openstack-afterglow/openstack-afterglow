import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushSync, tick } from 'svelte';
import { ApiError } from '$lib/api/client';
import type * as ClientModule from '$lib/api/client';
import { t } from '$lib/i18n/ns/database';
import DbInstanceDetailPanel from '../DbInstanceDetailPanel.svelte';
import { t as common } from '$lib/i18n/ns/common';

const transport = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('$lib/api/client', async (importOriginal) => {
	const actual = await importOriginal<typeof ClientModule>();
	return { ...actual, api: { get: transport.get, withExperience() { return this; } } };
});
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({ active: false, intervalSeconds: 15, intervalOptions: [10, 15, 30, 60] }),
}));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: vi.fn() }));
vi.mock('$lib/stores/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

beforeEach(() => { vi.clearAllMocks(); });

function serveEmptyCatalog(status: number) {
	const reads = new Map<string, number>();
	transport.get.mockImplementation((path: string, token?: string, project?: string) => {
		const key = JSON.stringify([path, token, project]);
		const count = (reads.get(key) ?? 0) + 1;
		reads.set(key, count);
		// Bound the failing-before effect: an unintended repeat cannot create an endless test loop.
		if (count > 1) return new Promise(() => {});
		if (/\/database-instances\/db-[ab]$/.test(path)) {
			return Promise.reject(new ApiError(status, 'PRIVATE-UPSTREAM-DETAIL'));
		}
		return Promise.resolve([]);
	});
	return reads;
}

async function settleAssignments() {
	await tick();
	flushSync();
	await tick();
}

describe('database detail read lifecycle', () => {
	it.each([404, 503])('does not reload after an empty flavor response and keeps HTTP%s outcome honest', async (status) => {
		const reads = serveEmptyCatalog(status);
		render(DbInstanceDetailPanel, { instanceId: 'db-a', token: 'token-a', projectId: 'project-a' });
		await screen.findByText(t(status === 404 ? 'instance.notFound' : 'instances.loadFailed'));
		await settleAssignments();
		expect(reads.get(JSON.stringify(['/api/v1/database-instances/flavors', 'token-a', 'project-a']))).toBe(1);
		expect(reads.get(JSON.stringify(['/api/v1/database-instances/db-a', 'token-a', 'project-a']))).toBe(1);
		expect(screen.queryByText('PRIVATE-UPSTREAM-DETAIL')).toBeNull();
		if (status === 503) {
			expect(screen.queryByText(t('instance.notFound'))).toBeNull();
			expect(screen.getByRole('alert').textContent).toContain(t('instances.loadFailed'));
		}
	});

	it.each(['instanceId', 'token', 'projectId'] as const)('still reloads once when the %s input changes', async (field) => {
		serveEmptyCatalog(404);
		const original = { instanceId: 'db-a', token: 'token-a', projectId: 'project-a' };
		const panel = render(DbInstanceDetailPanel, original);
		await screen.findByText(t('instance.notFound'));
		await settleAssignments();
		const before = transport.get.mock.calls.filter(([path]) => path === '/api/v1/database-instances/db-a').length;
		expect(before).toBe(1);
		const next = { ...original, [field]: field === 'instanceId' ? 'db-b' : field === 'token' ? 'token-b' : 'project-b' };
		await panel.rerender(next);
		await waitFor(() => expect(transport.get.mock.calls.filter(([path, token, project]) =>
			path === `/api/v1/database-instances/${next.instanceId}` && token === next.token && project === next.projectId
		)).toHaveLength(1));
		await settleAssignments();
		expect(transport.get.mock.calls.filter(([path, token, project]) =>
			path === `/api/v1/database-instances/${next.instanceId}` && token === next.token && project === next.projectId
		)).toHaveLength(1);
	});
});

describe('database detail table conditions', () => {
	it('preserves regex, exact filters and sorting across bearer refresh and resets on a new instance', async () => {
		const backup = { id: 'backup-a', name: 'daily-primary', status: 'COMPLETED', size: 10, created_at: '2026-01-01T00:00:00Z' };
		transport.get.mockImplementation((path: string) => {
			if (/\/database-instances\/db-[ab]$/.test(path)) return Promise.resolve({
				id: path.endsWith('db-b') ? 'db-b' : 'db-a', name: 'database-parent', status: 'ACTIVE',
				datastore: { type: 'mysql', version: '8.0' }, flavor_id: 'small', size: 20, created_at: '2026-01-01T00:00:00Z',
			});
			if (path.endsWith('/backups')) return Promise.resolve([backup, { ...backup, id: 'backup-b', name: 'weekly-secondary', status: 'FAILED', size: 30 }]);
			if (path.endsWith('/users')) return Promise.resolve([{ name: 'app-user', host: '%', databases: [{ name: 'app-data' }] }]);
			if (path.endsWith('/databases')) return Promise.resolve([{ name: 'app-data', character_set: 'utf8', collate: 'utf8_general_ci' }]);
			if (path.endsWith('/auto-backup')) return Promise.resolve(null);
			return Promise.resolve([]);
		});
		const panel = render(DbInstanceDetailPanel, { instanceId: 'db-a', token: 'token-a', projectId: 'project-a' });
		await waitFor(() => expect(panel.container.querySelector('#database-detail-backups-search')).toBeTruthy());
		const backupSearch = panel.container.querySelector('#database-detail-backups-search') as HTMLInputElement;
		const userSearch = panel.container.querySelector('#database-detail-users-search') as HTMLInputElement;
		const databaseSearch = panel.container.querySelector('#database-detail-databases-search') as HTMLInputElement;
		await fireEvent.input(backupSearch, { target: { value: '^daily|^weekly' } });
		await fireEvent.input(userSearch, { target: { value: '^app-' } });
		await fireEvent.input(databaseSearch, { target: { value: '^app-data$' } });
		const table = screen.getByRole('table');
		await fireEvent.click(within(table).getByRole('button', { name: common('table.sortColumn', { column: t('labels.size'), direction: common('table.none') }) }));
		await fireEvent.click(within(table).getByRole('button', { name: common('table.sortColumn', { column: t('labels.size'), direction: common('table.ascending') }) }));
		await fireEvent.click(within(table).getByRole('button', { name: common('table.filterColumn', { column: t('labels.status') }) }));
		await fireEvent.click(within(screen.getByRole('dialog')).getByRole('checkbox', { name: 'FAILED' }));
		await fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
		expect(within(table).queryByText('weekly-secondary')).toBeNull();
		await panel.rerender({ instanceId: 'db-a', token: 'token-renewed', projectId: 'project-a' });
		await settleAssignments();
		expect(backupSearch.value).toBe('^daily|^weekly');
		expect(userSearch.value).toBe('^app-');
		expect(databaseSearch.value).toBe('^app-data$');
		expect(within(screen.getByRole('table')).queryByText('weekly-secondary')).toBeNull();
		expect(screen.getByRole('table').querySelector('th[aria-sort="descending"]')).toBeTruthy();
		await fireEvent.input(backupSearch, { target: { value: '[' } });
		expect(within(screen.getByRole('table')).getAllByRole('row')).toHaveLength(1);
		expect(screen.getByText(common('table.regexError'))).toBeTruthy();
		await fireEvent.input(backupSearch, { target: { value: '^daily' } });
		expect(within(screen.getByRole('table')).getByText('daily-primary')).toBeTruthy();
		await panel.rerender({ instanceId: 'db-b', token: 'token-renewed', projectId: 'project-a' });
		await settleAssignments();
		expect((panel.container.querySelector('#database-detail-backups-search') as HTMLInputElement).value).toBe('');
		expect(within(screen.getByRole('table')).getByText('weekly-secondary')).toBeTruthy();
	});
});
