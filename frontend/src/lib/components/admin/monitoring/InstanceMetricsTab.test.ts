import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { writable } from 'svelte/store';
import { tick } from 'svelte';
import { setLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/admin-ops';
import { t as commonT } from '$lib/i18n/ns/common';

const mocks = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: { get: mocks.get } }));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token-a', projectId: 'admin-project', userId: 'admin-a', sessionId: 'session-a', isSystemAdmin: true }),
	authReady: writable(true),
	projectSwitching: writable(false),
	getAuthVerificationEpoch: () => 0,
}));
vi.mock('$lib/stores/servicePermissions', () => ({
	observedProjectPermissions: writable({ loading: false, error: null, permissions: null }),
}));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({ active: false, intervalSeconds: 30, intervalOptions: [15, 30, 60], setBoost: vi.fn() }),
}));
vi.mock('$lib/components/charts/runtime', () => ({
	mountChart: () => ({ update: vi.fn(), destroy: vi.fn() }),
}));

import { auth } from '$lib/stores/auth';
import InstanceMetricsTab, { type AdminInstance } from './InstanceMetricsTab.svelte';
import type { NativeMeter } from './MonitoringSummaryTab.svelte';

interface InstancePage {
	items: AdminInstance[];
	next_marker: string | null;
	count: number;
}
interface MetricBatchFixture {
	metrics: Record<string, NativeMeter & { native_status: string }>;
}

const instance = (id: string, project_id: string | null = 'tenant-a'): AdminInstance => ({
	id, name: id, status: 'ACTIVE', project_id, flavor: 'small', host: 'compute-a',
});
const list = (items: AdminInstance[]): InstancePage => ({ items, next_marker: null, count: items.length });
const metrics = (value: number): MetricBatchFixture => ({ metrics: {
	cpu: { series: [{ ts: 60, value }, { ts: 120, value }], error: null, source: 'gnocchi', unit: '%', status: 'available', native_status: 'available' },
} });

beforeEach(() => {
	setLocale('en');
	auth.update(state => ({ ...state, token: 'token-a', projectId: 'admin-project', userId: 'admin-a', sessionId: 'session-a', isSystemAdmin: true }));
	mocks.get.mockReset().mockImplementation((path: string) => {
		if (path.startsWith('/api/v1/admin/all-instances')) return Promise.resolve(list([instance('vm-a'), instance('vm-b', 'tenant-b')]));
		if (path.includes('/metrics-summary')) return Promise.resolve({ monitoring_available: true, stats: {} });
		if (path.includes('/metrics-batch')) return Promise.resolve(metrics(31.25));
		return Promise.resolve([]);
	});
});
afterEach(() => { cleanup(); setLocale('ko'); });

describe('administrator instance telemetry context', () => {
	it('retains local conditions on refresh but clears them when the inventory context changes', async () => {
		let reload: (() => void) | undefined;
		const { rerender } = render(InstanceMetricsTab, { token: 'token-a', projectId: 'admin-project', onReload: fn => { reload = fn; } });
		await screen.findByRole('button', { name: /vm-a/ });
		const filterLabel = commonT('table.filterColumn', { column: commonT('table.host') });
		await fireEvent.click(screen.getByRole('button', { name: filterLabel }));
		const popup = screen.getByRole('dialog', { name: filterLabel });
		await fireEvent.click(within(popup).getByRole('checkbox', { name: 'compute-a' }));
		await fireEvent.click(within(popup).getByRole('button', { name: commonT('table.ascending') }));
		await fireEvent.keyDown(popup, { key: 'Escape' });
		await fireEvent.input(screen.getByLabelText(t('monitoring.instances.search')), { target: { value: 'vm-a' } });
		reload!();
		await waitFor(() => expect(mocks.get.mock.calls.filter(([path]) => path.startsWith('/api/v1/admin/all-instances'))).toHaveLength(2));
		await tick();
		expect((screen.getByLabelText(t('monitoring.instances.search')) as HTMLInputElement).value).toBe('vm-a');
		expect(screen.queryByRole('button', { name: /vm-a/ })).toBeNull();
		expect(screen.getByRole('button', { name: filterLabel }).hasAttribute('aria-describedby')).toBe(true);

		mocks.get.mockResolvedValue(list([{ ...instance('fresh-vm', 'tenant-new'), host: 'compute-new' }]));
		await rerender({ token: 'token-a', projectId: 'new-project', onReload: fn => { reload = fn; } });
		await screen.findByRole('button', { name: /fresh-vm/ });
		expect((screen.getByLabelText(t('monitoring.instances.search')) as HTMLInputElement).value).toBe('');
		expect(screen.getByRole('button', { name: filterLabel }).hasAttribute('aria-describedby')).toBe(false);
		expect(screen.getByRole('button', { name: commonT('table.sortColumn', { column: commonT('table.host'), direction: commonT('table.none') }) })).toBeTruthy();
	});

	it('uses explicit administrator metrics in caller context and discards a previous instance response', async () => {
		const oldMetrics = Promise.withResolvers<MetricBatchFixture>();
		mocks.get.mockImplementation((path: string) => {
			if (path.startsWith('/api/v1/admin/all-instances')) return Promise.resolve(list([instance('vm-a'), instance('vm-b', 'tenant-b')]));
			if (path.includes('/metrics-summary')) return Promise.resolve({ monitoring_available: true, stats: {} });
			if (path.includes('/instances/vm-a/metrics-batch')) return oldMetrics.promise;
			if (path.includes('/instances/vm-b/metrics-batch')) return Promise.resolve(metrics(31.25));
			return Promise.resolve([]);
		});
		render(InstanceMetricsTab, { token: 'token-a', projectId: 'admin-project' });
		await fireEvent.click(await screen.findByRole('button', { name: /vm-a/ }));
		await waitFor(() => expect(mocks.get.mock.calls.some(([path, token, project]) => path.includes('/admin/instances/vm-a/metrics-batch') && token === 'token-a' && project === 'admin-project')).toBe(true));
		await fireEvent.click(screen.getByRole('button', { name: /vm-b/ }));
		await waitFor(() => expect(mocks.get.mock.calls.some(([path, token, project]) => path.includes('/admin/instances/vm-b/metrics-batch') && token === 'token-a' && project === 'admin-project')).toBe(true));
		oldMetrics.resolve(metrics(97.345));
		await oldMetrics.promise;
		await tick();
		expect(screen.queryByText(/97\.3/)).toBeNull();
		expect(screen.getByRole('button', { name: /vm-b/ }).getAttribute('aria-pressed')).toBe('true');
	});

	it('clears selection and ignores an old inventory page after token/project changes', async () => {
		const pending = Promise.withResolvers<InstancePage>();
		let reload: (() => void) | undefined;
		const { rerender } = render(InstanceMetricsTab, { token: 'token-a', projectId: 'admin-project', onReload: fn => { reload = fn; } });
		await fireEvent.click(await screen.findByRole('button', { name: /vm-a/ }));
		mocks.get.mockImplementation((path: string, token?: string) => {
			if (path.startsWith('/api/v1/admin/all-instances')) return token === 'token-a' ? pending.promise : Promise.resolve(list([instance('new-private-vm', 'tenant-new')]));
			if (path.includes('/metrics-summary')) return Promise.resolve({ monitoring_available: true, stats: {} });
			return Promise.resolve(metrics(31.25));
		});
		reload!();
		auth.update(state => ({ ...state, token: 'token-new', projectId: 'admin-new', userId: 'admin-new', sessionId: 'session-new' }));
		await rerender({ token: 'token-new', projectId: 'admin-new', onReload: fn => { reload = fn; } });
		await screen.findByRole('button', { name: /new-private-vm/ });
		pending.resolve(list([instance('old-private-vm')]));
		await pending.promise;
		await tick();
		expect(screen.queryByRole('button', { name: /old-private-vm/ })).toBeNull();
		expect(screen.queryByText('vm-a')).toBeNull();
		expect(screen.getByText(t('monitoring.instances.select'))).toBeTruthy();
	});

	it('keeps private measurements closed when inventory cannot establish an owning project', async () => {
		mocks.get.mockResolvedValue(list([instance('owner-unknown', null)]));
		render(InstanceMetricsTab, { token: 'token-a', projectId: 'admin-project' });
		await fireEvent.click(await screen.findByRole('button', { name: /owner-unknown/ }));
		expect(screen.getByText(t('monitoring.instances.unknownProject'))).toBeTruthy();
		expect(mocks.get.mock.calls.some(([path]) => path.includes('/metrics-'))).toBe(false);
	});

	it('does not resurrect inventory during an auth A → B → A transition in one task', async () => {
		const stale = Promise.withResolvers<InstancePage>();
		mocks.get.mockReturnValueOnce(stale.promise).mockResolvedValue(list([instance('fresh-vm')]));
		render(InstanceMetricsTab, { token: 'token-a', projectId: 'admin-project' });
		await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(1));
		auth.update(state => ({ ...state, projectId: 'other-project' }));
		auth.update(state => ({ ...state, projectId: 'admin-project' }));
		await screen.findByRole('button', { name: /fresh-vm/ });
		stale.resolve(list([instance('stale-private-vm')]));
		await stale.promise;
		await tick();
		expect(screen.queryByRole('button', { name: /stale-private-vm/ })).toBeNull();
	});
});
