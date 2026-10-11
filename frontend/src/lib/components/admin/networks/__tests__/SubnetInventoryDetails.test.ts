import { beforeEach, describe, expect, it } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { setLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/admin-network';
import SubnetInventoryDetails from '../SubnetInventoryDetails.svelte';
import { subnetFixture } from './subnetFixture';

beforeEach(() => setLocale('en'));

function allocations(length: number) {
	return Array.from({ length }, (_, index) => ({
		...subnetFixture.allocations[0], ip_address: `10.200.0.${index + 101}`,
		port_id: `port-${index}`, port_name: `allocation-port-${index}`,
	}));
}

function usageValue(label: Parameters<typeof t>[0]) {
	const tile = screen.getByText(t(label)).closest('.stat-tile');
	if (!tile) throw new Error('Missing usage tile');
	return within(tile as HTMLElement).getByText(/./, { selector: '.stat-value' }).textContent;
}

describe('shared subnet inventory presentation', () => {
	it('preserves integer precision and distinct port associations for IPv6 capacity', () => {
		const huge = '18446744073709551614';
		render(SubnetInventoryDetails, { subnet: {
			...subnetFixture,
			ip_version: 6, cidr: '2001:db8::/64', gateway_ip: 'fe80::1', ports: [], dhcp_bindings: [],
			allocation_pools: [{ start: '2001:db8::2', end: '2001:db8::ffff:ffff:ffff:ffff' }],
			allocations: [
				{ ...subnetFixture.allocations[0], ip_address: '2001:db8::abcd' },
				{ ...subnetFixture.allocations[0], ip_address: '2001:db8::abcd', port_id: 'duplicate-ip-port' },
			],
			ip_usage: { ...subnetFixture.ip_usage, total_pool_ips: huge, available_pool_ips: '18446744073709551613', allocated_pool_ips: '1', reserved_pool_ips: '0', allocated_ips: '1', outside_pool_ips: '0' },
		} });
		expect(usageValue('subnetDetailPage.totalPoolIps')).toBe(new Intl.NumberFormat('en').format(BigInt(huge)));
		expect(usageValue('subnetDetailPage.availablePoolIps')).toBe('18,446,744,073,709,551,613');
		expect(screen.getAllByText('2001:db8::abcd')).toHaveLength(2);
	});

	it('reacts to the current Intl locale while preserving exact integer precision', async () => {
		const huge = '18446744073709551615';
		render(SubnetInventoryDetails, { subnet: { ...subnetFixture, ip_usage: { ...subnetFixture.ip_usage, total_pool_ips: huge } } });
		setLocale('ko');
		expect(await screen.findByText(new Intl.NumberFormat('ko-KR').format(BigInt(huge)))).toBeTruthy();
		setLocale('zh-CN');
		expect(await screen.findByText(new Intl.NumberFormat('zh-CN').format(BigInt(huge)))).toBeTruthy();
	});

	it.each(['slaac', 'dhcpv6-stateless'] as const)('explains null remaining capacity for %s instead of claiming zero', (mode) => {
		render(SubnetInventoryDetails, { subnet: {
			...subnetFixture, ip_version: 6,
			ip_usage: { ...subnetFixture.ip_usage, available_pool_ips: null, allocation_mode: mode },
		} });
		expect(usageValue('subnetDetailPage.availablePoolIps')).toBe(t('subnetDetailPage.remainingUnavailable'));
		expect(screen.getByText(t('subnetDetailPage.autoIpv6Explanation', { mode }))).toBeTruthy();
	});

	it('links only compute attachments to the existing admin destination and retains names, exact IDs and raw owners', async () => {
		const subnet = { ...subnetFixture, allocations: [
			subnetFixture.allocations[0],
			{ ...subnetFixture.allocations[0], device_owner: 'compute:ironic', device_name: null, device_id: 'baremetal-exact-id' },
			{ ...subnetFixture.allocations[0], device_owner: 'network:router_interface', device_name: 'real-router-name', device_id: 'router-exact-id' },
			{ ...subnetFixture.allocations[0], device_owner: 'network:dhcp', device_name: null, device_id: 'dhcp-device-id' },
			{ ...subnetFixture.allocations[0], device_owner: '', device_name: null, device_id: '' },
		] };
		render(SubnetInventoryDetails, { subnet });
		expect(screen.getByRole('link', { name: 'web-instance' }).getAttribute('href')).toBe('/admin/instances');
		expect(screen.getByRole('link', { name: 'baremetal-exact-id' }).getAttribute('href')).toBe('/admin/instances');
		expect(screen.queryByRole('link', { name: 'real-router-name' })).toBeNull();
		expect(screen.queryByRole('link', { name: 'dhcp-device-id' })).toBeNull();
		for (const value of ['inst-1', 'router-exact-id', 'compute:nova', 'network:router_interface', 'proj-admin-1', 'compute-node-01', 'web-port']) {
			expect(screen.getAllByText(value).length).toBeGreaterThan(0);
		}
		expect(screen.getByText(t('subnetDetailPage.attachmentUnattached'))).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: t('subnetDetailPage.tabs.ports', { count: 1 }) }));
		expect(screen.getByRole('link', { name: 'web-instance' }).getAttribute('href')).toBe('/admin/instances');
		expect(screen.getByText('inst-1')).toBeTruthy();
		expect(screen.getByText('proj-admin-1')).toBeTruthy();
	});

	it('warns about names and scheduler outages without hiding port-sourced DHCP or inventing agents', () => {
		render(SubnetInventoryDetails, { subnet: {
			...subnetFixture, device_names_available: false, dhcp_agent_data_available: false,
			allocations: [{ ...subnetFixture.allocations[0], device_name: null }],
			dhcp_bindings: [{ source: 'port', host: 'ovn-chassis', agent_id: null, binary: null, availability_zone: null, alive: null, admin_state_up: null, ip_addresses: ['10.200.0.3'], port_ids: ['actual-dhcp-port'] }],
		} });
		expect(screen.getByText(t('subnetDetailPage.namesUnavailable'))).toBeTruthy();
		expect(screen.getByText(t('subnetDetailPage.schedulerUnavailable'))).toBeTruthy();
		expect(screen.getByText('ovn-chassis')).toBeTruthy();
		expect(screen.getByText('actual-dhcp-port')).toBeTruthy();
		expect(screen.getByText('10.200.0.3')).toBeTruthy();
		expect(screen.queryByText('agent-99')).toBeNull();
		expect(screen.queryByText('neutron-dhcp-agent')).toBeNull();
		expect(screen.getByRole('link', { name: 'inst-1' })).toBeTruthy();
	});

	it('retains independent allocation and port pages on refresh and clamps only when rows shrink', async () => {
		const subnet = { ...subnetFixture, allocations: allocations(41), ports: Array.from({ length: 41 }, (_, i) => ({ ...subnetFixture.ports[0], id: `port-${i}`, name: `port-name-${i}` })) };
		const view = render(SubnetInventoryDetails, { subnet });
		await fireEvent.click(screen.getByRole('button', { name: /Next/ }));
		await fireEvent.click(screen.getByRole('button', { name: /Next/ }));
		expect(screen.getByText('allocation-port-40')).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: t('subnetDetailPage.tabs.ports', { count: 41 }) }));
		await fireEvent.click(screen.getByRole('button', { name: /Next/ }));
		expect(screen.getByText('port-name-20')).toBeTruthy();
		await view.rerender({ subnet: { ...subnet } });
		expect(screen.getByText('port-name-20')).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: t('subnetDetailPage.tabs.allocations', { count: 41 }) }));
		expect(screen.getByText('allocation-port-40')).toBeTruthy();
		await view.rerender({ subnet: { ...subnet, allocations: allocations(21), ports: subnet.ports.slice(0, 1) } });
		expect(screen.getByText('allocation-port-20')).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: t('subnetDetailPage.tabs.ports', { count: 1 }) }));
		expect(screen.getByText('port-name-0')).toBeTruthy();
	});
});
