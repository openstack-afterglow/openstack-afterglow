import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import type { StampedeStatus } from '$lib/types/k3s';

const mocks = vi.hoisted(() => ({
	apiGet: vi.fn(),
	controller: {
		projectId: 'resource-project',
		cluster: { id: 'cluster-1', status: 'ACTIVE' },
	},
}));

vi.mock('$env/dynamic/public', () => ({
	env: { PUBLIC_API_BASE: 'http://backend.test' },
}));

vi.mock('$lib/api/client', () => ({
	api: { get: mocks.apiGet },
}));

vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'test-token', projectId: 'test-project' }),
}));

vi.mock('$lib/stores/k3sClusterDetailController.svelte', () => ({
	useK3sClusterDetailController: () => mocks.controller,
}));

import K3sStampedeTab from '../K3sStampedeTab.svelte';

const stampedeStatus: StampedeStatus = {
	cluster_id: 'cluster-1',
	stampede_enabled: true,
	global_stampede_enabled: true,
	nodegroups: [
		{
			id: 'ng-gpu',
			name: 'gpu-workers',
			stampede_enabled: true,
			min_size: 0,
			max_size: 5,
			node_count: 1,
			in_flight: 1,
			capacity: {
				allocatable: { cpu_m: 4000, memory_bytes: 4 * 1024 * 1024 * 1024, gpu: 2 },
				free: { cpu_m: 1750, memory_bytes: 1536 * 1024 * 1024, gpu: 7 },
			},
			pending_assignments: [{ namespace: 'ml', name: 'trainer' }],
			blocked_reasons: [{ namespace: 'ml', name: 'trainer', reason: 'gpu_quota' }],
			last_blocked_reason: 'gpu_quota',
			stampede_state: {},
		},
	],
};

const stampedeEvents = [
	{
		id: 1,
		created_at: '2026-07-03T10:00:00Z',
		action: 'blocked',
		status: 'success',
		nodegroup_id: 'ng-gpu',
		extra: {
			reason: 'gpu_quota',
			pod: { namespace: 'ml', name: 'trainer' },
		},
	},
];

function queueLoad(status: StampedeStatus = stampedeStatus, events = stampedeEvents) {
	mocks.apiGet.mockResolvedValueOnce(status).mockResolvedValueOnce(events);
}

describe('K3sStampedeTab', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		mocks.controller.cluster = { id: 'cluster-1', status: 'ACTIVE' };
	});

	it('renders GPU capacity, pending assignments, and blocked reasons from stampede status', async () => {
		queueLoad();

		render(K3sStampedeTab);

		expect(await screen.findByText('gpu-workers')).toBeTruthy();
		await waitFor(() => {
			expect(mocks.apiGet.mock.calls).toEqual([
				['/api/v1/k3s/clusters/cluster-1/stampede', 'test-token', 'resource-project'],
				['/api/v1/k3s/clusters/cluster-1/stampede/events?limit=100', 'test-token', 'resource-project'],
			]);
		});

		expect(screen.getByText('GPU')).toBeTruthy();
		expect(screen.getByText('CPU free')).toBeTruthy();
		expect(screen.getByText('1750m')).toBeTruthy();
		expect(screen.getByText('MEM free')).toBeTruthy();
		expect(screen.getByText('1536Mi')).toBeTruthy();
		expect(screen.getByText('GPU free')).toBeTruthy();
		expect(screen.getByText('7')).toBeTruthy();
		expect(screen.getByText('Pending: ml/trainer')).toBeTruthy();
		expect(screen.getByText('Blocked: gpu_quota: ml/trainer')).toBeTruthy();
		expect(screen.getByText('Last blocked: gpu_quota')).toBeTruthy();
		expect(screen.getByText('스케일 차단')).toBeTruthy();
		expect(screen.getByText('gpu_quota — ml/trainer')).toBeTruthy();
	});

	it('does not re-fetch stampede data after the initial mount flush', async () => {
		queueLoad(
			{
				cluster_id: 'cluster-1',
				stampede_enabled: true,
				global_stampede_enabled: true,
				nodegroups: [],
			},
			[],
		);

		render(K3sStampedeTab);

		expect(await screen.findByText('아직 Stampede 이벤트가 없습니다.')).toBeTruthy();
		await Promise.resolve();
		await Promise.resolve();

		expect(mocks.apiGet).toHaveBeenCalledTimes(2);
	});
});
