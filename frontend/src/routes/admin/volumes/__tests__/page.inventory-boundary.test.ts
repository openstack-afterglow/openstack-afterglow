import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { get, writable } from 'svelte/store';
import { tick } from 'svelte';

const mocks = vi.hoisted(() => ({ get: vi.fn(), prefetch: vi.fn(), post: vi.fn(), refresh: vi.fn(), goto: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: mocks }));
vi.mock('$app/navigation', () => ({ goto: mocks.goto }));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'token', projectId: 'project', userId: 'admin' }) }));
vi.mock('$lib/stores/projectNames', async () => {
	const names = writable(new Map<string, string>());
	return { projectNames: Object.assign(names, { load: vi.fn().mockResolvedValue(new Map()) }) };
});
vi.mock('$lib/utils/autoRefresh.svelte', () => ({ createAutoRefresh: (refresh: () => void) => {
	mocks.refresh.mockImplementation(refresh);
	return { active: false, intervalSeconds: 30, intervalOptions: [15, 30, 60] };
} }));
// Vitest hoists the mock factory before static Svelte component imports initialize.
vi.mock('$lib/components/admin/volumes/AdminVolumeDetailSlide.svelte', async () => ({ default: (await import('./_AdminVolumeDetailProbe.svelte')).default }));

import Page from '../+page.svelte';
import { adminInventoryScope, setAdminInventoryScope } from '$lib/stores/adminInventoryScope';
import type { AdminVolumeStatusSummary } from '$lib/types/volume';
import { page } from '$app/state';
import { t as commonT } from '$lib/i18n/ns/common';
import { t as storageT } from '$lib/i18n/ns/admin-storage';
const route = page as unknown as { url: URL };

const volume = { id: 'vol-1', name: 'first-volume', status: 'available', size: 20, volume_type: 'fast', project_id: 'project', project_name: 'Native project', domain_id: 'domain-a', domain_name: 'Research', owner_status: 'known' as const, created_at: null };
const summary: AdminVolumeStatusSummary = {
	total: 200, total_gb: 8000, attached_count: 80, attached_gb: 4000, available_count: 120, available_gb: 4000,
	statuses: [{ status: 'available', count: 120 }, { status: 'in-use', count: 80 }],
	filtered_total: 200, filtered_gb: 8000,
	domains: [{ domain_id: 'domain-a', domain_name: 'Research', owner_status: 'known', project_ids: ['project'], volumes: 200, volume_gb: 8000, attached_volumes: 80, attached_gb: 4000, available_volumes: 120, available_gb: 4000 }],
};

function defaultGet(path: string) {
	if (path.startsWith('/api/v1/admin/all-volumes')) return Promise.resolve({ items: [volume], next_marker: 'vol-1' });
	if (path.startsWith('/api/v1/admin/volumes/status-summary')) return Promise.resolve(summary);
	return Promise.resolve([]);
}

describe('administrator volume complete inventory and publication boundaries', () => {
	beforeEach(() => {
		vi.useFakeTimers();
		route.url = new URL('http://localhost/admin/volumes');
		mocks.goto.mockReset().mockResolvedValue(undefined);
		vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
		setAdminInventoryScope('', '');
		mocks.get.mockReset().mockImplementation(defaultGet);
		mocks.prefetch.mockReset().mockResolvedValue(undefined);
		mocks.post.mockReset();
	});
	afterEach(() => { cleanup(); setAdminInventoryScope('', ''); vi.useRealTimers(); vi.unstubAllGlobals(); });

	it('keeps complete totals and marker continuation independent of loaded-page regex and retains the expression on refresh', async () => {
		render(Page);
		await screen.findByRole('checkbox', { name: 'first-volume 선택' });
		expect(screen.getByTestId('admin-volume-complete-total').textContent).toBe('볼륨 200개 · 8,000 GiB');
		await fireEvent.click(screen.getByRole('button', { name: '다음 →' }));
		await screen.findByRole('checkbox', { name: 'first-volume 선택' });
		const search = screen.getByRole('searchbox') as HTMLInputElement;
		await fireEvent.input(search, { target: { value: '^first-volume$' } });
		mocks.get.mockImplementation((path: string) => path.startsWith('/api/v1/admin/all-volumes')
			? Promise.resolve({ items: [volume, { ...volume, id: 'vol-2', name: 'second-volume' }], next_marker: 'vol-2' })
			: defaultGet(path));
		mocks.refresh();
		await tick();
		await screen.findByRole('checkbox', { name: 'first-volume 선택' });
		expect(search.value).toBe('^first-volume$');
		expect(screen.queryByRole('checkbox', { name: 'second-volume 선택' })).toBeNull();
		expect(screen.getByTestId('admin-volume-complete-total').textContent).toBe('볼륨 200개 · 8,000 GiB');
		const path = mocks.get.mock.calls.map(([value]) => String(value)).filter(value => value.startsWith('/api/v1/admin/all-volumes')).at(-1)!;
		expect(path).toContain('marker=');
		expect(path).not.toContain('name=');
		await fireEvent.input(search, { target: { value: '[' } });
		expect(search.getAttribute('aria-invalid')).toBe('true');
		expect(screen.queryByRole('checkbox', { name: 'first-volume 선택' })).toBeNull();
		expect(screen.getByRole('button', { name: '다음 →' })).toBeTruthy();
	});

	it('applies server-wide status and arbitrary size range from column popovers to both native inventory endpoints', async () => {
		render(Page); await screen.findByRole('checkbox', { name: 'first-volume 선택' });
		const statusLabel = commonT('table.filterColumn', { column: storageT('volumeList.column.status') });
		await fireEvent.click(screen.getByRole('button', { name: statusLabel }));
		await fireEvent.click(within(screen.getByRole('dialog', { name: statusLabel })).getByRole('checkbox', { name: 'available' }));
		await screen.findByRole('checkbox', { name: 'first-volume 선택' });
		const sizeLabel = commonT('table.filterColumn', { column: storageT('volumeList.column.size') });
		await fireEvent.click(screen.getByRole('button', { name: sizeLabel }));
		const range = within(screen.getByRole('dialog', { name: sizeLabel }));
		await fireEvent.input(range.getByLabelText(commonT('table.minimum')), { target: { value: '10' } });
		await fireEvent.input(range.getByLabelText(commonT('table.maximum')), { target: { value: '30' } });
		await fireEvent.click(range.getByRole('button', { name: commonT('table.apply') }));
		await screen.findByRole('checkbox', { name: 'first-volume 선택' });
		for (const prefix of ['/api/v1/admin/all-volumes', '/api/v1/admin/volumes/status-summary']) {
			const path = mocks.get.mock.calls.map(([value]) => String(value)).filter(value => value.startsWith(prefix)).at(-1)!;
			expect(Object.fromEntries(new URL(path, 'http://localhost').searchParams)).toMatchObject({ status: 'available', min_size: '10', max_size: '30' });
		}
	});
	it('opens the complete domain list even when drilling into the already selected domain', async () => {
		setAdminInventoryScope('domain-a', '');
		render(Page);
		await screen.findByRole('checkbox', { name: 'first-volume 선택' });
		await fireEvent.input(screen.getByRole('searchbox'), { target: { value: 'narrow-query' } });
		await vi.advanceTimersByTimeAsync(300);
		await fireEvent.click(screen.getByRole('tab', { name: '용량 분석' }));
		await screen.findByRole('button', { name: 'Research 볼륨 보기' });
		await fireEvent.click(screen.getByRole('button', { name: 'Research 볼륨 보기' }));
		await screen.findByRole('checkbox', { name: 'first-volume 선택' });
		const path = mocks.get.mock.calls.map(([value]) => String(value)).filter(value => value.startsWith('/api/v1/admin/all-volumes')).at(-1)!;
		expect(path).toContain('domain_id=domain-a');
		expect(path).not.toContain('name=');
		expect((screen.getByRole('searchbox') as HTMLInputElement).value).toBe('');
	});

	it('keeps refresh controls usable in the capacity view and publishes a newly read summary', async () => {
		route.url = new URL('http://localhost/admin/volumes?tab=capacity');
		render(Page);
		await vi.waitFor(() => expect(screen.getByTestId('admin-volume-analytics-total').textContent).toContain('200'));
		const interval = screen.getByRole('combobox', { name: '자동 새로고침:' }) as HTMLSelectElement;
		await fireEvent.change(interval, { target: { value: '15' } });
		expect(interval.value).toBe('15');
		await fireEvent.change(interval, { target: { value: 'off' } });
		expect(interval.value).toBe('off');
		mocks.get.mockImplementation((path: string) => path.startsWith('/api/v1/admin/volumes/status-summary') ? Promise.resolve({ ...summary, total: 201 }) : defaultGet(path));
		await fireEvent.click(screen.getByRole('button', { name: '지금 새로고침' }));
		await vi.waitFor(() => expect(screen.getByTestId('admin-volume-analytics-total').textContent).toContain('201'));
	});

	it('rejects list and summary completions after same-tick scope A→B→A, then publishes only the remounted scope', async () => {
		setAdminInventoryScope('domain-a', '');
		const oldList = Promise.withResolvers<{ items: typeof volume[]; next_marker: null }>();
		const oldSummary = Promise.withResolvers<AdminVolumeStatusSummary>();
		mocks.get.mockImplementation((path: string) => path.startsWith('/api/v1/admin/all-volumes') ? oldList.promise : oldSummary.promise);
		const view = render(Page);
		await vi.waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(2));
		setAdminInventoryScope('domain-b', '');
		setAdminInventoryScope('domain-a', '');
		oldList.resolve({ items: [{ ...volume, name: 'stale-A' }], next_marker: null });
		oldSummary.resolve({ ...summary, total: 999, total_gb: 999 });
		await tick(); await tick();
		expect(screen.queryByText('stale-A')).toBeNull();
		expect(screen.getByTestId('admin-volume-complete-total').textContent).toBe('—');
		view.unmount();
		mocks.get.mockImplementation(defaultGet);
		render(Page);
		await screen.findByRole('checkbox', { name: 'first-volume 선택' });
		expect(screen.getByTestId('admin-volume-complete-total').textContent).toBe('볼륨 200개 · 8,000 GiB');
		expect(mocks.get.mock.calls.at(-1)?.[0]).toContain('domain_id=domain-a');
	});

	it('retains a local regex across analytics tabs without sending it as a provider query', async () => {
		render(Page);
		await screen.findByRole('checkbox', { name: 'first-volume 선택' });
		const before = mocks.get.mock.calls.length;
		await fireEvent.input(screen.getByRole('searchbox'), { target: { value: '^pending-query$' } });
		await fireEvent.click(screen.getByRole('tab', { name: '용량 분석' }));
		await tick();
		expect(mocks.get.mock.calls.length).toBe(before);
		expect(screen.getByTestId('admin-volume-analytics-total').textContent).toContain('200');
		await fireEvent.click(screen.getByRole('tab', { name: '리소스 목록' }));
		expect((screen.getByRole('searchbox') as HTMLInputElement).value).toBe('^pending-query$');
	});

	it('drills a project-scoped capacity report into its exact owning domain through one list navigation', async () => {
		route.url = new URL('http://localhost/admin/volumes?domain_id=domain-a&project_id=project-a&tab=capacity');
		setAdminInventoryScope('domain-a', 'project-a');
		const before = get(adminInventoryScope);
		render(Page);
		await fireEvent.click(await screen.findByRole('button', { name: 'Research 볼륨 보기' }));
		expect(mocks.goto).toHaveBeenCalledOnce();
		const destination = new URL(String(mocks.goto.mock.calls[0][0]), 'http://localhost');
		expect(destination.pathname).toBe('/admin/volumes');
		expect(destination.searchParams.get('domain_id')).toBe('domain-a');
		expect(destination.searchParams.has('project_id')).toBe(false);
		expect(destination.searchParams.has('tab')).toBe(false);
		expect(mocks.goto.mock.calls[0][1]).toEqual({ noScroll: true, keepFocus: true });
		expect(get(adminInventoryScope)).toEqual(before);
		expect(screen.getByRole('tab', { name: '리소스 목록' }).getAttribute('aria-selected')).toBe('true');
	});
});
