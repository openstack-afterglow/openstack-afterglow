import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import { tick } from 'svelte';

const mocks = vi.hoisted(() => ({
	get: vi.fn(),
	post: vi.fn(),
	prefetch: vi.fn(),
	confirm: vi.fn(),
	success: vi.fn(),
	error: vi.fn(),
}));

vi.mock('$lib/api/client', () => ({ api: { get: mocks.get, post: mocks.post, prefetch: mocks.prefetch } }));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'token', projectId: 'project' }) }));
vi.mock('$lib/stores/projectNames', async () => {
	const names = writable(new Map<string, string>());
	return { projectNames: Object.assign(names, { load: vi.fn().mockResolvedValue(new Map<string, string>()) }) };
});
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: mocks.confirm }));
vi.mock('$lib/stores/toast', () => ({ toast: { success: mocks.success, error: mocks.error } }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({ active: false, intervalSeconds: 30, intervalOptions: [15, 30, 60] }),
}));

import Page from '../+page.svelte';

const firstVolume = { id: 'vol-1', name: 'first-volume', status: 'available', size: 10, project_id: 'project', created_at: '2026-09-01' };
const secondVolume = { id: 'vol-2', name: 'second-volume', status: 'in-use', size: 20, project_id: 'project', created_at: '2026-09-02' };

function setupGet(listResponses: Array<{ items: typeof firstVolume[]; next_marker: string | null }>, summaries: Array<{ total: number; statuses: { status: string; count: number }[] }>) {
	mocks.get.mockImplementation((path: string) => {
		if (path.startsWith('/api/v1/admin/all-volumes')) return Promise.resolve(listResponses.shift() ?? { items: [], next_marker: null });
		if (path === '/api/v1/admin/volumes/status-summary') return Promise.resolve(summaries.shift() ?? { total: 0, statuses: [] });
		if (path.startsWith('/api/v1/admin/timeseries/volumes')) return Promise.resolve([]);
		return Promise.resolve([]);
	});
}

describe('admin volume bulk deletion', () => {
	beforeEach(() => {
		vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
		mocks.get.mockReset();
		mocks.post.mockReset();
		mocks.prefetch.mockReset().mockResolvedValue(undefined);
		mocks.confirm.mockReset().mockResolvedValue(true);
		mocks.success.mockReset();
		mocks.error.mockReset();
	});

	afterEach(() => vi.unstubAllGlobals());

	it('removes successful selections and retains failed volumes after a confirmed request', async () => {
		setupGet(
			[{ items: [firstVolume, secondVolume], next_marker: null }, { items: [secondVolume], next_marker: null }],
			[{ total: 2, statuses: [{ status: 'available', count: 1 }, { status: 'in-use', count: 1 }] }, { total: 1, statuses: [{ status: 'in-use', count: 1 }] }],
		);
		mocks.post.mockResolvedValue({
			results: [
				{ id: 'vol-1', ok: true, error: null },
				{ id: 'vol-2', ok: false, error: 'attached' },
			],
		});

		render(Page);
		await fireEvent.click(await screen.findByRole('checkbox', { name: 'first-volume 선택' }));
		await fireEvent.click(screen.getByRole('checkbox', { name: 'second-volume 선택' }));
		const overlay = screen.getByRole('region', { name: '선택한 관리자 볼륨 일괄 작업' });
		expect(overlay.textContent).toContain('2개 선택됨');
		await fireEvent.click(within(overlay).getByRole('button', { name: '삭제' }));

		await vi.waitFor(() => expect(mocks.post).toHaveBeenCalledWith(
			'/api/v1/admin/volumes/bulk-delete',
			{ volume_ids: ['vol-1', 'vol-2'] },
			'token',
			'project',
		));
		await vi.waitFor(() => expect(screen.getByRole('region', { name: '선택한 관리자 볼륨 일괄 작업' }).textContent).toContain('1개 선택됨'));
		expect(mocks.confirm).toHaveBeenCalledWith(expect.stringContaining('선택한 볼륨 2개'));
		expect(mocks.success).toHaveBeenCalledWith('1개 볼륨 삭제 요청을 완료했습니다.');
		expect(mocks.error).toHaveBeenCalledWith(expect.stringContaining('1개 볼륨 삭제에 실패했습니다'));
		expect((screen.getByRole('checkbox', { name: 'second-volume 선택' }) as HTMLInputElement).checked).toBe(true);
	});

	it('resets an active status filter when bulk deletion removes its final volume', async () => {
		setupGet(
			[{ items: [firstVolume], next_marker: null }, { items: [firstVolume], next_marker: null }, { items: [], next_marker: null }],
			[{ total: 1, statuses: [{ status: 'available', count: 1 }] }, { total: 0, statuses: [] }],
		);
		mocks.post.mockResolvedValue({ results: [{ id: 'vol-1', ok: true, error: null }] });

		render(Page);
		await fireEvent.click(await screen.findByRole('button', { name: 'available 1' }));
		await vi.waitFor(() => expect(mocks.get.mock.calls.some((call) => String(call[0]).includes('status=available'))).toBe(true));
		await fireEvent.click(screen.getByRole('checkbox', { name: 'first-volume 선택' }));
		await fireEvent.click(within(screen.getByRole('region', { name: '선택한 관리자 볼륨 일괄 작업' })).getByRole('button', { name: '삭제' }));

		await vi.waitFor(() => {
			const listPaths = mocks.get.mock.calls.map((call) => String(call[0])).filter((path) => path.startsWith('/api/v1/admin/all-volumes'));
			expect(listPaths.at(-1)).not.toContain('status=available');
		});
		expect(screen.queryByRole('button', { name: 'available 0' })).toBeNull();
		expect(screen.queryByRole('option', { name: 'available' })).toBeNull();
	});

	it('does not offer stale-row selection while a replacement boundary loads', async () => {
		setupGet([{ items: [firstVolume], next_marker: 'vol-1' }], [{ total: 2, statuses: [{ status: 'available', count: 2 }] }]);
		render(Page);
		await screen.findByRole('checkbox', { name: 'first-volume 선택' });
		const replacement = Promise.withResolvers<{ items: typeof firstVolume[]; next_marker: null }>();
		mocks.get.mockReturnValueOnce(replacement.promise);
		await fireEvent.click(screen.getByRole('button', { name: '다음 →' }));
		expect(screen.queryByRole('checkbox', { name: 'first-volume 선택' })).toBeNull();
		expect(screen.queryByRole('region', { name: '선택한 관리자 볼륨 일괄 작업' })).toBeNull();
		replacement.resolve({ items: [secondVolume], next_marker: null });
		await screen.findByRole('checkbox', { name: 'second-volume 선택' });
	});

	it('does not submit a confirmation accepted after its result boundary changes', async () => {
		setupGet([{ items: [firstVolume], next_marker: 'vol-1' }, { items: [secondVolume], next_marker: null }], [{ total: 2, statuses: [{ status: 'available', count: 1 }, { status: 'in-use', count: 1 }] }]);
		const confirmation = Promise.withResolvers<boolean>();
		mocks.confirm.mockReturnValueOnce(confirmation.promise);
		render(Page);
		await fireEvent.click(await screen.findByRole('checkbox', { name: 'first-volume 선택' }));
		await fireEvent.click(within(screen.getByRole('region', { name: '선택한 관리자 볼륨 일괄 작업' })).getByRole('button', { name: '삭제' }));
		await fireEvent.click(screen.getByRole('button', { name: '다음 →' }));
		await screen.findByRole('checkbox', { name: 'second-volume 선택' });
		confirmation.resolve(true);
		await tick();
		expect(mocks.post).not.toHaveBeenCalled();
	});
});
