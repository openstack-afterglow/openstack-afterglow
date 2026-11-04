import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import type { Writable } from 'svelte/store';

interface DashboardAuthFixture {
	token: string | null;
	userId: string | null;
	identityDomainId: string | null;
	username: string | null;
	projectId: string | null;
	projectName: string | null;
	sessionId?: string;
	domainId?: string;
	roles?: string[];
	isSystemAdmin?: boolean;
}
const mocks = vi.hoisted(() => ({
	auth: null as unknown as Writable<DashboardAuthFixture>,
	authReady: null as unknown as Writable<boolean>,
	canWrite: null as unknown as Writable<boolean>,
	projectSwitching: null as unknown as Writable<boolean>,
	siteConfig: null as unknown as Writable<{ services: { k3s: boolean } }>,
	// Keep the overview batch spy separate from the independently mounted reminder inventory.
	apiGet: vi.fn(),
	usageGet: vi.fn(),
	autoCallback: null as (() => void | Promise<void>) | null,
}));
vi.mock('$lib/stores/auth', async () => {
	// This factory is hoisted before static store bindings initialize.
	const { writable } = await import('svelte/store');
	mocks.auth = writable<DashboardAuthFixture>({ token: 'token-a', userId: 'user-a', identityDomainId: 'domain-a', username: 'tester', projectId: 'project-a', projectName: 'Project A' });
	mocks.authReady = writable(true);
	mocks.projectSwitching = writable(false);
	mocks.canWrite = writable(true);
	return { auth: mocks.auth, authReady: mocks.authReady, projectSwitching: mocks.projectSwitching, canWrite: mocks.canWrite };
});
vi.mock('$lib/config/site', async () => {
	// This factory is hoisted before static store bindings initialize.
	const { writable } = await import('svelte/store');
	mocks.siteConfig = writable({ services: { k3s: true } });
	return { siteConfig: mocks.siteConfig };
});
vi.mock('$lib/api/client', () => {
	const get = (path: string, ...args: unknown[]) => path === '/api/v1/instances/usage-schedules' ? mocks.usageGet(path, ...args) : mocks.apiGet(path, ...args);
	return {
		api: { get, withExperience: () => ({ get }) },
		ApiError: class ApiError extends Error {},
	};
});
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: (callback: () => void | Promise<void>) => {
		mocks.autoCallback = callback;
		return {
			active: false,
			intervalSeconds: 30,
			intervalOptions: [10, 15, 30, 60],
			setBoost: () => {},
		};
	},
}));

import Page from '../+page.svelte';

type Deferred<T> = { promise: Promise<T>; resolve(value: T): void; reject(error: unknown): void };

function deferred<T>(): Deferred<T> {
	let resolve!: (value: T) => void;
	let reject!: (error: unknown) => void;
	return { promise: new Promise<T>((res, rej) => { resolve = res; reject = rej; }), resolve, reject };
}

const summary = {
	instances: { total: 1, active: 1, shutoff: 0, error: 0 },
	recent_instances: [{ id: 'newest', name: 'newest', status: 'ACTIVE', flavor_name: 'small', ip_addresses: [], created_at: '2026-01-01T00:00:00Z' }],
};
const quotas = {
	compute: { instances: { limit: 0, in_use: 0 }, cores: { limit: 4, in_use: 1 }, ram: { limit: 1024, in_use: 512 } },
	storage: { volumes: { limit: 2, in_use: 1 }, gigabytes: { limit: 20, in_use: 10 } },
	network: { floatingip: { limit: -1, in_use: 0 } },
	file_storage: null,
	alerts: [],
};
const trend = {
	vcpu: { data: [10], points: 1, available: true, source: 'gnocchi', status: 'available', native_status: 'available' },
	memory: { data: [20], points: 1, available: true, source: 'gnocchi', status: 'available', native_status: 'available' },
	storage: { data: [30], points: 1, available: true, source: 'prometheus', status: 'available', native_status: 'not_collected' },
	network: { data: [], points: 0, available: false, unit: 'KiB/s', source: null, status: 'not_collected', native_status: 'not_collected' },
	monitoring_available: true,
	range: '14d' as const,
};
const announcements: unknown[] = [];

const authContext = { token: 'token-a', sessionId: 'session-a', userId: 'user-a', identityDomainId: 'domain-a', domainId: 'working-a', username: 'tester', projectId: 'project-a', projectName: 'Project A', roles: ['member'], isSystemAdmin: false };

function resolveOverview(path: string, metrics: unknown = trend): unknown {
	if (path.includes('/snapshot')) return { summary: { data: summary, error: null }, quotas: { data: quotas, error: null } };
	if (path.includes('/k3s-stats')) return { total: 1, active: 1, available: true };
	if (path.includes('/announcements')) return announcements;
	return metrics;
}

beforeEach(() => {
	mocks.auth.set(authContext);
	mocks.authReady.set(true);
	mocks.projectSwitching.set(false);
	mocks.canWrite.set(true);
	mocks.usageGet.mockReset();
	mocks.usageGet.mockResolvedValue({ schedules: [], errors: [] });
	mocks.siteConfig.set({ services: { k3s: true } });
	mocks.apiGet.mockReset();
	mocks.autoCallback = null;
	localStorage.clear();
});

afterEach(() => cleanup());

describe('dashboard overview loading', () => {
	it('keeps rendered data and pending reads across credential renewal, then uses the latest token', async () => {
		const pendingTrend = deferred<unknown>();
		mocks.apiGet.mockImplementation((path: string) => path.includes('/metrics/trend') ? pendingTrend.promise : Promise.resolve(resolveOverview(path)));
		render(Page);
		await screen.findByText('newest');
		const oldSignals = mocks.apiGet.mock.calls.map(call => call[3].signal as AbortSignal);
		mocks.auth.update(state => ({ ...state, token: 'token-renewed' }));
		await waitFor(() => expect(screen.getByText('newest')).toBeTruthy());
		expect(mocks.apiGet).toHaveBeenCalledTimes(4);
		expect(oldSignals.every(signal => !signal.aborted)).toBe(true);
		pendingTrend.resolve(trend);
		await screen.findByText('최근 동기화', { exact: false });
		await mocks.autoCallback?.();
		expect(mocks.apiGet.mock.calls.slice(4).map(call => call[1])).toEqual(Array(4).fill('token-renewed'));
	});

	it.each(['sessionId', 'domainId', 'userId', 'projectId', 'identityDomainId', 'isSystemAdmin'] as const)(
		'clears settled data and fences same-tick %s ABA requests', async field => {
			mocks.apiGet.mockImplementation((path: string) => Promise.resolve(resolveOverview(path)));
			render(Page);
			await screen.findByText('newest');
			const late = deferred<unknown>();
			mocks.apiGet.mockReturnValue(deferred<unknown>().promise).mockReturnValueOnce(late.promise);
			void mocks.autoCallback?.();
			const prior = authContext;
			mocks.auth.set({ ...prior, [field]: field === 'isSystemAdmin' ? true : 'other-owner' });
			mocks.auth.set(prior);
			await waitFor(() => expect(screen.queryByText('newest')).toBeNull());
			late.resolve(resolveOverview('/snapshot'));
			await waitFor(() => expect(mocks.apiGet.mock.calls.length).toBeGreaterThan(8));
			expect(screen.queryByText('newest')).toBeNull();
		});

	it('starts four reads sharing native summary/quota proof and renders before slow independent domains settle', async () => {
		const requests = new Map<string, Deferred<unknown>>();
		mocks.apiGet.mockImplementation((path: string) => {
			const pending = deferred<unknown>();
			requests.set(path, pending);
			return pending.promise;
		});

		const rendered = render(Page);
		expect(screen.queryByText('인스턴스가 없습니다')).toBeNull();
		expect(screen.queryByText('메트릭 수집 미설정')).toBeNull();
		await waitFor(() => expect(mocks.apiGet).toHaveBeenCalledTimes(4));
		const paths = mocks.apiGet.mock.calls.map(([path]) => path);
		expect(paths).toEqual(expect.arrayContaining([
			'/api/v1/dashboard/snapshot?recent_limit=12',
			'/api/v1/dashboard/k3s-stats',
			'/api/v1/dashboard/metrics/trend?range=14d&include_network=false',
			'/api/v1/announcements',
		]));
		expect(mocks.usageGet).toHaveBeenCalledWith('/api/v1/instances/usage-schedules', 'token-a', 'project-a', expect.objectContaining({ cache: 'no-store' }));
		expect(paths.join(' ')).not.toContain('/api/v1/instances');
		expect(paths.join(' ')).not.toContain('/api/v1/dashboard/notifications');
		expect(paths.join(' ')).not.toContain('/api/v1/k3s/clusters');

		requests.get('/api/v1/dashboard/snapshot?recent_limit=12')!.resolve(resolveOverview('/snapshot'));
		await screen.findByText('newest');
		expect(screen.getByText('일부 동기화', { exact: false })).toBeTruthy();

		requests.get('/api/v1/dashboard/k3s-stats')!.resolve({ total: 1, active: 1, available: true });
		requests.get('/api/v1/dashboard/metrics/trend?range=14d&include_network=false')!.resolve(trend);
		requests.get('/api/v1/announcements')!.resolve(announcements);
		await waitFor(() => expect(screen.getByText('최근 동기화', { exact: false })).toBeTruthy());
		expect(screen.getAllByText('/ 0').length).toBeGreaterThan(0);
		expect(screen.queryByText('Manila Shares')).toBeNull();
		rendered.unmount();
	});

	it('publishes readable snapshot summary while quotas fail without inventing empty usage', async () => {
		mocks.apiGet.mockImplementation((path: string) => Promise.resolve(path.includes('/snapshot')
			? { summary: { data: summary, error: null }, quotas: { data: null, error: 'quotas_unavailable' } }
			: resolveOverview(path)));
		render(Page);
		await screen.findByText('newest');
		await screen.findByText('일부 동기화', { exact: false });
		expect(mocks.apiGet.mock.calls.filter(([path]) => path.includes('/snapshot'))).toHaveLength(1);
		expect(screen.queryByText('/ 0')).toBeNull();
	});

	it('skips K3s when disabled and requests exactly three reads', async () => {
		mocks.siteConfig.set({ services: { k3s: false } });
		mocks.apiGet.mockImplementation((path: string) => {
			if (path.includes('/snapshot')) return Promise.resolve(resolveOverview(path));
			if (path.includes('/announcements')) return Promise.resolve(announcements);
			return Promise.resolve(trend);
		});

		render(Page);
		await waitFor(() => expect(mocks.apiGet).toHaveBeenCalledTimes(3));
		expect(mocks.apiGet.mock.calls.map(([path]) => path)).not.toContain('/api/v1/dashboard/k3s-stats');
		expect(screen.getByText('N/A')).toBeTruthy();
	});

	it('keeps terminal states hidden and makes no request until auth hydration completes', async () => {
		mocks.authReady.set(false);
		mocks.apiGet.mockImplementation((path: string) => {
			if (path.includes('/snapshot')) return Promise.resolve(resolveOverview(path));
			if (path.includes('/k3s-stats')) return Promise.resolve({ total: 1, active: 1, available: true });
			if (path.includes('/announcements')) return Promise.resolve(announcements);
			return Promise.resolve(trend);
		});

		render(Page);
		await Promise.resolve();
		expect(mocks.apiGet).not.toHaveBeenCalled();
		expect(mocks.usageGet).not.toHaveBeenCalled();
		expect(screen.queryByText('인스턴스가 없습니다')).toBeNull();
		expect(screen.queryByText('메트릭 수집 미설정')).toBeNull();

		mocks.authReady.set(true);
		await waitFor(() => expect(mocks.apiGet).toHaveBeenCalledTimes(4));
		await screen.findByText('newest');
	});

	it('aborts project-stale requests and prevents their late data from committing', async () => {
		type Request = {
			path: string;
			projectId: string | undefined;
			signal: AbortSignal | undefined;
			pending: Deferred<unknown>;
		};
		const requests: Request[] = [];
		mocks.apiGet.mockImplementation((
			path: string,
			_token: string | undefined,
			projectId: string | undefined,
			options: { signal?: AbortSignal },
		) => {
			const pending = deferred<unknown>();
			requests.push({ path, projectId, signal: options.signal, pending });
			return pending.promise;
		});

		render(Page);
		await waitFor(() => expect(requests).toHaveLength(4));
		const oldRequests = [...requests];
		mocks.auth.set({ ...authContext, token: 'token-b', projectId: 'project-b', projectName: 'Project B' });
		await waitFor(() => expect(requests).toHaveLength(8));
		expect(oldRequests.every((request) => request.signal?.aborted)).toBe(true);
		expect(requests.slice(4).every((request) => request.projectId === 'project-b')).toBe(true);

		oldRequests.find((request) => request.path.includes('/snapshot'))!.pending.resolve({
			summary: { data: { ...summary, recent_instances: [{ ...summary.recent_instances[0], name: 'old-project-instance' }] }, error: null },
			quotas: { data: quotas, error: null },
		});
		await Promise.resolve();
		expect(screen.queryByText('old-project-instance')).toBeNull();

		for (const request of requests.slice(4)) {
			if (request.path.includes('/snapshot')) request.pending.resolve({
				summary: { data: { ...summary, recent_instances: [{ ...summary.recent_instances[0], name: 'new-project-instance' }] }, error: null },
				quotas: { data: quotas, error: null },
			});
			else if (request.path.includes('/k3s-stats')) request.pending.resolve({ total: 1, active: 1, available: true });
			else if (request.path.includes('/announcements')) request.pending.resolve(announcements);
			else request.pending.resolve(trend);
		}
		await screen.findByText('new-project-instance');
	});

	it('keeps a manual batch authoritative while auto refresh joins and its range replacement inherits refresh', async () => {
		type Request = { path: string; options: { refresh?: boolean; signal?: AbortSignal }; pending: Deferred<unknown> };
		const manualRequests: Request[] = [];
		let callCount = 0;
		mocks.apiGet.mockImplementation((path: string, _token: string | undefined, _project: string | undefined, options: Request['options']) => {
			callCount += 1;
			if (callCount <= 4) {
				if (path.includes('/snapshot')) return Promise.resolve(resolveOverview(path));
				if (path.includes('/k3s-stats')) return Promise.resolve({ total: 1, active: 1, available: true });
				if (path.includes('/announcements')) return Promise.resolve(announcements);
				return Promise.resolve(trend);
			}
			const pending = deferred<unknown>();
			manualRequests.push({ path, options, pending });
			return pending.promise;
		});

		render(Page);
		await waitFor(() => expect(mocks.apiGet).toHaveBeenCalledTimes(4));
		await screen.findByText('최근 동기화', { exact: false });
		await fireEvent.click(screen.getByTitle('지금 새로고침'));
		await waitFor(() => expect(manualRequests).toHaveLength(4));
		expect(manualRequests.every((request) => request.options.refresh === true)).toBe(true);
		expect(screen.getByTitle('로딩 중…')).toBeTruthy();

		const originalTrend = manualRequests.find((request) => request.path.includes('/metrics/trend'))!;
		await fireEvent.click(screen.getByRole('button', { name: '24h' }));
		await waitFor(() => expect(manualRequests).toHaveLength(5));
		const replacementTrend = manualRequests.at(-1)!;
		expect(originalTrend.options.signal?.aborted).toBe(true);
		expect(replacementTrend.path).toContain('range=24h');
		expect(replacementTrend.options.refresh).toBe(true);
		expect(screen.queryByText('10.0')).toBeNull();
		originalTrend.pending.resolve({ ...trend, vcpu: { ...trend.vcpu, data: [99] } });
		await Promise.resolve();
		expect(screen.queryByText('99.0')).toBeNull();

		const auto = mocks.autoCallback!();
		await Promise.resolve();
		expect(manualRequests).toHaveLength(5);
		for (const request of manualRequests) {
			if (request === originalTrend) continue;
			if (request.path.includes('/snapshot')) request.pending.resolve(resolveOverview(request.path));
			else if (request.path.includes('/k3s-stats')) request.pending.resolve({ total: 1, active: 1, available: true });
			else if (request.path.includes('/announcements')) request.pending.resolve(announcements);
			else request.pending.resolve({ ...trend, range: '24h' });
		}
		await auto;
		await waitFor(() => expect(screen.getByTitle('지금 새로고침')).toBeTruthy());
	});


	it('lets a failed range replacement settle the original batch as partial', async () => {
		type Request = { path: string; signal: AbortSignal | undefined; pending: Deferred<unknown> };
		const requests: Request[] = [];
		mocks.apiGet.mockImplementation((
			path: string,
			_token: string | undefined,
			_project: string | undefined,
			options: { signal?: AbortSignal },
		) => {
			const pending = deferred<unknown>();
			requests.push({ path, signal: options.signal, pending });
			return pending.promise;
		});

		render(Page);
		await waitFor(() => expect(requests).toHaveLength(4));
		const originalTrend = requests.find((request) => request.path.includes('/metrics/trend'))!;
		await fireEvent.click(screen.getByRole('button', { name: '24h' }));
		await waitFor(() => expect(requests).toHaveLength(5));
		expect(originalTrend.signal?.aborted).toBe(true);
		for (const request of requests.slice(0, 4)) {
			if (request === originalTrend) continue;
			if (request.path.includes('/snapshot')) request.pending.resolve(resolveOverview(request.path));
			else if (request.path.includes('/announcements')) request.pending.resolve(announcements);
			else request.pending.resolve({ total: 1, active: 1, available: true });
		}
		requests.at(-1)!.pending.reject(new Error('range failed'));
		await screen.findByText('일부 동기화', { exact: false });
	});
	it('keeps stale successful data and prior sync text when a later batch entirely fails', async () => {
		let callCount = 0;
		mocks.apiGet.mockImplementation((path: string) => {
			callCount += 1;
			if (callCount > 4) return Promise.reject(new Error(`failed ${path}`));
			if (path.includes('/snapshot')) return Promise.resolve(resolveOverview(path));
			if (path.includes('/k3s-stats')) return Promise.resolve({ total: 1, active: 1, available: true });
			if (path.includes('/announcements')) return Promise.resolve(announcements);
			return Promise.resolve(trend);
		});

		render(Page);
		await screen.findByText('newest');
		await screen.findByText('최근 동기화', { exact: false });
		await fireEvent.click(screen.getByTitle('지금 새로고침'));
		await waitFor(() => expect(mocks.apiGet).toHaveBeenCalledTimes(8));
		expect(screen.getByText('newest')).toBeTruthy();
		expect(screen.getByText('최근 동기화', { exact: false })).toBeTruthy();
		await waitFor(() => expect(screen.getByTitle('지금 새로고침')).toBeTruthy());
	});

	it('renders exact Korean unavailable text when K3s stats return available false', async () => {
		mocks.apiGet.mockImplementation((path: string) => {
			if (path.includes('/snapshot')) return Promise.resolve(resolveOverview(path));
			if (path.includes('/k3s-stats')) return Promise.resolve({ total: 0, active: 0, available: false });
			if (path.includes('/announcements')) return Promise.resolve(announcements);
			return Promise.resolve(trend);
		});

		render(Page);
		await screen.findByText('사용할 수 없음');
	});

	it('aborts every outstanding domain request during teardown', async () => {
		const requests: Array<{ signal: AbortSignal | undefined; pending: Deferred<unknown> }> = [];
		mocks.apiGet.mockImplementation((
			_path: string,
			_token: string | undefined,
			_project: string | undefined,
			options: { signal?: AbortSignal },
		) => {
			const pending = deferred<unknown>();
			requests.push({ signal: options.signal, pending });
			return pending.promise;
		});

		const rendered = render(Page);
		await waitFor(() => expect(requests).toHaveLength(4));
		rendered.unmount();
		expect(requests.every((request) => request.signal?.aborted)).toBe(true);
	});

	it('shows native zero, partial coverage and exporter fallback with the native reason', async () => {
		const metrics = {
			...trend,
			scope: 'native_policy',
			vcpu: { ...trend.vcpu, data: [0] },
			memory: { ...trend.memory, status: 'partial', native_status: 'partial' },
			storage: { ...trend.storage, native_status: 'not_configured' },
		};
		mocks.apiGet.mockImplementation((path: string) => Promise.resolve(resolveOverview(path, metrics)));
		render(Page);
		const cpu = within(await screen.findByRole('group', { name: 'vCPU 사용률 (14d)' }));
		await cpu.findByText('0.0');
		expect(cpu.getByText('네이티브 텔레메트리 · Gnocchi')).toBeTruthy();
		expect(cpu.getByText('min 0.0% · max 0.0%')).toBeTruthy();
		expect(screen.getByText('부분 수집 · 일부 표본 또는 리소스 누락')).toBeTruthy();
		const disk = within(screen.getByRole('group', { name: '게스트 파일시스템 사용률 (14d)' }));
		expect(disk.getByText('Exporter 대체 수집 · Prometheus')).toBeTruthy();
		expect(disk.getByText('네이티브 텔레메트리: 메트릭 수집 미설정')).toBeTruthy();
		expect(screen.getByText('네이티브 범위는 현재 사용자 정책에 표시되는 리소스로 제한됩니다.')).toBeTruthy();
	});

	it.each([
		[false, 'not_configured', '메트릭 수집 미설정'],
		[true, 'not_collected', '해당 메트릭의 텔레메트리 미수집'],
		[true, 'forbidden', '텔레메트리 접근 거부'],
		[false, 'unavailable', '텔레메트리를 사용할 수 없음'],
	] as const)('keeps empty %s/%s telemetry distinct from measured zero', async (available, status, message) => {
		const empty = { data: [], points: 0, available: false, source: null, status, native_status: status };
		const metrics = { ...trend, vcpu: empty, memory: empty, storage: empty, monitoring_available: available };
		mocks.apiGet.mockImplementation((path: string) => Promise.resolve(resolveOverview(path, metrics)));
		render(Page);
		const collection = within(await screen.findByRole('region', { name: '텔레메트리 수집 상태' }));
		expect((await collection.findAllByText(message)).length).toBeGreaterThan(0);
		expect(collection.getByRole('link').getAttribute('href')).toBe('/dashboard/observability');
		expect(collection.getByRole('group', { name: 'vCPU 사용률 (14d)' })).toBeTruthy();
		expect(collection.queryByText('0.0')).toBeNull();
	});

	it.each(['sessionId', 'userId', 'identityDomainId', 'domainId', 'projectId'] as const)(
		'clears displayed trends on %s changes and rejects late same-project responses',
		async (field) => {
			const requests: Array<{ path: string; signal: AbortSignal; pending: Deferred<unknown> }> = [];
			let calls = 0;
			mocks.apiGet.mockImplementation((path: string, _token: string, _project: string, options: { signal: AbortSignal }) => {
				if (++calls <= 4) return Promise.resolve(resolveOverview(path));
				const pending = deferred<unknown>();
				requests.push({ path, signal: options.signal, pending });
				return pending.promise;
			});
			render(Page);
			await screen.findByText('10.0');
			void mocks.autoCallback!();
			await waitFor(() => expect(requests).toHaveLength(4));
			const stale = [...requests];
			mocks.auth.set({ ...authContext, [field]: 'changed-context' });
			await waitFor(() => expect(requests).toHaveLength(8));
			expect(screen.queryByText('10.0')).toBeNull();
			expect(screen.queryByText('newest')).toBeNull();
			expect(stale.every(({ signal }) => signal.aborted)).toBe(true);
			for (const request of stale) {
				request.pending.resolve(resolveOverview(request.path, { ...trend, vcpu: { ...trend.vcpu, data: [91] } }));
			}
			for (const request of requests.slice(4)) {
				request.pending.resolve(resolveOverview(request.path, { ...trend, vcpu: { ...trend.vcpu, data: [7] } }));
			}
			await screen.findByText('7.0');
			expect(screen.queryByText('91.0')).toBeNull();
		},
	);

	it('clears loaded trends when the session is removed and ignores a pending refresh', async () => {
		const pending = deferred<unknown>();
		let calls = 0;
		mocks.apiGet.mockImplementation((path: string) => ++calls <= 4 ? Promise.resolve(resolveOverview(path)) : pending.promise);
		render(Page);
		await screen.findByText('10.0');
		void mocks.autoCallback!();
		await waitFor(() => expect(mocks.apiGet).toHaveBeenCalledTimes(8));
		mocks.auth.set({ ...authContext, token: null });
		await waitFor(() => expect(screen.queryByText('10.0')).toBeNull());
		pending.resolve(trend);
		await Promise.resolve();
		expect(screen.queryByText('10.0')).toBeNull();
		expect(mocks.apiGet).toHaveBeenCalledTimes(8);
	});

	it('keeps the same metric slots through first load, all-missing data, mixed coverage and refresh failure', async () => {
		const initialMetrics = deferred<unknown>();
		const nextMetrics = deferred<unknown>();
		const unavailable = { data: [], points: 0, available: false, source: null, status: 'not_collected', native_status: 'not_collected' };
		let metricReads = 0;
		mocks.apiGet.mockImplementation((path: string) => {
			if (!path.includes('/metrics/trend')) return Promise.resolve(resolveOverview(path));
			metricReads += 1;
			if (metricReads === 1) return initialMetrics.promise;
			if (metricReads === 2) return nextMetrics.promise;
			return Promise.reject(new Error('metrics unavailable'));
		});
		render(Page);
		const labels = ['vCPU 사용률 (14d)', '메모리 (14d)', '게스트 파일시스템 사용률 (14d)'];
		const slots = labels.map(name => screen.getByRole('group', { name }));
		for (const slot of slots) expect(slot.getAttribute('aria-busy')).toBe('true');
		initialMetrics.resolve({ ...trend, vcpu: unavailable, memory: unavailable, storage: unavailable });
		await waitFor(() => expect(within(slots[0]).getByText('해당 메트릭의 텔레메트리 미수집')).toBeTruthy());
		for (let index = 0; index < labels.length; index++) expect(screen.getByRole('group', { name: labels[index] })).toBe(slots[index]);
		await screen.findByText('최근 동기화', { exact: false });
		const refreshing = mocks.autoCallback!();
		await waitFor(() => expect(metricReads).toBe(2));
		expect(within(slots[0]).getByText('해당 메트릭의 텔레메트리 미수집')).toBeTruthy();
		expect(slots[0].getAttribute('aria-busy')).toBe('false');
		nextMetrics.resolve({ ...trend, vcpu: { ...trend.vcpu, data: [0, 12] }, storage: unavailable });
		await refreshing;
		await within(slots[0]).findByText('12.0');
		expect(within(slots[2]).getByText('해당 메트릭의 텔레메트리 미수집')).toBeTruthy();
		await mocks.autoCallback!();
		expect(within(slots[0]).getByText('12.0')).toBeTruthy();
		for (let index = 0; index < labels.length; index++) {
			expect(screen.getByRole('group', { name: labels[index] })).toBe(slots[index]);
			expect(within(slots[index]).getByText('갱신 실패')).toBeTruthy();
		}
	});

	it('keeps successful empty onboarding and notifications mounted during background refresh', async () => {
		const refreshRequests: Array<{ path: string; result: Deferred<unknown> }> = [];
		const emptySnapshot = { summary: { data: { instances: { total: 0, active: 0, shutoff: 0, error: 0 }, recent_instances: [] }, error: null }, quotas: { data: quotas, error: null } };
		let initial = true;
		mocks.apiGet.mockImplementation((path: string) => {
			if (initial) return Promise.resolve(path.includes('/snapshot') ? emptySnapshot : resolveOverview(path));
			const result = deferred<unknown>();
			refreshRequests.push({ path, result });
			return result.promise;
		});
		render(Page);
		const start = await screen.findByRole('region', { name: '첫 인스턴스 시작하기' });
		const emptyAlerts = await screen.findByText('알림 없음');
		await screen.findByText('최근 동기화', { exact: false });
		initial = false;
		const refreshing = mocks.autoCallback!();
		await waitFor(() => expect(refreshRequests).toHaveLength(4));
		expect(screen.getByRole('region', { name: '첫 인스턴스 시작하기' })).toBe(start);
		expect(screen.getByText('알림 없음')).toBe(emptyAlerts);
		expect(screen.queryByText('최근 인스턴스 로딩 중…')).toBeNull();
		for (const request of refreshRequests) request.result.reject(new Error('read failed'));
		await refreshing;
		expect(screen.getByRole('region', { name: '첫 인스턴스 시작하기' })).toBe(start);
		expect(screen.getByText('최근 인스턴스를 불러오지 못했습니다')).toBeTruthy();
		expect(screen.getByText('일부 알림을 불러오지 못했습니다')).toBeTruthy();
	});

	it('renders metric request errors in all three existing slots without claiming missing telemetry or measured zero', async () => {
		mocks.apiGet.mockImplementation((path: string) => path.includes('/metrics/trend')
			? Promise.reject(new Error('503')) : Promise.resolve(resolveOverview(path)));
		render(Page);
		const collection = within(screen.getByRole('region', { name: '텔레메트리 수집 상태' }));
		await waitFor(() => expect(collection.getAllByText('메트릭을 불러오지 못했습니다')).toHaveLength(3));
		for (const name of ['vCPU 사용률 (14d)', '메모리 (14d)', '게스트 파일시스템 사용률 (14d)']) {
			const card = within(collection.getByRole('group', { name }));
			expect(card.getByText('메트릭을 불러오지 못했습니다')).toBeTruthy();
			expect(card.queryByText('0.0')).toBeNull();
			expect(card.queryByText('해당 메트릭의 텔레메트리 미수집')).toBeNull();
		}
	});

	it('never substitutes zero for a missing newest sample while preserving finite sample history', async () => {
		mocks.apiGet.mockImplementation((path: string) => Promise.resolve(resolveOverview(path, {
			...trend, vcpu: { ...trend.vcpu, data: [0, 12, null], status: 'partial' },
		})));
		render(Page);
		const cpu = within(screen.getByRole('group', { name: 'vCPU 사용률 (14d)' }));
		await cpu.findByText('min 0.0% · max 12.0%');
		expect(cpu.queryByText('0.0')).toBeNull();
		expect(cpu.queryByText('12.0')).toBeNull();
	});

	it.each([true, false])('shows a real empty-project start area with create capability %s', async writable => {
		mocks.canWrite.set(writable);
		mocks.apiGet.mockImplementation((path: string) => Promise.resolve(path.includes('/snapshot')
			? { summary: { data: { instances: { total: 0, active: 0, shutoff: 0, error: 0 }, recent_instances: [] }, error: null }, quotas: { data: quotas, error: null } }
			: resolveOverview(path)));
		render(Page);
		const start = within(await screen.findByRole('region', { name: '첫 인스턴스 시작하기' }));
		expect(screen.getByRole('region', { name: '첫 인스턴스 시작하기' }).getAttribute('data-tour')).toBe('dashboard-recent');
		expect(Boolean(start.queryByRole('link', { name: '인스턴스 만들기' }))).toBe(writable);
		if (writable) expect(start.getByRole('link', { name: '인스턴스 만들기' }).getAttribute('href')).toBe('/dashboard/compute/instances');
		expect(start.getByRole('link', { name: '이미지 살펴보기' }).getAttribute('href')).toBe('/dashboard/compute/images');
		expect(start.getByRole('link', { name: '가이드 열기' }).getAttribute('href')).toBe('/docs');
	});

	it('never turns a failed instance snapshot into an empty-project start area', async () => {
		mocks.apiGet.mockImplementation((path: string) => Promise.resolve(path.includes('/snapshot')
			? { summary: { data: null, error: 'unavailable' }, quotas: { data: quotas, error: null } }
			: resolveOverview(path)));
		render(Page);
		await screen.findByText('최근 인스턴스를 불러오지 못했습니다');
		expect(screen.queryByRole('region', { name: '첫 인스턴스 시작하기' })).toBeNull();
	});

});
