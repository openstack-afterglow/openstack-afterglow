import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';

const mocks = vi.hoisted(() => {
	function store<T>(initial: T) {
		let value = initial;
		const subscribers = new Set<(value: T) => void>();
		return {
			subscribe(subscriber: (value: T) => void) {
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
		auth: store({ token: 'token' as string | null, userId: 'user', identityDomainId: 'domain', projectId: 'project', projectName: 'Project One' }),
		authReady: store(true),
		get: vi.fn(),
		autoCallback: null as (() => Promise<void>) | null,
	};
});

vi.mock('$lib/api/client', () => ({ api: { get: mocks.get } }));
vi.mock('$lib/stores/auth', () => ({ auth: mocks.auth, authReady: mocks.authReady }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: (callback: () => Promise<void>) => {
		mocks.autoCallback = callback;
		return { active: false, intervalSeconds: 60, intervalOptions: [30, 60] };
	},
}));

import Page from '../+page.svelte';

const authContext = { token: 'token', userId: 'user', identityDomainId: 'domain', projectId: 'project', projectName: 'Project One' };
const collected = { data: [10], points: 1, available: true, source: 'gnocchi', status: 'available', native_status: 'available' };
const empty = { data: [], points: 0, available: false, source: null, status: 'not_collected', native_status: 'not_collected' };
const trend = {
	range: '7d', monitoring_available: true,
	vcpu: collected, memory: empty, storage: empty,
	network: { ...empty, unit: 'KiB/s' },
};
const instance = {
	id: 'instance', name: 'measured-instance', flavor_name: 'small', vcpus: 2, ram_mb: 2048, disk_gb: 20,
	status: 'ACTIVE', usage_hours: 4, cpu_pct: 0, ram_pct: 42,
	cpu_source: 'gnocchi', ram_source: 'prometheus', cpu_status: 'available', ram_status: 'available',
	cpu_native_status: 'available', ram_native_status: 'not_configured',
};
const stats = { range: '7d', top_instances: [instance] };
type Request = { path: string; token: string; project: string; signal: AbortSignal; pending: PromiseWithResolvers<unknown> };

function deferRequests(): Request[] {
	const requests: Request[] = [];
	mocks.get.mockImplementation((path: string, token: string, project: string, options: { signal: AbortSignal }) => {
		const pending = Promise.withResolvers<unknown>();
		requests.push({ path, token, project, signal: options.signal, pending });
		return pending.promise;
	});
	return requests;
}

function resolveRequests(requests: Request[], name = instance.name, cpu = 10, period = '7d', range = '7d') {
	for (const request of requests) {
		request.pending.resolve(request.path.includes('/metrics/trend')
			? { ...trend, range, vcpu: { ...collected, data: [cpu] } }
			: { ...stats, range: period, top_instances: [{ ...instance, name }] });
	}
}

beforeEach(() => {
	mocks.auth.set(authContext);
	mocks.authReady.set(true);
	mocks.get.mockReset();
	mocks.autoCallback = null;
	localStorage.clear();
});
afterEach(() => cleanup());

describe('usage loading boundaries', () => {
	it('renders usage stats while best-effort trends remain pending or fail', async () => {
		const statsRequest = Promise.withResolvers<unknown>();
		const trendRequest = Promise.withResolvers<unknown>();
		mocks.get.mockImplementation((path: string) => path.includes('/metrics/trend') ? trendRequest.promise : statsRequest.promise);

		render(Page);
		await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(2));
		statsRequest.resolve({ range: '7d', top_instances: [] });
		expect(await screen.findByText('인스턴스 없음')).toBeTruthy();
		expect(screen.getByText('추세 메트릭을 불러오는 중...')).toBeTruthy();

		trendRequest.reject(new Error('trend unavailable'));
		await waitFor(() => expect(screen.queryByText('추세 메트릭을 불러오는 중...')).toBeNull());
		expect(screen.getByText('인스턴스 없음')).toBeTruthy();
		expect(screen.getAllByText('메트릭을 불러오지 못했습니다')).toHaveLength(4);
		expect(screen.queryByText('메트릭 수집 미설정')).toBeNull();
	});

	it('shows native zero, partial and fallback measurements with truthful filesystem and KiB/s units', async () => {
		mocks.get.mockImplementation((path: string) => Promise.resolve(path.includes('/metrics/trend') ? {
			...trend, scope: 'native_policy',
			vcpu: { ...collected, data: [0], status: 'partial', native_status: 'partial' },
			storage: { ...collected, data: [22], source: 'prometheus', native_status: 'not_configured' },
			network: { ...collected, data: [2048], unit: 'KiB/s' },
		} : stats));
		render(Page);
		await screen.findByText(instance.name);
		const cpu = within(screen.getByRole('group', { name: 'vCPU 7d 추세' }));
		expect(cpu.getByText('0.0')).toBeTruthy();
		expect(cpu.getByText('네이티브 텔레메트리 · Gnocchi')).toBeTruthy();
		expect(cpu.getByText('부분 수집 · 일부 표본 또는 리소스 누락')).toBeTruthy();
		const ram = within(screen.getByRole('group', { name: 'RAM 7d 추세' }));
		expect(ram.getByText('해당 메트릭의 텔레메트리 미수집')).toBeTruthy();
		expect(ram.queryByText('0.0')).toBeNull();
		const disk = within(screen.getByRole('group', { name: '게스트 파일시스템 7d 추세' }));
		expect(disk.getByText('min 22.0% · max 22.0%')).toBeTruthy();
		expect(disk.getByText('Exporter 대체 수집 · Prometheus')).toBeTruthy();
		expect(disk.getByText('네이티브 텔레메트리: 메트릭 수집 미설정')).toBeTruthy();
		const network = within(screen.getByRole('group', { name: '네트워크 7d 추세' }));
		expect(network.getByText('2048.0')).toBeTruthy();
		expect(network.getByText('KiB/s')).toBeTruthy();
		expect(network.queryByText('MiB/s')).toBeNull();
		expect(screen.getByText('네이티브 범위는 현재 사용자 정책에 표시되는 리소스로 제한됩니다.')).toBeTruthy();
		const row = within(screen.getByRole('row', { name: /measured-instance/ }));
		expect(row.getByText('0%')).toBeTruthy();
		expect(row.getByText('42%')).toBeTruthy();
		expect(row.getByText('네이티브 텔레메트리 · Gnocchi')).toBeTruthy();
		expect(row.getByText('Exporter 대체 수집 · Prometheus')).toBeTruthy();
	});

	it('does not paint unavailable row metrics as zero or measured values', async () => {
		mocks.get.mockImplementation((path: string) => Promise.resolve(path.includes('/metrics/trend') ? {
			...trend, vcpu: { ...collected, data: [88], available: false, status: 'unavailable', native_status: 'unavailable' },
		} : {
			...stats, top_instances: [{ ...instance, cpu_pct: 88, ram_pct: 0, cpu_status: 'unavailable', ram_status: 'not_collected', cpu_source: null, ram_source: null }],
		}));
		render(Page);
		await screen.findByText(instance.name);
		const row = within(screen.getByRole('row', { name: /measured-instance/ }));
		expect(row.queryByText('88%')).toBeNull();
		expect(row.queryByText('0%')).toBeNull();
		expect(row.getAllByText('—')).toHaveLength(2);
		expect(row.queryByRole('progressbar')).toBeNull();
		expect(row.getByText('텔레메트리를 사용할 수 없음')).toBeTruthy();
		expect(row.getByText('해당 메트릭의 텔레메트리 미수집')).toBeTruthy();
		const cpuTrend = within(screen.getByRole('group', { name: 'vCPU 7d 추세' }));
		expect(cpuTrend.queryByText('88.0')).toBeNull();
		expect(cpuTrend.queryByText(/min .*max/)).toBeNull();
		expect(cpuTrend.getByText('텔레메트리를 사용할 수 없음')).toBeTruthy();
	});

	it.each([
		[true, 'not_collected', '해당 메트릭의 텔레메트리 미수집'],
		[false, 'not_configured', '메트릭 수집 미설정'],
	] as const)('distinguishes readable empty telemetry from unconfigured providers (%s)', async (available, status, message) => {
		const missing = { ...empty, status, native_status: status };
		mocks.get.mockImplementation((path: string) => Promise.resolve(path.includes('/metrics/trend')
			? { ...trend, monitoring_available: available, vcpu: missing, memory: missing, storage: missing, network: { ...missing, unit: 'KiB/s' } }
			: { range: '7d', top_instances: [] }));
		render(Page);
		await waitFor(() => expect(screen.getAllByText(message)).toHaveLength(4));
		expect(screen.queryByText('0.0')).toBeNull();
		expect(screen.queryByText(/min .*max/)).toBeNull();
		if (available) expect(screen.queryByText('메트릭 수집 미설정')).toBeNull();
	});

	it.each(['token', 'userId', 'identityDomainId', 'projectId'] as const)('clears private data on %s changes and rejects late refreshes', async (field) => {
		const requests = deferRequests();
		render(Page);
		await waitFor(() => expect(requests).toHaveLength(2));
		resolveRequests(requests);
		await screen.findByText(instance.name);
		await screen.findByText('10.0');
		void mocks.autoCallback!();
		await waitFor(() => expect(requests).toHaveLength(4));
		const stale = requests.slice(2);
		mocks.auth.set({ ...authContext, [field]: 'next-context' });
		await waitFor(() => expect(requests).toHaveLength(6));
		expect(screen.queryByText(instance.name)).toBeNull();
		expect(screen.queryByText('10.0')).toBeNull();
		expect(stale.every(({ signal }) => signal.aborted)).toBe(true);
		expect(requests.slice(4).every((request) => request.token === (field === 'token' ? 'next-context' : authContext.token)
			&& request.project === (field === 'projectId' ? 'next-context' : authContext.projectId))).toBe(true);
		resolveRequests(stale, 'stale-instance', 91);
		resolveRequests(requests.slice(4), 'current-instance', 7);
		await screen.findByText('current-instance');
		await screen.findByText('7.0');
		expect(screen.queryByText('stale-instance')).toBeNull();
		expect(screen.queryByText('91.0')).toBeNull();
	});

	it('clears the old range while the 30d table and 14d trend load and rejects a late 7d trend', async () => {
		const requests = deferRequests();
		render(Page);
		await waitFor(() => expect(requests).toHaveLength(2));
		resolveRequests(requests);
		await screen.findByText('10.0');
		void mocks.autoCallback!();
		await waitFor(() => expect(requests).toHaveLength(4));
		await fireEvent.click(screen.getByRole('button', { name: '30d' }));
		await waitFor(() => expect(requests).toHaveLength(6));
		expect(requests[4].path).toContain('usage-stats?range=30d');
		expect(requests[5].path).toContain('metrics/trend?range=14d');
		expect(screen.queryByText('10.0')).toBeNull();
		expect(screen.queryByText(instance.name)).toBeNull();
		resolveRequests(requests.slice(2, 4), 'old-range-instance', 91);
		resolveRequests(requests.slice(4), 'current-range-instance', 7, '30d', '14d');
		await screen.findByText('current-range-instance');
		await screen.findByText('7.0');
		expect(screen.getByRole('group', { name: 'vCPU 14d 추세' })).toBeTruthy();
		expect(screen.queryByText('old-range-instance')).toBeNull();
		expect(screen.queryByText('91.0')).toBeNull();
	});

	it('rejects the original response after an A → B → A project switch', async () => {
		const requests = deferRequests();
		render(Page);
		await waitFor(() => expect(requests).toHaveLength(2));
		mocks.auth.set({ ...authContext, projectId: 'project-b' });
		await waitFor(() => expect(requests).toHaveLength(4));
		mocks.auth.set(authContext);
		await waitFor(() => expect(requests).toHaveLength(6));
		resolveRequests(requests.slice(0, 4), 'retired-instance', 91);
		resolveRequests(requests.slice(4), 'fresh-instance', 7);
		await screen.findByText('fresh-instance');
		await screen.findByText('7.0');
		expect(screen.queryByText('retired-instance')).toBeNull();
		expect(screen.queryByText('91.0')).toBeNull();
	});

	it('waits for auth readiness and clears loaded data when readiness is revoked', async () => {
		mocks.authReady.set(false);
		mocks.get.mockImplementation((path: string) => Promise.resolve(path.includes('/metrics/trend') ? trend : stats));
		render(Page);
		await Promise.resolve();
		expect(mocks.get).not.toHaveBeenCalled();
		mocks.authReady.set(true);
		await screen.findByText(instance.name);
		await screen.findByText('10.0');
		mocks.authReady.set(false);
		await waitFor(() => expect(screen.queryByText(instance.name)).toBeNull());
		expect(screen.queryByText('10.0')).toBeNull();
		expect(mocks.get).toHaveBeenCalledTimes(2);
	});
});
