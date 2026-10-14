import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import HostHealthPanel from './HostHealthPanel.svelte';
import HostMetricCell from './HostMetricCell.svelte';
import { continuousMetricTail, type HostHealthSnapshot } from '$lib/types/hostHealth';
import { auth } from '$lib/stores/auth';
import { t } from '$lib/i18n/ns/admin-compute';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: { get } }));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'token-a', userId: 'user-a', projectId: 'project-a', isSystemAdmin: true }), authReady: writable(true), projectSwitching: writable(false) }));

function observations(name = 'compute-a', stale = false): HostHealthSnapshot {
	const metric = (value: number) => ({ value, unit: '%' as const, series: [{ ts: 100, value: value - 10 }, { ts: 110, value }] });
	return {
		enabled: true, interval_seconds: 10, collected_at: new Date().toISOString(), stale, error: null,
		hosts: [{
			id: name, name, role: 'compute', address: '10.0.0.10',
			reachability: { status: 'up', checked_at: new Date().toISOString(), latency_ms: 2.5, error: null },
			heartbeat: { status: 'up', updated_at: new Date().toISOString(), source: 'nova-compute' },
			metrics: { cpu: metric(25), memory: metric(50), disk: metric(75), network_rx: { ...metric(1024), unit: 'B/s' }, network_tx: { ...metric(2048), unit: 'B/s' } },
			metrics_error: null,
			interfaces: null, interfaces_omitted: null,
		}],
	};
}

beforeEach(() => {
	get.mockReset();
	auth.set({ token: 'token-a', userId: 'user-a', projectId: 'project-a', isSystemAdmin: true } as never);
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

describe('host resource observations', () => {
	it('does not connect sparkline points across missing samples or missed collection rounds', () => {
		expect(continuousMetricTail([{ ts: 100, value: 80 }, { ts: 110, value: null }, { ts: 120, value: 20 }, { ts: 130, value: 30 }])).toEqual([20, 30]);
		expect(continuousMetricTail([{ ts: 100, value: 80 }, { ts: 150, value: 20 }, { ts: 160, value: 30 }])).toEqual([20, 30]);
		expect(continuousMetricTail([{ ts: 100, value: 80 }, { ts: 110, value: null }])).toEqual([]);
	});

	it('distinguishes measured zero from missing utilization', async () => {
		const { rerender } = render(HostMetricCell, { metric: { value: 0, unit: '%', series: [] }, verified: true, label: 'CPU' });
		expect(screen.getByLabelText('CPU: 0%')).toBeTruthy();
		await rerender({ metric: { value: null, unit: '%', series: [] }, verified: true, label: 'CPU' });
		expect(screen.queryByText('0%')).toBeNull();
		expect(screen.getByLabelText(`CPU: ${t('hostHealth.unmeasured')}`)).toBeTruthy();
	});

	it('masks healthy badges and current utilization when the collector snapshot is stale', async () => {
		get.mockResolvedValue(observations('compute-a', true));
		render(HostHealthPanel);
		await screen.findByText(t('hostHealth.stale'));
		expect(screen.queryByText('25%')).toBeNull();
		expect(screen.queryByText(t('hostHealth.connection.up'))).toBeNull();
		expect(screen.queryByText(t('hostHealth.heartbeat.up'))).toBeNull();
		expect(screen.getAllByText(t('hostHealth.connection.unknown')).length).toBeGreaterThan(0);
	});

	it('preserves host identity but does not reuse current healthy proof after a polling failure', async () => {
		get.mockResolvedValueOnce(observations()).mockRejectedValue(new Error('unavailable'));
		render(HostHealthPanel);
		await screen.findAllByText('25%');
		await fireEvent.click(screen.getByRole('button', { name: t('hostHealth.refresh') }));
		await screen.findByText(t('hostHealth.loadFailed'));
		expect(screen.getAllByText('compute-a').length).toBeGreaterThan(0);
		expect(screen.queryByText('25%')).toBeNull();
		expect(screen.queryByText(t('hostHealth.connection.up'))).toBeNull();
	});

	it('discards an old response across an A→B→A identity transition', async () => {
		let resolveOld!: (value: HostHealthSnapshot) => void;
		get.mockImplementationOnce(() => new Promise<HostHealthSnapshot>((resolve) => { resolveOld = resolve; })).mockResolvedValue(observations('new-compute'));
		render(HostHealthPanel);
		await waitFor(() => expect(resolveOld).toBeTypeOf('function'));
		auth.set({ token: 'token-b', userId: 'user-b', projectId: 'project-b', isSystemAdmin: true } as never);
		await screen.findAllByText('new-compute');
		auth.set({ token: 'token-a', userId: 'user-a', projectId: 'project-a', isSystemAdmin: true } as never);
		await screen.findAllByText('new-compute');
		resolveOld(observations('old-private-compute'));
		await waitFor(() => expect(screen.queryByText('old-private-compute')).toBeNull());
		expect(screen.getAllByText('new-compute').length).toBeGreaterThan(0);
	});

	it('removes the previous inventory when administrator authority is lost', async () => {
		get.mockResolvedValue(observations('private-compute'));
		render(HostHealthPanel);
		await screen.findAllByText('private-compute');
		auth.set({ token: 'token-a', userId: 'user-a', projectId: 'project-a', isSystemAdmin: false } as never);
		await waitFor(() => expect(screen.queryByText('private-compute')).toBeNull());
		expect(screen.queryByText('25%')).toBeNull();
	});
});
