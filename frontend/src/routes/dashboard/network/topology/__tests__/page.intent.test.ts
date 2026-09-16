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
// 레인(GlobalTopology)·캔버스(TopologyCanvas) 두 뷰 모두 같은 intent 콜백 계약을 쓰므로 동일한 probe 로 대체한다
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
	instances: [],
	floating_ips: [],
	load_balancers: [],
};

async function expectIntentContract() {
	render(Page);
	await vi.advanceTimersByTimeAsync(0);
	const instance = await screen.findByRole('button', { name: 'instance intent' });

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

function pressedView(): string | null {
	const group = screen.getByRole('group', { name: '토폴로지 보기' });
	const pressed = Array.from(group.querySelectorAll('button')).find((b) => b.getAttribute('aria-pressed') === 'true');
	return pressed?.textContent?.trim() ?? null;
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
			expect(pressedView()).toBe('레인');
		});
	});

	describe('canvas view (default)', () => {
		it('keeps the same 150ms intent contract and persists the toggle choice', async () => {
			await expectIntentContract();
			expect(pressedView()).toBe('캔버스');

			await fireEvent.click(screen.getByRole('button', { name: '레인' }));
			await vi.advanceTimersByTimeAsync(0);
			expect(pressedView()).toBe('레인');
			expect(localStorage.getItem('topology.view')).toBe('lane');
		});
	});
});
