import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import { writable } from 'svelte/store';

const { mockGet, mockPrefetch } = vi.hoisted(() => ({
	mockGet: vi.fn(),
	mockPrefetch: vi.fn(),
}));

vi.mock('$lib/api/client', () => ({
	api: { get: mockGet, prefetch: mockPrefetch },
	ApiError: class ApiError extends Error { status = 500; },
}));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token', projectId: 'project' }),
}));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({
		active: false,
		intervalSeconds: 30,
		intervalOptions: [10, 15, 30, 60],
	}),
}));
// The incumbent views use the same probe; the grid exercises real scene selection targets.
vi.mock('$lib/components/GlobalTopology.svelte', async () => ({
	default: (await import('./_TopologyIntentProbe.svelte')).default,
}));
vi.mock('$lib/components/topology/canvas/TopologyCanvas.svelte', async () => ({
	default: (await import('./_TopologyIntentProbe.svelte')).default,
}));

import Page from '../+page.svelte';

const topology = {
	networks: [],
	subnets: [],
	routers: [],
	ports: [],
	instances: [{ id: 'instance-1', name: 'grid-workload', status: 'ACTIVE', network_names: [], ip_addresses: [] }],
	floating_ips: [],
	load_balancers: [],
};

async function expectIntentContract(name: string | RegExp = 'instance intent') {
	render(Page);
	await vi.advanceTimersByTimeAsync(0);
	const instance = await screen.findByRole('button', { name });

	await fireEvent.pointerEnter(instance);
	await vi.advanceTimersByTimeAsync(149);
	expect(mockPrefetch).not.toHaveBeenCalled();
	await fireEvent.pointerLeave(instance);
	await vi.advanceTimersByTimeAsync(1);
	expect(mockPrefetch).not.toHaveBeenCalled();

	await fireEvent.pointerEnter(instance);
	await vi.advanceTimersByTimeAsync(150);
	expect(mockPrefetch).toHaveBeenCalledOnce();
	expect(mockPrefetch.mock.calls[0].slice(0, 3)).toEqual([
		'/api/v1/instances/instance-1',
		'token',
		'project',
	]);
	const signal = mockPrefetch.mock.calls[0][3].signal as AbortSignal;
	expect(signal.aborted).toBe(false);
	await fireEvent.pointerLeave(instance);
	expect(signal.aborted).toBe(true);
}


describe('topology detail intent', () => {
	beforeEach(() => {
		vi.useFakeTimers();
		mockGet.mockReset();
		mockPrefetch.mockReset();
		mockGet.mockResolvedValue(topology);
		mockPrefetch.mockResolvedValue(undefined);
		localStorage.clear();
	});

	afterEach(() => {
		vi.useRealTimers();
		localStorage.clear();
	});

	describe('lane view', () => {
		beforeEach(() => {
			localStorage.setItem('topology.view', 'lane');
		});

		it('waits 150ms, cancels on leave, and aborts started speculation', async () => {
			await expectIntentContract();
		});
	});

	describe('canvas view', () => {
		beforeEach(() => {
			localStorage.setItem('topology.view', 'canvas');
		});
		it('keeps the same 150ms intent contract and persists the toggle choice', async () => {
			await expectIntentContract();

			await fireEvent.click(screen.getByRole('button', { name: '레인' }));
			await vi.advanceTimersByTimeAsync(0);
			expect(localStorage.getItem('topology.view')).toBe('lane');
		});
	});

	it('defaults to grid, uses the same intent contract, and persists both transitions', async () => {
		await expectIntentContract(/grid-workload/);
		expect(screen.getByRole('button', { name: '그리드' }).getAttribute('aria-pressed')).toBe('true');
		await fireEvent.click(screen.getByRole('button', { name: '캔버스' }));
		expect(localStorage.getItem('topology.view')).toBe('canvas');
		await fireEvent.click(screen.getByRole('button', { name: '그리드' }));
		expect(localStorage.getItem('topology.view')).toBe('grid');
	});
});
