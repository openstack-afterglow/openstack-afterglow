import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import { t as common } from '$lib/i18n/ns/common';
import { t as database } from '$lib/i18n/ns/database';

const { mockGet, mockPrefetch, mockDelete } = vi.hoisted(() => ({
	mockGet: vi.fn(),
	mockPrefetch: vi.fn(),
	mockDelete: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('$lib/api/client', () => ({
	api: {
		get: mockGet,
		prefetch: mockPrefetch,
		post: vi.fn(),
		delete: mockDelete,
	},
	ApiError: class ApiError extends Error { status = 500; },
}));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token', projectId: 'project' }),
}));
vi.mock('$lib/stores/authDisplayContext', () => ({
	authDisplayContext: writable({ key: 'database-backup-owner', project: 'project', ready: true }),
}));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({
		active: false,
		intervalSeconds: 15,
		intervalOptions: [10, 15, 30, 60],
	}),
}));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: vi.fn().mockResolvedValue(true) }));

import Page from '../+page.svelte';

describe('database backup restore intent', () => {
	beforeEach(() => {
		mockGet.mockReset();
		mockPrefetch.mockReset().mockResolvedValue(undefined);
		mockGet.mockImplementation((path: string) => {
			if (path === '/api/v1/database-instances/backups') {
				return Promise.resolve([{
					id: 'backup-1',
					name: 'daily-backup',
					status: 'COMPLETED',
					size: 10,
					created_at: '2026-01-01T00:00:00Z',
				}]);
			}
			if (path === '/api/v1/database-instances') return Promise.resolve([]);
			if (path === '/api/v1/database-instances/flavors') return Promise.resolve([]);
			throw new Error(`unexpected GET ${path}`);
		});
	});

	it('does not load restore flavors initially, then prefetches on intent and loads on click', async () => {
		render(Page);
		const restore = await screen.findByRole('button', { name: '복원' });
		expect(mockGet).toHaveBeenCalledTimes(2);
		expect(mockGet.mock.calls.some((call) => call[0].endsWith('/flavors'))).toBe(false);

		await fireEvent.pointerEnter(restore);
		expect(mockPrefetch).toHaveBeenCalledWith(
			'/api/v1/database-instances/flavors',
			'token',
			'project',
		);

		await fireEvent.click(restore);
		await vi.waitFor(() => expect(mockGet.mock.calls.some((call) => call[0].endsWith('/flavors'))).toBe(true));
	});
});

describe('database backup view refresh', () => {
	it('keeps regex, filter and descending sort while refresh replaces rows, including empty projections', async () => {
		mockGet.mockImplementation((path: string) => Promise.resolve(path.endsWith('/backups') ? [
			{ id: 'daily-a', name: 'daily-a', status: 'COMPLETED', size: 10, created_at: '2026-01-01T00:00:00Z' },
			{ id: 'weekly-b', name: 'weekly-b', status: 'FAILED', size: 30, created_at: '2026-01-02T00:00:00Z' },
		] : []));
		render(Page);
		await screen.findByText('daily-a');
		const search = screen.getByRole('searchbox', { name: common('table.search') }) as HTMLInputElement;
		await fireEvent.input(search, { target: { value: '^daily' } });
		const table = screen.getByRole('table');
		await fireEvent.click(within(table).getByRole('button', { name: common('table.sortColumn', { column: database('labels.size'), direction: common('table.none') }) }));
		await fireEvent.click(within(table).getByRole('button', { name: common('table.sortColumn', { column: database('labels.size'), direction: common('table.ascending') }) }));
		await fireEvent.click(within(table).getByRole('button', { name: common('table.filterColumn', { column: database('labels.status') }) }));
		await fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: common('table.selectAll') }));
		await fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
		mockGet.mockImplementation((path: string) => Promise.resolve(path.endsWith('/backups') ? [
			{ id: 'daily-new', name: 'daily-new', status: 'FAILED', size: 25, created_at: '2026-01-03T00:00:00Z' },
		] : []));
		await fireEvent.click(screen.getByRole('button', { name: common('autoRefresh.refreshNow') }));
		await screen.findByText(common('table.noMatches'));
		expect(search.value).toBe('^daily');
		expect(table.querySelector('th[aria-sort="descending"]')).toBeTruthy();
		expect(within(table).queryByText('daily-new')).toBeNull();
		await fireEvent.click(within(table).getByRole('button', { name: common('table.filterColumn', { column: database('labels.status') }) }));
		expect((within(screen.getByRole('dialog')).getByRole('checkbox', { name: 'COMPLETED' }) as HTMLInputElement).checked).toBe(true);
		await fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: common('table.resetFilter') }));
		await fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
		await waitFor(() => expect(within(table).getByText('daily-new')).toBeTruthy());
		await fireEvent.input(search, { target: { value: '[' } });
		expect(screen.getByText(common('table.regexError'))).toBeTruthy();
		expect(within(table).getAllByRole('row')).toHaveLength(1);
	});
});

describe('database backup visible selection', () => {
	it('drops hidden selections before bulk deletion', async () => {
		mockDelete.mockClear();
		mockGet.mockImplementation((path: string) => Promise.resolve(path.endsWith('/backups') ? [
			{ id: 'backup-a', name: 'daily-a', status: 'COMPLETED', size: 10, created_at: '2026-01-01T00:00:00Z' },
			{ id: 'backup-b', name: 'weekly-b', status: 'COMPLETED', size: 20, created_at: '2026-01-02T00:00:00Z' },
		] : []));
		render(Page);
		await screen.findByText('daily-a');
		await fireEvent.click(screen.getByRole('checkbox', { name: database('selection.item', { name: 'daily-a' }) }));
		expect(screen.getByRole('region', { name: database('backups.bulkLabel') })).toBeTruthy();
		await fireEvent.input(screen.getByRole('searchbox', { name: common('table.search') }), { target: { value: '^weekly-b$' } });
		await waitFor(() => expect(screen.queryByRole('region', { name: database('backups.bulkLabel') })).toBeNull());
		await fireEvent.click(screen.getByRole('checkbox', { name: database('selection.item', { name: 'weekly-b' }) }));
		await fireEvent.click(within(screen.getByRole('region', { name: database('backups.bulkLabel') })).getByRole('button', { name: database('actions.delete') }));
		await waitFor(() => expect(mockDelete).toHaveBeenCalledWith('/api/v1/database-instances/backups/backup-b', 'token', 'project'));
		expect(mockDelete.mock.calls.some(([path]) => path.endsWith('/backup-a'))).toBe(false);
	});
});
