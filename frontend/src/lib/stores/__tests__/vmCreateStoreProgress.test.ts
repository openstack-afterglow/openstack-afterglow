import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { goto } from '$app/navigation';
import { auth } from '../auth';
import { DEFAULT_BETA_FEATURES, betaFeatures } from '../betaFeatures';
import { resetWizard, wizard } from '../wizard';
import { siteConfig } from '$lib/config/site';

const mocks = vi.hoisted(() => ({ apiGet: vi.fn(), fetchWithAuth: vi.fn() }));
vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$lib/api/client', async (importOriginal) => {
	const actual = await importOriginal<typeof import('$lib/api/client')>();
	return { ...actual, api: { get: mocks.apiGet }, fetchWithAuth: mocks.fetchWithAuth };
});
vi.mock('$lib/mockup/transport', () => ({ maybeMockInstanceCreateStream: () => null }));

import VmCreateStoreLoadWrapper from './_VmCreateStoreLoadWrapper.svelte';

const flavor = {
	id: 'f1', name: 'small', vcpus: 1, ram: 1024, disk: 20,
	eligibility: {
		selectable: true, blockers: [],
		requirements: { instances: 1, cores: 1, ram_mb: 1024, gpus: {} },
		remaining: { instances: 5, cores: 8, ram_mb: 8192, gpus: {} },
		capacity: {
			status: 'available', checked_at: '2026-10-01T00:00:00Z', candidate_hosts: 1,
			cpu_resource_class: 'VCPU', remaining_vcpus: 8, remaining_ram_mb: 8192,
		},
	},
};

let now = 0;
let controller: ReadableStreamDefaultController<Uint8Array>;
const encoder = new TextEncoder();

async function advance(seconds: number) {
	now += seconds * 1000;
	await vi.advanceTimersByTimeAsync(seconds * 1000);
}

async function send(step: string, elapsedSeconds: number) {
	controller.enqueue(encoder.encode(`data: ${JSON.stringify({
		step, progress: step === 'completed' ? 100 : 65, message: step, elapsed_seconds: elapsedSeconds,
	})}\n\n`));
	await vi.advanceTimersByTimeAsync(0);
}

function elapsed() {
	return Number(screen.getByTestId('elapsed').textContent);
}

function durations(): Record<string, number> {
	return JSON.parse(screen.getByTestId('step-elapsed').textContent ?? '{}');
}

async function start(adminMode = false) {
	render(VmCreateStoreLoadWrapper, { adminMode });
	await fireEvent.click(screen.getByTestId('init'));
	await vi.advanceTimersByTimeAsync(0);
	await fireEvent.click(screen.getByTestId('select-first-flavor'));
	await fireEvent.click(screen.getByTestId('deploy'));
	await vi.advanceTimersByTimeAsync(0);
}

beforeEach(() => {
	vi.useFakeTimers();
	vi.clearAllMocks();
	now = 0;
	vi.spyOn(performance, 'now').mockImplementation(() => now);
	resetWizard();
	betaFeatures.set(DEFAULT_BETA_FEATURES);
	auth.set({ token: 'token', refreshToken: null, accessExpiresAt: null, userId: 'user', username: 'user', projectId: 'project', projectName: 'project', availableProjects: [], roles: [], isSystemAdmin: false, federated: false });
	siteConfig.update(config => ({ ...config, services: { ...config.services, manila: false } }));
	mocks.apiGet.mockImplementation((path: string) => Promise.resolve(path.includes('flavors') ? [flavor] : []));
	mocks.fetchWithAuth.mockImplementation(() => Promise.resolve(new Response(new ReadableStream<Uint8Array>({
		start(next) { controller = next; },
	}), { headers: { 'Content-Type': 'text/event-stream' } })));
});

afterEach(() => {
	cleanup();
	vi.useRealTimers();
	vi.restoreAllMocks();
});

describe('VM deployment live timing', () => {
	it('advances without SSE updates, retains finished stage durations, and freezes on completion', async () => {
		await start();
		await send('boot_volume_creating', 2);
		await advance(3);
		expect(elapsed()).toBe(5);
		expect(durations()).toEqual({ boot_volume_creating: 3 });

		// A repeated stage and stale server duration must not reset either live clock.
		await send('boot_volume_creating', 4);
		await advance(2);
		expect(elapsed()).toBe(7);
		expect(durations().boot_volume_creating).toBe(5);
		await send('server_creating', 7);
		await advance(4);
		expect(elapsed()).toBe(11);
		expect(durations()).toEqual({ boot_volume_creating: 5, server_creating: 4 });
		await send('completed', 11);
		expect(goto).toHaveBeenCalledWith('/dashboard/compute/instances');
		await advance(6);
		expect(elapsed()).toBe(11);
		expect(durations()).toEqual({ boot_volume_creating: 5, server_creating: 4 });
	});

	it('freezes a failed deployment and starts a retry with fresh total and stage timings', async () => {
		await start();
		await send('server_creating', 10);
		await advance(3);
		await send('failed', 13);
		await advance(5);
		expect(elapsed()).toBe(13);
		expect(durations().server_creating).toBe(3);
		expect(screen.getByTestId('deploying').textContent).toBe('idle');
		expect(goto).not.toHaveBeenCalled();

		await fireEvent.click(screen.getByTestId('deploy'));
		await vi.advanceTimersByTimeAsync(0);
		expect(elapsed()).toBe(0);
		expect(durations()).toEqual({});
		await send('boot_volume_creating', 0);
		await advance(2);
		expect(elapsed()).toBe(2);
		expect(durations()).toEqual({ boot_volume_creating: 2 });
	});

	it('stops time on panel destruction and never navigates on a late completion', async () => {
		await start();
		await send('server_creating', 0);
		await advance(2);
		await fireEvent.click(screen.getByTestId('destroy'));
		await advance(5);
		expect(elapsed()).toBe(2);
		await send('completed', 7);
		expect(goto).not.toHaveBeenCalled();
	});

	it('keeps the administrator instance-list destination', async () => {
		wizard.update(state => ({ ...state, targetProjectId: 'project' }));
		await start(true);
		await send('completed', 1);
		expect(goto).toHaveBeenCalledWith('/admin/instances');
	});
});
