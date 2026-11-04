import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { goto } from '$app/navigation';
import { auth, authReady } from '../auth';
import { DEFAULT_BETA_FEATURES, betaFeatures } from '../betaFeatures';
import { resetWizard, wizard } from '../wizard';
import { siteConfig } from '$lib/config/site';
import { get } from 'svelte/store';
import { captureFlowExperience, type CapturedFlowExperience } from './experienceFlowHarness';

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
	if (adminMode) { auth.update(value => ({ ...value, isSystemAdmin: true })); authReady.set(true); }
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
	auth.set({ token: 'token', refreshToken: null, accessExpiresAt: null, userId: 'user', username: 'user', projectId: 'project', projectName: 'project', availableProjects: [], roles: [], isSystemAdmin: false, federated: false, domainId: 'domain-1', domainName: 'Domain', isDomainManager: false });
	auth.update(value => ({ ...value, canWrite: true }));
	authReady.set(true);
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

describe('VM creation semantic experience from the real store and SSE consumer', () => {
	let captured: CapturedFlowExperience;
	beforeEach(() => {
		captured = captureFlowExperience('/dashboard/compute/instances', () => get(auth));
	});
	afterEach(() => captured.collector.destroy());

	it('retains one action across awaited capacity admission and actual progress application, without payload text', async () => {
		await start();
		const capacity = mocks.apiGet.mock.calls.find(call => call[3]?.experience);
		const postContext = mocks.fetchWithAuth.mock.calls[0][4].experience;
		expect(capacity?.[3].experience).toBe(postContext);
		await captured.flush();
		expect(captured.events.some(event => event.payload.state === 'ready')).toBe(false);
		await send('server_creating', 1);
		expect(screen.getByTestId('deploy-step').textContent).toBe('server_creating');
		await send('completed', 2);
		const events = await captured.flush();
		const action = events.find(event => event.event_type === 'action.started' && event.feature === 'compute')!;
		const linked = events.filter(event => event.action_id === action.action_id);
		expect(linked.filter(event => event.event_type === 'action.started')).toHaveLength(1);
		const received = linked.findIndex(event => event.event_type === 'result.received' && event.payload.stage === 'state');
		const applied = linked.findIndex((event, index) => index > received && event.event_type === 'result.applied');
		const committed = linked.findIndex((event, index) => index > applied && event.event_type === 'result.committed');
		expect(received).toBeGreaterThan(-1);
		expect(applied).toBeGreaterThan(received);
		expect(committed).toBeGreaterThan(applied);
		expect(linked.some(event => event.event_type === 'view.state_changed' && event.payload.state === 'ready' && event.payload.step === 9)).toBe(true);
		expect(linked.some(event => event.event_type === 'view.exposure_changed' && event.payload.visibility === 'hidden')).toBe(true);
		expect(JSON.stringify(events)).not.toContain('server_creating');
		expect(JSON.stringify(events)).not.toContain('elapsed_seconds');
		expect(JSON.stringify(events)).not.toContain('token');
	});

	it('does not turn an unterminated SSE EOF into ready, failed, or a replay', async () => {
		await start();
		await send('server_creating', 1);
		controller.close();
		await vi.advanceTimersByTimeAsync(0);
		const events = await captured.flush();
		expect(events.some(event => event.event_type === 'result.discarded' && event.payload.reason === 'unknown')).toBe(true);
		expect(events.some(event => event.event_type === 'view.state_changed' && ['ready', 'error'].includes(event.payload.state ?? ''))).toBe(false);
		expect(mocks.fetchWithAuth).toHaveBeenCalledTimes(1);
		expect(goto).not.toHaveBeenCalled();
	});

	it('discards a destroyed stream as unknown native outcome without applying a late completed frame', async () => {
		await start();
		await send('server_creating', 1);
		await fireEvent.click(screen.getByTestId('destroy'));
		await captured.flush();
		const committedBefore = captured.events.filter(event => event.event_type === 'result.committed').length;
		await send('completed', 2);
		const events = await captured.flush();
		expect(events.some(event => event.event_type === 'result.discarded' && event.payload.reason === 'unmounted')).toBe(true);
		expect(events.filter(event => event.event_type === 'result.committed')).toHaveLength(committedBefore);
		expect(events.some(event => event.event_type === 'view.state_changed' && event.payload.state === 'ready')).toBe(false);
		expect(mocks.fetchWithAuth).toHaveBeenCalledTimes(1);
		expect(goto).not.toHaveBeenCalled();
	});

	it('keeps the existing completion flow after project change while dropping stale observations', async () => {
		await start();
		await captured.flush();
		const commitsBefore = captured.events.filter(event => event.event_type === 'result.committed').length;
		auth.update(value => ({ ...value, projectId: 'another-project' }));
		await vi.advanceTimersByTimeAsync(0);
		await send('server_creating', 1);
		await send('completed', 2);
		await captured.flush();
		expect(goto).toHaveBeenCalledWith('/dashboard/compute/instances');
		expect(captured.events.filter(event => event.event_type === 'result.committed')).toHaveLength(commitsBefore);
		expect(captured.events.some(event => event.payload.state === 'ready')).toBe(false);
		expect(mocks.fetchWithAuth).toHaveBeenCalledTimes(1);
	});

	it('keeps the existing 503 error UI but does not call the ambiguous native outcome failed', async () => {
		mocks.fetchWithAuth.mockResolvedValueOnce(new Response('gateway unavailable', { status: 503 }));
		await start();
		const events = await captured.flush();
		expect(screen.getByTestId('deploying').textContent).toBe('idle');
		expect(events.some(event => event.event_type === 'result.discarded' && event.payload.reason === 'unknown')).toBe(true);
		expect(events.some(event => event.payload.state === 'error' || event.payload.state === 'ready')).toBe(false);
		expect(mocks.fetchWithAuth).toHaveBeenCalledTimes(1);
	});

	it('rejects a superseded capacity recheck before POST and records only a discarded source result', async () => {
		render(VmCreateStoreLoadWrapper);
		await fireEvent.click(screen.getByTestId('init'));
		await vi.advanceTimersByTimeAsync(0);
		await fireEvent.click(screen.getByTestId('select-first-flavor'));
		const capacity = Promise.withResolvers<unknown>();
		mocks.apiGet.mockImplementationOnce(() => capacity.promise);
		void fireEvent.click(screen.getByTestId('deploy'));
		await vi.advanceTimersByTimeAsync(0);
		await fireEvent.click(screen.getByTestId('refresh-manual'));
		await vi.advanceTimersByTimeAsync(0);
		capacity.resolve([flavor]);
		await vi.advanceTimersByTimeAsync(0);
		const events = await captured.flush();
		expect(events.some(event => event.event_type === 'result.discarded' && event.payload.reason === 'stale')).toBe(true);
		expect(mocks.fetchWithAuth).not.toHaveBeenCalled();
		expect(goto).not.toHaveBeenCalled();
	});
});
