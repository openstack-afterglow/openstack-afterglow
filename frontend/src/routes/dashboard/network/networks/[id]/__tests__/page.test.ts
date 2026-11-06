import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { NetworkDetail, RouterListItem } from '$lib/types/networks';

const { mocks, toastMock, confirmMock, refreshCallbacks } = vi.hoisted(() => ({
	mocks: { get: vi.fn(), post: vi.fn(), delete: vi.fn(), put: vi.fn() },
	toastMock: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
	confirmMock: vi.fn(),
	refreshCallbacks: [] as Array<(force?: boolean) => Promise<void>>,
}));

vi.mock('$lib/api/client', () => ({
	ApiError: class ApiError extends Error {},
	api: mocks,
}));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: confirmMock }));
vi.mock('$lib/stores/toast', () => ({ toast: toastMock }));
vi.mock('$lib/stores/auth', () => ({
	auth: {
		subscribe: (fn: (val: { token: string; projectId: string; isSystemAdmin: boolean }) => void) => {
			fn({ token: 'test-token', projectId: 'project-1', isSystemAdmin: false });
			return () => {};
		},
	},
}));
vi.mock('$app/stores', () => ({
	page: {
		subscribe: (fn: (val: { params: { id: string } }) => void) => {
			fn({ params: { id: 'net-1' } });
			return () => {};
		},
	},
}));
vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: (callback: (force?: boolean) => Promise<void>) => {
		refreshCallbacks.push(callback);
		return { active: false, intervalSeconds: 30, intervalOptions: [10, 30, 60], refresh: () => callback(true) };
	},
}));

import Page from '../+page.svelte';
import { t as commonT } from '$lib/i18n/ns/common';
import { t as networkT } from '$lib/i18n/ns/network-pages';
import { t as resourceT } from '$lib/i18n/ns/network-resources';

const ownedNetwork: NetworkDetail = {
	id: 'net-1',
	name: 'my-network',
	status: 'ACTIVE',
	subnets: ['sub-1'],
	is_external: false,
	is_shared: false,
	project_id: 'project-1',
	subnet_details: [
		{ id: 'sub-1', name: 'subnet-1', cidr: '10.0.0.0/24', ip_version: 4, gateway_ip: '10.0.0.1', dhcp_enabled: true },
	],
	routers: [
		{ id: 'router-foreign', name: 'foreign-router', status: 'ACTIVE', project_id: 'other-project', external_gateway_network_id: null, connected_subnet_ids: ['sub-1'] },
	],
};

const foreignNetwork: NetworkDetail = {
	...ownedNetwork,
	id: 'net-foreign',
	name: 'shared-network',
	is_shared: true,
	project_id: 'other-project',
};

const routers: RouterListItem[] = [
	{ id: 'router-1', name: 'my-router', status: 'ACTIVE', project_id: 'project-1', external_gateway_network_id: null, connected_subnet_ids: [] },
];

describe('Network detail page (+page.svelte)', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		refreshCallbacks.length = 0;
		mocks.get.mockImplementation((path: string) => {
			if (path === '/api/v1/routers') return Promise.resolve(routers);
			if (path === '/api/v1/networks/net-1') return Promise.resolve(ownedNetwork);
			return Promise.resolve(ownedNetwork);
		});
	});

	it('closes an open portaled filter on automatic read failure while retaining its display state for recovery', async () => {
		render(Page);
		await screen.findByRole('heading', { name: 'my-network' });
		const filterLabel = commonT('table.filterColumn', { column: 'CIDR' });
		await fireEvent.click(screen.getByRole('button', { name: filterLabel }));
		await fireEvent.click(screen.getByRole('button', { name: commonT('table.descending') }));
		await fireEvent.click(screen.getByRole('button', { name: commonT('table.selectNone') }));
		expect(screen.getByRole('dialog', { name: filterLabel })).toBeTruthy();
		mocks.get.mockRejectedValueOnce(new Error('automatic read failed'));
		await refreshCallbacks[0](true);
		await waitFor(() => expect(screen.queryByRole('dialog', { name: filterLabel })).toBeNull());
		expect(screen.getByText(networkT('networkDetail.serverError'))).toBeTruthy();
		await refreshCallbacks[0](true);
		await screen.findByRole('heading', { name: 'my-network' });
		expect(screen.getByRole('button', { name: commonT('table.sortColumn', { column: 'CIDR', direction: commonT('table.descending') }) })).toBeTruthy();
		const subnetSection = screen.getByRole('heading', { name: resourceT('network.subnets.title') }).parentElement!.parentElement!;
		expect(within(subnetSection).queryByRole('cell', { name: 'subnet-1' })).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: filterLabel }));
		expect(screen.getByRole('checkbox', { name: '10.0.0.0/24' })).toHaveProperty('checked', false);
	});

	it('renders network detail and allows creating subnet with router connection', async () => {
		mocks.post.mockImplementation((path: string) => {
			if (path.includes('/subnets')) return Promise.resolve({ id: 'sub-new', gateway_ip: '10.0.1.1' });
			if (path.includes('/interfaces')) return Promise.resolve({ subnet_id: 'sub-new' });
			return Promise.resolve({});
		});

		render(Page);
		expect(await screen.findByRole('heading', { name: 'my-network' })).toBeTruthy();
		expect(screen.getAllByRole('button', { name: '삭제' }).length).toBeGreaterThan(0);
		expect(screen.getByRole('button', { name: '+ 서브넷 추가' })).toBeTruthy();

		await fireEvent.click(screen.getByRole('button', { name: '+ 서브넷 추가' }));
		await fireEvent.input(screen.getByPlaceholderText('10.0.0.0/24'), { target: { value: '10.0.1.0/24' } });

		// Select router to connect
		const routerSelect = screen.getByLabelText('라우터 연결 (선택)');
		await fireEvent.change(routerSelect, { target: { value: 'router-1' } });

		await fireEvent.click(screen.getByRole('button', { name: '서브넷 추가' }));

		await waitFor(() => {
			expect(mocks.post).toHaveBeenCalledWith(
				'/api/v1/networks/net-1/subnets',
				{ name: 'my-network-subnet', cidr: '10.0.1.0/24', gateway_ip: null, enable_dhcp: true },
				'test-token',
				'project-1',
			);
			expect(mocks.post).toHaveBeenCalledWith(
				'/api/v1/routers/router-1/interfaces',
				{ subnet_id: 'sub-new', auto_gateway: false },
				'test-token',
				'project-1',
			);
		});
	});

	it('hides delete and management controls for non-owned network', async () => {
		mocks.get.mockImplementation((path: string) => {
			if (path === '/api/v1/routers') return Promise.resolve(routers);
			return Promise.resolve(foreignNetwork);
		});

		render(Page);
		expect(await screen.findByRole('heading', { name: 'shared-network' })).toBeTruthy();
		expect(screen.queryAllByRole('button', { name: '삭제' })).toHaveLength(0);
		expect(screen.queryByRole('button', { name: '+ 서브넷 추가' })).toBeNull();
	});

	it('does not allow disconnecting foreign router attached to owned network', async () => {
		render(Page);
		expect(await screen.findByRole('heading', { name: 'my-network' })).toBeTruthy();
		// Disconnect button for foreign router should not exist
		expect(screen.queryByRole('button', { name: /해제/ })).toBeNull();
	});
});
