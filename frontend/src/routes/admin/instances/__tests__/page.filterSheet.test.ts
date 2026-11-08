import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import { t as commonT } from '$lib/i18n/ns/common';
import { t } from '$lib/i18n/ns/admin-compute';

const { mockGet, mockPrefetch } = vi.hoisted(() => {
	// Mobile card mode: only the shared 767.98px query matches.
	vi.stubGlobal('matchMedia', (media: string) => ({
		media,
		matches: media.includes('max-width: 767.98px'),
		onchange: null,
		addEventListener: () => undefined,
		removeEventListener: () => undefined,
		dispatchEvent: () => false,
		addListener: () => undefined,
		removeListener: () => undefined,
	}));
	return { mockGet: vi.fn(), mockPrefetch: vi.fn() };
});

vi.mock('$lib/api/client', () => ({ api: { get: mockGet, prefetch: mockPrefetch, post: vi.fn() } }));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'token', projectId: 'project' }) }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({ active: false, intervalSeconds: 15, intervalOptions: [10, 15, 30, 60], setBoost: vi.fn() }),
}));

import Page from '../+page.svelte';

const listRequests = () => mockGet.mock.calls.map(([path]) => String(path)).filter((path) => path.startsWith('/api/v1/admin/all-instances'));

describe('admin instances mobile filter sheet', () => {
	beforeEach(() => {
		mockGet.mockReset().mockImplementation((path: string) => {
			if (path.startsWith('/api/v1/admin/all-instances')) return Promise.resolve({ items: [{ id: 'vm', name: 'Listed instance', status: 'ACTIVE', project_id: 'project' }], next_marker: null });
			if (path.endsWith('/health')) return Promise.resolve(null);
			return Promise.resolve([]);
		});
		mockPrefetch.mockReset().mockResolvedValue(undefined);
	});

	afterEach(() => vi.clearAllMocks());

	it('applies two provider filters and a sort with exactly one list query', async () => {
		render(Page);
		expect(await screen.findByText('Listed instance')).toBeTruthy();
		const before = listRequests().length;

		await fireEvent.click(screen.getByRole('button', { name: new RegExp(`^${commonT('table.filters')}`) }));
		const sheet = screen.getByRole('dialog', { name: commonT('table.filtersTitle') });
		await fireEvent.change(within(sheet).getByRole('combobox', { name: commonT('table.sortBy') }), { target: { value: 'name' } });
		await fireEvent.click(within(sheet).getByRole('button', { name: commonT('table.descending') }));
		await fireEvent.click(within(sheet).getByRole('checkbox', { name: 'SHUTOFF' }));
		const nameSection = within(within(sheet).getByText(commonT('table.filterColumn', { column: t('instances.table.name') })).closest('details') as HTMLElement);
		await fireEvent.input(nameSection.getByRole('textbox', { name: commonT('table.filterValue') }), { target: { value: 'web' } });
		expect(listRequests()).toHaveLength(before);

		await fireEvent.click(within(sheet).getByRole('button', { name: commonT('table.applyQuery') }));
		expect(listRequests()).toHaveLength(before + 1);
		const query = new URL(listRequests().at(-1)!, 'https://example.test').searchParams;
		expect(query.get('name')).toBe('web');
		expect(query.get('status')).toBe('SHUTOFF');
		expect(query.get('sort')).toBe('name_desc');
	});
});
