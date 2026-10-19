import { cleanup, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { writable } from 'svelte/store';
import { tick } from 'svelte';
import { setLocale } from '$lib/i18n/runtime.svelte';
import type { MonitoringSummary } from '$lib/components/admin/monitoring/MonitoringSummaryTab.svelte';

const mocks = vi.hoisted(() => ({ get: vi.fn(), refresh: undefined as (() => Promise<void>) | undefined }));
vi.mock('$lib/api/client', () => ({ api: { get: mocks.get } }));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token-a', projectId: 'project-a', userId: 'admin-a', sessionId: 'session-a', isSystemAdmin: true }),
}));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: (refresh: () => Promise<void>) => {
		mocks.refresh = refresh;
		return { active: false, intervalSeconds: 15, intervalOptions: [10, 15, 30, 60], setBoost: vi.fn() };
	},
}));
vi.mock('$lib/components/charts/runtime', () => ({
	mountChart: () => ({ update: vi.fn(), destroy: vi.fn() }),
}));

import { auth } from '$lib/stores/auth';
import Page from './+page.svelte';

function summary(hostName: string): MonitoringSummary {
	return {
		compute: { hypervisors_total: 1, hypervisors_up: 1, vcpus_used: 2, vcpus_total: 8, memory_used_mb: 1024, memory_total_mb: 4096, running_vms: 1, gpu_instances: 0, instance_stats: { total: 1, active: 1, shutoff: 0, error: 0, other: 0 } },
		storage: { volume_count: 0, volume_by_status: {}, total_gb: 0, file_storage_count: 0 },
		network: { network_count: 0, router_count: 0, router_active: 0, floatingip_count: 0, floatingip_active: 0, port_count: 0 },
		containers: { zun_count: 0, k3s_count: 0 },
		telemetry: { source: 'gnocchi', status: 'partial', error: null, truncated: false, resources: [{ id: hostName, name: hostName, type: 'compute_host', metrics: {} }] },
	};
}

beforeEach(() => {
	setLocale('en');
	auth.update(state => ({ ...state, token: 'token-a', projectId: 'project-a', userId: 'admin-a', sessionId: 'session-a', isSystemAdmin: true }));
	mocks.get.mockReset();
	mocks.refresh = undefined;
});
afterEach(() => { cleanup(); setLocale('ko'); });

describe('administrator monitoring summary authority', () => {
	it('clears rendered native data on identity/project change and ignores an older refresh', async () => {
		const pending = Promise.withResolvers<MonitoringSummary>();
		mocks.get.mockResolvedValueOnce(summary('old-private-host')).mockReturnValueOnce(pending.promise).mockResolvedValue(summary('new-host'));
		render(Page);
		await screen.findByText('old-private-host');
		const refreshing = mocks.refresh!();
		auth.update(state => ({ ...state, token: 'token-b', projectId: 'project-b', userId: 'admin-b', sessionId: 'session-b' }));
		await screen.findByText('new-host');
		expect(screen.queryByText('old-private-host')).toBeNull();
		pending.resolve(summary('late-private-host'));
		await refreshing;
		await tick();
		expect(screen.queryByText('late-private-host')).toBeNull();
		expect(screen.getByText('new-host')).toBeTruthy();
		expect(mocks.get).toHaveBeenLastCalledWith('/api/v1/admin/monitoring/summary', 'token-b', 'project-b');
	});

	it('does not publish a pending summary after system-admin authority is revoked', async () => {
		const pending = Promise.withResolvers<MonitoringSummary>();
		mocks.get.mockReturnValue(pending.promise);
		render(Page);
		await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(1));
		auth.update(state => ({ ...state, isSystemAdmin: false }));
		pending.resolve(summary('revoked-private-host'));
		await pending.promise;
		await tick();
		expect(screen.queryByText('revoked-private-host')).toBeNull();
		expect(mocks.get).toHaveBeenCalledTimes(1);
	});

	it('invalidates requests even when auth changes A → B → A before rendering', async () => {
		const pending = Promise.withResolvers<MonitoringSummary>();
		mocks.get.mockReturnValueOnce(pending.promise).mockResolvedValue(summary('fresh-host'));
		render(Page);
		await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(1));
		auth.update(state => ({ ...state, projectId: 'project-b' }));
		auth.update(state => ({ ...state, projectId: 'project-a' }));
		await screen.findByText('fresh-host');
		pending.resolve(summary('stale-private-host'));
		await pending.promise;
		await tick();
		expect(screen.queryByText('stale-private-host')).toBeNull();
	});
});
