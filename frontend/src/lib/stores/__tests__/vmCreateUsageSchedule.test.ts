import { fireEvent, render, screen } from '@testing-library/svelte';
import { get } from 'svelte/store';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '$lib/api/client';
import { siteConfig } from '$lib/config/site';
import { auth, authReady } from '$lib/stores/auth';
import { resetWizard, wizard } from '$lib/stores/wizard';
import { toLocalDateTime } from '$lib/utils/instanceUsage';
import VmCreateStoreLoadWrapper from './_VmCreateStoreLoadWrapper.svelte';
import type * as MockTransport from '$lib/mockup/transport';

vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$app/environment', () => ({ browser: true }));
vi.mock('$lib/mockup/transport', async (importOriginal) => {
	const actual = await importOriginal<typeof MockTransport>();
	return { ...actual, maybeMockInstanceCreateStream: () => null };
});

function json(value: unknown) {
	return new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } });
}

function installResources(vcpus = 12, overrides: Record<string, unknown> = {}) {
	const requests: Record<string, unknown>[] = [];
	const flavor = {
		id: 'required', name: 'cpu.fixture', vcpus, ram: 8192, disk: 20, is_public: true,
		...overrides,
		eligibility: { selectable: true, blockers: [], requirements: { instances: 1, cores: vcpus, ram_mb: 8192, gpus: {} },
			remaining: { instances: 10, cores: 100, ram_mb: 100000, gpus: {} },
			capacity: { status: 'available', candidate_hosts: 1, cpu_resource_class: 'VCPU', remaining_vcpus: 100, remaining_ram_mb: 100000, checked_at: new Date().toISOString() } },
	};
	vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
		const path = new URL(String(input)).pathname;
		if (path.endsWith('/instances/async')) {
			requests.push(JSON.parse(String(init?.body)));
			return Promise.resolve(new Response('data: {"step":"failed","error":"fixture complete"}\n\n', { headers: { 'Content-Type': 'text/event-stream' } }));
		}
		if (path === '/api/v1/flavors' || path.endsWith('/flavors-for-project')) return Promise.resolve(json([flavor]));
		if (path === '/api/v1/images') return Promise.resolve(json([{ id: 'image-1', name: 'Ubuntu', os_distro: 'ubuntu', status: 'active', min_disk: 1 }]));
		if (path === '/api/v1/keypairs') return Promise.resolve(json([{ name: 'key' }]));
		if (path === '/api/v1/networks/default') return Promise.resolve(json({ network_id: null }));
		if (path.includes('/quotas')) return Promise.resolve(json({}));
		return Promise.resolve(json([]));
	}));
	return requests;
}

async function prepare(adminMode = false) {
	if (adminMode) { auth.update(value => ({ ...value, isSystemAdmin: true })); authReady.set(true); }
	if (adminMode) wizard.update(value => ({ ...value, targetProjectId: 'target-project' }));
	render(VmCreateStoreLoadWrapper, { adminMode });
	await fireEvent.click(screen.getByTestId('init'));
	await vi.waitFor(() => expect(screen.getByTestId('flavor').textContent).toBe('cpu.fixture'));
	await fireEvent.click(screen.getByTestId('select-first-flavor'));
	wizard.update(value => ({ ...value, imageId: 'image-1', imageName: 'Ubuntu', keyName: 'key' }));
	await fireEvent.click(screen.getByTestId('step-six'));
}

describe('wizard native usage schedule payload', () => {
	beforeEach(() => {
		vi.restoreAllMocks(); api.clearPrefetchCache(); resetWizard();
		auth.set({ token: 'token', refreshToken: null, accessExpiresAt: null, userId: 'user', username: 'user', projectId: 'project-a', projectName: 'A', availableProjects: [], roles: [], isSystemAdmin: false, federated: false, domainId: 'domain', domainName: 'Domain', isDomainManager: false });
		auth.update(value => ({ ...value, canWrite: true }));
		authReady.set(true);
		siteConfig.update(value => ({ ...value, runtime: { ...value.runtime, api_base: 'https://usage.test' }, services: { ...value.services, manila: false } }));
	});

	it.each([false, true])('sends explicit safe initial schedule for required flavor (admin=%s)', async (adminMode) => {
		const requests = installResources();
		await prepare(adminMode);
		await vi.waitFor(() => expect(get(wizard).usageSchedule?.expiryAction).toBe('shelve'));
		await fireEvent.click(screen.getByTestId('deploy'));
		await vi.waitFor(() => expect(requests).toHaveLength(1));
		expect(requests[0].usage_schedule).toEqual({ expires_at: null, expiry_action: 'shelve', delete_volumes: false, reason: '' });
		if (adminMode) expect(requests[0].project_id).toBe('target-project');
	});

	it('does not dispatch later expiry without reason; explicit delete retains volumes unless opted in', async () => {
		const requests = installResources();
		await prepare();
		await vi.waitFor(() => expect(get(wizard).usageSchedule).not.toBeNull());
		wizard.update(value => ({ ...value, usageSchedule: { ...value.usageSchedule!, expiryAction: 'delete', expiresLocal: toLocalDateTime(new Date(Date.now() + 90 * 86400000).toISOString()) } }));
		await fireEvent.click(screen.getByTestId('deploy'));
		await vi.waitFor(() => expect(get(wizard).step).toBe(5));
		expect(requests).toHaveLength(0);
		wizard.update(value => ({ ...value, usageSchedule: { ...value.usageSchedule!, reason: 'Long-running research' } }));
		await fireEvent.click(screen.getByTestId('deploy'));
		await vi.waitFor(() => expect(requests).toHaveLength(1));
		expect(requests[0].usage_schedule).toMatchObject({ expiry_action: 'delete', delete_volumes: false, reason: 'Long-running research' });
	});

	it('does not add a schedule for an unrequired flavor', async () => {
		const requests = installResources(2, { usage_schedule_required: false, extra_specs: { 'afterglow:gpu_model': 'display metadata' } });
		await prepare();
		await fireEvent.click(screen.getByTestId('deploy'));
		await vi.waitFor(() => expect(requests).toHaveLength(1));
		expect(requests[0]).not.toHaveProperty('usage_schedule');
	});

	it('preserves draft on token refresh but clears it for another actor and project A to B to A', async () => {
		installResources(); await prepare(true);
		await vi.waitFor(() => expect(get(wizard).usageSchedule).not.toBeNull());
		wizard.update(value => ({ ...value, usageSchedule: { ...value.usageSchedule!, expiryAction: 'delete', deleteVolumes: true, reason: 'old actor' } }));
		auth.update(value => ({ ...value, token: 'new-token' }));
		expect(get(wizard).usageSchedule).toMatchObject({ expiryAction: 'delete', deleteVolumes: true, reason: 'old actor' });
		auth.update(value => ({ ...value, userId: 'another-user' }));
		authReady.set(true);
		await vi.waitFor(() => expect(get(wizard).usageSchedule?.deleteVolumes ?? false).toBe(false));
		await fireEvent.click(screen.getByTestId('project-b'));
		await vi.waitFor(() => expect(get(wizard).flavorId).toBeNull());
		await fireEvent.click(screen.getByTestId('project-a'));
		await vi.waitFor(() => expect(screen.getByTestId('flavor').textContent).toBe('cpu.fixture'));
		await fireEvent.click(screen.getByTestId('select-first-flavor'));
		await vi.waitFor(() => expect(get(wizard).usageSchedule?.expiryAction).toBe('shelve'));
		expect(get(wizard).usageSchedule?.deleteVolumes).toBe(false);
		expect(get(wizard).usageSchedule?.reason).toBe('');
	});
});
