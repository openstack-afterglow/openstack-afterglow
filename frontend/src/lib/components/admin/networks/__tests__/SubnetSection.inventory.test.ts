import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import type { AdminSubnetDetail, SubnetDetail } from '$lib/types/networks';
import { subnetFixture } from './subnetFixture';

const mocks = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: { get: mocks.get }, ApiError: class extends Error {} }));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'token', userId: 'user', projectId: 'scope' }) }));
vi.mock('$app/stores', () => ({ page: writable({ params: { id: 'network' }, url: new URL('https://example.test/admin/networks/network') }) }));

import SubnetSection from '../SubnetSection.svelte';

const subnets: SubnetDetail[] = [
	{ id: 'sub-first', name: 'first-subnet', cidr: '10.200.0.0/24', gateway_ip: '10.200.0.1', dhcp_enabled: true, ip_version: 4 },
	{ id: 'sub-second', name: 'second-subnet', cidr: '2001:db8::/64', gateway_ip: null, dhcp_enabled: false, ip_version: 6 },
];
function detail(id: string): AdminSubnetDetail {
	const ip = id === 'sub-first' ? '10.200.0.15' : '2001:db8::15';
	return {
		...subnetFixture, ...subnets.find((subnet) => subnet.id === id)!, dhcp_bindings: [],
		allocation_pools: id === 'sub-first' ? subnetFixture.allocation_pools : [],
		ip_usage: id === 'sub-first' ? subnetFixture.ip_usage : {
			total_pool_ips: '0', allocated_ips: '1', allocated_pool_ips: '0', reserved_pool_ips: '0', available_pool_ips: null, outside_pool_ips: '1', allocation_mode: 'slaac',
		},
		ports: [{ ...subnetFixture.ports[0], id: `${id}-port`, ip_addresses: [ip] }],
		allocations: [{ ...subnetFixture.allocations[0], ip_address: ip, port_id: `${id}-port` }],
	};
}
function inventory(id: string) {
	return within(document.getElementById(`subnet-inventory-${id}`)!);
}

beforeEach(() => { cleanup(); mocks.get.mockReset(); });

describe('network card inline IP inventories', () => {
	it('keeps expanded subnets independent and refresh failure cannot turn an inventory into empty capacity', async () => {
		mocks.get.mockImplementation((path: string) => Promise.resolve(detail(path.split('/').pop()!)));
		render(SubnetSection, { subnets, onAdd: vi.fn(), onSave: vi.fn(), onDelete: vi.fn(), deletingSubnetId: null, addError: '', saveError: '', addingSubnet: false, savingSubnet: false });
		expect(screen.getByText('IPv6')).toBeTruthy();
		const expand = screen.getAllByRole('button', { expanded: false });
		await fireEvent.click(expand[0]);
		expect(await inventory('sub-first').findByText('10.200.0.15')).toBeTruthy();
		expect(screen.queryByText('2001:db8::15')).toBeNull();
		await fireEvent.click(expand[1]);
		expect(await inventory('sub-second').findByText('2001:db8::15')).toBeTruthy();
		expect(inventory('sub-second').queryByText('10.200.0.15')).toBeNull();
		mocks.get.mockRejectedValue(new Error('port provider unavailable'));
		const firstRefresh = inventory('sub-first').getAllByRole('button')[0];
		await fireEvent.click(firstRefresh);
		expect(await inventory('sub-first').findByRole('alert')).toBeTruthy();
		expect(inventory('sub-first').getByText('10.200.0.15')).toBeTruthy();
		expect(inventory('sub-second').getByText('2001:db8::15')).toBeTruthy();
		await fireEvent.click(screen.getAllByRole('button', { expanded: true })[0]);
		await waitFor(() => expect(screen.queryByText('10.200.0.15')).toBeNull());
		expect(inventory('sub-second').getByText('2001:db8::15')).toBeTruthy();
	});
});
