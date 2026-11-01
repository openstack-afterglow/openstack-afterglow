import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
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

	it('keeps complete domain totals independent of marker pages and sends every detail filter to both full-inventory APIs', async () => {
		render(Page);
		await screen.findByRole('checkbox', { name: 'first-volume 선택' });
		expect(screen.getByTestId('admin-volume-complete-total').textContent).toBe('볼륨 200개 · 8,000 GiB');
		await fireEvent.click(screen.getByRole('button', { name: '다음 →' }));
		await screen.findByRole('checkbox', { name: 'first-volume 선택' });
		expect(screen.getByTestId('admin-volume-complete-total').textContent).toBe('볼륨 200개 · 8,000 GiB');
		expect(mocks.get.mock.calls.filter(([path]) => path.startsWith('/api/v1/admin/volumes/status-summary'))).toHaveLength(1);
		await fireEvent.change(screen.getByLabelText('상태'), { target: { value: 'available' } });
		await fireEvent.input(screen.getByLabelText('이름 또는 ID'), { target: { value: 'vol-1' } });
		await fireEvent.input(screen.getByLabelText('볼륨 유형'), { target: { value: 'fast' } });
		await fireEvent.input(screen.getByLabelText('최소 용량 (GiB)'), { target: { value: '10' } });
		await fireEvent.input(screen.getByLabelText('최대 용량 (GiB)'), { target: { value: '30' } });
		mocks.get.mockImplementation((path: string) => path.startsWith('/api/v1/admin/volumes/status-summary') ? Promise.resolve({ ...summary, filtered_total: 7, filtered_gb: 140 }) : defaultGet(path));
		await vi.advanceTimersByTimeAsync(300);
		await vi.waitFor(() => expect(screen.getByTestId('admin-volume-filtered-total').textContent).toContain('볼륨 7개 · 140 GiB'));
		for (const prefix of ['/api/v1/admin/all-volumes', '/api/v1/admin/volumes/status-summary']) {
			const path = mocks.get.mock.calls.map(([value]) => String(value)).filter(value => value.startsWith(prefix)).at(-1)!;
			const params = new URL(path, 'http://localhost').searchParams;
			expect(Object.fromEntries(params)).toMatchObject({ status: 'available', name: 'vol-1', volume_type: 'fast', min_size: '10', max_size: '30' });
			expect(params.has('marker')).toBe(false);
		}
		expect(screen.getByTestId('admin-volume-complete-total').textContent).toBe('볼륨 200개 · 8,000 GiB');
		await fireEvent.change(screen.getByLabelText('정렬 기준'), { target: { value: 'name_desc' } });
		await vi.waitFor(() => expect(screen.getByTestId('admin-volume-filtered-total').textContent).toContain('볼륨 7개 · 140 GiB'));
		const sortedPath = mocks.get.mock.calls.map(([path]) => String(path)).filter(path => path.startsWith('/api/v1/admin/all-volumes')).at(-1)!;
		expect(Object.fromEntries(new URL(sortedPath, 'http://localhost').searchParams)).toMatchObject({ sort: 'name_desc', status: 'available', name: 'vol-1', volume_type: 'fast', min_size: '10', max_size: '30' });
	});

	it('clears selection, detail and marker immediately when search changes, before debounce or an old response completes', async () => {
		const view = render(Page);
		await screen.findByRole('checkbox', { name: 'first-volume 선택' });
		await fireEvent.click(screen.getByRole('button', { name: '다음 →' }));
		await fireEvent.click(await screen.findByRole('checkbox', { name: 'first-volume 선택' }));
		await fireEvent.click(screen.getByRole('button', { name: 'first-volume' }));
		expect(view.container.querySelector('[data-tour="admin-storage-detail"]')).toBeTruthy();
		const oldPage = Promise.withResolvers<{ items: typeof volume[]; next_marker: string }>();
		mocks.get.mockImplementation((path: string) => path.includes('marker=') ? oldPage.promise : defaultGet(path));
		mocks.refresh();
		await tick();
		await fireEvent.input(screen.getByLabelText('이름 또는 ID'), { target: { value: 'new-query' } });
		expect(view.container.querySelector('[data-tour="admin-storage-detail"]')).toBeNull();
		expect(screen.queryByRole('region', { name: '선택한 관리자 볼륨 일괄 작업' })).toBeNull();
		oldPage.resolve({ items: [{ ...volume, name: 'stale-marker-volume' }], next_marker: 'stale-marker' });
		await tick();
		expect(screen.queryByText('stale-marker-volume')).toBeNull();
		await vi.advanceTimersByTimeAsync(300);
		await screen.findByRole('checkbox', { name: 'first-volume 선택' });
		const lastPath = mocks.get.mock.calls.map(([path]) => String(path)).filter(path => path.startsWith('/api/v1/admin/all-volumes')).at(-1)!;
		expect(lastPath).toContain('name=new-query');
		expect(lastPath).not.toContain('marker=');
	});

	it('resets sorted pages, selection, detail and prefetch without changing totals, and rejects stale marker completions', async () => {
		const view = render(Page);
		await screen.findByRole('checkbox', { name: 'first-volume 선택' });
		const sort = view.container.querySelector<HTMLSelectElement>('#admin-volume-sort')!;
		expect(sort.value).toBe('created_desc');
		expect(mocks.get.mock.calls.some(([path]) => String(path).includes('sort=created_desc'))).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: '다음 →' }));
		await fireEvent.click(await screen.findByRole('checkbox', { name: 'first-volume 선택' }));
		await fireEvent.click(screen.getByRole('button', { name: 'first-volume' }));
		await vi.advanceTimersByTimeAsync(200);
		const previousPrefetch = mocks.prefetch.mock.calls.at(-1)!;
		expect(previousPrefetch[3].signal.aborted).toBe(false);
		const oldPage = Promise.withResolvers<{ items: typeof volume[]; next_marker: string }>();
		mocks.get.mockImplementation((path: string) => path.includes('marker=') ? oldPage.promise : defaultGet(path));
		mocks.refresh();
		await tick();
		await fireEvent.change(sort, { target: { value: 'name_desc' } });
		expect(previousPrefetch[3].signal.aborted).toBe(true);
		expect(view.container.querySelector('[data-tour="admin-storage-detail"]')).toBeNull();
		expect(screen.queryByRole('region', { name: '선택한 관리자 볼륨 일괄 작업' })).toBeNull();
		await screen.findByRole('checkbox', { name: 'first-volume 선택' });
		oldPage.resolve({ items: [{ ...volume, name: 'stale-sort-volume' }], next_marker: 'stale-marker' });
		await tick();
		expect(screen.queryByText('stale-sort-volume')).toBeNull();
		for (const value of ['created_asc', 'name_asc', 'name_desc', 'created_desc']) {
			await fireEvent.change(sort, { target: { value } });
			await screen.findByRole('checkbox', { name: 'first-volume 선택' });
			const path = mocks.get.mock.calls.map(([value]) => String(value)).filter(value => value.startsWith('/api/v1/admin/all-volumes')).at(-1)!;
			const params = new URL(path, 'http://localhost').searchParams;
			expect(params.get('sort')).toBe(value);
			expect(params.has('marker')).toBe(false);
			expect(screen.getByTestId('admin-volume-complete-total').textContent).toBe('볼륨 200개 · 8,000 GiB');
		}
		await fireEvent.change(sort, { target: { value: 'name_asc' } });
		await screen.findByRole('checkbox', { name: 'first-volume 선택' });
		mocks.refresh();
		await tick();
		expect(sort.value).toBe('name_asc');
		const listPath = mocks.get.mock.calls.map(([path]) => String(path)).filter(path => path.startsWith('/api/v1/admin/all-volumes')).at(-1)!;
		expect(new URL(listPath, 'http://localhost').searchParams.get('sort')).toBe('name_asc');
		for (const [path] of mocks.get.mock.calls.filter(([path]) => String(path).startsWith('/api/v1/admin/volumes/status-summary'))) {
			expect(new URL(String(path), 'http://localhost').searchParams.has('sort')).toBe(false);
		}
	});

	it('opens the complete domain list even when drilling into the already selected domain', async () => {
		setAdminInventoryScope('domain-a', '');
		render(Page);
		await screen.findByRole('checkbox', { name: 'first-volume 선택' });
		await fireEvent.input(screen.getByLabelText('이름 또는 ID'), { target: { value: 'narrow-query' } });
		await vi.advanceTimersByTimeAsync(300);
		await fireEvent.click(screen.getByRole('tab', { name: '용량 분석' }));
		await screen.findByRole('button', { name: 'Research 볼륨 보기' });
		await fireEvent.click(screen.getByRole('button', { name: 'Research 볼륨 보기' }));
		await screen.findByRole('checkbox', { name: 'first-volume 선택' });
		const path = mocks.get.mock.calls.map(([value]) => String(value)).filter(value => value.startsWith('/api/v1/admin/all-volumes')).at(-1)!;
		expect(path).toContain('domain_id=domain-a');
		expect(path).not.toContain('name=');
		expect((screen.getByLabelText('이름 또는 ID') as HTMLInputElement).value).toBe('');
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

	it('publishes a pending query even when analytics opens before the debounce expires', async () => {
		render(Page);
		await screen.findByRole('checkbox', { name: 'first-volume 선택' });
		await fireEvent.input(screen.getByLabelText('이름 또는 ID'), { target: { value: 'pending-query' } });
		await fireEvent.click(screen.getByRole('tab', { name: '용량 분석' }));
		await vi.advanceTimersByTimeAsync(300);
		for (const prefix of ['/api/v1/admin/all-volumes', '/api/v1/admin/volumes/status-summary']) {
			const path = mocks.get.mock.calls.map(([value]) => String(value)).filter(value => value.startsWith(prefix)).at(-1)!;
			expect(new URL(path, 'http://localhost').searchParams.get('name')).toBe('pending-query');
		}
		expect(screen.getByTestId('admin-volume-analytics-total').textContent).toContain('200');
		await fireEvent.click(screen.getByRole('tab', { name: '리소스 목록' }));
		expect((screen.getByLabelText('이름 또는 ID') as HTMLInputElement).value).toBe('pending-query');
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
