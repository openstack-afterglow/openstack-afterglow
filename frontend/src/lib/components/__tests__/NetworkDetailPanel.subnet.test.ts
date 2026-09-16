import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { NetworkDetail } from '$lib/types/networks';

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));

vi.mock('$lib/api/client', () => ({
	ApiError: class ApiError extends Error {},
	api: mocks,
}));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: vi.fn() }));
vi.mock('$lib/stores/toast', () => ({ toast: { error: vi.fn(), warning: vi.fn() } }));

import NetworkDetailPanel from '../NetworkDetailPanel.svelte';

const network: NetworkDetail = {
	id: 'net-app',
	name: 'app',
	status: 'ACTIVE',
	subnets: [],
	is_external: false,
	is_shared: false,
	subnet_details: [],
	routers: [],
};

describe('NetworkDetailPanel subnet creation', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		mocks.get.mockResolvedValue(network);
		mocks.post.mockResolvedValue({ id: 'subnet-app' });
	});

	it('posts an optional-name subnet to the user network route', async () => {
		render(NetworkDetailPanel, { networkId: network.id, apiBase: '/api/v1/networks' });
		await screen.findByRole('button', { name: '+ 서브넷 추가' });
		await fireEvent.click(screen.getByRole('button', { name: '+ 서브넷 추가' }));
		await fireEvent.input(screen.getByPlaceholderText('10.0.0.0/24'), { target: { value: '10.10.0.0/24' } });
		await fireEvent.click(screen.getByRole('button', { name: '서브넷 생성' }));

		await waitFor(() => {
			expect(mocks.post).toHaveBeenCalledWith(
			'/api/v1/networks/net-app/subnets',
			{ name: 'app-subnet', cidr: '10.10.0.0/24', gateway_ip: null, enable_dhcp: true },
			undefined,
			undefined,
		);
		});
	});
});
