import type { AdminSubnetDetail } from '$lib/types/networks';

export const subnetFixture: AdminSubnetDetail = {
	id: 'sub-100',
	name: 'admin-subnet-primary',
	network_id: 'net-200',
	network_name: 'production-network',
	project_id: 'proj-admin-1',
	cidr: '10.200.0.0/24',
	gateway_ip: '10.200.0.1',
	ip_version: 4,
	dhcp_enabled: true,
	allocation_pools: [
		{ start: '10.200.0.10', end: '10.200.0.250' },
	],
	ports: [
		{
			id: 'port-1',
			name: 'web-port',
			status: 'ACTIVE',
			mac_address: 'fa:16:3e:11:22:33',
			device_owner: 'compute:nova',
			device_id: 'inst-1',
			device_name: 'web-instance',
			project_id: 'proj-admin-1',
			ip_addresses: ['10.200.0.15'],
			binding_host_id: 'compute-node-01',
		},
	],
	allocations: [
		{
			ip_address: '10.200.0.15',
			port_id: 'port-1',
			port_name: 'web-port',
			device_owner: 'compute:nova',
			device_id: 'inst-1',
			device_name: 'web-instance',
			project_id: 'proj-admin-1',
			binding_host_id: 'compute-node-01',
		},
	],
	dhcp_bindings: [
		{
			agent_id: 'agent-99',
			host: 'network-node-01',
			binary: 'neutron-dhcp-agent',
			availability_zone: 'nova',
			alive: true,
			admin_state_up: true,
			source: 'agent',
			ip_addresses: ['10.200.0.2'],
			port_ids: ['port-dhcp-1'],
		},
	],
	dhcp_agent_data_available: true,
	device_names_available: true,
	ip_usage: {
		total_pool_ips: '241', allocated_ips: '1', allocated_pool_ips: '1',
		reserved_pool_ips: '0', available_pool_ips: '240', outside_pool_ips: '0', allocation_mode: 'pool',
	},
};
