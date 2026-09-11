// 목업 기본 데이터셋을 축약한 테스트 픽스처: 6개 네트워크(외부 1, 공유 1, 내부 4), 라우터 2, VM 9(2-homed·3-homed·NIC 없음 포함), LB 1, FIP 3
import type { FloatingIpInfo } from '$lib/types/networks';
import type { TopologyData, TopologyInstance, TopologyIpAddress, TopologyLBMember, TopologyLoadBalancer, TopologyNetwork, TopologyRouter, TopologyTraffic } from '$lib/types/topology';

export const P = 'proj-a1b2';
export const OTHER = 'proj-other';

export function mkNet(id: string, name: string, cidr: string, gw: string, o: { external?: boolean; shared?: boolean; project?: string | null; mtu?: number } = {}): TopologyNetwork {
	return {
		id, name, status: 'ACTIVE',
		is_external: Boolean(o.external), is_shared: Boolean(o.shared), project_id: o.project ?? null,
		subnet_details: [{ id: 'sn-' + id.replace(/^net-/, ''), name: `${name}-subnet`, cidr, gateway_ip: gw, dhcp_enabled: !o.external }],
		mtu: o.mtu ?? 1450,
	};
}

export const NET_NAME: Record<string, string> = {
	'net-pub': 'public', 'net-transit': 'transit-shared', 'net-web': 'web-net', 'net-app': 'app-net', 'net-mgmt': 'mgmt-isolated', 'net-lab': 'lab-isolated', 'net-other': 'other-tenant',
};

type NicSpec = [netId: string, ip: string, macSuffix: string];

export function mkInst(id: string, name: string, status: string, nics: NicSpec[], fips: string[] = [], project: string | null = P): TopologyInstance {
	const ip_addresses: TopologyIpAddress[] = [
		...nics.map(([nid, ip, mac], k) => ({ addr: ip, type: 'fixed', network_name: NET_NAME[nid] ?? nid, network_id: nid, port_id: `port-${name}-eth${k}`, mac_addr: `fa:16:3e:${mac}` })),
		...fips.map((f) => ({ addr: f, type: 'floating', network_name: 'public', network_id: 'net-pub', port_id: null, mac_addr: null })),
	];
	return { id, name, status, project_id: project, network_names: [...new Set(nics.map((n) => NET_NAME[n[0]] ?? n[0]))], ip_addresses, flavor_name: 'cpu.4c_8g', image_id: 'img-ubuntu' };
}

/**
 * 단일 LB 픽스처. makeFixture() 기본 데이터셋은 건드리지 않으며(기존 lbvip 단정 유지),
 * vipNetId / vipSubnetId 조합별 회귀 케이스를 테스트에서 직접 push 할 때 쓴다.
 */
export function mkLb(id: string, name: string, o: { vipNetId?: string | null; vipSubnetId?: string | null; vip?: string; project?: string | null; members?: TopologyLBMember[] } = {}): TopologyLoadBalancer {
	return {
		id, name,
		vip_address: o.vip ?? '10.10.1.200', vip_port_id: `port-${id}-vip`,
		vip_subnet_id: o.vipSubnetId ?? null, vip_network_id: o.vipNetId ?? null,
		provisioning_status: 'ACTIVE', operating_status: 'ONLINE', project_id: o.project ?? P,
		listeners: [], members: o.members ?? [],
	};
}

export function makeFixture(): TopologyData {
	const networks: TopologyNetwork[] = [
		mkNet('net-pub', 'public', '203.0.113.0/24', '203.0.113.1', { external: true, shared: true, mtu: 1500 }),
		mkNet('net-transit', 'transit-shared', '198.51.100.0/24', '198.51.100.1', { shared: true, mtu: 1500 }),
		mkNet('net-web', 'web-net', '10.10.1.0/24', '10.10.1.1', { project: P }),
		mkNet('net-app', 'app-net', '10.10.2.0/24', '10.10.2.1', { project: P }),
		mkNet('net-mgmt', 'mgmt-isolated', '192.0.2.0/24', '192.0.2.1', { project: P }),
		mkNet('net-lab', 'lab-isolated', '10.10.9.0/24', '10.10.9.1', { project: P }),
		mkNet('net-other', 'other-tenant', '10.20.1.0/24', '10.20.1.1', { project: OTHER }),
	];
	const routers: TopologyRouter[] = [
		{ id: 'rtr-edge', name: 'edge-router', status: 'ACTIVE', external_gateway_network_id: 'net-pub', external_gateway_ips: ['203.0.113.10'], interface_ips: [{ ip_address: '10.10.1.1', subnet_id: 'sn-web' }, { ip_address: '10.10.2.1', subnet_id: 'sn-app' }], is_distributed: false, is_ha: true, connected_subnet_ids: ['sn-web', 'sn-app'], dvr_subnet_ids: [], project_id: P, enable_snat: true, routes: [{ destination: '10.20.0.0/16', nexthop: '10.10.2.250' }] },
		{ id: 'rtr-transit', name: 'transit-router', status: 'ACTIVE', external_gateway_network_id: null, external_gateway_ips: [], interface_ips: [{ ip_address: '198.51.100.20', subnet_id: 'sn-transit' }, { ip_address: '10.10.2.254', subnet_id: 'sn-app' }], is_distributed: true, is_ha: false, connected_subnet_ids: ['sn-transit', 'sn-app'], dvr_subnet_ids: ['sn-app'], project_id: P, enable_snat: false, routes: [] },
		{ id: 'rtr-other', name: 'other-router', status: 'ACTIVE', external_gateway_network_id: 'net-pub', external_gateway_ips: ['203.0.113.99'], interface_ips: [{ ip_address: '10.20.1.1', subnet_id: 'sn-other' }], is_distributed: false, is_ha: false, connected_subnet_ids: ['sn-other'], dvr_subnet_ids: [], project_id: OTHER, enable_snat: true, routes: [] },
	];
	const instances: TopologyInstance[] = [
		mkInst('vm-web-01', 'web-01', 'ACTIVE', [['net-web', '10.10.1.11', 'a1:00:11']], ['203.0.113.101']),
		mkInst('vm-web-02', 'web-02', 'ACTIVE', [['net-web', '10.10.1.12', 'a1:00:12']], ['203.0.113.102']),
		mkInst('vm-web-03', 'web-03', 'SHUTOFF', [['net-web', '10.10.1.13', 'a1:00:13']]),
		mkInst('vm-app-01', 'app-01', 'ACTIVE', [['net-app', '10.10.2.21', 'a2:00:21'], ['net-mgmt', '192.0.2.21', 'a5:00:21']]),
		mkInst('vm-db-01', 'db-01', 'ACTIVE', [['net-app', '10.10.2.31', 'a2:00:31'], ['net-mgmt', '192.0.2.31', 'a5:00:31'], ['net-web', '10.10.1.31', 'a1:00:31']]),
		mkInst('vm-bastion-01', 'bastion-01', 'ACTIVE', [['net-transit', '198.51.100.15', 'a3:00:15'], ['net-web', '10.10.1.5', 'a1:00:05']], ['203.0.113.100']),
		mkInst('vm-worker-01', 'worker-01', 'ACTIVE', [['net-transit', '198.51.100.31', 'a3:00:31']]),
		mkInst('vm-monitor-01', 'monitor-01', 'ACTIVE', [['net-mgmt', '192.0.2.10', 'a5:00:10']]),
		mkInst('vm-lab-01', 'lab-01', 'ACTIVE', [['net-lab', '10.10.9.10', 'a9:00:10']]),
		{ id: 'vm-orphan-01', name: 'orphan-01', status: 'SHUTOFF', project_id: P, network_names: [], ip_addresses: [], flavor_name: 'cpu.2c_4g', image_id: 'img-debian' },
		mkInst('vm-other-01', 'other-01', 'ACTIVE', [['net-other', '10.20.1.10', 'aa:00:10']], [], OTHER),
	];
	const floating_ips: FloatingIpInfo[] = [
		{ id: 'fip-1', floating_ip_address: '203.0.113.101', fixed_ip_address: '10.10.1.11', port_id: 'port-web-01-eth0', status: 'ACTIVE', instance_id: 'vm-web-01', instance_name: 'web-01', floating_network_id: 'net-pub' },
		{ id: 'fip-2', floating_ip_address: '203.0.113.102', fixed_ip_address: '10.10.1.12', port_id: 'port-web-02-eth0', status: 'ACTIVE', instance_id: 'vm-web-02', instance_name: 'web-02', floating_network_id: 'net-pub' },
		{ id: 'fip-3', floating_ip_address: '203.0.113.100', fixed_ip_address: '10.10.1.5', port_id: 'port-bastion-01-eth1', status: 'ACTIVE', instance_id: 'vm-bastion-01', instance_name: 'bastion-01', floating_network_id: 'net-pub' },
	];
	const load_balancers = [{
		id: 'lb-web', name: 'web-lb', vip_address: '10.10.1.100', vip_port_id: 'port-lb-web-vip', vip_subnet_id: 'sn-web', vip_network_id: 'net-web', provisioning_status: 'ACTIVE', operating_status: 'ONLINE', project_id: P,
		listeners: [{ id: 'lsn-443', name: 'https', protocol: 'HTTPS', protocol_port: 443, default_pool_id: 'pool-web' }],
		members: [
			{ id: 'mbr-1', address: '10.10.1.11', protocol_port: 8080, status: 'ONLINE', subnet_id: 'sn-web', pool_id: 'pool-web', server_id: 'vm-web-01' },
			{ id: 'mbr-2', address: '10.10.1.12', protocol_port: 8080, status: 'ONLINE', subnet_id: 'sn-web', pool_id: 'pool-web', server_id: 'vm-web-02' },
		],
	}];
	return { networks, routers, instances, floating_ips, load_balancers };
}

export function makeTraffic(): TopologyTraffic {
	const interfaces: NonNullable<TopologyTraffic['interfaces']> = {
		'port-web-01-eth0': { instance_id: 'vm-web-01', network_id: 'net-web', mac_address: 'fa:16:3e:a1:00:11', rx_bps: 3.2e6, tx_bps: 1.1e6 },
		'port-web-02-eth0': { instance_id: 'vm-web-02', network_id: 'net-web', mac_address: 'fa:16:3e:a1:00:12', rx_bps: 2.6e6, tx_bps: 9.0e5 },
		'port-app-01-eth0': { instance_id: 'vm-app-01', network_id: 'net-app', mac_address: 'fa:16:3e:a2:00:21', rx_bps: 1.4e7, tx_bps: 6.0e6 },
		'port-app-01-eth1': { instance_id: 'vm-app-01', network_id: 'net-mgmt', mac_address: 'fa:16:3e:a5:00:21', rx_bps: 2.0e4, tx_bps: 1.5e4 },
		'port-worker-01-eth0': { instance_id: 'vm-worker-01', network_id: 'net-transit', mac_address: 'fa:16:3e:a3:00:31', rx_bps: 1.2e8, tx_bps: 6.5e7 },
	};
	const networks: Record<string, { rx_bps: number; tx_bps: number }> = {};
	const instances: Record<string, { rx_bps: number; tx_bps: number }> = {};
	const add = (m: Record<string, { rx_bps: number; tx_bps: number }>, k: string, v: { rx_bps: number; tx_bps: number }) => {
		const c = m[k] ?? (m[k] = { rx_bps: 0, tx_bps: 0 });
		c.rx_bps += v.rx_bps; c.tx_bps += v.tx_bps;
	};
	for (const v of Object.values(interfaces)) { add(networks, v.network_id, v); add(instances, v.instance_id, v); }
	return { ts: 1_783_555_200, instances, networks, routers: {}, load_balancers: { 'lb-web': { rx_bps: 2.9e6, tx_bps: 2.7e6 } }, interfaces, _meta: { router_traffic: 'exporter_required' } };
}
