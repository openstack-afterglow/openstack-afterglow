import { fireEvent, render, screen } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { RouterDetail } from '$lib/types/router';
import type { Network } from '$lib/types/networks';
const { mocks, confirmMock } = vi.hoisted(() => ({
	mocks: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
	confirmMock: vi.fn(),
}));

vi.mock('$lib/api/client', () => ({
	ApiError: class ApiError extends Error {},
	api: mocks,
}));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: confirmMock }));
vi.mock('$lib/stores/toast', () => ({ toast: { error: vi.fn(), success: vi.fn(), warning: vi.fn() } }));
vi.mock('$lib/stores/auth', () => ({
	auth: {
		subscribe: (fn: (val: { token: string; projectId: string; isSystemAdmin: boolean }) => void) => {
			fn({ token: 'test-token', projectId: 'project-1', isSystemAdmin: false });
			return () => {};
		},
	},
}));

import RouterDetailPanel from '../RouterDetailPanel.svelte';

const ownedRouter: RouterDetail = {
	id: 'router-owned',
	name: 'owned-router',
	status: 'ACTIVE',
	project_id: 'project-1',
	external_gateway_network_id: null,
	external_gateway_network_name: null,
	interfaces: [
		{ id: 'port-1', subnet_id: 'sub-1', subnet_name: 'subnet-1', network_id: 'net-1', ip_address: '10.0.0.1' },
	],
};

const foreignRouter: RouterDetail = {
	id: 'router-foreign',
	name: 'foreign-router',
	status: 'ACTIVE',
	project_id: 'other-project',
	external_gateway_network_id: null,
	external_gateway_network_name: null,
	interfaces: [
		{ id: 'port-2', subnet_id: 'sub-2', subnet_name: 'subnet-2', network_id: 'net-2', ip_address: '10.1.0.1' },
	],
};

const networks: Network[] = [
	{ id: 'net-owned', name: 'my-net', is_external: false, is_shared: false, project_id: 'project-1', subnets: ['sub-1'] },
	{ id: 'net-foreign', name: 'shared-net', is_external: false, is_shared: true, project_id: 'other-project', subnets: ['sub-2'] },
	{ id: 'net-ext', name: 'public', is_external: true, is_shared: false, project_id: null, subnets: [] },
];

describe('RouterDetailPanel ownership guards', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		mocks.get.mockImplementation((path: string) => {
			if (path === '/api/v1/networks') return Promise.resolve(networks);
			if (path === '/api/v1/routers/router-owned') return Promise.resolve(ownedRouter);
			if (path === '/api/v1/routers/router-foreign') return Promise.resolve(foreignRouter);
			return Promise.resolve(ownedRouter);
		});
	});

	it('shows mutation actions when router is owned by current project', async () => {
		render(RouterDetailPanel, { routerId: 'router-owned' });
		expect(await screen.findByRole('button', { name: '삭제' })).toBeTruthy();
		expect(screen.getByRole('button', { name: '게이트웨이 설정' })).toBeTruthy();
		expect(screen.getByRole('button', { name: '+ 추가' })).toBeTruthy();
		expect(screen.getByRole('button', { name: '제거' })).toBeTruthy();
	});

	it('hides mutation actions when router is owned by another project', async () => {
		render(RouterDetailPanel, { routerId: 'router-foreign' });
		expect(await screen.findByText('foreign-router')).toBeTruthy();
		expect(screen.queryByRole('button', { name: '삭제' })).toBeNull();
		expect(screen.queryByRole('button', { name: '게이트웨이 설정' })).toBeNull();
		expect(screen.queryByRole('button', { name: '+ 추가' })).toBeNull();
		expect(screen.queryByRole('button', { name: '제거' })).toBeNull();
	});

	it('cancels router deletion when confirm dialog is rejected', async () => {
		confirmMock.mockResolvedValue(false);
		render(RouterDetailPanel, { routerId: 'router-owned' });
		const deleteBtn = await screen.findByRole('button', { name: '삭제' });
		await fireEvent.click(deleteBtn);
		expect(confirmMock).toHaveBeenCalled();
		expect(mocks.delete).not.toHaveBeenCalled();
	});

	it('proceeds with router deletion when confirm dialog is accepted', async () => {
		confirmMock.mockResolvedValue(true);
		mocks.delete.mockResolvedValue({});
		render(RouterDetailPanel, { routerId: 'router-owned' });
		const deleteBtn = await screen.findByRole('button', { name: '삭제' });
		await fireEvent.click(deleteBtn);
		expect(confirmMock).toHaveBeenCalled();
		expect(mocks.delete).toHaveBeenCalledWith('/api/v1/routers/router-owned', 'test-token', 'project-1');
	});
});
