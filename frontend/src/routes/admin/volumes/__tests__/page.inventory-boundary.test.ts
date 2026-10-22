import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import { tick } from 'svelte';

const mocks = vi.hoisted(() => ({ get: vi.fn(), prefetch: vi.fn(), post: vi.fn(), refresh: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: mocks }));
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
import { setAdminInventoryScope } from '$lib/stores/adminInventoryScope';
import type { AdminVolumeStatusSummary } from '$lib/types/volume';

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

	it('opens the complete domain list even when drilling into the already selected domain', async () => {
		setAdminInventoryScope('domain-a', '');
		render(Page);
		await screen.findByRole('checkbox', { name: 'first-volume 선택' });
		await fireEvent.input(screen.getByLabelText('이름 또는 ID'), { target: { value: 'narrow-query' } });
		await vi.advanceTimersByTimeAsync(300);
		await screen.findByRole('button', { name: 'Research 볼륨 보기' });
		await fireEvent.click(screen.getByRole('button', { name: 'Research 볼륨 보기' }));
		await screen.findByRole('checkbox', { name: 'first-volume 선택' });
		const path = mocks.get.mock.calls.map(([value]) => String(value)).filter(value => value.startsWith('/api/v1/admin/all-volumes')).at(-1)!;
		expect(path).toContain('domain_id=domain-a');
		expect(path).not.toContain('name=');
		expect((screen.getByLabelText('이름 또는 ID') as HTMLInputElement).value).toBe('');
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
});
