import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';

const mocks = vi.hoisted(() => {
	type Subscriber<T> = (value: T) => void;
	function store<T>(initial: T) {
		let value = initial;
		const subscribers = new Set<Subscriber<T>>();
		return {
			subscribe(subscriber: Subscriber<T>) {
				subscribers.add(subscriber);
				subscriber(value);
				return () => subscribers.delete(subscriber);
			},
			set(next: T) {
				value = next;
				for (const subscriber of subscribers) subscriber(value);
			},
		};
	}

	return {
		auth: store({
			token: 'token-a' as string | null,
			username: 'tester' as string | null,
			projectId: 'project-a' as string | null,
			projectName: 'Project A' as string | null,
		}),
		authReady: store(true),
		siteConfig: store({ services: { k3s: true } }),
		apiGet: vi.fn(),
		autoCallback: null as (() => void | Promise<void>) | null,
	};
});

vi.mock('$lib/stores/auth', () => ({ auth: mocks.auth, authReady: mocks.authReady }));
vi.mock('$lib/config/site', () => ({ siteConfig: mocks.siteConfig }));
vi.mock('$lib/api/client', () => ({ api: { get: mocks.apiGet } }));
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
	vcpu: { data: [10], points: 1, available: true },
	memory: { data: [20], points: 1, available: true },
	storage: { data: [30], points: 1, available: true },
	network: { data: [], points: 0, available: false, unit: 'KiB/s' },
	prometheus_available: true,
	range: '14d' as const,
};
const announcements: unknown[] = [];

beforeEach(() => {
	mocks.auth.set({ token: 'token-a', username: 'tester', projectId: 'project-a', projectName: 'Project A' });
	mocks.authReady.set(true);
	mocks.siteConfig.set({ services: { k3s: true } });
	mocks.apiGet.mockReset();
	mocks.autoCallback = null;
	localStorage.clear();
});

afterEach(() => cleanup());

describe('dashboard overview loading', () => {
	it('starts five independent overview requests and renders the summary before slow domains settle', async () => {
		const requests = new Map<string, Deferred<unknown>>();
		mocks.apiGet.mockImplementation((path: string) => {
			const pending = deferred<unknown>();
			requests.set(path, pending);
			return pending.promise;
		});

		const rendered = render(Page);
		expect(screen.queryByText('인스턴스가 없습니다')).toBeNull();
		expect(screen.queryByText('메트릭 수집 미설정')).toBeNull();
		await waitFor(() => expect(mocks.apiGet).toHaveBeenCalledTimes(5));
		const paths = mocks.apiGet.mock.calls.map(([path]) => path);
		expect(paths).toEqual(expect.arrayContaining([
			'/api/v1/dashboard/summary?view=overview&recent_limit=12',
			'/api/v1/dashboard/quotas?view=overview',
			'/api/v1/dashboard/k3s-stats',
			'/api/v1/dashboard/metrics/trend?range=14d&include_network=false',
			'/api/v1/announcements',
		]));
		expect(paths.join(' ')).not.toContain('/api/v1/instances');
		expect(paths.join(' ')).not.toContain('/api/v1/dashboard/notifications');
		expect(paths.join(' ')).not.toContain('/api/v1/k3s/clusters');

		requests.get('/api/v1/dashboard/summary?view=overview&recent_limit=12')!.resolve(summary);
		await screen.findByText('newest');
		expect(screen.getByText('일부 동기화', { exact: false })).toBeTruthy();

		requests.get('/api/v1/dashboard/quotas?view=overview')!.resolve(quotas);
		requests.get('/api/v1/dashboard/k3s-stats')!.resolve({ total: 1, active: 1, available: true });
		requests.get('/api/v1/dashboard/metrics/trend?range=14d&include_network=false')!.resolve(trend);
		requests.get('/api/v1/announcements')!.resolve(announcements);
		await waitFor(() => expect(screen.getByText('최근 동기화', { exact: false })).toBeTruthy());
		expect(screen.getAllByText('/ 0').length).toBeGreaterThan(0);
		expect(screen.queryByText('Manila Shares')).toBeNull();
		rendered.unmount();
	});

	it('skips K3s when disabled and requests exactly four domains', async () => {
		mocks.siteConfig.set({ services: { k3s: false } });
		mocks.apiGet.mockImplementation((path: string) => {
			if (path.includes('/summary')) return Promise.resolve(summary);
			if (path.includes('/quotas')) return Promise.resolve(quotas);
			if (path.includes('/announcements')) return Promise.resolve(announcements);
			return Promise.resolve(trend);
		});

		render(Page);
		await waitFor(() => expect(mocks.apiGet).toHaveBeenCalledTimes(4));
		expect(mocks.apiGet.mock.calls.map(([path]) => path)).not.toContain('/api/v1/dashboard/k3s-stats');
		expect(screen.getByText('N/A')).toBeTruthy();
	});

	it('keeps terminal states hidden and makes no request until auth hydration completes', async () => {
		mocks.authReady.set(false);
		mocks.apiGet.mockImplementation((path: string) => {
			if (path.includes('/summary')) return Promise.resolve(summary);
			if (path.includes('/quotas')) return Promise.resolve(quotas);
			if (path.includes('/k3s-stats')) return Promise.resolve({ total: 1, active: 1, available: true });
			if (path.includes('/announcements')) return Promise.resolve(announcements);
			return Promise.resolve(trend);
		});

		render(Page);
		await Promise.resolve();
		expect(mocks.apiGet).not.toHaveBeenCalled();
		expect(screen.queryByText('인스턴스가 없습니다')).toBeNull();
		expect(screen.queryByText('메트릭 수집 미설정')).toBeNull();

		mocks.authReady.set(true);
		await waitFor(() => expect(mocks.apiGet).toHaveBeenCalledTimes(5));
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
		await waitFor(() => expect(requests).toHaveLength(5));
		const oldRequests = [...requests];
		mocks.auth.set({ token: 'token-b', username: 'tester', projectId: 'project-b', projectName: 'Project B' });
		await waitFor(() => expect(requests).toHaveLength(10));
		expect(oldRequests.every((request) => request.signal?.aborted)).toBe(true);
		expect(requests.slice(5).every((request) => request.projectId === 'project-b')).toBe(true);

		oldRequests.find((request) => request.path.includes('/summary'))!.pending.resolve({
			...summary,
			recent_instances: [{ ...summary.recent_instances[0], name: 'old-project-instance' }],
		});
		await Promise.resolve();
		expect(screen.queryByText('old-project-instance')).toBeNull();

		for (const request of requests.slice(5)) {
			if (request.path.includes('/summary')) request.pending.resolve({
				...summary,
				recent_instances: [{ ...summary.recent_instances[0], name: 'new-project-instance' }],
			});
			else if (request.path.includes('/quotas')) request.pending.resolve(quotas);
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
			if (callCount <= 5) {
				if (path.includes('/summary')) return Promise.resolve(summary);
				if (path.includes('/quotas')) return Promise.resolve(quotas);
				if (path.includes('/k3s-stats')) return Promise.resolve({ total: 1, active: 1, available: true });
				if (path.includes('/announcements')) return Promise.resolve(announcements);
				return Promise.resolve(trend);
			}
			const pending = deferred<unknown>();
			manualRequests.push({ path, options, pending });
			return pending.promise;
		});

		render(Page);
		await waitFor(() => expect(mocks.apiGet).toHaveBeenCalledTimes(5));
		await screen.findByText('최근 동기화', { exact: false });
		await fireEvent.click(screen.getByTitle('지금 새로고침'));
		await waitFor(() => expect(manualRequests).toHaveLength(5));
		expect(manualRequests.every((request) => request.options.refresh === true)).toBe(true);
		expect(screen.getByTitle('로딩 중…')).toBeTruthy();

		const originalTrend = manualRequests.find((request) => request.path.includes('/metrics/trend'))!;
		await fireEvent.click(screen.getByRole('button', { name: '24h' }));
		await waitFor(() => expect(manualRequests).toHaveLength(6));
		const replacementTrend = manualRequests.at(-1)!;
		expect(originalTrend.options.signal?.aborted).toBe(true);
		expect(replacementTrend.path).toContain('range=24h');
		expect(replacementTrend.options.refresh).toBe(true);

		const auto = mocks.autoCallback!();
		await Promise.resolve();
		expect(manualRequests).toHaveLength(6);
		for (const request of manualRequests) {
			if (request === originalTrend) continue;
			if (request.path.includes('/summary')) request.pending.resolve(summary);
			else if (request.path.includes('/quotas')) request.pending.resolve(quotas);
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
		await waitFor(() => expect(requests).toHaveLength(5));
		const originalTrend = requests.find((request) => request.path.includes('/metrics/trend'))!;
		await fireEvent.click(screen.getByRole('button', { name: '24h' }));
		await waitFor(() => expect(requests).toHaveLength(6));
		expect(originalTrend.signal?.aborted).toBe(true);
		for (const request of requests.slice(0, 5)) {
			if (request === originalTrend) continue;
			if (request.path.includes('/summary')) request.pending.resolve(summary);
			else if (request.path.includes('/quotas')) request.pending.resolve(quotas);
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
			if (callCount > 5) return Promise.reject(new Error(`failed ${path}`));
			if (path.includes('/summary')) return Promise.resolve(summary);
			if (path.includes('/quotas')) return Promise.resolve(quotas);
			if (path.includes('/k3s-stats')) return Promise.resolve({ total: 1, active: 1, available: true });
			if (path.includes('/announcements')) return Promise.resolve(announcements);
			return Promise.resolve(trend);
		});

		render(Page);
		await screen.findByText('newest');
		await screen.findByText('최근 동기화', { exact: false });
		await fireEvent.click(screen.getByTitle('지금 새로고침'));
		await waitFor(() => expect(mocks.apiGet).toHaveBeenCalledTimes(10));
		expect(screen.getByText('newest')).toBeTruthy();
		expect(screen.getByText('최근 동기화', { exact: false })).toBeTruthy();
		await waitFor(() => expect(screen.getByTitle('지금 새로고침')).toBeTruthy());
	});

	it('renders exact Korean unavailable text when K3s stats return available false', async () => {
		mocks.apiGet.mockImplementation((path: string) => {
			if (path.includes('/summary')) return Promise.resolve(summary);
			if (path.includes('/quotas')) return Promise.resolve(quotas);
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
		await waitFor(() => expect(requests).toHaveLength(5));
		rendered.unmount();
		expect(requests.every((request) => request.signal?.aborted)).toBe(true);
	});
});
