import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import type { Volume } from '$lib/types/volume';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/volume';
import { t as commonT } from '$lib/i18n/ns/common';

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn(), prefetch: vi.fn() }));
vi.mock('$lib/api/client', () => {
	class ApiError extends Error { constructor(public status: number, message: string) { super(message); } }
	return { api: mocks, ApiError };
});
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token', userId: 'user-a', projectId: 'project-a', canWrite: true, isSystemAdmin: false }),
	canWrite: writable(true), projectSwitching: writable(false),
}));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: (refresh: (force?: boolean) => Promise<void>) => ({ active: false, intervalSeconds: 15, intervalOptions: [10, 15, 30, 60], refresh: () => refresh(true) }),
}));
vi.mock('$lib/stores/betaFeatures', () => ({ betaFeatures: writable({ volumeSnapshots: true }) }));

import Page from '../+page.svelte';

let inventory: Volume[];
const makeVolume = (id: string, name: string, created_at: string | null): Volume => ({ id, name, created_at, status: 'available', size: 20, volume_type: 'ssd', attachments: [] });
const namesInPanel = () => within(document.getElementById('volume-resource-panel')!).getAllByText(/^(Alpha|Bravo|Charlie|Delta)$/).map(element => element.textContent);

beforeAll(() => {
	Element.prototype.animate = vi.fn().mockReturnValue({ finished: Promise.resolve(), cancel: vi.fn(), play: vi.fn() });
	window.matchMedia ??= ((query: string) => ({ matches: false, media: query, onchange: null, addEventListener: () => {}, removeEventListener: () => {}, addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false })) as unknown as typeof window.matchMedia;
});
beforeEach(() => {
	vi.clearAllMocks();
	initLocale('ko');
	inventory = [makeVolume('vol-b', 'Bravo', '2026-10-01T00:00:00Z'), makeVolume('vol-a', 'Alpha', '2026-10-03T00:00:00Z'), makeVolume('vol-c', 'Charlie', null)];
	mocks.get.mockImplementation((path: string) => {
		if (path === '/api/v1/volumes') return Promise.resolve([...inventory]);
		if (path === '/api/v1/dashboard/quotas') return Promise.resolve({ storage: { volumes: { limit: 10, in_use: inventory.length }, gigabytes: { limit: 1000, in_use: inventory.length * 20 } } });
		return Promise.resolve([]);
	});
});
afterEach(cleanup);

describe('project volume list sorting', () => {
	it('renders all four orderings without mutating API inventory or selection, and retains sorting through refresh and snapshot tabs', async () => {
		const view = render(Page);
		await screen.findByText('Alpha');
		const sort = view.container.querySelector<HTMLSelectElement>('#project-volume-sort')!;
		expect(sort.value).toBe('created_desc');
		expect(namesInPanel()).toEqual(['Alpha', 'Bravo', 'Charlie']);
		await fireEvent.click(screen.getByRole('checkbox', { name: 'Alpha 선택' }));
		for (const [value, expected] of [
			['created_asc', ['Bravo', 'Alpha', 'Charlie']],
			['name_asc', ['Alpha', 'Bravo', 'Charlie']],
			['name_desc', ['Charlie', 'Bravo', 'Alpha']],
			['created_desc', ['Alpha', 'Bravo', 'Charlie']],
		] as const) {
			await fireEvent.change(sort, { target: { value } });
			expect(namesInPanel()).toEqual(expected);
			expect((screen.getByRole('checkbox', { name: 'Alpha 선택' }) as HTMLInputElement).checked).toBe(true);
			expect((screen.getByRole('checkbox', { name: 'Bravo 선택' }) as HTMLInputElement).checked).toBe(false);
			expect((screen.getByRole('checkbox', { name: 'Charlie 선택' }) as HTMLInputElement).checked).toBe(false);
		}
		expect(inventory.map(volume => volume.id)).toEqual(['vol-b', 'vol-a', 'vol-c']);
		expect(mocks.get.mock.calls.filter(([path]) => path === '/api/v1/volumes')).toHaveLength(1);
		await fireEvent.change(sort, { target: { value: 'name_desc' } });
		inventory = [...inventory, makeVolume('vol-d', 'Delta', '2026-10-04T00:00:00Z')];
		await fireEvent.click(screen.getByRole('button', { name: commonT('autoRefresh.refreshNow') }));
		await waitFor(() => expect(namesInPanel()).toEqual(['Delta', 'Charlie', 'Bravo', 'Alpha']));
		expect(sort.value).toBe('name_desc');
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/volumes', 'token', 'project-a', { refresh: true });
		await fireEvent.click(screen.getByRole('tab', { name: /스냅샷/ }));
		expect(view.container.querySelector('#project-volume-sort')).toBeNull();
		await fireEvent.click(screen.getByRole('tab', { name: /볼륨/ }));
		expect(view.container.querySelector<HTMLSelectElement>('#project-volume-sort')!.value).toBe('name_desc');
		expect(namesInPanel()).toEqual(['Delta', 'Charlie', 'Bravo', 'Alpha']);
	});

	it('filters the complete project inventory and paginates only the matching projection', async () => {
		inventory = Array.from({ length: 25 }, (_, index) => makeVolume(`vol-${String(index).padStart(2, '0')}`, `Dataset ${index}`, null));
		const view = render(Page);
		await screen.findByRole('button', { name: 'Dataset 0' });
		expect(screen.queryByRole('button', { name: 'Dataset 24' })).toBeNull();
		await fireEvent.input(view.container.querySelector<HTMLInputElement>('#project-volume-search')!, { target: { value: 'Dataset 24' } });
		expect(screen.getByRole('button', { name: 'Dataset 24' })).toBeTruthy();
		expect(screen.queryByRole('button', { name: 'Dataset 0' })).toBeNull();
		expect(screen.getByTestId('project-volume-footer').textContent).toContain(t('page.resultCount', { filtered: 1, total: 25 }));
		expect(mocks.get.mock.calls.filter(([path]) => path === '/api/v1/volumes')).toHaveLength(1);
		expect(mocks.post).not.toHaveBeenCalled();
	});

	it('does not present snapshot or quota failures as successful empty observations', async () => {
		mocks.get.mockImplementation((path: string) => {
			if (path === '/api/v1/volumes') return Promise.resolve([]);
			if (path === '/api/v1/volume-snapshots' || path === '/api/v1/dashboard/quotas') return Promise.reject(new Error('provider unavailable'));
			return Promise.resolve([]);
		});
		render(Page);
		expect(await screen.findByText(t('page.quotasUnavailable'))).toBeTruthy();
		await fireEvent.click(screen.getByRole('tab', { name: t('tabs.snapshotsUnknown') }));
		expect(await screen.findByText(t('page.snapshotsUnavailable'))).toBeTruthy();
		expect(screen.queryByText(t('snapshotListTable.empty'))).toBeNull();
		expect(screen.getByRole('button', { name: t('transferModal.receiveTitle') })).toBeTruthy();
		expect(screen.getByRole('button', { name: t('transferModal.listTitle') })).toBeTruthy();
		expect(mocks.post).not.toHaveBeenCalled();
	});
});
