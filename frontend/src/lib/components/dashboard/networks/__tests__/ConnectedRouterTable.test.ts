import { fireEvent, render, screen } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { NetworkRouterInfo, RouterListItem } from '$lib/types/networks';
import ConnectedRouterTable from '../ConnectedRouterTable.svelte';

const ownedRouter: NetworkRouterInfo = {
	id: 'router-owned',
	name: 'my-router',
	status: 'ACTIVE',
	project_id: 'project-1',
	external_gateway_network_id: null,
	connected_subnet_ids: ['sub-1'],
};

const foreignRouter: NetworkRouterInfo = {
	id: 'router-foreign',
	name: 'other-router',
	status: 'ACTIVE',
	project_id: 'other-project',
	external_gateway_network_id: null,
	connected_subnet_ids: ['sub-2'],
};

const availableRouters: RouterListItem[] = [
	{ id: 'router-owned', name: 'my-router', status: 'ACTIVE', project_id: 'project-1', external_gateway_network_id: null, connected_subnet_ids: ['sub-1'] },
];

const subnets = [
	{ id: 'sub-1', name: 'subnet-1', cidr: '10.0.0.0/24', gateway_ip: '10.0.0.1' },
	{ id: 'sub-2', name: 'subnet-2', cidr: '10.1.0.0/24', gateway_ip: '10.1.0.1' },
];

describe('ConnectedRouterTable ownership and connection', () => {
	it('hides disconnect action for foreign router attached to owned network', () => {
		render(ConnectedRouterTable, {
			routers: [ownedRouter, foreignRouter],
			subnets,
			availableRouters,
			canManage: true,
			projectId: 'project-1',
			isSystemAdmin: false,
			onDisconnect: vi.fn(),
		});

		const buttons = screen.getAllByRole('button', { name: /해제/ });
		expect(buttons.length).toBe(1);
		expect(buttons[0].closest('tr')?.textContent).toContain('my-router');
	});

	it('calls onDisconnect when clicking disconnect on an owned router', async () => {
		const onDisconnect = vi.fn().mockResolvedValue(true);
		render(ConnectedRouterTable, {
			routers: [ownedRouter],
			subnets,
			availableRouters,
			canManage: true,
			projectId: 'project-1',
			isSystemAdmin: false,
			onDisconnect,
		});

		const button = screen.getByRole('button', { name: /해제/ });
		await fireEvent.click(button);
		expect(onDisconnect).toHaveBeenCalledWith('router-owned', 'sub-1');
	});

	it('opens connect form and triggers onConnect', async () => {
		const onConnect = vi.fn().mockResolvedValue(true);
		render(ConnectedRouterTable, {
			routers: [],
			subnets,
			availableRouters,
			canManage: true,
			projectId: 'project-1',
			isSystemAdmin: false,
			onConnect,
		});

		const openBtn = screen.getByRole('button', { name: '+ 라우터 연결' });
		await fireEvent.click(openBtn);

		const connectBtn = screen.getByRole('button', { name: '연결' });
		await fireEvent.click(connectBtn);

		expect(onConnect).toHaveBeenCalledWith('router-owned', 'sub-1');
	});
});
