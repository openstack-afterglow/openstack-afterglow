import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import type { Instance } from '$lib/types/compute';
import type { InstanceDetailController } from '../instanceDetailController.svelte';

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));

vi.mock('$lib/api/client', () => ({
	api: { get: mockGet, post: vi.fn(), put: vi.fn(), delete: vi.fn() },
	ApiError: class ApiError extends Error { status = 500; },
}));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token', projectId: 'project' }),
}));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({
		active: false,
		intervalSeconds: 30,
		intervalOptions: [15, 30, 60, 120],
		setBoost: vi.fn(),
	}),
}));

import Probe from './_InstanceDetailControllerProbe.svelte';


const instance = (id: string, name: string): Instance => ({
	id,
	name,
	status: 'ACTIVE',
	image_name: 'Ubuntu',
	flavor_name: 'small',
	ip_addresses: [],
	created_at: null,
	union_libraries: [],
	union_strategy: null,
});

function resolvedAncillary(path: string): unknown {
	if (path.endsWith('/security-groups')) return { ports: [], security_groups: [] };
	if (path.endsWith('/owner')) return { display: '' };
	return [];
}

describe('instance detail loading graph', () => {
	beforeEach(() => {
		mockGet.mockReset();
	});

	it('starts all core and ancillary GETs together and releases ancillary data independently', async () => {
		const primary = Promise.withResolvers<Instance>();
		const networks = Promise.withResolvers<Array<{ id: string; name: string }>>();
		mockGet.mockImplementation((path: string) => {
			if (path === '/api/v1/instances/instance-1') return primary.promise;
			if (path === '/api/v1/networks') return networks.promise;
			return Promise.resolve(resolvedAncillary(path));
		});
		let controller: InstanceDetailController | null = null;
		render(Probe, {
			source: { id: 'instance-1', projectId: 'project' },
			onReady: (value) => { controller = value; },
		});
		await vi.waitFor(() => expect(controller).not.toBeNull());

		const request = controller!.fetchInstance('instance-1');
		networks.resolve([{ id: 'network-1', name: 'private' }]);
		await vi.waitFor(() => expect(screen.getByTestId('detail-network-count').textContent).toBe('1'));
		expect(screen.getByTestId('detail-loading').textContent).toBe('loading');

		primary.resolve(instance('instance-1', 'primary-instance'));
		await request;
		expect(screen.getByTestId('detail-instance').textContent).toBe('primary-instance');
		expect(screen.getByTestId('detail-loading').textContent).toBe('ready');
	});

	it('waits for every derivation input without delaying primary detail', async () => {
		const floatingIps = Promise.withResolvers<Array<{ floating_ip_address: string }>>();
		const attachments = Promise.withResolvers<Array<{ volume_id: string }>>();
		const allVolumes = Promise.withResolvers<Array<{ id: string; status: string }>>();
		mockGet.mockImplementation((path: string) => {
			if (path === '/api/v1/instances/instance-1') {
				return Promise.resolve({
					...instance('instance-1', 'primary-instance'),
					ip_addresses: [{ addr: '203.0.113.10', type: 'floating' }],
				});
			}
			if (path === '/api/v1/networks/floating-ips') return floatingIps.promise;
			if (path === '/api/v1/instances/instance-1/volumes') return attachments.promise;
			if (path === '/api/v1/volumes') return allVolumes.promise;
			return Promise.resolve(resolvedAncillary(path));
		});
		let controller: InstanceDetailController | null = null;
		render(Probe, {
			source: { id: 'instance-1', projectId: 'project' },
			onReady: (value) => { controller = value; },
		});
		await vi.waitFor(() => expect(controller).not.toBeNull());

		await controller!.fetchInstance('instance-1');
		expect(screen.getByTestId('detail-instance').textContent).toBe('primary-instance');
		expect(screen.getByTestId('detail-floating-count').textContent).toBe('0');
		expect(screen.getByTestId('detail-volume-count').textContent).toBe('0');

		floatingIps.resolve([{ floating_ip_address: '203.0.113.10' }]);
		await vi.waitFor(() => expect(screen.getByTestId('detail-floating-count').textContent).toBe('1'));

		allVolumes.resolve([
			{ id: 'volume-attached', status: 'available' },
			{ id: 'volume-free', status: 'available' },
		]);
		await Promise.resolve();
		expect(screen.getByTestId('detail-volume-count').textContent).toBe('0');
		attachments.resolve([{ volume_id: 'volume-attached' }]);
		await vi.waitFor(() => expect(screen.getByTestId('detail-volume-count').textContent).toBe('1'));
	});

	it('ignores a previous instance response after a newer generation starts', async () => {
		const oldPrimary = Promise.withResolvers<Instance>();
		const newPrimary = Promise.withResolvers<Instance>();
		mockGet.mockImplementation((path: string) => {
			if (path === '/api/v1/instances/old-id') return oldPrimary.promise;
			if (path === '/api/v1/instances/new-id') return newPrimary.promise;
			return Promise.resolve(resolvedAncillary(path));
		});
		const source = { id: 'old-id', projectId: 'project' };
		let controller: InstanceDetailController | null = null;
		render(Probe, { source, onReady: (value) => { controller = value; } });
		await vi.waitFor(() => expect(controller).not.toBeNull());

		void controller!.fetchInstance('old-id');
		source.id = 'new-id';
		const latest = controller!.fetchInstance('new-id');
		newPrimary.resolve(instance('new-id', 'new-instance'));
		await latest;
		expect(screen.getByTestId('detail-instance').textContent).toBe('new-instance');

		oldPrimary.resolve(instance('old-id', 'old-instance'));
		await Promise.resolve();
		expect(screen.getByTestId('detail-instance').textContent).toBe('new-instance');
	});
});
