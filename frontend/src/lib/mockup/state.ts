import type { Instance } from '$lib/types/compute';
import type { AdminVolume, AdminVolumeDetail, AdminVolumeStatusSummary, Volume } from '$lib/types/volume';
import type { DashboardQuotas } from '$lib/types/quotas';
import type { TopologyData, TopologyTraffic } from '$lib/types/topology';
import type { K3sCluster } from '$lib/types/k3s';
import type { Overview, ProjectUsage, VersionInfo } from '$lib/types/adminOverview';
import type { Project } from '$lib/stores/auth';
import type { AdminInstance, TsPoint } from '$lib/types/adminInstance';
import type { EndpointGroup, NetworkAgent, Service, StoragePool } from '$lib/types/adminServices';
import type { User } from '$lib/types/common';
import type { ZunContainerDetail } from '$lib/types/zunContainer';
import type { MonitoringSummary } from '$lib/components/admin/monitoring/MonitoringSummaryTab.svelte';

const NOW = '2026-07-09T00:00:00Z';
const PROJECT_ID = 'mock-project-1';

interface MockMcpAccessRecord {
	id: string;
	grant_id: string;
	name: string;
	source: 'personal_token' | 'oauth';
	access_level: 'read' | 'manage';
	status: 'active' | 'revoked';
	visible_prefix: string | null;
	issued_at: string | null;
	expires_at: string;
	last_used_at: string | null;
	revoked_at: string | null;
	is_lumen_default: boolean;
}

interface MockupState {
	projects: Project[];
	selectedProjectId: string;
	tutorialStatuses: Record<string, 'completed' | 'dismissed'>;
	mcpAccess: {
		personalTokens: MockMcpAccessRecord[];
		oauthGrants: MockMcpAccessRecord[];
	};
	instances: Instance[];
	volumes: Volume[];
	k3sClusters: K3sCluster[];
	topology: TopologyData;
	traffic: TopologyTraffic;
	quotas: DashboardQuotas;
	admin: {
		overview: Overview;
		projects: ProjectUsage[];
		version: VersionInfo;
		notifications: { severity: string; message: string; target: string; href: string }[];
		identitySummary: {
			user_count: number;
			project_count: number;
			role_count: number;
			group_count: number;
			recent_users: { id: string; name: string }[];
			recent_projects: { id: string; name: string }[];
		};
		instances: AdminInstance[];
		instanceHealth: { total: number; active: number; error: number; with_alerts: number; gpu_count: number };
		instanceTimeseries: TsPoint[];
		hypervisors: { id: string; name: string }[];
		volumes: AdminVolume[];
		volumeStatusSummary: AdminVolumeStatusSummary;
		volumeTimeseries: TsPoint[];
		volumeDetails: Record<string, AdminVolumeDetail>;
		library: {
			baseImages: Record<string, unknown>[];
			artifacts: Record<string, unknown>[];
			profiles: Record<string, unknown>[];
			builds: Record<string, unknown>[];
			imports: Record<string, unknown>[];
			consumes: Record<string, unknown>[];
		};
		containers: {
			uuid: string;
			name: string;
			status: string;
			image: string | null;
			cpu: number | null;
			memory: string | null;
			host: string | null;
			created_at: string | null;
			project_id: string | null;
		}[];
		containerDetails: Record<string, ZunContainerDetail>;
		containerLogs: Record<string, string>;
		keyManagerQuotas: { project_id: string; project_quotas: { secrets: number; orders: number; containers: number } }[];
		monitoringSummary: MonitoringSummary;
		services: {
			compute: Service[];
			network: NetworkAgent[];
			block_storage: Service[];
			shared_file_system: Service[];
			orchestration: Service[];
			container: Service[];
			container_infra: Service[];
			endpoints: EndpointGroup[];
			storage_pools: StoragePool[];
		};
		users: User[];
		userActivity: { id: number; created_at: string; username: string; action: string; resource_name: string | null; status: string }[];
	};
}

function instance(id: string, name: string, status: string, fixed: string, floating: string | null, flavor: string): Instance {
	return {
		id,
		name,
		status,
		image_name: 'Ubuntu 24.04 LTS',
		flavor_name: flavor,
		ip_addresses: [
			{ addr: fixed, type: 'fixed', network_name: 'sample-private' },
			...(floating ? [{ addr: floating, type: 'floating', network_name: 'sample-external' }] : []),
		],
		created_at: NOW,
		union_libraries: name.includes('sample-ci') ? ['sample-runner-tools'] : [],
		union_strategy: name.includes('sample-project') ? 'overlayfs' : null,
		metadata: { role: name.includes('sample-ci') ? 'ci' : 'sample' },
		image_id: 'fixture-image-ubuntu',
		flavor_id: `fixture-flavor-${flavor.replace(/[^a-z0-9]+/gi, '-')}`,
		key_name: 'sample-keypair',
		host: 'sample-hypervisor-a',
	};
}

function seedState(): MockupState {
	const instances = [
		instance('mock-instance-1', 'sample-project-alpha', 'ACTIVE', '192.0.2.24', '203.0.113.216', 'cpu.8c_32g'),
		instance('mock-instance-2', 'sample-project-beta', 'ACTIVE', '192.0.2.25', '203.0.113.221', 'cpu.4c_8g'),
		instance('mock-instance-3', 'sample-ci-runner', 'ACTIVE', '192.0.2.66', null, 'cpu.4c_16g'),
		instance('mock-instance-4', 'sample-ml-notebook', 'SHUTOFF', '192.0.2.41', null, 'gpu.8c_64g_a10'),
		instance('mock-instance-5', 'sample-api-check', 'SHELVED_OFFLOADED', '192.0.2.51', null, 'cpu.2c_4g'),
		instance('mock-instance-6', 'sample-batch-worker', 'ERROR', '192.0.2.67', null, 'cpu.4c_8g'),
		instance('mock-instance-7', 'sample-database', 'ACTIVE', '192.0.2.71', null, 'cpu.4c_16g'),
		instance('mock-instance-8', 'sample-observer', 'SHUTOFF', '192.0.2.72', '203.0.113.230', 'cpu.2c_4g'),
	];

	const networks = [
		{ id: 'mock-net-private', name: 'sample-private', status: 'ACTIVE', is_external: false, is_shared: false, project_id: PROJECT_ID, mtu: 1450, subnet_details: [{ id: 'mock-subnet-private', name: 'sample-private-subnet', cidr: '192.0.2.0/24', gateway_ip: '192.0.2.1', dhcp_enabled: true }] },
		{ id: 'mock-net-data', name: 'sample-data', status: 'ACTIVE', is_external: false, is_shared: true, project_id: PROJECT_ID, mtu: 1450, subnet_details: [{ id: 'mock-subnet-data', name: 'sample-data-subnet', cidr: '198.51.100.0/24', gateway_ip: '198.51.100.1', dhcp_enabled: true }] },
		{ id: 'mock-net-public', name: 'sample-external', status: 'ACTIVE', is_external: true, is_shared: true, project_id: null, mtu: 1500, subnet_details: [{ id: 'mock-subnet-public', name: 'sample-external-subnet', cidr: '203.0.113.0/24', gateway_ip: '203.0.113.1', dhcp_enabled: false }] },
	];

	const routers = [
		{ id: 'mock-router-main', name: 'sample-edge-router', status: 'ACTIVE', external_gateway_network_id: 'mock-net-public', external_gateway_ips: ['203.0.113.218'], interface_ips: [{ ip_address: '192.0.2.1', subnet_id: 'mock-subnet-private' }], is_distributed: true, is_ha: true, connected_subnet_ids: ['mock-subnet-private'], dvr_subnet_ids: [], project_id: PROJECT_ID, enable_snat: true, routes: [{ destination: '198.51.100.0/24', nexthop: '192.0.2.254' }] },
		{ id: 'mock-router-data', name: 'sample-data-router', status: 'ACTIVE', external_gateway_network_id: null, external_gateway_ips: [], interface_ips: [{ ip_address: '198.51.100.1', subnet_id: 'mock-subnet-data' }], is_distributed: false, is_ha: false, connected_subnet_ids: ['mock-subnet-data'], dvr_subnet_ids: [], project_id: PROJECT_ID, enable_snat: false, routes: [] },
	];

	// 캔버스 토폴로지용: 포트 단위 NIC(port_id/mac_addr/network_id). FIP 의 port_id 와 fixed 포트 id 를 일치시킨다.
	const topologyNic = (portId: string, addr: string, mac: string, networkId: 'mock-net-private' | 'mock-net-data') => ({
		addr,
		type: 'fixed',
		network_name: networkId === 'mock-net-private' ? 'sample-private' : 'sample-data',
		network_id: networkId,
		port_id: portId,
		mac_addr: mac,
	});
	const topologyFip = (addr: string) => ({ addr, type: 'floating', network_name: 'sample-external', network_id: 'mock-net-public', port_id: null, mac_addr: null });
	const topologyInstances: TopologyData['instances'] = [
		{ id: 'mock-instance-1', name: 'sample-project-alpha', status: 'ACTIVE', project_id: PROJECT_ID, flavor_name: 'cpu.8c_32g', image_id: 'fixture-image-ubuntu', network_names: ['sample-private'], ip_addresses: [topologyNic('mock-port-1', '192.0.2.24', 'fa:16:3e:00:00:01', 'mock-net-private'), topologyFip('203.0.113.216')] },
		{ id: 'mock-instance-2', name: 'sample-project-beta', status: 'ACTIVE', project_id: PROJECT_ID, flavor_name: 'cpu.4c_8g', image_id: 'fixture-image-ubuntu', network_names: ['sample-private'], ip_addresses: [topologyNic('mock-port-2', '192.0.2.25', 'fa:16:3e:00:00:02', 'mock-net-private'), topologyFip('203.0.113.221')] },
		{ id: 'mock-instance-3', name: 'sample-ci-runner', status: 'ACTIVE', project_id: PROJECT_ID, flavor_name: 'cpu.4c_16g', image_id: 'fixture-image-ubuntu', network_names: ['sample-private', 'sample-data'], ip_addresses: [topologyNic('mock-port-3-eth0', '192.0.2.66', 'fa:16:3e:00:00:03', 'mock-net-private'), topologyNic('mock-port-3-eth1', '198.51.100.66', 'fa:16:3e:00:01:03', 'mock-net-data')] },
		{ id: 'mock-instance-4', name: 'sample-ml-notebook', status: 'SHUTOFF', project_id: PROJECT_ID, flavor_name: 'gpu.8c_64g_a10', image_id: 'fixture-image-ubuntu', network_names: ['sample-private'], ip_addresses: [topologyNic('mock-port-4-eth0', '192.0.2.41', 'fa:16:3e:00:00:04', 'mock-net-private')] },
	];

	const adminInstances: AdminInstance[] = [
		{ id: 'mock-instance-1', name: 'sample-project-alpha', status: 'ACTIVE', project_id: PROJECT_ID, user_id: 'mock-user-1', flavor: 'cpu.8c_32g', host: 'sample-hypervisor-a', created_at: '2026-07-02T08:30:00Z' },
		{ id: 'mock-instance-4', name: 'sample-ml-notebook', status: 'SHUTOFF', project_id: 'mock-project-2', user_id: 'mock-user-2', flavor: 'gpu.8c_64g_a10', host: 'sample-hypervisor-gpu', created_at: '2026-07-04T12:00:00Z' },
		{ id: 'mock-instance-6', name: 'sample-batch-worker', status: 'ERROR', project_id: 'mock-project-3', user_id: 'mock-user-3', flavor: 'cpu.4c_8g', host: 'sample-hypervisor-b', created_at: '2026-07-08T21:10:00Z', fault: 'Sample scheduler retry exhausted' },
	];
	const adminVolumes: AdminVolume[] = [
		{ id: 'mock-admin-volume-available', name: 'sample-dataset-ready', status: 'available', size: 200, project_id: PROJECT_ID, project_name: 'sample-project-alpha', created_at: '2026-07-01T10:00:00Z', bootable: false },
		{ id: 'mock-admin-volume-in-use', name: 'sample-notebook-root', status: 'in-use', size: 120, project_id: 'mock-project-2', project_name: 'sample-project-beta', created_at: '2026-07-03T11:30:00Z', bootable: true },
		{ id: 'mock-admin-volume-error', name: 'sample-recovery-volume', status: 'error', size: 80, project_id: 'mock-project-3', project_name: 'sample-ci-runner', created_at: '2026-07-06T16:45:00Z', bootable: false },
	];
	const baseImage = {
		id: 'fixture-image-ubuntu',
		name: 'Ubuntu 24.04 LTS',
		status: 'active',
		ubuntu_base: 'ubuntu-24.04',
		size: 6442450944,
		min_disk: 20,
		min_ram: 2048,
		disk_format: 'qcow2',
		visibility: 'public',
		owner: PROJECT_ID,
		checksum: 'mock-checksum',
		os_hash_algo: 'sha256',
		os_hash_value: 'mock-sha256',
		created_at: '2026-06-20T00:00:00Z',
	};
	const artifactCommon = {
		is_sealed: true,
		is_published: true,
		ubuntu_base: 'ubuntu-24.04',
		base_image_id: baseImage.id,
		base_image_name: baseImage.name,
		base_image_min_disk: baseImage.min_disk,
		base_image_visibility: baseImage.visibility,
		profile_references: [{ id: 1, name: 'sample-ml-stack', layers: ['sample-uv', 'sample-python', 'sample-numpy'] }],
		active_consume_references: [],
		active_build_references: [],
		delete_blockers: [],
		can_delete: false,
	};
	const uvSummary = { id: 101, name: 'sample-uv', kind: 'uv', python_version: null, parent_id: null, is_sealed: true, is_published: true, pip_packages: [], apt_packages: [], ubuntu_base: 'ubuntu-24.04', base_image_id: baseImage.id, base_image_name: baseImage.name, base_image_min_disk: 20, base_image_visibility: 'public', requested_packages: [], created_at: '2026-07-01T08:00:00Z' };
	const pythonSummary = { ...uvSummary, id: 102, name: 'sample-python', kind: 'python', python_version: '3.11', parent_id: 101, created_at: '2026-07-01T09:00:00Z' };
	const pipSummary = { ...pythonSummary, id: 103, name: 'sample-numpy', kind: 'pip', parent_id: 102, pip_packages: ['numpy==1.26.4'], requested_packages: ['numpy==1.26.4'], created_at: '2026-07-01T10:00:00Z' };
	const libraryArtifacts = [
		{ ...uvSummary, ...artifactCommon, sqsh_filename: 'sample-uv.sqsh', lineage: [], ancestors: [], direct_children: [pythonSummary], child_count: 1 },
		{ ...pythonSummary, ...artifactCommon, sqsh_filename: 'sample-python.sqsh', lineage: [uvSummary], ancestors: [uvSummary], direct_children: [pipSummary], child_count: 1 },
		{ ...pipSummary, ...artifactCommon, sqsh_filename: 'sample-numpy.sqsh', lineage: [uvSummary, pythonSummary], ancestors: [uvSummary, pythonSummary], direct_children: [], child_count: 0 },
	];

	return {
		projects: [
			{ id: PROJECT_ID, name: 'sample-project-alpha', description: '튜토리얼 기본 프로젝트', domain_name: 'Sample Research Org', last_accessed_at: '2026-07-08T23:00:00Z' },
			{ id: 'mock-project-2', name: 'sample-project-beta', description: 'GPU 워크로드 데모', domain_name: 'Sample Research Org', last_accessed_at: '2026-07-08T12:30:00Z' },
			{ id: 'mock-project-3', name: 'sample-ci-runner', description: 'CI runner demo', domain_name: 'Sample Research Org', last_accessed_at: '2026-07-07T18:00:00Z' },
		],
		selectedProjectId: PROJECT_ID,
		tutorialStatuses: {},
		mcpAccess: {
			personalTokens: [
				{
					id: 'mock-mcp-token-lumen',
					grant_id: 'mock-mcp-grant-lumen',
					name: 'Lumen',
					source: 'personal_token',
					access_level: 'read',
					status: 'active',
					visible_prefix: 'mcp_mock_lumen_',
					issued_at: NOW,
					expires_at: '2026-12-31T23:59:59Z',
					last_used_at: '2026-07-08T18:30:00Z',
					revoked_at: null,
					is_lumen_default: true,
				},
			],
			oauthGrants: [
				{
					id: 'mock-mcp-oauth-desktop',
					grant_id: 'mock-mcp-oauth-grant-desktop',
					name: 'Desktop MCP client',
					source: 'oauth',
					access_level: 'read',
					status: 'active',
					visible_prefix: null,
					issued_at: '2026-07-06T12:00:00Z',
					expires_at: '2026-12-31T23:59:59Z',
					last_used_at: '2026-07-08T16:15:00Z',
					revoked_at: null,
					is_lumen_default: false,
				},
			],
		},
		instances,
		volumes: [
			{ id: 'mock-volume-1', name: 'root-disk', status: 'in-use', size: 80, volume_type: 'ceph-ssd', attachments: [{ server_id: 'mock-instance-1', device: '/dev/vda' }], bootable: true },
			{ id: 'mock-volume-2', name: 'scratch', status: 'available', size: 200, volume_type: 'ceph-ssd', attachments: [], bootable: false },
		],
		k3sClusters: [
			{ id: 'mock-k3s-1', name: 'sample-cluster-alpha', status: 'ACTIVE', status_reason: null, server_vm_id: 'mock-instance-1', agent_vm_ids: ['mock-instance-2', 'mock-instance-3'], agent_count: 2, api_address: 'https://192.0.2.24:6443', server_ip: '192.0.2.24', network_id: 'mock-net-private', key_name: 'sample-keypair', k3s_version: 'v1.30.4+k3s1', created_at: NOW, updated_at: NOW, deleted_at: null, deleted_by_user_id: null, deleted_reason: null, master_count: 1, stampede_enabled: true },
			{ id: 'mock-k3s-2', name: 'sample-cluster-pending', status: 'CREATE_IN_PROGRESS', status_reason: 'Installing sample agents', server_vm_id: 'mock-instance-4', agent_vm_ids: [], agent_count: 1, api_address: null, server_ip: '192.0.2.41', network_id: 'mock-net-private', key_name: 'sample-keypair', k3s_version: 'v1.30.4+k3s1', created_at: NOW, updated_at: NOW, deleted_at: null, deleted_by_user_id: null, deleted_reason: null, master_count: 1 },
			{ id: 'mock-k3s-3', name: 'sample-cluster-error', status: 'ERROR', status_reason: 'Sample agent bootstrap timed out', server_vm_id: 'mock-instance-6', agent_vm_ids: [], agent_count: 0, api_address: null, server_ip: '192.0.2.67', network_id: 'mock-net-private', key_name: 'sample-keypair', k3s_version: 'v1.29.8+k3s1', created_at: NOW, updated_at: NOW, deleted_at: null, deleted_by_user_id: null, deleted_reason: null, master_count: 1 },
		],
		topology: {
			networks,
			routers,
			instances: topologyInstances,
			floating_ips: [
				{ id: 'mock-fip-1', floating_ip_address: '203.0.113.216', status: 'ACTIVE', fixed_ip_address: '192.0.2.24', port_id: 'mock-port-1', instance_id: 'mock-instance-1', instance_name: 'sample-project-alpha', project_id: PROJECT_ID, router_id: 'mock-router-main', floating_network_id: 'mock-net-public' },
				{ id: 'mock-fip-2', floating_ip_address: '203.0.113.221', status: 'ACTIVE', fixed_ip_address: '192.0.2.25', port_id: 'mock-port-2', instance_id: 'mock-instance-2', instance_name: 'sample-project-beta', project_id: PROJECT_ID, router_id: 'mock-router-main', floating_network_id: 'mock-net-public' },
			],
			load_balancers: [{ id: 'mock-lb-1', name: 'sample-web-balancer', vip_address: '192.0.2.80', vip_port_id: 'mock-lb-port', vip_subnet_id: 'mock-subnet-private', vip_network_id: 'mock-net-private', provisioning_status: 'ACTIVE', operating_status: 'ONLINE', project_id: PROJECT_ID, listeners: [{ id: 'mock-listener-1', name: 'sample-https-listener', protocol: 'HTTPS', protocol_port: 443, default_pool_id: 'mock-pool-1' }], members: [{ id: 'mock-member-1', address: '192.0.2.24', protocol_port: 8443, status: 'ACTIVE', subnet_id: 'mock-subnet-private', pool_id: 'mock-pool-1', server_id: 'mock-instance-1' }] }],
		},
		traffic: {
			ts: 1783555200,
			// interfaces 합 = instances 합 = networks 합(포트 단위 텔레메트리와 집계값의 정합성 유지)
			instances: { 'mock-instance-1': { rx_bps: 2400000, tx_bps: 1800000 }, 'mock-instance-2': { rx_bps: 1200000, tx_bps: 900000 }, 'mock-instance-3': { rx_bps: 2400000, tx_bps: 2200000 } },
			networks: { 'mock-net-private': { rx_bps: 5200000, tx_bps: 4300000 }, 'mock-net-data': { rx_bps: 800000, tx_bps: 600000 } },
			// 라우터 exporter 가 없으므로 항상 비어 있고 _meta 로 사유를 알린다(캔버스 트렁크 배지는 networks 합산값 사용)
			routers: {},
			load_balancers: { 'mock-lb-1': { rx_bps: 1600000, tx_bps: 1500000 } },
			interfaces: {
				'mock-port-1': { instance_id: 'mock-instance-1', network_id: 'mock-net-private', mac_address: 'fa:16:3e:00:00:01', rx_bps: 2400000, tx_bps: 1800000 },
				'mock-port-2': { instance_id: 'mock-instance-2', network_id: 'mock-net-private', mac_address: 'fa:16:3e:00:00:02', rx_bps: 1200000, tx_bps: 900000 },
				'mock-port-3-eth0': { instance_id: 'mock-instance-3', network_id: 'mock-net-private', mac_address: 'fa:16:3e:00:00:03', rx_bps: 1600000, tx_bps: 1600000 },
				'mock-port-3-eth1': { instance_id: 'mock-instance-3', network_id: 'mock-net-data', mac_address: 'fa:16:3e:00:01:03', rx_bps: 800000, tx_bps: 600000 },
			},
			_meta: { router_traffic: 'exporter_required' },
		},
		quotas: {
			compute: { instances: { limit: 30, in_use: 8 }, cores: { limit: 128, in_use: 36 }, ram: { limit: 262144, in_use: 86016 } },
			storage: { volumes: { limit: 60, in_use: 14 }, gigabytes: { limit: 8000, in_use: 1250 } },
			network: { floatingip: { limit: 16, in_use: 3 } },
			file_storage: { shares: { limit: 12, in_use: 4 }, gigabytes: { limit: 4096, in_use: 780 } },
		},
		admin: {
			overview: { hypervisor_count: 7, running_vms: 46, gpu_instances: 8, instance_stats: { total: 58, active: 46, shutoff: 9, error: 3, other: 0 }, vcpus: { total: 768, allowed: 620, used: 312 }, ram_gb: { total: 2048, used: 890 }, disk_gb: { total: 78000, used: 31200 }, containers_count: 12, file_storage_count: 9, database_instances_count: 5, object_storage_containers_count: 18 },
			projects: [
				{ project_id: PROJECT_ID, project_name: 'sample-project-alpha', cpu: { used: 36, quota: 128 }, ram_mb: { used: 86016, quota: 262144 }, instances: { used: 8, quota: 30 }, disk_gb: { used: 1250, quota: 8000 }, gpu_instances: 1 },
				{ project_id: 'mock-project-2', project_name: 'sample-project-beta', cpu: { used: 72, quota: 160 }, ram_mb: { used: 196608, quota: 393216 }, instances: { used: 14, quota: 40 }, disk_gb: { used: 2600, quota: 12000 }, gpu_instances: 4 },
				{ project_id: 'mock-project-3', project_name: 'sample-ci-runner', cpu: { used: 24, quota: 80 }, ram_mb: { used: 49152, quota: 131072 }, instances: { used: 11, quota: 25 }, disk_gb: { used: 900, quota: 4000 }, gpu_instances: 0 },
				{ project_id: 'mock-project-4', project_name: 'sample-visual-research', cpu: { used: 96, quota: 192 }, ram_mb: { used: 262144, quota: 524288 }, instances: { used: 16, quota: 50 }, disk_gb: { used: 4200, quota: 16000 }, gpu_instances: 3 },
			],
			version: { platform: { backend_version: '0.0.0-mock' }, runtime: { python_version: '3.12.8', uptime_seconds: 864000 }, dependencies: { fastapi: '0.125.0', openstacksdk: '3.3.0' }, git: { commit: 'mockup', tag: 'v0.0.0-mock', branch: 'mockup' } },
			notifications: [
				{ severity: 'critical', message: 'sample-compute-node-a GPU 온도가 임계치에 접근했습니다.', target: 'sample-compute-node-a', href: '/admin/monitoring' },
				{ severity: 'warning', message: 'sample-project-beta RAM quota 사용률 80% 초과', target: 'mock-project-2', href: '/admin/projects' },
				{ severity: 'info', message: '야간 백업 검증이 완료되었습니다.', target: 'sample-backup', href: '/admin/services' },
			],
			identitySummary: { user_count: 128, project_count: 24, role_count: 9, group_count: 14, recent_users: [{ id: 'mock-user-1', name: 'sample-user' }, { id: 'mock-user-2', name: 'sample-researcher' }], recent_projects: [{ id: PROJECT_ID, name: 'sample-project-alpha' }, { id: 'mock-project-4', name: 'sample-visual-research' }] },
			instances: adminInstances,
			instanceHealth: { total: 3, active: 1, error: 1, with_alerts: 1, gpu_count: 1 },
			instanceTimeseries: [
				{ ts: 1783036800, total: 48, active: 39, shutoff: 7, error: 2, shelved: 0 },
				{ ts: 1783123200, total: 50, active: 40, shutoff: 7, error: 2, shelved: 1 },
				{ ts: 1783209600, total: 52, active: 42, shutoff: 7, error: 2, shelved: 1 },
				{ ts: 1783296000, total: 54, active: 43, shutoff: 8, error: 2, shelved: 1 },
				{ ts: 1783382400, total: 56, active: 45, shutoff: 8, error: 2, shelved: 1 },
				{ ts: 1783468800, total: 57, active: 45, shutoff: 9, error: 2, shelved: 1 },
				{ ts: 1783555200, total: 58, active: 46, shutoff: 9, error: 3, shelved: 0 },
			],
			hypervisors: [
				{ id: 'mock-hypervisor-a', name: 'sample-hypervisor-a' },
				{ id: 'mock-hypervisor-b', name: 'sample-hypervisor-b' },
				{ id: 'mock-hypervisor-gpu', name: 'sample-hypervisor-gpu' },
			],
			volumes: adminVolumes,
			volumeStatusSummary: {
				total: 3,
				statuses: [
					{ status: 'available', count: 1 },
					{ status: 'in-use', count: 1 },
					{ status: 'error', count: 1 },
				],
			},
			volumeTimeseries: [
				{ ts: 1783036800, total: 28, available: 11, in_use: 16, error: 1 },
				{ ts: 1783123200, total: 29, available: 12, in_use: 16, error: 1 },
				{ ts: 1783209600, total: 29, available: 11, in_use: 17, error: 1 },
				{ ts: 1783296000, total: 30, available: 12, in_use: 17, error: 1 },
				{ ts: 1783382400, total: 31, available: 12, in_use: 18, error: 1 },
				{ ts: 1783468800, total: 31, available: 11, in_use: 19, error: 1 },
				{ ts: 1783555200, total: 32, available: 12, in_use: 19, error: 1 },
			],
			volumeDetails: {
				'mock-admin-volume-available': { id: 'mock-admin-volume-available', name: 'sample-dataset-ready', status: 'available', size: 200, volume_type: 'ceph-ssd', project_id: PROJECT_ID, attachments: [], created_at: '2026-07-01T10:00:00Z', description: '튜토리얼용 가용 볼륨', bootable: false, encrypted: false, multiattach: false, metadata: { purpose: 'tutorial' } },
				'mock-admin-volume-in-use': { id: 'mock-admin-volume-in-use', name: 'sample-notebook-root', status: 'in-use', size: 120, volume_type: 'ceph-ssd', project_id: 'mock-project-2', attachments: [{ server_id: 'mock-instance-4', device: '/dev/vda', id: 'mock-attachment-1' }], created_at: '2026-07-03T11:30:00Z', description: 'GPU notebook root volume', bootable: true, encrypted: false, multiattach: false, metadata: { workload: 'notebook' } },
				'mock-admin-volume-error': { id: 'mock-admin-volume-error', name: 'sample-recovery-volume', status: 'error', size: 80, volume_type: 'ceph-ssd', project_id: 'mock-project-3', attachments: [], created_at: '2026-07-06T16:45:00Z', description: '복구 절차 예시', bootable: false, encrypted: false, multiattach: false, metadata: { state: 'sample-error' } },
			},
			library: {
				baseImages: [baseImage],
				artifacts: libraryArtifacts,
				profiles: [{ id: 1, name: 'sample-ml-stack', layers: ['sample-uv', 'sample-python', 'sample-numpy'], is_published: true, created_at: '2026-07-01T10:10:00Z', updated_at: '2026-07-01T10:10:00Z' }],
				builds: [{ id: 501, layer_name: 'sample-numpy', kind: 'pip', python_version: null, share_id: 'mock-share-layer', server_id: null, port_id: null, build_token: null, cloud_init_status: 'done', status: 'complete', progress_step: 'sealed', progress_pct: 100, error_message: null, console_log_excerpt: null, started_at: '2026-07-01T09:30:00Z', completed_at: '2026-07-01T10:00:00Z', created_at: '2026-07-01T09:29:00Z', pip_packages: ['numpy==1.26.4'], apt_packages: [], ubuntu_base: 'ubuntu-24.04', base_image_id: baseImage.id, base_image_name: baseImage.name, base_image_min_disk: 20, base_image_visibility: 'public', parent_artifact_id: 102 }],
				imports: [{ id: 601, status: 'complete', progress_step: 'profile_saved', progress_pct: 100, error_message: null, github_url: 'https://github.com/example/sample-stack', commit_sha: '0123456789abcdef0123456789abcdef01234567', dockerfile_path: 'Dockerfile', layer_prefix: 'sample-import', profile_name: 'sample-import-profile', ubuntu_base: 'ubuntu-24.04', base_image_id: baseImage.id, base_image_name: baseImage.name, planned_layers: [{ name: 'sample-import-run-1', line: 4, instruction: 'RUN apt-get update' }], artifact_ids: [101], build_ids: [501], created_at: '2026-07-01T07:00:00Z', completed_at: '2026-07-01T08:00:00Z' }],
				consumes: [{ id: 701, profile_name: 'sample-ml-stack', server_id: null, port_id: null, server_name: 'sample-consume-deleted', share_id: 'mock-share-consume', status: 'deleted', error_message: null, created_at: '2026-07-02T10:00:00Z', completed_at: '2026-07-02T11:00:00Z', vm_status: null, vm_ip: null }],
			},
			containers: [
				{ uuid: 'mock-container-1', name: 'sample-api', status: 'Running', image: 'ghcr.io/example/sample-api:1.4', cpu: 2, memory: '2048', host: 'sample-hypervisor-a', created_at: '2026-07-05T08:00:00Z', project_id: PROJECT_ID },
				{ uuid: 'mock-container-2', name: 'sample-worker', status: 'Stopped', image: 'ghcr.io/example/sample-worker:1.4', cpu: 1, memory: '1024', host: 'sample-hypervisor-b', created_at: '2026-07-06T09:00:00Z', project_id: 'mock-project-3' },
			],
			containerDetails: {
				'mock-container-1': { uuid: 'mock-container-1', name: 'sample-api', status: 'Running', status_reason: null, image: 'ghcr.io/example/sample-api:1.4', command: 'python -m sample_api', cpu: 2, memory: '2048', created_at: '2026-07-05T08:00:00Z', addresses: { 'sample-private': [{ addr: '192.0.2.91' }] } },
				'mock-container-2': { uuid: 'mock-container-2', name: 'sample-worker', status: 'Stopped', status_reason: 'Tutorial fixture', image: 'ghcr.io/example/sample-worker:1.4', command: 'python worker.py', cpu: 1, memory: '1024', created_at: '2026-07-06T09:00:00Z', addresses: { 'sample-private': [{ addr: '192.0.2.92' }] } },
			},
			containerLogs: {
				'mock-container-1': '2026-07-09T00:00:00Z INFO sample-api ready\n2026-07-09T00:01:00Z INFO health check ok',
				'mock-container-2': '2026-07-08T22:00:00Z INFO sample-worker stopped cleanly',
			},
			keyManagerQuotas: [
				{ project_id: PROJECT_ID, project_quotas: { secrets: 100, orders: 20, containers: 20 } },
				{ project_id: 'mock-project-2', project_quotas: { secrets: -1, orders: 50, containers: 25 } },
			],
			monitoringSummary: {
				compute: { hypervisors_total: 7, hypervisors_up: 7, vcpus_used: 312, vcpus_total: 768, memory_used_mb: 911360, memory_total_mb: 2097152, running_vms: 46, gpu_instances: 8, instance_stats: { total: 58, active: 46, shutoff: 9, error: 3, other: 0 } },
				storage: { volume_count: 32, volume_by_status: { available: 12, 'in-use': 19, error: 1 }, total_gb: 7200, file_storage_count: 9, volume_snapshot_count: 14, volume_backup_count: 8, share_snapshot_count: 5, image_count: 22 },
				network: { network_count: 18, router_count: 7, router_active: 7, floatingip_count: 12, floatingip_active: 10, port_count: 96, subnet_count: 24, security_group_count: 31, load_balancer_count: 4, load_balancer_active: 4 },
				containers: { zun_count: 2, k3s_count: 3, k3s_active: 1 },
				data_services: { database_instance_count: 5 },
				identity: { user_count: 128, project_count: 24 },
			},
			services: {
				compute: [{ id: 'mock-nova-service', binary: 'nova-compute', host: 'sample-hypervisor-a', status: 'enabled', state: 'up', zone: 'nova', updated_at: NOW, disabled_reason: null }],
				network: [{ id: 'mock-neutron-agent', binary: 'neutron-openvswitch-agent', host: 'sample-network-a', agent_type: 'Open vSwitch agent', availability_zone: 'nova', alive: true, admin_state_up: true, updated_at: NOW }],
				block_storage: [{ id: 'mock-cinder-service', binary: 'cinder-volume', host: 'sample-storage-a@ceph', status: 'enabled', state: 'up', zone: 'nova', updated_at: NOW, disabled_reason: null }],
				shared_file_system: [{ id: 'mock-manila-service', binary: 'manila-share', host: 'sample-storage-a', status: 'enabled', state: 'up', zone: 'nova', updated_at: NOW, disabled_reason: null }],
				orchestration: [{ id: 'mock-heat-service', binary: 'heat-engine', host: 'sample-controller-a', status: 'enabled', state: 'up', zone: 'internal', updated_at: NOW, disabled_reason: null }],
				container: [{ id: 'mock-zun-service', binary: 'zun-compute', host: 'sample-hypervisor-a', status: 'enabled', state: 'up', zone: 'nova', updated_at: NOW, disabled_reason: null }],
				container_infra: [{ id: 'mock-magnum-service', binary: 'magnum-conductor', host: 'sample-controller-a', status: 'enabled', state: 'up', zone: 'internal', updated_at: NOW, disabled_reason: null }],
				endpoints: [{ service_id: 'mock-nova-endpoint', name: 'nova', service: 'compute', region: 'RegionOne', endpoints: { public: 'https://api.example.test/compute', internal: 'http://nova-api.openstack.svc', admin: 'http://nova-api.openstack.svc' } }],
				storage_pools: [{ name: 'sample-storage-a@ceph#rbd', volume_backend_name: 'ceph', driver_version: '3.0.0', storage_protocol: 'ceph', vendor_name: 'Open Source', total_capacity_gb: 16000, free_capacity_gb: 8800, allocated_capacity_gb: 7200 }],
			},
			users: [
				{ id: 'mock-user-1', name: 'sample-admin', email: 'sample-admin@example.test', enabled: true, domain_id: 'default', default_project_id: PROJECT_ID, created_at: '2026-06-01T00:00:00Z', first_seen: '2026-06-01T00:00:00Z', last_seen: NOW },
				{ id: 'mock-user-2', name: 'sample-researcher', email: 'sample-researcher@example.test', enabled: true, domain_id: 'default', default_project_id: 'mock-project-2', created_at: '2026-06-10T00:00:00Z', first_seen: '2026-06-11T00:00:00Z', last_seen: '2026-07-08T12:00:00Z' },
				{ id: 'mock-user-3', name: 'sample-disabled', email: 'sample-disabled@example.test', enabled: false, domain_id: 'default', default_project_id: 'mock-project-3', created_at: '2026-06-20T00:00:00Z', first_seen: '2026-06-21T00:00:00Z', last_seen: '2026-06-30T00:00:00Z' },
			],
			userActivity: [
				{ id: 1, created_at: '2026-07-08T12:00:00Z', username: 'sample-researcher', action: '사용자 수정', resource_name: 'sample-researcher', status: 'success' },
				{ id: 2, created_at: '2026-07-07T09:30:00Z', username: 'sample-admin', action: '사용자 생성', resource_name: 'sample-disabled', status: 'success' },
			],
		},
	};
}

let state = seedState();
let revision = 0;
const revisionListeners = new Set<() => void>();

export function resetMockupState(): void {
	state = seedState();
	revision += 1;
	for (const listener of revisionListeners) listener();
}

export function getMockupState(): MockupState {
	return state;
}

export function getMockupRevision(): number {
	return revision;
}

export function onMockupRevisionChange(listener: () => void): () => void {
	revisionListeners.add(listener);
	return () => revisionListeners.delete(listener);
}

export function cloneMockup<T>(value: T): T {
	return structuredClone(value);
}
