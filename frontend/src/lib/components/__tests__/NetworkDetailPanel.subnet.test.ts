import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { NetworkDetail } from '$lib/types/networks';

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));

vi.mock('$lib/api/client', () => ({
	ApiError: class ApiError extends Error {},
	api: mocks,
}));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: vi.fn() }));
vi.mock('$lib/stores/toast', () => ({ toast: { error: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

import NetworkDetailPanel from '../NetworkDetailPanel.svelte';

const network: NetworkDetail = {
	id: 'net-app',
	name: 'app',
	status: 'ACTIVE',
	subnets: [],
	is_external: false,
	is_shared: false,
	project_id: 'project-1',
	subnet_details: [],
	routers: [],
};

describe('NetworkDetailPanel subnet creation', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		mocks.get.mockImplementation((path: string) => Promise.resolve(
			path === '/api/v1/routers'
				? [{ id: 'router-1', name: 'edge', status: 'ACTIVE', project_id: 'project-1', external_gateway_network_id: null, connected_subnet_ids: [] }]
				: network,
		));
		mocks.post.mockResolvedValue({ id: 'subnet-app', gateway_ip: '10.10.0.1' });
	});

	it('posts an optional-name subnet to the user network route', async () => {
		render(NetworkDetailPanel, { networkId: network.id, apiBase: '/api/v1/networks', projectId: 'project-1' });
		await screen.findByRole('button', { name: '+ 서브넷 추가' });
		await fireEvent.click(screen.getByRole('button', { name: '+ 서브넷 추가' }));
		await fireEvent.input(screen.getByPlaceholderText('10.0.0.0/24'), { target: { value: '10.10.0.0/24' } });
		await fireEvent.click(screen.getByRole('button', { name: '서브넷 생성' }));

		await waitFor(() => {
			expect(mocks.post).toHaveBeenCalledWith(
				'/api/v1/networks/net-app/subnets',
				{ name: 'app-subnet', cidr: '10.10.0.0/24', gateway_ip: null, enable_dhcp: true },
				undefined,
				'project-1',
			);
		});
	});

	it('connects a new subnet to the selected owned router', async () => {
		render(NetworkDetailPanel, { networkId: network.id, apiBase: '/api/v1/networks', projectId: 'project-1' });
		await fireEvent.click(await screen.findByRole('button', { name: '+ 서브넷 추가' }));
		await fireEvent.change(screen.getByLabelText('라우터 연결'), { target: { value: 'router-1' } });
		await fireEvent.input(screen.getByPlaceholderText('10.0.0.0/24'), { target: { value: '10.20.0.0/24' } });
		await fireEvent.click(screen.getByRole('button', { name: '서브넷 생성' }));

		await waitFor(() => {
			expect(mocks.post).toHaveBeenNthCalledWith(
				2,
				'/api/v1/routers/router-1/interfaces',
				{ subnet_id: 'subnet-app', auto_gateway: false },
				undefined,
				'project-1',
			);
		});
	});

	it('hides subnet and router mutation controls for a shared network owned by another project', async () => {
		mocks.get.mockResolvedValue({ ...network, project_id: 'other-project', is_shared: true });
		render(NetworkDetailPanel, { networkId: network.id, apiBase: '/api/v1/networks', projectId: 'project-1' });

		expect(await screen.findByText('서브넷 (0)')).toBeTruthy();
		expect(screen.queryByRole('button', { name: '+ 서브넷 추가' })).toBeNull();
		expect(screen.queryByRole('button', { name: '+ 연결' })).toBeNull();
	});

	it('connects an existing subnet to a router from the router section', async () => {
		mocks.get.mockImplementation((path: string) => Promise.resolve(
			path === '/api/v1/routers'
				? [{ id: 'router-1', name: 'edge', status: 'ACTIVE', project_id: 'project-1', external_gateway_network_id: null, connected_subnet_ids: [] }]
				: { ...network, subnet_details: [{ id: 'sub-1', name: 'sub-1', cidr: '10.10.0.0/24', gateway_ip: '10.10.0.1', dhcp_enabled: true }] },
		));
		render(NetworkDetailPanel, { networkId: network.id, apiBase: '/api/v1/networks', projectId: 'project-1' });
		await fireEvent.click(await screen.findByRole('button', { name: '+ 연결' }));
		await fireEvent.click(screen.getByRole('button', { name: '연결' }));
		await waitFor(() => {
			expect(mocks.post).toHaveBeenCalledWith(
				'/api/v1/routers/router-1/interfaces',
				{ subnet_id: 'sub-1', auto_gateway: false },
				undefined,
				'project-1',
			);
		});
	});
});
