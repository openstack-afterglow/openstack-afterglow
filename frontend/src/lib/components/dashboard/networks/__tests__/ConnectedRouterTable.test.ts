import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
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

		expect(within(screen.getByRole('row', { name: /my-router/ })).getByRole('button', { name: /해제/ })).toBeTruthy();
		expect(within(screen.getByRole('row', { name: /other-router/ })).queryByRole('button', { name: /해제/ })).toBeNull();
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

		const button = within(screen.getByRole('row', { name: /my-router/ })).getByRole('button', { name: /해제/ });
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

	it('marks only the clicked disconnect as in flight, and only once the request has started', async () => {
		const request = Promise.withResolvers<boolean>();
		const onDisconnect = vi.fn(() => request.promise);
		const secondRouter: NetworkRouterInfo = { ...ownedRouter, id: 'router-second', name: 'second-router', connected_subnet_ids: ['sub-2'] };
		const props = {
			routers: [ownedRouter, secondRouter],
			subnets,
			availableRouters,
			canManage: true,
			projectId: 'project-1',
			isSystemAdmin: false,
			onDisconnect,
		};
		const { rerender } = render(ConnectedRouterTable, { ...props, connecting: false });
		const first = within(screen.getByRole('row', { name: /my-router/ })).getByRole('button', { name: /해제/ }) as HTMLButtonElement;
		const second = within(screen.getByRole('row', { name: /second-router/ })).getByRole('button', { name: /해제/ }) as HTMLButtonElement;
		expect(first.getAttribute('aria-busy')).not.toBe('true');
		expect(second.getAttribute('aria-busy')).not.toBe('true');

		await fireEvent.click(first);
		expect(onDisconnect).toHaveBeenCalledOnce();
		expect(onDisconnect).toHaveBeenCalledWith('router-owned', 'sub-1');
		// The callback may still be confirming; only the shared request flag establishes in-flight activity.
		expect(first.getAttribute('aria-busy')).not.toBe('true');
		expect(second.getAttribute('aria-busy')).not.toBe('true');
		expect(first.disabled).toBe(false);
		expect(second.disabled).toBe(false);

		await rerender({ ...props, connecting: true });
		expect(first.getAttribute('aria-busy')).toBe('true');
		expect(first.disabled).toBe(true);
		expect(second.getAttribute('aria-busy')).not.toBe('true');
		expect(second.disabled).toBe(true);

		request.resolve(true);
		await rerender({ ...props, connecting: false });
		await waitFor(() => expect(first.getAttribute('aria-busy')).not.toBe('true'));
		expect(second.getAttribute('aria-busy')).not.toBe('true');
		expect(first.disabled).toBe(false);
		expect(second.disabled).toBe(false);
	});
});
