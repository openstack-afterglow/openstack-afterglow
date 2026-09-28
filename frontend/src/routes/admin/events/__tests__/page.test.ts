import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { get, writable } from 'svelte/store';
import { tick } from 'svelte';
const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));
vi.mock('$lib/api/client', () => ({
	api: { get: mockGet },
	ApiError: class ApiError extends Error {},
}));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'admin-token', projectId: 'admin-project' }),
}));
import { auth } from '$lib/stores/auth';
import Page from '../+page.svelte';

const record = {
	id: 42, created_at: '2026-09-28T08:30:00Z', project_id: 'tenant-1', user_id: 'actor-1',
	username: 'operator', service: 'nova', page: '/admin/instances', source: 'afterglow',
	resource_type: 'instance', resource_id: 'vm-123', resource_name: 'workload',
	action: 'instance.create', status: 'failed', error_message: 'Nova request failed\nsecond line',
	request_id: 'req-42', external_id: 'native-id-42', event_type: 'compute.instance.create.error', http_status: 503,
};
const stats = {
	total: 12, success: 5, failed: 7, started: 0,
	by_service: [{ key: 'nova', total: 5, failed: 4 }],
	by_project: [{ key: 'tenant-1', total: 4, failed: 3 }],
	by_action: [{ key: 'instance.create', total: 3, failed: 2 }],
	by_page: [{ key: '/admin/instances', total: 3, failed: 2 }],
};
function response(path: string) {
	const url = new URL(path, 'http://localhost');
	if (url.pathname.endsWith('/stats')) return stats;
	if (url.pathname.endsWith('/42')) return { ...record, extra: { error_type: 'QuotaExceeded', error_code: 503, access_token: 'DO_NOT_SHOW' } };
	return [record];
}
function deferred<T>() {
	let resolve!: (value: T) => void;
	const promise = new Promise<T>((done) => { resolve = done; });
	return { promise, resolve };
}

beforeEach(() => {
	mockGet.mockReset();
	mockGet.mockImplementation((path: string) => Promise.resolve(response(path)));
	Element.prototype.animate = vi.fn().mockReturnValue({ finished: Promise.resolve(), cancel: vi.fn(), play: vi.fn() });
	window.matchMedia = vi.fn().mockImplementation((query: string) => ({
		matches: false, media: query, onchange: null,
		addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
	}));
});
afterEach(() => {
	cleanup();
	// Restore scope for the next mounted page.
	auth.set({ ...get(auth), token: 'admin-token', projectId: 'admin-project' });
});

describe('admin event viewer', () => {
	it('refreshes the time window without applying unsaved filter edits', async () => {
		render(Page);
		await screen.findByRole('button', { name: 'instance.create 이벤트 42 상세 보기' });
		const firstPath = mockGet.mock.calls.find(([path]) => !path.includes('/stats'))![0] as string;
		const first = new URL(firstPath, 'http://localhost').searchParams;
		const now = Date.parse(first.get('to_at')!) + 60_000;
		const clock = vi.spyOn(Date, 'now').mockReturnValue(now);
		try {
			await fireEvent.input(screen.getByLabelText('프로젝트 ID'), { target: { value: 'unsaved' } });
			await fireEvent.click(screen.getByRole('button', { name: '새로고침' }));
			const lastPath = mockGet.mock.calls.filter(([path]) => !path.includes('/stats')).at(-1)![0] as string;
			const last = new URL(lastPath, 'http://localhost').searchParams;
			expect(Date.parse(last.get('to_at')!)).toBe(now);
			expect(Date.parse(last.get('from_at')!) - Date.parse(first.get('from_at')!)).toBe(60_000);
			expect(last.has('project_id')).toBe(false);
		} finally {
			clock.mockRestore();
		}
	});

	it('applies time, identity, service, page, resource, action, status and source filters to both list and failure analysis', async () => {
		render(Page);
		await screen.findByRole('button', { name: 'instance.create 이벤트 42 상세 보기' });
		await fireEvent.change(screen.getByLabelText('기간'), { target: { value: '1d' } });
		for (const [label, value] of [
			['프로젝트 ID', 'tenant-a'], ['사용자 ID', 'actor-a'], ['사용자 이름', 'operator-a'], ['서비스', 'nova'],
			['페이지 경로', '/admin/instances'], ['리소스 유형', 'instance'], ['리소스 ID', 'vm-a'], ['액션', 'instance.create'],
		]) await fireEvent.input(screen.getByLabelText(label), { target: { value } });
		await fireEvent.change(screen.getByLabelText('상태'), { target: { value: 'failed' } });
		await fireEvent.change(screen.getByLabelText('출처'), { target: { value: 'openstack' } });
		await fireEvent.click(screen.getByRole('button', { name: '필터 적용' }));
		await waitFor(() => {
			const paths = mockGet.mock.calls.map(([path]) => path as string);
			const list = paths.filter((path: string) => new URL(path, 'http://localhost').pathname === '/api/v1/admin/events').at(-1)!;
			const params = new URL(list, 'http://localhost').searchParams;
			expect(Object.fromEntries(params)).toMatchObject({ project_id: 'tenant-a', user_id: 'actor-a', username: 'operator-a', service: 'nova', page: '/admin/instances', resource_type: 'instance', resource_id: 'vm-a', action: 'instance.create', status: 'failed', source: 'openstack' });
			expect(Date.parse(params.get('to_at')!) - Date.parse(params.get('from_at')!)).toBe(86_400_000);
			expect(paths.some((path: string) => path.startsWith('/api/v1/admin/events/stats?') && path.includes('page=%2Fadmin%2Finstances'))).toBe(true);
		});
	});

	it('shows server-wide failure counts and reveals complete error and identifiers without dumping extra', async () => {
		render(Page);
		const analysis = await screen.findByRole('region', { name: '실패 분석' });
		await waitFor(() => expect(within(analysis).getByText('4건')).toBeTruthy());
		for (const [label, count] of [['프로젝트별 실패', '3건'], ['액션별 실패', '2건'], ['페이지별 실패', '2건']]) {
			expect(within(analysis).getByText(label)).toBeTruthy();
			expect(within(analysis).getAllByText(count).length).toBeGreaterThan(0);
		}
		await fireEvent.click(await screen.findByRole('button', { name: 'instance.create 이벤트 42 상세 보기' }));
		const detail = await screen.findByRole('dialog', { name: '이벤트 상세 42' });
		await waitFor(() => expect(within(detail).getByText(/Nova request failed\s+second line/)).toBeTruthy());
		for (const value of ['vm-123', 'req-42', 'native-id-42', 'compute.instance.create.error', 'QuotaExceeded', 'tenant-1', '/admin/instances']) expect(within(detail).getByText(value)).toBeTruthy();
		expect(detail.textContent).not.toContain('DO_NOT_SHOW');
		expect(mockGet).toHaveBeenCalledWith('/api/v1/admin/events/42', 'admin-token', 'admin-project');
	});

	it('explains native notification detail limits and never displays arbitrary metadata', async () => {
		const native = { ...record, id: 73, source: 'openstack', username: '', user_id: '', project_id: '', error_message: null };
		mockGet.mockImplementation((path: string) => {
			if (path.includes('/stats?')) return Promise.resolve(stats);
			if (path.endsWith('/73')) return Promise.resolve({ ...native, extra: { error_type: 'MaxRetriesExceeded', error_code: 'E429', credential: 'SECRET' } });
			return Promise.resolve([native]);
		});
		render(Page);
		const list = await screen.findByRole('region', { name: '이벤트 목록' });
		await waitFor(() => expect(within(list).getAllByText('알 수 없음').length).toBeGreaterThanOrEqual(2));
		await fireEvent.click(screen.getByRole('button', { name: 'instance.create 이벤트 73 상세 보기' }));
		const detail = await screen.findByRole('dialog', { name: '이벤트 상세 73' });
		await waitFor(() => expect(within(detail).getByText('MaxRetriesExceeded')).toBeTruthy());
		expect(within(detail).getByText('E429')).toBeTruthy();
		expect(detail.textContent).toContain('원문 오류는 수집하지 않습니다');
		expect(detail.textContent).not.toContain('SECRET');
	});

	it('distinguishes a genuinely empty list from failure to load statistics', async () => {
		mockGet.mockImplementation((path: string) => path.includes('/stats?') ? Promise.reject(new Error('offline')) : Promise.resolve([]));
		render(Page);
		await screen.findByText('조건에 맞는 이벤트가 없습니다.');
		expect(await screen.findByText('실패 분석을 불러오지 못했습니다')).toBeTruthy();
		expect(screen.queryByText('이벤트를 불러오지 못했습니다')).toBeNull();
	});

	it('appends the next 50-row cursor window without replacing previous rows', async () => {
		const first = Array.from({ length: 50 }, (_, index) => ({ ...record, id: 100 - index, resource_name: `original-${index}` }));
		mockGet.mockImplementation((path: string) => {
			if (path.includes('/stats?')) return Promise.resolve(stats);
			return Promise.resolve(path.includes('before_id=51') ? [{ ...record, id: 50, resource_name: 'older-event' }] : first);
		});
		render(Page);
		await fireEvent.click(await screen.findByRole('button', { name: '더 보기' }));
		await screen.findByText('older-event');
		expect(screen.getByText('original-0')).toBeTruthy();
		expect(screen.queryByRole('button', { name: '더 보기' })).toBeNull();
	});

	it('appends cursor pages and ignores a stale load-more response after filters change', async () => {
		const pending = deferred<typeof record[]>();
		const first = Array.from({ length: 50 }, (_, index) => ({ ...record, id: 100 - index, resource_name: index === 0 ? 'first' : `row-${index}` }));
		mockGet.mockImplementation((path: string) => {
			if (path.includes('before_id=51')) return pending.promise;
			if (path.includes('/stats?')) return Promise.resolve(stats);
			if (path.includes('project_id=tenant-b')) return Promise.resolve([{ ...record, id: 88, resource_name: 'newer' }]);
			return Promise.resolve(first);
		});
		render(Page);
		await fireEvent.click(await screen.findByRole('button', { name: '더 보기' }));
		await waitFor(() => expect(mockGet.mock.calls.some(([path]) => (path as string).includes('before_id=51'))).toBe(true));
		await fireEvent.input(screen.getByLabelText('프로젝트 ID'), { target: { value: 'tenant-b' } });
		await fireEvent.click(screen.getByRole('button', { name: '필터 적용' }));
		await screen.findByText('newer');
		pending.resolve([{ ...record, id: 77, resource_name: 'stale' }]);
		await tick();
		expect(screen.queryByText('stale')).toBeNull();
		expect(screen.getByText('newer')).toBeTruthy();
	});

	it('reports API failures instead of an empty feed, and does not publish an older login response', async () => {
		const pending = deferred<typeof record[]>();
		mockGet.mockImplementation((path: string) => {
			if (path.includes('/stats?')) return Promise.reject(new Error('offline'));
			if (path.includes('project_id=tenant-b')) return Promise.reject(new Error('offline'));
			return pending.promise;
		});
		render(Page);
		await fireEvent.input(screen.getByLabelText('프로젝트 ID'), { target: { value: 'tenant-b' } });
		await fireEvent.click(screen.getByRole('button', { name: '필터 적용' }));
		await screen.findByText('이벤트를 불러오지 못했습니다');
		expect(screen.queryByText('조건에 맞는 이벤트가 없습니다.')).toBeNull();
		pending.resolve([record]);
		auth.set({ ...get(auth), token: 'other-session' });
		await tick();
		expect(screen.queryByText('workload')).toBeNull();
	});
});
