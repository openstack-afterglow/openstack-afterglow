import { get } from 'svelte/store';
import { ApiError } from '$lib/api/errors';
import { getMockupProfile, isMockAuthActive } from '$lib/stores/auth';
import { siteConfig } from '$lib/config/site';
import { buildMockAuth } from '$lib/mockup/auth';
import { MOCK_MCP_CONSENT_TICKET, MOCKUP_QUERY_KEY, MOCKUP_SESSION_KEY, MOCKUP_SERVICE_OVERRIDES, isMockupProfileId } from '$lib/mockup/contracts';
import type { MockupProfileId } from '$lib/mockup/contracts';
import { cloneMockup, getMockupState } from '$lib/mockup/state';
import type { K3sSseProgressMessage } from '$lib/api/k3sSseStream';
import { RESOURCE_CATEGORIES, type ProjectResourceInventory, type ResourceCategory, type ResourceInventory, type ResourceItem, type ResourceTotal, type UserDashboardSummary } from '$lib/types/userDashboard';
import { isTourId } from '$lib/tutorial/tours';
import { t } from '$lib/i18n/ns/tutorial';
import { sortResources, type ResourceSort } from '$lib/utils/resourceSort';
import { mockComputePolicy } from '$lib/mockup/computePools';
import { mockContainers } from '$lib/mockup/containers';
import { mockObjectStorage } from '$lib/mockup/objectStorage';
import { parseContainerListResponse } from '$lib/types/zunContainer';
import { mockComputeNetwork } from '$lib/mockup/computeNetwork';
import { mockStorageSecrets } from '$lib/mockup/storageSecrets';
import { mockIdentity } from '$lib/mockup/identity';
import { mockAdminAnnouncements } from '$lib/mockup/adminAnnouncements';
import { mockIdentityAdmin } from '$lib/mockup/identityAdmin';
import { mockAdminResources } from '$lib/mockup/adminResources';
import { mockAdminFloatingIps } from '$lib/mockup/adminFloatingIps';
import { mockAdminPorts } from '$lib/mockup/adminPorts';
import { mockAdminUsers } from '$lib/mockup/adminUsers';
import { mockAdminGroups } from '$lib/mockup/adminGroups';
import { mockAdminRolesDomains } from '$lib/mockup/adminRolesDomains';
import { mockAdminObjectStorage } from '$lib/mockup/adminObjectStorage';
import { mockStorageFiles } from '$lib/mockup/storageFiles';
import { mockNetworkLbRouter } from '$lib/mockup/networkLbRouter';
import { mockDatabaseContainers } from '$lib/mockup/databaseContainers';
import { mockDatabaseBackups } from '$lib/mockup/databaseBackups';
import type { ContainerInfo, OrderInfo, QuotaInfo } from '$lib/api/secrets';

export const symbolNoMatch = Symbol('mockup-no-match');
const MOCK_EXPIRES_AT_ISO = '2026-12-31T23:59:59Z';
const NOW_ISO = '2026-07-09T00:00:00Z';
const MOCK_SECRET_CONTAINER_ITEMS: ContainerInfo[] = [
	{ id: 'mock-secret-container', name: 'tutorial-application-secrets', type: 'generic', status: 'ACTIVE', created: NOW_ISO, secret_refs: [{ name: 'api-password', secret_ref: 'https://barbican.mock.invalid/v1/secrets/mock-secret-api' }] },
];
const MOCK_SECRET_ORDER_ITEMS: OrderInfo[] = [
	{ id: 'mock-secret-order-ready', type: 'key', status: 'ACTIVE', created: NOW_ISO, secret_ref: 'https://barbican.mock.invalid/v1/secrets/mock-secret-api', container_ref: null, meta: { algorithm: 'aes', bit_length: 256 }, error_reason: null },
	{ id: 'mock-secret-order-pending', type: 'asymmetric', status: 'PENDING', created: NOW_ISO, secret_ref: null, container_ref: null, meta: { algorithm: 'rsa', bit_length: 2048 }, error_reason: null },
];
const MOCK_SECRET_QUOTA: QuotaInfo = { secrets: 50, orders: 20, containers: 20, consumers: 100, cas: 5 };
const MOCK_IMAGES = [
	{
		id: 'fixture-image-ubuntu',
		name: 'Ubuntu 24.04 LTS',
		repository: 'ubuntu',
		tag: '24.04',
		verification_status: 'verified',
		verified_at: NOW_ISO,
		status: 'active',
		visibility: 'public',
		size: 2361393152,
		virtual_size: 2361393152,
		min_disk: 10,
		min_ram: 1024,
		disk_format: 'qcow2',
		container_format: 'bare',
		checksum: '0'.repeat(32),
		owner: 'mock-project-1',
		protected: false,
		tags: ['ubuntu', 'lts'],
		properties: {},
		os_distro: 'ubuntu',
		os_version: '24.04',
		created_at: NOW_ISO,
		updated_at: NOW_ISO,
	},
	{
		id: 'fixture-image-rocky',
		name: 'Rocky Linux 9',
		repository: 'rocky',
		tag: '9',
		verification_status: 'unverified',
		verified_at: null,
		status: 'active',
		visibility: 'public',
		size: 1932735283,
		virtual_size: 1932735283,
		min_disk: 10,
		min_ram: 1024,
		disk_format: 'qcow2',
		container_format: 'bare',
		checksum: '1'.repeat(32),
		owner: 'mock-project-1',
		protected: false,
		tags: ['rocky', 'linux'],
		properties: {},
		os_distro: 'rocky',
		created_at: NOW_ISO,
		updated_at: NOW_ISO,
	},
] as const;

function nextMockId(existingIds: string[], prefix: string): string {
	let n = existingIds.length + 1;
	while (existingIds.includes(`${prefix}-${n}`)) n += 1;
	return `${prefix}-${n}`;
}
export function getActiveMockupProfile(): MockupProfileId | null {
	if (typeof window !== 'undefined' && typeof window.location?.search === 'string') {
		const params = new URLSearchParams(window.location.search);
		const requested = params.get(MOCKUP_QUERY_KEY);
		if (params.has(MOCKUP_QUERY_KEY)) return isMockupProfileId(requested) ? requested : null;
	}
	if (!isMockAuthActive()) return null;
	const profile = getMockupProfile() ?? (
		typeof sessionStorage === 'undefined' ? null : sessionStorage.getItem(MOCKUP_SESSION_KEY)
	);
	return isMockupProfileId(profile) ? profile : null;
}

function normalizePath(path: string): string {
	const url = new URL(path, 'http://mockup.local');
	url.searchParams.delete('cache');
	url.searchParams.delete('refresh');
	const qs = url.searchParams.toString();
	return qs ? `${url.pathname}?${qs}` : url.pathname;
}

function ok204(): Record<string, never> {
	return {};
}

export function mockUnsupported(_message?: string): never {
	throw new ApiError(409, t('mockup.unsupported'));
}

function updateInstanceStatus(id: string, status: string): void {
	const state = getMockupState();
	const target = state.instances.find((item) => item.id === id);
	if (target) target.status = status;
}

function deleteInstance(id: string): void {
	const state = getMockupState();
	state.instances = state.instances.filter((item) => item.id !== id);
	type TopologyWithMutableInstances = typeof state.topology & { instances: typeof state.topology.instances };
	const topology = state.topology as TopologyWithMutableInstances;
	topology.instances = topology.instances.filter((item) => item.id !== id);
}

function projectTokenResponse(projectId: string, profile: MockupProfileId): Record<string, unknown> {
	const state = getMockupState();
	const project = state.projects.find((item) => item.id === projectId) ?? state.projects[0];
	state.selectedProjectId = project.id;
	const admin = profile === 'admin';
	return {
		token: `mock-token-${admin ? 'admin' : 'tutorial'}-${project.id}`,
		refresh_token: `mock-refresh-${admin ? 'admin' : 'tutorial'}-${project.id}`,
		expires_at: MOCK_EXPIRES_AT_ISO,
		project_id: project.id,
		project_name: project.name,
		user_id: admin ? 'mock-admin-1' : 'mock-user-1',
		username: admin ? 'demo-admin' : 'demo-user',
		roles: admin ? ['admin'] : ['member'],
		is_system_admin: admin,
		domain_id: 'mock-domain',
		domain_name: 'Demo',
		is_domain_manager: false,
	};
}

interface MockInstanceSummary {
	cpu_avg: number | null;
	mem_avg: number | null;
	underutilized: boolean;
	source: string;
	native_status: string;
}
function instanceMetrics(ids: string[]): Record<string, MockInstanceSummary> {
	const result: Record<string, MockInstanceSummary> = {};
	for (const [index, id] of ids.entries()) {
		result[id] = { cpu_avg: 8 + index * 7, mem_avg: 22 + index * 5, underutilized: index % 3 === 0, source: 'gnocchi', native_status: 'partial' };
	}
	return result;
}

function metricSeries(scale: number): { ts: number; value: number }[] {
	return [0, 1, 2, 3, 4, 5].map((step) => ({ ts: 1783551600 + step * 600, value: scale + step * 3 }));
}

function mockMetric(key: string) {
	const units: Record<string, string> = {
		cpu: '%', memory: '%', network_rx: 'B/s', network_tx: 'B/s', disk_read: 'B/s', disk_write: 'B/s',
		gpu_util: '%', gpu_mem: '%', disk_read_iops: 'request/s', disk_write_iops: 'request/s',
		network_rx_packets: 'packet/s', network_tx_packets: 'packet/s', memory_resident: 'MiB',
		disk_allocation: 'B', memory_swap_in: 'MiB/s', memory_swap_out: 'MiB/s',
	};
	const unit = units[key] ?? '';
	const fallback = key === 'memory' || key.startsWith('gpu_');
	const absent = key.startsWith('memory_swap_') || !unit;
	return {
		series: absent ? [] : metricSeries(key === 'disk_allocation' ? 8589934592 : key === 'memory_resident' ? 384 : key === 'memory' ? 36 : 18),
		source: absent ? 'gnocchi' : fallback ? 'prometheus' : 'gnocchi',
		unit, status: absent ? 'not_collected' : 'available', native_status: fallback || absent ? 'not_collected' : 'available', error: null,
	};
}

function dashboardTrend(range: string | null, includeNetwork: boolean): Record<string, unknown> {
	return {
		vcpu: { data: [24, 27, 31, 29, 33, 36], points: 6, available: true, unit: '%', source: 'gnocchi', status: 'partial', native_status: 'partial' },
		memory: { data: [38, 41, 44, 43, 45, 47], points: 6, available: true, unit: '%', source: 'prometheus', status: 'available', native_status: 'not_collected' },
		storage: { data: [16, 18, 19, 20, 21, 23], points: 6, available: true, unit: '%', source: 'prometheus', status: 'available', native_status: 'not_collected' },
		network: includeNetwork
			? { data: [120, 150, 170, 140, 190, 210], points: 6, available: true, unit: 'KiB/s', source: 'gnocchi', status: 'partial', native_status: 'partial' }
			: { data: [], points: 0, available: false, unit: 'KiB/s', source: null, status: 'not_collected', native_status: null },
		monitoring_available: true,
		scope: 'native_policy',
		range: range ?? '14d',
	};
}

function dashboardOverviewSummary(recentLimit: string | null): Record<string, unknown> {
	const state = getMockupState();
	const parsedLimit = Number.parseInt(recentLimit ?? '', 10);
	const limit = Number.isInteger(parsedLimit) ? Math.min(Math.max(parsedLimit, 5), 12) : 5;
	const instances = [...state.instances]
		.sort((a, b) => {
			const aTime = a.created_at ? Date.parse(a.created_at) : Number.NaN;
			const bTime = b.created_at ? Date.parse(b.created_at) : Number.NaN;
			const aValid = Number.isFinite(aTime);
			const bValid = Number.isFinite(bTime);
			if (aValid && bValid && aTime !== bTime) return bTime - aTime;
			if (aValid !== bValid) return aValid ? -1 : 1;
			return a.id.localeCompare(b.id);
		})
		.slice(0, limit)
		.map(({ id, name, status, flavor_name, ip_addresses, created_at }) => ({
			id,
			name,
			status,
			flavor_name: flavor_name ?? null,
			ip_addresses: ip_addresses ?? [],
			created_at: created_at ?? null,
		}));
	return {
		instances: {
			total: state.instances.length,
			active: state.instances.filter((item) => item.status === 'ACTIVE').length,
			shutoff: state.instances.filter((item) => item.status === 'SHUTOFF').length,
			error: state.instances.filter((item) => item.status === 'ERROR').length,
		},
		recent_instances: instances,
	};
}

function dashboardOverviewQuotas(): Record<string, unknown> {
	const state = getMockupState();
	return {
		compute: structuredClone(state.quotas.compute),
		storage: structuredClone(state.quotas.storage),
		network: structuredClone(state.quotas.network),
		file_storage: structuredClone(state.quotas.file_storage),
		alerts: [],
	};
}

function routerDetail(id: string): Record<string, unknown> | null {
	const topology = getMockupState().topology;
	const router = topology.routers.find((item) => item.id === id);
	if (!router) return null;
	return {
		id: router.id,
		name: router.name,
		status: router.status,
		project_id: router.project_id,
		external_gateway_network_id: router.external_gateway_network_id,
		external_gateway_network_name: topology.networks.find((net) => net.id === router.external_gateway_network_id)?.name ?? null,
		interfaces: router.interface_ips.map((iface) => {
			const network = topology.networks.find((net) => net.subnet_details.some((subnet) => subnet.id === iface.subnet_id));
			const subnet = network?.subnet_details.find((item) => item.id === iface.subnet_id);
			return { id: `${router.id}-${iface.subnet_id}`, subnet_id: iface.subnet_id, subnet_name: subnet?.name ?? iface.subnet_id, network_id: network?.id ?? '', ip_address: iface.ip_address };
		}),
	};
}

function networkDetail(id: string): Record<string, unknown> | null {
	const topology = getMockupState().topology;
	const network = topology.networks.find((item) => item.id === id);
	if (!network) return null;
	return {
		...network,
		subnets: network.subnet_details.map((subnet) => subnet.id),
		routers: topology.routers.filter((router) => router.connected_subnet_ids.some((subnetId) => network.subnet_details.some((subnet) => subnet.id === subnetId))),
	};
}

function userInventoryFixture(profile: MockupProfileId, projectId?: string): UserDashboardSummary {
	const state = getMockupState();
	const userId = buildMockAuth(profile, '/dashboard').userId!;
	const services = { ...get(siteConfig).services, ...MOCKUP_SERVICE_OVERRIDES };
	const paths: Partial<Record<ResourceCategory, string>> = {
		instances: '/api/v1/instances', volumes: '/api/v1/volumes', floating_ips: '/api/v1/networks/floating-ips',
		networks: '/api/v1/networks', routers: '/api/v1/routers', security_groups: '/api/v1/security-groups',
		load_balancers: '/api/v1/loadbalancers', images: '/api/v1/images', keypairs: '/api/v1/keypairs',
		database_instances: '/api/v1/database-instances', database_backups: '/api/v1/database-instances/backups',
		k3s_clusters: '/api/v1/k3s/clusters', containers: '/api/v1/containers', magnum_clusters: '/api/v1/clusters',
		shares: '/api/v1/file-storage', share_snapshots: '/api/v1/share-snapshots', share_networks: '/api/v1/share-networks',
		security_services: '/api/v1/security-services', buckets: '/api/v1/object-storage', volume_snapshots: '/api/v1/volume-snapshots',
	};
	const gates: Partial<Record<ResourceCategory, keyof typeof services>> = {
		database_instances: 'trove', database_backups: 'trove', k3s_clusters: 'k3s', waygate_gateways: 'waygate',
		containers: 'zun', magnum_clusters: 'magnum', shares: 'manila', share_snapshots: 'manila',
		share_networks: 'manila', security_services: 'manila', buckets: 'swift', secrets: 'barbican',
	};
	const routes: Record<ResourceCategory, string> = {
		instances: '/dashboard/compute/instances', volumes: '/dashboard/volumes', floating_ips: '/dashboard/network/floating-ips',
		networks: '/dashboard/network/networks', subnets: '/dashboard/network/networks', routers: '/dashboard/network/routers',
		security_groups: '/dashboard/network/security-groups', load_balancers: '/dashboard/network/loadbalancers',
		images: '/dashboard/compute/images', keypairs: '/dashboard/compute/keypairs', database_instances: '/dashboard/database/instances',
		database_backups: '/dashboard/database/backups', k3s_clusters: '/dashboard/drover', waygate_gateways: '/dashboard/network/waygate',
		containers: '/dashboard/containers/instances', magnum_clusters: '/dashboard/containers/clusters', shares: '/dashboard/file-storage',
		share_snapshots: '/dashboard/file-storage/snapshots', share_networks: '/dashboard/file-storage/networks',
		security_services: '/dashboard/file-storage/security-services', buckets: '/dashboard/object-storage/buckets',
		volume_snapshots: '/dashboard/volumes/snapshots', volume_backups: '/dashboard/volumes/backups', packages: '/palimpsest/packages', secrets: '/dashboard/secrets',
	};
	const projects: ProjectResourceInventory[] = state.projects.map(project => {
		const resources = Object.fromEntries(RESOURCE_CATEGORIES.map(category => {
			const gate = gates[category];
			if (gate && !services[gate]) return [category, { state: 'disabled', count: null, items: [], error: 'service_disabled' }];
			let rows: Record<string, unknown>[] = [];
			if (project.id === state.selectedProjectId || category === 'keypairs') {
				if (category === 'subnets') rows = state.topology.networks.filter(net => net.project_id === project.id).flatMap(net => net.subnet_details.map(subnet => ({ ...subnet, network_id: net.id })));
				else if (category === 'containers') rows = parseContainerListResponse(jsonFixture('GET', paths.containers!, undefined, profile, project.id)).items as unknown as Record<string, unknown>[];
				else if (paths[category]) rows = jsonFixture('GET', paths[category]!, undefined, profile, project.id) as Record<string, unknown>[];
			}
			const items: ResourceItem[] = rows.filter(row => !row.project_id || row.project_id === project.id).map(row => {
				const id = String(row.id ?? row.uuid ?? row.name);
				const personal = ['instances', 'volumes', 'keypairs'].includes(category);
				const item: ResourceItem = { id, name: String(row.name ?? row.floating_ip_address ?? id), status: String(row.status ?? row.provisioning_status ?? ''), project_id: project.id, project_name: project.name, owner_scope: personal ? 'user' : 'project', owner_id: personal ? userId : project.id, href: routes[category] };
				if (['instances', 'volumes', 'networks', 'routers', 'load_balancers', 'database_instances', 'k3s_clusters', 'containers', 'magnum_clusters', 'shares', 'buckets'].includes(category)) item.href += '/' + encodeURIComponent(id);
				if (category === 'subnets') item.href += '/' + encodeURIComponent(String(row.network_id));
				if (category === 'instances') { item.vcpus = null; item.ram_mb = null; item.flavor_name = String(row.flavor_name ?? ''); }
				if (category === 'volumes') item.size = typeof row.size === 'number' ? row.size : null;
				return item;
			});
			return [category, { state: 'ready', count: items.length, items }];
		})) as Record<ResourceCategory, ResourceInventory>;
		return { project_id: project.id, project_name: project.name, resources, usage: { vcpus: resources.instances.count ? null : 0, ram_mb: resources.instances.count ? null : 0, storage_gb: resources.volumes.items.reduce((sum, item) => sum + (item.size ?? 0), 0) } };
	});
	const resources = Object.fromEntries(RESOURCE_CATEGORIES.map(category => {
		const values = projects.map(project => project.resources[category]);
		const ready = values.filter(value => value.state === 'ready');
		const count = category === 'keypairs' ? new Set(ready.flatMap(value => value.items.map(item => item.owner_id + ':' + item.name))).size : ready.reduce((sum, value) => sum + value.count, 0);
		return [category, ready.length === values.length ? { state: 'ready', count, known_count: count } : { state: 'disabled', count: null, known_count: count }];
	})) as Record<ResourceCategory, ResourceTotal>;
	return { user_id: userId, current_project_id: projectId ?? state.selectedProjectId, projects, totals: { resources, usage: { vcpus: null, ram_mb: null, storage_gb: projects.reduce((sum, project) => sum + (project.usage.storage_gb ?? 0), 0) } } };
}

function jsonFixture(method: string, normalized: string, body: unknown, profile: MockupProfileId, requestProjectId?: string): unknown | typeof symbolNoMatch {
	const state = getMockupState();
	const [pathname, query = ''] = normalized.split('?');
	const params = new URLSearchParams(query);
	const computePolicy = mockComputePolicy(method, pathname, params, body, profile);
	if (computePolicy !== undefined) return computePolicy;
	const identityAdmin = mockIdentityAdmin(method, pathname, params, body, profile, requestProjectId);
	if (identityAdmin !== undefined) return identityAdmin;
	const adminResources = mockAdminResources(method, pathname, params, body, profile);
	if (adminResources !== undefined) return adminResources;
	const adminFloatingIps = mockAdminFloatingIps(method, pathname, params, body, profile);
	if (adminFloatingIps !== undefined) return adminFloatingIps;
	const adminPorts = mockAdminPorts(method, pathname, params, body, profile);
	if (adminPorts !== undefined) return adminPorts;
	const adminUsers = mockAdminUsers(method, pathname, params, body, profile);
	if (adminUsers !== undefined) return adminUsers;
	const adminGroups = mockAdminGroups(method, pathname, params, body, profile);
	if (adminGroups !== undefined) return adminGroups;
	const adminRolesDomains = mockAdminRolesDomains(method, pathname, body, profile);
	if (adminRolesDomains !== undefined) return adminRolesDomains;
	const adminObjectStorage = mockAdminObjectStorage(method, pathname, params, body, profile, requestProjectId);
	if (adminObjectStorage !== undefined) return adminObjectStorage;

	if (method === 'GET' && pathname === '/api/v1/site-config') {
		return { ...get(siteConfig), services: { ...get(siteConfig).services, ...MOCKUP_SERVICE_OVERRIDES } };
	}
	if (method === 'GET' && pathname === '/api/v1/auth/me') {
		const auth = buildMockAuth(profile, profile === 'admin' ? '/admin' : '/dashboard');
		return { user_id: auth.userId, username: auth.username, project_id: auth.projectId, project_name: auth.projectName, roles: auth.roles, is_system_admin: auth.isSystemAdmin, domain_id: auth.domainId, domain_name: auth.domainName, is_domain_manager: auth.isDomainManager, auth_method: 'tutorial' };
	}
	if (method === 'GET' && (pathname === '/api/v1/auth/projects/recent' || pathname === '/api/v1/auth/projects')) return state.projects;
	if (method === 'GET' && pathname === '/api/v1/profile') return { id: 'mock-user-1', name: 'Demo User', email: 'demo@example.com', default_project_id: null };
	if (method === 'GET' && pathname === '/api/v1/tutorials/status') {
		return { statuses: state.tutorialStatuses };
	}
	if (method === 'GET' && pathname === '/api/v1/user-dashboard/summary') return userInventoryFixture(profile, requestProjectId);
	if (method === 'GET' && pathname === '/api/v1/profile/activity') {
		const before = Number(params.get('before_id') || Infinity);
		const limit = Math.min(200, Math.max(1, Number(params.get('limit') || 10)));
		return Array.from({ length: 43 }, (_, index) => ({ id: 43 - index, created_at: new Date(Date.parse(NOW_ISO) - index * 60000).toISOString(), project_id: requestProjectId ?? state.selectedProjectId, user_id: buildMockAuth(profile, '/dashboard').userId, username: 'demo-user', resource_type: index % 2 ? 'instance' : 'auth', resource_id: null, resource_name: index % 2 ? 'sample-project-alpha' : 'auth', action: index % 2 ? 'instance.create' : 'login', status: 'success', error_message: null, extra: null })).filter(row => row.id < before && (!params.get('resource_type') || row.resource_type === params.get('resource_type')) && (!params.get('action') || row.action.includes(params.get('action')!))).slice(0, limit);
	}
	const tutorialStatusMatch = pathname.match(/^\/api\/v1\/tutorials\/([^/]+)\/status$/);
	if (method === 'POST' && tutorialStatusMatch) {
		const tourId = tutorialStatusMatch[1];
		const status = (body as { status?: unknown } | null)?.status;
		if (!isTourId(tourId) || (status !== 'completed' && status !== 'dismissed')) mockUnsupported();
		state.tutorialStatuses[tourId] = status;
		return { tour_id: tourId, status };
	}

	if (method === 'GET' && pathname === '/api/v1/auth/mcp-projects') return state.projects.map(({ id, name }) => {
		if (params.get('preview') !== 'true') return { id, name };
		// Reuse explicit tutorial authority, never derive native leaves from member.
		const permissions = jsonFixture('GET', '/api/v1/projects/current/permissions', undefined, profile, id) as {
			can_write: boolean; service_permissions: Record<string, string[]>;
		};
		const { drover, palimpsest, waygate } = permissions.service_permissions;
		return { id, name, can_write: permissions.can_write, service_permissions: { drover, palimpsest, waygate }, service_errors: {} };
	});
	if (method === 'GET' && pathname === '/api/v1/auth/mcp-tokens') return state.mcpAccess.personalTokens.filter((record) => record.status !== 'revoked' && !record.revoked_at).map((record) => ({ ...record, is_lumen_default: record.status === 'active' && record.id === state.mcpAccess.lumenDefaults[requestProjectId ?? state.selectedProjectId] }));
	if (method === 'GET' && ['/api/v1/chat/custom-tools', '/api/v1/chat/mcp-servers', '/api/v1/chat/skills'].includes(pathname)) return [];
	if (pathname === '/api/v1/chat/cloud-tools' && ['GET', 'POST', 'DELETE'].includes(method)) {
		const project = state.projects.find((item) => item.id === (requestProjectId ?? state.selectedProjectId));
		if (!project) mockUnsupported();
		if (method === 'DELETE') {
			delete state.mcpAccess.cloudApprovals[project.id];
			delete state.mcpAccess.lumenDefaults[project.id];
		} else if (method === 'POST') {
			const access = (body as { access_level?: unknown } | null)?.access_level;
			if (access !== 'read' && access !== 'manage') mockUnsupported();
			state.mcpAccess.cloudApprovals[project.id] = { access_level: access, expires_at: new Date(Date.parse(NOW_ISO) + 30 * 86400000).toISOString() };
			delete state.mcpAccess.lumenDefaults[project.id];
		}
		const selected = state.mcpAccess.personalTokens.find((record) => record.status === 'active' && record.id === state.mcpAccess.lumenDefaults[project.id]);
		const approved = state.mcpAccess.cloudApprovals[project.id];
		return {
			available: true,
			enabled: Boolean(selected || approved),
			access_level: selected?.access_level ?? approved?.access_level ?? 'read',
			project_id: project.id,
			project_name: project.name,
			tool_count: selected || approved ? 24 : 0,
			source: selected ? 'personal_token' : 'lumen',
			allowed_projects: selected?.projects ?? (approved ? [{ id: project.id, name: project.name }] : []),
			selection_name: selected?.name ?? null,
			expires_at: selected ? selected.expires_at : approved?.expires_at ?? null,
		};
	}
	if (method === 'GET' && pathname === '/api/v1/auth/mcp-oauth/grants') return state.mcpAccess.oauthGrants.filter((record) => record.status !== 'revoked');
	if (method === 'DELETE' && pathname === '/api/v1/auth/mcp-tokens/lumen-default') {
		delete state.mcpAccess.lumenDefaults[requestProjectId ?? state.selectedProjectId];
		return { lumen_selection_generation: 2 };
	}
	const lumenDefaultTokenId = pathname.match(/^\/api\/v1\/auth\/mcp-tokens\/([^/]+)\/lumen-default$/)?.[1];
	if (method === 'PUT' && lumenDefaultTokenId) {
		const selected = state.mcpAccess.personalTokens.find((record) => record.id === lumenDefaultTokenId && record.status === 'active');
		if (!selected) mockUnsupported();
		state.mcpAccess.lumenDefaults[requestProjectId ?? state.selectedProjectId] = selected.id;
		return { lumen_selection_generation: 2 };
	}
	const oauthGrantId = pathname.match(/^\/api\/v1\/auth\/mcp-oauth\/grants\/([^/]+)$/)?.[1];
	if (method === 'DELETE' && oauthGrantId) {
		const record = state.mcpAccess.oauthGrants.find((item) => item.grant_id === oauthGrantId);
		if (!record) mockUnsupported();
		record.status = 'revoked';
		record.revoked_at = NOW_ISO;
		return ok204();
	}
	const consentTicket = pathname.match(/^\/api\/v1\/auth\/mcp-oauth\/consents\/([^/]+)$/)?.[1];
	if (method === 'GET' && consentTicket) {
		if (consentTicket !== MOCK_MCP_CONSENT_TICKET) mockUnsupported();
		return {
			client_id: 'mock-mcp-desktop-client',
			client_name: 'Tutorial Desktop MCP',
			redirect_uri: 'http://mock-client.example.test/oauth/callback',
			scopes: ['mcp:read'],
			grant_deadline: MOCK_EXPIRES_AT_ISO,
			ongoing_supported: true,
		};
	}
	const consentDecision = pathname.match(/^\/api\/v1\/auth\/mcp-oauth\/consents\/([^/]+)\/(approve|deny)$/);
	if (method === 'POST' && consentDecision) {
		if (consentDecision[1] !== MOCK_MCP_CONSENT_TICKET) mockUnsupported();
		if (consentDecision[2] === 'approve') {
			const payload = body as { access_level?: unknown; project_scope?: unknown; project_ids?: unknown; ongoing?: unknown } | null;
			// This tutorial client requests read only, so manage cannot be approved.
			if (payload?.access_level !== 'read') mockUnsupported();
			if (payload?.ongoing !== undefined && typeof payload.ongoing !== 'boolean') mockUnsupported();
			const ids = payload?.project_ids;
			if (!Array.isArray(ids) || ids.some((id) => typeof id !== 'string' || !state.projects.some((project) => project.id === id)) || (payload?.project_scope === 'selected' ? ids.length === 0 : payload?.project_scope !== 'all' || ids.length !== 0)) mockUnsupported();
		}
		return { redirect_uri: `/dashboard/account?${MOCKUP_QUERY_KEY}=on`, ...(consentDecision[2] === 'approve' ? { effective_ongoing: (body as { ongoing?: boolean } | null)?.ongoing === true } : {}) };
	}


	if (method === 'POST' && profile === 'admin' && pathname === '/api/v1/palimpsest/builds/dockerfile/lint') {
		return {
			valid: true,
			diagnostics: [],
			warnings: [],
			from: {
				line: 1, ref: 'ubuntu:24.04', kind: 'ubuntu_tag',
				image: state.admin.library.baseImages[0] ?? null, parent: null,
				completions: [], error: null, note: null,
			},
			layers: { new: 3, inherited: 0, total: 3, limit: 25, by_instruction: { RUN: 1, ENV: 1, WORKDIR: 1 } },
		};
	}
	const adminAnnouncements = profile === 'admin' ? mockAdminAnnouncements(method, pathname, body) : undefined;
	if (adminAnnouncements !== undefined) return adminAnnouncements;
	if (profile === 'admin' && method !== 'GET') {
		const dockerfileFixture = method === 'POST' && [
			'/api/v1/palimpsest/builds/dockerfile/fetch-url',
			'/api/v1/palimpsest/builds/dockerfile/plan',
			'/api/v1/palimpsest/builds/dockerfile',
		].includes(pathname);
		if (!dockerfileFixture) mockUnsupported();
	}

	if (profile === 'admin' && pathname === '/api/v1/admin/projects/names') {
		return state.projects.map(({ id, name }) => ({ id, name, domain_id: 'mock-domain' }));
	}
	if (profile === 'admin' && pathname === '/api/v1/admin/gpu-aliases') return { aliases: [] };
	if (profile === 'admin' && pathname === '/api/v1/admin/gpu-quotas/defaults') return [];
	const adminQuotaId = pathname.match(/^\/api\/v1\/admin\/quotas\/([^/]+)$/)?.[1];
	if (profile === 'admin' && adminQuotaId) {
		if (!state.projects.some((project) => project.id === adminQuotaId)) mockUnsupported();
		return {
			project_id: adminQuotaId,
			compute: { ...state.quotas.compute, metadata_items: { limit: 128, in_use: 20 }, key_pairs: { limit: 50, in_use: 4 }, server_groups: { limit: 10, in_use: 2 }, server_group_members: { limit: 10, in_use: 3 }, injected_files: { limit: 5, in_use: 0 }, injected_file_content_bytes: { limit: 10240, in_use: 0 }, injected_file_path_bytes: { limit: 255, in_use: 0 } },
			volume: { ...state.quotas.storage, snapshots: { limit: 80, in_use: 6 } },
			network: { network: { limit: 40, in_use: 3 }, subnet: { limit: 60, in_use: 5 }, port: { limit: 150, in_use: 18 }, router: { limit: 15, in_use: 2 }, ...state.quotas.network, security_group: { limit: 30, in_use: 4 }, security_group_rule: { limit: 150, in_use: 12 } },
			file_storage: { ...state.quotas.file_storage, snapshots: { limit: 24, in_use: 2 }, snapshot_gigabytes: { limit: 2048, in_use: 150 }, share_networks: { limit: 12, in_use: 3 }, share_groups: { limit: 10, in_use: 1 }, share_group_snapshots: { limit: 10, in_use: 1 } },
			availability: { compute: true, volume: true, network: true, file_storage: true }, errors: {},
		};
	}
	if (profile === 'admin' && /^\/api\/v1\/admin\/gpu-quotas\/[^/]+$/.test(pathname)) return [];
	if (profile === 'admin' && pathname === '/api/v1/admin/images') {
		const marker = params.get('marker');
		const start = marker ? MOCK_IMAGES.findIndex((image) => image.id === marker) + 1 : 0;
		const limit = Math.max(1, Math.min(100, Number(params.get('limit') || 20)));
		const items = MOCK_IMAGES.slice(start, start + limit);
		return { items, count: items.length, next_marker: start + limit < MOCK_IMAGES.length ? items.at(-1)?.id ?? null : null };
	}
	const adminImageId = pathname.match(/^\/api\/v1\/admin\/images\/([^/]+)$/)?.[1];
	if (profile === 'admin' && adminImageId) return MOCK_IMAGES.find((image) => image.id === adminImageId) ?? mockUnsupported();
	if (profile === 'admin' && pathname === '/api/v1/admin/all-instances') {
		let items = [...state.admin.instances];
		const name = params.get('name')?.toLowerCase();
		const status = params.get('status')?.toLowerCase();
		const project = params.get('project_id');
		const host = params.get('host')?.toLowerCase();
		if (name) items = items.filter((item) => item.name.toLowerCase().includes(name) || item.id.toLowerCase().includes(name));
		if (status) items = items.filter((item) => item.status.toLowerCase() === status);
		if (project) items = items.filter((item) => item.project_id === project);
		if (params.get('domain_id') && params.get('domain_id') !== 'mock-domain') items = [];
		if (host) items = items.filter((item) => item.host?.toLowerCase() === host);
		const sort = params.get('sort') ?? 'created_desc';
		if (!['created_desc', 'created_asc', 'name_asc', 'name_desc'].includes(sort)) throw new ApiError(422, 'invalid_sort');
		items = sortResources(items, sort as ResourceSort);
		const marker = params.get('marker');
		const index = marker ? items.findIndex(item => item.id === marker) : -1;
		if (marker && index < 0) throw new ApiError(400, 'inventory_marker_outside_scope');
		const limit = Number(params.get('limit') || 20);
		const page = items.slice(index + 1, index + 1 + limit);
		return { items: page, next_marker: index + 1 + limit < items.length ? page.at(-1)?.id ?? null : null, count: page.length };
	}
	if (profile === 'admin' && pathname === '/api/v1/admin/instances/health') return state.admin.instanceHealth;
	if (profile === 'admin' && pathname === '/api/v1/admin/timeseries/instances') return state.admin.instanceTimeseries;
	if (profile === 'admin' && pathname === '/api/v1/admin/hypervisors') return state.admin.hypervisors;

	if (profile === 'admin' && ['/api/v1/admin/all-volumes', '/api/v1/admin/volumes/status-summary'].includes(pathname)) {
		const domain = params.get('domain_id');
		if (domain && domain !== 'mock-domain') throw new ApiError(404, 'inventory_domain_not_found');
		const project = params.get('project_id');
		const scoped = state.admin.volumes.filter(item => (!domain || item.domain_id === domain) && (!project || item.project_id === project));
		const name = params.get('name')?.toLowerCase();
		const status = params.get('status')?.toLowerCase();
		const type = params.get('volume_type')?.toLowerCase();
		const min = params.has('min_size') ? Number(params.get('min_size')) : 0;
		const max = params.has('max_size') ? Number(params.get('max_size')) : Infinity;
		if (min > max) throw new ApiError(422, 'inventory_size_range_invalid');
		let items = scoped.filter(item => (!name || item.name.toLowerCase().includes(name) || item.id.toLowerCase().includes(name))
			&& (!status || item.status.toLowerCase() === status) && (!type || item.volume_type?.toLowerCase() === type)
			&& item.size >= min && item.size <= max);
		if (pathname.endsWith('/status-summary')) {
			const counts = new Map<string, number>();
			for (const item of scoped) counts.set(item.status, (counts.get(item.status) ?? 0) + 1);
			const total = (rows: typeof scoped) => rows.reduce((sum, item) => sum + item.size, 0);
			const attached = scoped.filter(item => item.status === 'in-use');
			const available = scoped.filter(item => item.status === 'available');
			return {
				total: scoped.length, total_gb: total(scoped), attached_count: attached.length, attached_gb: total(attached),
				available_count: available.length, available_gb: total(available), filtered_total: items.length, filtered_gb: total(items),
				statuses: [...counts].map(([status, count]) => ({ status, count })).sort((a, b) => b.count - a.count || a.status.localeCompare(b.status)),
				domains: [{ domain_id: 'mock-domain', domain_name: 'Demo', owner_status: 'known', project_ids: [...new Set(scoped.map(item => item.project_id))], volumes: scoped.length, volume_gb: total(scoped), attached_volumes: attached.length, attached_gb: total(attached), available_volumes: available.length, available_gb: total(available) }],
			};
		}
		const sort = params.get('sort') ?? 'created_desc';
		if (!['created_desc', 'created_asc', 'name_asc', 'name_desc'].includes(sort)) throw new ApiError(422, 'invalid_sort');
		items = sortResources(items, sort as ResourceSort);
		const marker = params.get('marker');
		const index = marker ? items.findIndex(item => item.id === marker) : -1;
		if (marker && index < 0) throw new ApiError(400, 'inventory_marker_outside_scope');
		const limit = Number(params.get('limit') || 20);
		const page = items.slice(index + 1, index + 1 + limit);
		return { items: page, next_marker: index + 1 + limit < items.length ? page.at(-1)?.id ?? null : null, count: page.length };
	}
	if (profile === 'admin' && pathname === '/api/v1/admin/timeseries/volumes') return state.admin.volumeTimeseries;
	const adminVolumeDiagnosticId = pathname.match(/^\/api\/v1\/admin\/volumes\/([^/]+)\/delete-diagnostics$/)?.[1];
	if (profile === 'admin' && adminVolumeDiagnosticId) {
		return state.admin.volumeDeleteDiagnostics[adminVolumeDiagnosticId] ?? mockUnsupported();
	}
	const adminVolumeId = pathname.match(/^\/api\/v1\/admin\/volumes\/([^/]+)$/)?.[1];
	if (profile === 'admin' && adminVolumeId) return state.admin.volumeDetails[adminVolumeId] ?? mockUnsupported();

	if (profile === 'admin' && pathname === '/api/v1/admin/libraries/base-images') return state.admin.library.baseImages;
	if (profile === 'admin' && pathname === '/api/v1/admin/libraries/artifacts') return state.admin.library.artifacts;
	if (profile === 'admin' && pathname === '/api/v1/admin/libraries/profiles') return state.admin.library.profiles;
	if (profile === 'admin' && pathname === '/api/v1/admin/libraries/builds') return state.admin.library.builds;
	if (profile === 'admin' && pathname === '/api/v1/admin/libraries/imports') return state.admin.library.imports;
	if (profile === 'admin' && pathname === '/api/v1/admin/libraries/consumes') return state.admin.library.consumes;
	if (profile === 'admin' && pathname === '/api/v1/palimpsest/builds/dockerfile/fetch-url') {
		const payload = body as { url?: string } | null;
		const url = payload?.url ?? 'https://example.com/Dockerfile';
		return {
			dockerfile: 'FROM ubuntu:24.04\nRUN apt-get update && apt-get install -y curl\nENV APP_ENV=production\nWORKDIR /app\n',
			url,
			filename: 'Dockerfile',
			size_bytes: 98,
		};
	}
	if (profile === 'admin' && pathname === '/api/v1/palimpsest/builds/dockerfile/plan') {
		const payload = body as { dockerfile?: string; layer_prefix?: string; profile_name?: string } | null;
		return {
			source_type: 'inline_dockerfile',
			dockerfile_digest: 'sha256:mockdockerfiledigest00000000000000000000000000000000000000000000',
			parent_digest: null,
			ubuntu_base: 'ubuntu-24.04',
			cached_artifact_ids: [],
			steps: [
				{ name: `${payload?.layer_prefix ?? 'custom'}-01-run`, instruction: 'RUN', args: 'apt-get update', step_digest: 'sha256:mockstep1000000000000000000000000000000000000000000000000000000' },
				{ name: `${payload?.layer_prefix ?? 'custom'}-02-env`, instruction: 'ENV', args: 'APP_ENV=production', step_digest: 'sha256:mockstep2000000000000000000000000000000000000000000000000000000' },
				{ name: `${payload?.layer_prefix ?? 'custom'}-03-workdir`, instruction: 'WORKDIR', args: '/app', step_digest: 'sha256:mockstep3000000000000000000000000000000000000000000000000000000' },
			],
		};
	}
	if (profile === 'admin' && pathname === '/api/v1/palimpsest/builds/dockerfile') {
		const payload = body as { dockerfile?: string; layer_prefix?: string; profile_name?: string } | null;
		const newJob = {
			id: state.admin.library.imports.length + 101,
			status: 'building',
			progress_step: 'preparing',
			progress_pct: 10,
			error_message: null,
			github_url: '',
			commit_sha: '',
			dockerfile_path: 'inline:Dockerfile',
			layer_prefix: payload?.layer_prefix ?? 'custom',
			profile_name: payload?.profile_name || (payload?.layer_prefix ?? 'custom'),
			ubuntu_base: 'ubuntu-24.04',
			base_image_id: 'fixture-image-ubuntu',
			base_image_name: 'Ubuntu 24.04 LTS (Fixture)',
			planned_layers: [
				{ name: `${payload?.layer_prefix ?? 'custom'}-01-run`, line: 2, instruction: 'RUN' },
			],
			artifact_ids: [],
			build_ids: [],
			created_at: new Date().toISOString(),
			completed_at: null,
		};
		state.admin.library.imports = [newJob, ...state.admin.library.imports];
		return {
			...newJob,
			source_type: 'inline_dockerfile',
			dockerfile_digest: 'sha256:mockdockerfiledigest00000000000000000000000000000000000000000000',
			parent_digest: null,
			cached_artifact_ids: [],
			planned_step_count: 1,
		};
	}

	if (profile === 'admin' && pathname === '/api/v1/admin/topology') return state.topology;
	if (profile === 'admin' && pathname === '/api/v1/admin/all-containers') return state.admin.containers;
	const adminContainerLogsId = pathname.match(/^\/api\/v1\/admin\/containers\/([^/]+)\/logs$/)?.[1];
	if (profile === 'admin' && adminContainerLogsId) {
		return { logs: state.admin.containerLogs[adminContainerLogsId] ?? '' };
	}
	const adminContainerId = pathname.match(/^\/api\/v1\/admin\/containers\/([^/]+)$/)?.[1];
	if (profile === 'admin' && adminContainerId) return state.admin.containerDetails[adminContainerId] ?? mockUnsupported();
	if (profile === 'admin' && pathname === '/api/v1/admin/key-manager/project-quotas') return state.admin.keyManagerQuotas;
	if (profile === 'admin' && pathname === '/api/v1/admin/monitoring/summary') return {
		...state.admin.monitoringSummary,
		telemetry: {
			source: 'gnocchi', status: 'partial', error: null, truncated: false,
			resources: [
				{ id: 'mock-compute-1', name: 'compute-01', type: 'host', metrics: {
					'compute.node.cpu.percent': { ...mockMetric('cpu'), unit: '%' },
					'compute.node.memory.usage': { ...mockMetric('memory_resident'), unit: 'MiB' },
				} },
				{ id: 'mock-storage-1', name: 'storage-01', type: 'storage', metrics: {
					'storage.objects.size': { ...mockMetric('disk_allocation'), unit: 'B' },
				} },
			],
		},
	};
	if (profile === 'admin' && pathname === '/api/v1/admin/services') {
		const category = params.get('category');
		if (!category || !(category in state.admin.services)) mockUnsupported();
		return { [category]: state.admin.services[category as keyof typeof state.admin.services] };
	}
	if (profile === 'admin' && ['/api/v1/admin/users', '/api/v1/admin/users/activity', '/api/v1/admin/users/stats'].includes(pathname)) {
		if (!params.get('domain_id')) throw new ApiError(422, 'Select a domain');
		if (params.get('domain_id') !== 'mock-domain') throw new ApiError(404, 'Domain not found');
	}
	if (profile === 'admin' && pathname === '/api/v1/admin/users/stats') {
		return { total: state.admin.users.length, enabled: state.admin.users.filter(user => user.enabled).length, disabled: state.admin.users.filter(user => !user.enabled).length };
	}
	if (profile === 'admin' && pathname === '/api/v1/admin/users/activity') return state.admin.userActivity;
	if (profile === 'admin' && pathname === '/api/v1/admin/users') {
		let items = [...state.admin.users];
		const marker = params.get('marker');
		if (marker) {
			const index = items.findIndex((item) => item.id === marker);
			items = index >= 0 ? items.slice(index + 1) : [];
		}
		const limit = Math.max(1, Number.parseInt(params.get('limit') ?? '100', 10) || 100);
		const page = items.slice(0, limit);
		return { items: page, next_marker: items.length > limit ? page.at(-1)?.id ?? null : null, count: page.length };
	}
	if (method === 'POST' && pathname === '/api/v1/auth/token/project') return projectTokenResponse(String((body as { project_id?: string } | null)?.project_id ?? state.projects[0].id), profile);
	if (method === 'POST' && pathname === '/api/v1/networks/ensure-default') return ok204();

	if (method === 'GET' && pathname === '/api/v1/dashboard/snapshot') {
		return {
			summary: { data: dashboardOverviewSummary(params.get('recent_limit')), error: null },
			quotas: { data: dashboardOverviewQuotas(), error: null },
		};
	}
	if (method === 'GET' && pathname === '/api/v1/dashboard/summary') {
		if (params.get('view') === 'overview') return dashboardOverviewSummary(params.get('recent_limit'));
		return { instances: { total: state.instances.length, active: state.instances.filter((item) => item.status === 'ACTIVE').length, shutoff: state.instances.filter((item) => item.status === 'SHUTOFF').length, error: state.instances.filter((item) => item.status === 'ERROR').length }, gpu_used: state.instances.filter((item) => item.flavor_name?.startsWith('gpu.')).length };
	}
	if (method === 'GET' && pathname === '/api/v1/dashboard/quotas') {
		if (params.get('view') === 'overview') return dashboardOverviewQuotas();
		return state.quotas;
	}
	if (method === 'GET' && pathname === '/api/v1/dashboard/k3s-stats') {
		const clusters = state.k3sClusters.filter((cluster) => !cluster.deleted_at);
		return { total: clusters.length, active: clusters.filter((cluster) => cluster.status === 'ACTIVE').length, available: true };
	}
	if (method === 'GET' && pathname === '/api/v1/dashboard/notifications') return { notifications: [{ type: 'quota', severity: 'warning', message: 'GPU quota 사용률이 70%를 넘었습니다.', count: 1 }, { type: 'backup', severity: 'info', message: '오늘 3개의 스냅샷 검증이 완료되었습니다.', count: 3 }] };
	if (method === 'GET' && pathname === '/api/v1/dashboard/metrics/trend') return dashboardTrend(params.get('range'), params.get('include_network') !== 'false');

	if (method === 'GET' && pathname === '/api/v1/instances') return state.instances;
	if (method === 'GET' && pathname === '/api/v1/instances/availability-zones') return [{ name: 'nova', available: true }];
	if (method === 'GET' && pathname === '/api/v1/instances/metrics-summary-batch') return { monitoring_available: true, instances: instanceMetrics(state.instances.map((item) => item.id)) };
	const instanceAction = pathname.match(/^\/api\/v1\/instances\/([^/]+)\/(start|stop|shelve|unshelve)$/);
	if (method === 'POST' && instanceAction) {
		const status = { start: 'ACTIVE', stop: 'SHUTOFF', shelve: 'SHELVED_OFFLOADED', unshelve: 'ACTIVE' }[instanceAction[2]] ?? 'ACTIVE';
		updateInstanceStatus(instanceAction[1], status);
		return ok204();
	}
	if (method === 'DELETE' && /^\/api\/v1\/instances\/[^/]+$/.test(pathname)) {
		deleteInstance(pathname.split('/').at(-1) ?? '');
		return ok204();
	}
	if (method === 'POST' && pathname === '/api/v1/instances/bulk-action') {
		const payload = body as { action?: string; instance_ids?: string[] } | null;
		for (const id of payload?.instance_ids ?? []) {
			if (payload?.action === 'delete') deleteInstance(id);
			else updateInstanceStatus(id, payload?.action === 'stop' ? 'SHUTOFF' : 'ACTIVE');
		}
		return { results: (payload?.instance_ids ?? []).map((id) => ({ id, ok: true })) };
	}
	const instanceId = pathname.match(/^\/api\/v1\/instances\/([^/]+)$/)?.[1];
	if (method === 'GET' && instanceId) return state.instances.find((item) => item.id === instanceId) ?? mockUnsupported();
	const metricInstanceId = pathname.match(/^\/api\/v1\/instances\/([^/]+)\/metrics-summary$/)?.[1];
	if (method === 'GET' && metricInstanceId) return { monitoring_available: true, stats: { cpu: { min: 4, avg: 18, max: 44, source: 'gnocchi', unit: '%', status: 'available', native_status: 'available' }, memory: { min: 18, avg: 36, max: 61, source: 'prometheus', unit: '%', status: 'available', native_status: 'not_collected' } }, recommendation: null };
	if (method === 'GET' && /^\/api\/v1\/instances\/[^/]+\/metrics-batch$/.test(pathname)) {
		const keys = (params.get('metrics') ?? 'cpu,memory').split(',');
		return { metrics: Object.fromEntries(keys.map((key) => [key, mockMetric(key)])) };
	}
	if (method === 'GET' && /^\/api\/v1\/instances\/[^/]+\/metrics$/.test(pathname)) return { instance_id: pathname.split('/')[4], metric: params.get('metric'), range: params.get('range') ?? '1h', ...mockMetric(params.get('metric') ?? '') };
	if (method === 'GET' && /^\/api\/v1\/instances\/[^/]+\/console$/.test(pathname)) return { url: '/mockup-console.html' };
	if (method === 'GET' && /^\/api\/v1\/instances\/[^/]+\/log$/.test(pathname)) return { output: 'cloud-init finished\nk3s service active\nmock workload healthy\n' };
	if (method === 'GET' && /^\/api\/v1\/instances\/[^/]+\/interfaces$/.test(pathname)) return [{ id: 'mock-port-1', name: 'primary', status: 'ACTIVE', device_owner: 'compute:nova', fixed_ips: [{ ip_address: '192.0.2.24' }], project_id: state.selectedProjectId, security_group_ids: ['mock-sg-default'], mac_address: 'fa:16:3e:00:00:01', network_id: 'mock-net-private' }];
	if (method === 'GET' && /^\/api\/v1\/instances\/[^/]+\/volumes$/.test(pathname)) return [{ id: 'mock-attachment-1', volume_id: 'mock-volume-1', server_id: 'mock-instance-1', device: '/dev/vda', name: 'root-disk', size: 80, status: 'in-use', delete_on_termination: false }];
	if (method === 'GET' && /^\/api\/v1\/instances\/[^/]+\/security-groups$/.test(pathname)) return { ports: [], security_groups: [{ id: 'mock-sg-default', name: 'default', description: 'Mock default SG', rules: [{ id: 'mock-rule-ssh', direction: 'ingress', protocol: 'tcp', port_range_min: 22, port_range_max: 22, remote_ip_prefix: '0.0.0.0/0', ethertype: 'IPv4' }] }] };
	if (method === 'GET' && /^\/api\/v1\/instances\/[^/]+\/owner$/.test(pathname)) return { display: 'Sample Cloud Demo / demo-user' };
	if (method === 'GET' && /^\/api\/v1\/instances\/[^/]+\/storage-attachments$/.test(pathname)) return [{ file_storage_id: 'mock-share-1', name: 'demo-dataset', share_proto: 'CEPHFS', status: 'available' }];

	const storageSecrets = mockStorageSecrets(method, pathname, body); if (storageSecrets !== undefined) return storageSecrets;
	const storageFiles = mockStorageFiles(method, pathname, body); if (storageFiles !== undefined) return storageFiles;
	if (method === 'GET' && pathname === '/api/v1/volumes') return state.volumes;
	if (method === 'POST' && pathname === '/api/v1/volumes') {
		const payload = body as { name?: string; size_gb?: number } | null;
		const volume = {
			id: nextMockId(state.volumes.map((item) => item.id), 'mock-volume'),
			name: payload?.name?.trim() || 'mock-volume',
			status: 'available',
			size: payload?.size_gb ?? 10,
			volume_type: 'ceph-ssd',
			attachments: [],
			bootable: false,
		};
		state.volumes.push(volume);
		return volume;
	}
	const volumeId = pathname.match(/^\/api\/v1\/volumes\/([^/]+)$/)?.[1];
	if (method === 'DELETE' && volumeId) {
		state.volumes = state.volumes.filter((item) => item.id !== volumeId);
		return ok204();
	}

	const imageId = pathname.match(/^\/api\/v1\/images\/([^/]+)$/)?.[1];
	if (method === 'GET' && imageId) {
		return MOCK_IMAGES.find((image) => image.id === imageId) ?? mockUnsupported();
	}
	if (method === 'GET' && pathname === '/api/v1/palimpsest/hub/image-exports') return [];
	if (method === 'POST' && pathname === '/api/v1/palimpsest/hub/image-exports') {
		const payload = body as { image_id?: string; disk_format?: string } | null;
		return {
			id: 'mock-image-export-1',
			source_image_id: payload?.image_id ?? 'fixture-image-ubuntu',
			target_disk_format: payload?.disk_format ?? 'qcow2',
			status: 'queued',
			progress_pct: 0,
			error_code: null,
			error_message: null,
			download_path: null,
		};
	}
	const imageExportId = pathname.match(/^\/api\/v1\/palimpsest\/hub\/image-exports\/([^/]+)$/)?.[1];
	if (method === 'GET' && imageExportId) {
		return {
			id: imageExportId,
			source_image_id: 'fixture-image-ubuntu',
			target_disk_format: 'qcow2',
			status: 'complete',
			progress_pct: 100,
			error_code: null,
			error_message: null,
			download_path: `/api/v1/palimpsest/hub/image-exports/${imageExportId}/blob`,
		};
	}
	const imageExportDownloadId = pathname.match(
		/^\/api\/v1\/palimpsest\/hub\/image-exports\/([^/]+)\/download-token$/,
	)?.[1];
	if (method === 'POST' && imageExportDownloadId) {
		return { url: 'http://127.0.0.1:3080/robots.txt', expires_in: 60 };
	}

	if (method === 'GET' && pathname === '/api/v1/images') return MOCK_IMAGES;
	if (method === 'GET' && pathname === '/api/v1/libraries') return [];
	const computeNetwork = mockComputeNetwork(method, pathname, body);
	if (computeNetwork !== undefined) return computeNetwork;
	const networkLbRouter = mockNetworkLbRouter(method, pathname, body);
	if (networkLbRouter !== undefined) return networkLbRouter;
	if (method === 'GET' && pathname === '/api/v1/networks/default') return { network_id: 'mock-net-private' };
	if (method === 'GET' && pathname === '/api/v1/dashboard/gpu-available') return { gpu_types: [] };

	// 튜토리얼에서 실제 콘솔과 동일한 내비게이션을 제공하기 위한 페이지 픽스처들 (빈/샘플 상태)
	const databaseContainers = mockDatabaseContainers(method, pathname, body);
	if (databaseContainers !== undefined) return databaseContainers;
	const databaseBackups = mockDatabaseBackups(method, pathname, body);
	if (databaseBackups !== undefined) return databaseBackups;
	const containers = mockContainers(method, pathname, body);
	if (containers !== undefined) return containers;
	const identity = mockIdentity(method, pathname, params, body, profile);
	if (identity !== undefined) return identity;
	const objectStorage = mockObjectStorage(method, pathname, body);
	if (objectStorage !== undefined) return objectStorage;
	if (method === 'GET' && pathname === '/api/v1/share-networks') return [];
	if (method === 'GET' && pathname === '/api/v1/share-snapshots') return [];
	if (method === 'GET' && pathname === '/api/v1/security-services') return [];
	// Synthetic native-policy projection for the tutorial's standard member graph.
	if (method === 'GET' && pathname === '/api/v1/projects/current/permissions') return {
		is_owner: true, is_manager: true, can_write: true,
		service_permissions: {
			waygate: ['waygate-inventory_reader', 'waygate-connect_user', 'waygate-clients_editor', 'waygate-gateways_editor', 'waygate-clients_admin', 'waygate-gateways_admin', 'waygate-routing_admin'],
			lumen: ['lumen-inventory_reader', 'lumen-history_reader', 'lumen-chat_user', 'lumen-images_user', 'lumen-audio_user', 'lumen-tools_user', 'lumen-assets_editor', 'lumen-agents_editor', 'lumen-mcp_editor', 'lumen-keys_editor', 'lumen-history_editor', 'lumen-resources_admin'],
			drover: ['drover-inventory_reader', 'drover-access_user', 'drover-clusters_editor', 'drover-workloads_editor', 'drover-clusters_admin', 'drover-access_admin'],
			palimpsest: profile === 'admin' ? [] : ['palimpsest-inventory_reader', 'palimpsest-download_user', 'palimpsest-publish_editor', 'palimpsest-keys_editor', 'palimpsest-keys_admin'],
		},
	};
	if (method === 'GET' && /^\/api\/v1\/projects\/[^/]+\/assignable-roles$/.test(pathname)) return {
		is_owner: true, can_manage_owners: true, roles: [
			{ id: 'mock-role-owner', name: 'project_owner', area: 'project', grade: 'owner', implied_role_ids: ['mock-role-admin'], inherited_role_ids: ['mock-role-admin', 'mock-role-member', 'mock-role-reader', 'mock-native-member', 'mock-native-reader'] },
			{ id: 'mock-role-admin', name: 'project_admin', area: 'project', grade: 'admin', implied_role_ids: ['mock-role-member'], inherited_role_ids: ['mock-role-member', 'mock-role-reader', 'mock-native-member', 'mock-native-reader'] },
			{ id: 'mock-role-member', name: 'project_member', area: 'project', grade: 'member', implied_role_ids: ['mock-role-reader', 'mock-native-member'], inherited_role_ids: ['mock-role-reader', 'mock-native-member', 'mock-native-reader'] },
			{ id: 'mock-role-reader', name: 'project_reader', area: 'project', grade: 'reader', implied_role_ids: ['mock-native-reader'], inherited_role_ids: ['mock-native-reader'] },
			{ id: 'mock-native-member', name: 'member', area: null, grade: null, implied_role_ids: ['mock-native-reader'], inherited_role_ids: ['mock-native-reader'] },
			{ id: 'mock-native-reader', name: 'reader', area: null, grade: null, implied_role_ids: [], inherited_role_ids: [] },
		],
	};
	if (method === 'GET' && /^\/api\/v1\/projects\/[^/]+\/members$/.test(pathname)) {
		return { items: [
			{ user_id: 'mock-user-1', username: 'demo-user', email: 'demo@example.com', is_owner: true, is_manager: true, roles: ['project_owner', 'project_admin', 'project_member', 'project_reader', 'member', 'reader'], direct_role_ids: ['mock-role-owner'], direct_roles: [{ id: 'mock-role-owner', name: 'project_owner', inherited_role_ids: ['mock-role-admin', 'mock-role-member', 'mock-role-reader', 'mock-native-member', 'mock-native-reader'] }], effective_role_ids: ['mock-role-owner', 'mock-role-admin', 'mock-role-member', 'mock-role-reader', 'mock-native-member', 'mock-native-reader'], external_role_ids: [], source: 'direct' },
			{ user_id: 'mock-user-2', username: 'sample-researcher', email: 'researcher@example.com', is_owner: false, is_manager: false, roles: ['project_member', 'project_reader', 'member', 'reader'], direct_role_ids: ['mock-role-member'], direct_roles: [{ id: 'mock-role-member', name: 'project_member', inherited_role_ids: ['mock-role-reader', 'mock-native-member', 'mock-native-reader'] }], effective_role_ids: ['mock-role-member', 'mock-role-reader', 'mock-native-member', 'mock-native-reader'], external_role_ids: [], source: 'direct' },
		] };
	}
	if (method === 'GET' && pathname === '/api/v1/announcements') return [];
	if (method === 'GET' && pathname === '/api/v1/announcements/unread-count') return { unread_count: 0 };
	if (method === 'GET' && pathname === '/api/v1/chat/usage') {
		return {
			found: false,
			total_credited_cost: 0,
			lifetime_prompt_tokens: 0,
			lifetime_completion_tokens: 0,
			lifetime_request_count: 0,
			month_credited_cost: 0,
			month_prompt_tokens: 0,
			month_completion_tokens: 0,
			month_request_count: 0,
			quota_used: 0,
			quota_max: 0
		};
	}
	if (method === 'GET' && pathname === '/api/v1/dashboard/usage-stats') {
		return {
			range: params.get('range') ?? '7d',
			top_instances: state.instances.slice(0, 5).map((item, index) => ({
				id: item.id, name: item.name, flavor_name: item.flavor_name ?? 'cpu.4c_8g',
				vcpus: 4, ram_mb: 8192, disk_gb: 80, status: item.status, usage_hours: 96 - index * 12,
				cpu_pct: index === 0 ? 0 : 18 + index * 7, ram_pct: index === 0 ? null : 36 + index * 5,
				cpu_source: 'gnocchi', ram_source: index === 0 ? null : 'prometheus',
				cpu_status: 'available', ram_status: index === 0 ? 'not_collected' : 'available',
				cpu_native_status: 'available', ram_native_status: 'not_collected',
			})),
		};
	}
	if (method === 'GET' && pathname === '/api/v1/dashboard/activity') {
		return {
			range: params.get('range') ?? '7d',
			kpi: { total: 42, success: 39, failed: 3, last_24h: 6, unique_users: 3 },
			hour_distribution: [0, 0, 0, 0, 0, 1, 2, 3, 4, 5, 4, 3, 4, 5, 3, 2, 2, 2, 1, 1, 0, 0, 0, 0],
			recent_actions: [],
			db_status: 'ok',
		};
	}
	if (method === 'GET' && pathname === '/api/v1/dashboard/usage-report') {
		const { compute, storage } = state.quotas;
		return {
			range: params.get('range') ?? '30d',
			start: '2026-06-09T00:00:00Z',
			end: NOW_ISO,
			stats: { instance_hours: 4320, vcpu_hours: 17280, ram_gb_hours: 69120, gpu_hours: 720, active_instances: 6, total_instances: 8 },
			flavor_hours: [
				{ flavor: 'cpu.4c_8g', instance_count: 4, usage_hours: 2160, vcpus: 4, ram_mb: 8192, gpu_count: 0, vcpu_hours: 8640, gpu_hours: 0 },
				{ flavor: 'gpu.8c_64g_a10', instance_count: 1, usage_hours: 720, vcpus: 8, ram_mb: 65536, gpu_count: 1, vcpu_hours: 5760, gpu_hours: 720 },
			],
			instance_usage: state.instances.slice(0, 2).map((item, index) => ({
				instance_id: item.id,
				name: item.name,
				flavor: index === 0 ? 'cpu.4c_8g' : 'gpu.8c_64g_a10',
				state: 'active',
				hours: 720,
				started_at: '2026-06-10T00:00:00+00:00',
				ended_at: null,
				vcpus: index === 0 ? 4 : 8,
				memory_mb: index === 0 ? 8192 : 65536,
				gpu_count: index === 0 ? 0 : 1,
			})),
			quota: {
				compute_available: true,
				storage_available: true,
				instances: structuredClone(compute.instances),
				vcpus: structuredClone(compute.cores),
				ram_mb: structuredClone(compute.ram),
				volume_gb: structuredClone(storage.gigabytes),
				volumes: structuredClone(storage.volumes),
				gpu: [{ gpu_type: 'A10', in_use: 1, limit: 2 }],
				gpu_available: true,
			},
			forecast: {
				window_days: 7,
				horizon_days: 30,
				vcpus: { current_pct: 28.1, slope_per_day: 0.57, projected_pct: 41.4, days_to_limit: 161, trend_available: true, series: [30, 30, 32, 32, 34, 36, 36] },
				ram_mb: { current_pct: 32.8, slope_per_day: 1024, projected_pct: 44.5, days_to_limit: 172, trend_available: true, series: [73728, 73728, 77824, 77824, 81920, 86016, 86016] },
				volume_gb: { current_pct: 15.6, slope_per_day: null, projected_pct: null, days_to_limit: null, trend_available: false, series: [] },
				gpu: { A10: { current_pct: 50, slope_per_day: 0, projected_pct: 50, days_to_limit: null, trend_available: true, series: [1, 1, 1, 1, 1, 1, 1] } },
			},
		};
	}

	if (method === 'GET' && pathname === '/api/v1/networks') return state.topology.networks.map((net) => ({ id: net.id, name: net.name, status: net.status, subnets: net.subnet_details.map((subnet) => subnet.id), cidrs: net.subnet_details.map((subnet) => subnet.cidr), is_external: net.is_external, is_shared: net.is_shared, project_id: net.project_id }));
	if (method === 'GET' && pathname === '/api/v1/networks/floating-ips') return state.topology.floating_ips;
	if (method === 'GET' && pathname === '/api/v1/networks/topology') {
		return {
			...state.topology,
			networks: state.topology.networks.map((n) => ({ ...n, subnet_details: [...n.subnet_details] })),
			routers: state.topology.routers.map((r) => ({ ...r, interface_ips: [...r.interface_ips], connected_subnet_ids: [...r.connected_subnet_ids] })),
			instances: state.topology.instances.map((inst) => ({ ...inst, ip_addresses: [...inst.ip_addresses], network_names: [...inst.network_names] })),
		};
	}
	if (method === 'GET' && pathname === '/api/v1/networks/topology/traffic') return state.traffic;
	if (method === 'GET' && pathname === '/api/v1/networks/topology/traffic/history') {
		// 결정론적 합성 시계열 — 목업은 난수를 쓰지 않는다. 마지막 샘플을 instant 값과 일치시켜
		// 패널의 "합산 트래픽" 행과 스파크라인이 어긋나 보이지 않게 한다.
		const netId = params.get('network_id') ?? '';
		const range = params.get('range') ?? '15m';
		const spans: Record<string, [number, number]> = { '15m': [900, 15], '30m': [1800, 30], '1h': [3600, 30] };
		const [rangeS, stepS] = spans[range] ?? spans['15m'];
		const n = rangeS / stepS;
		const cur = state.traffic.networks[netId];
		const series = cur
			? Array.from({ length: n }, (_, i) => {
				const k = i === n - 1 ? 1 : 0.75 + 0.25 * Math.sin((i / n) * Math.PI * 4);
				return {
					ts: state.traffic.ts - (n - 1 - i) * stepS,
					rx_bps: Math.round(cur.rx_bps * k),
					tx_bps: Math.round(cur.tx_bps * k),
				};
			})
			: [];
		const rxs = series.map((p) => p.rx_bps);
		const txs = series.map((p) => p.tx_bps);
		const mean = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length;
		return {
			network_id: netId,
			range,
			step_s: stepS,
			window: '30s',
			series,
			stats: series.length
				? {
					avg: { rx_bps: mean(rxs), tx_bps: mean(txs) },
					max: { rx_bps: Math.max(...rxs), tx_bps: Math.max(...txs) },
					latest: { rx_bps: rxs[rxs.length - 1], tx_bps: txs[txs.length - 1] },
				}
				: { avg: null, max: null, latest: null },
			_meta: { source: 'network_nic_sum', router_traffic: 'exporter_required' },
		};
	}
	const networkSubnet = pathname.match(/^\/api\/v1\/networks\/([^/]+)\/subnets$/)?.[1];
	if (method === 'POST' && networkSubnet) {
		const network = state.topology.networks.find((item) => item.id === networkSubnet);
		const payload = body as { name?: string; cidr?: string; gateway_ip?: string | null; enable_dhcp?: boolean } | null;
		if (!network || network.project_id !== state.selectedProjectId || !payload?.cidr) return mockUnsupported();
		const subnet = { id: `${network.id}-subnet-${network.subnet_details.length + 1}`, name: payload.name || `${network.name}-subnet`, cidr: payload.cidr, ip_version: payload.cidr.includes(':') ? 6 : 4, gateway_ip: payload.gateway_ip ?? null, dhcp_enabled: payload.enable_dhcp ?? true };
		network.subnet_details.push(subnet);
		return subnet;
	}
	const instanceInterface = pathname.match(/^\/api\/v1\/instances\/([^/]+)\/interfaces$/)?.[1];
	if (method === 'POST' && instanceInterface) {
		const payload = body as { net_id?: string } | null;
		const instance = state.topology.instances.find((item) => item.id === instanceInterface);
		const network = state.topology.networks.find((item) => item.id === payload?.net_id);
		if (!instance || !network || instance.ip_addresses.some((ip) => ip.network_id === network.id)) return mockUnsupported();
		const n = instance.ip_addresses.length + 1;
		instance.ip_addresses.push({ addr: `10.250.${n}.10`, type: 'fixed', network_name: network.name, network_id: network.id, port_id: `mock-port-${instance.id}-${network.id}`, mac_addr: `fa:16:3e:00:00:${n < 10 ? '0' + n : n}` });
		if (!instance.network_names.includes(network.name)) instance.network_names.push(network.name);
		return { net_id: network.id };
	}
	const routerGateway = pathname.match(/^\/api\/v1\/routers\/([^/]+)\/gateway$/)?.[1];
	if (method === 'POST' && routerGateway) {
		const payload = body as { external_network_id?: string } | null;
		const router = state.topology.routers.find((item) => item.id === routerGateway);
		const network = state.topology.networks.find((item) => item.id === payload?.external_network_id && item.is_external);
		if (!router || !network) return mockUnsupported();
		router.external_gateway_network_id = network.id;
		return routerDetail(router.id);
	}
	const routerInterfaces = pathname.match(/^\/api\/v1\/routers\/([^/]+)\/interfaces$/)?.[1];
	if (method === 'POST' && routerInterfaces) {
		const payload = body as { subnet_id?: string; auto_gateway?: boolean } | null;
		const router = state.topology.routers.find((item) => item.id === routerInterfaces);
		const network = state.topology.networks.find((item) => item.subnet_details.some((subnet) => subnet.id === payload?.subnet_id));
		const subnet = network?.subnet_details.find((item) => item.id === payload?.subnet_id);
		if (!router || !network || router.project_id !== state.selectedProjectId || network.project_id !== state.selectedProjectId || !subnet || router.connected_subnet_ids.includes(subnet.id)) return mockUnsupported();
		if (payload?.auto_gateway && !subnet.gateway_ip && subnet.cidr) {
			const m = subnet.cidr.match(/^(\d+\.\d+\.\d+)\.\d+\/\d+$/);
			subnet.gateway_ip = m ? `${m[1]}.1` : '10.250.0.1';
		}
		const gw = subnet.gateway_ip ?? '10.250.0.1';
		router.connected_subnet_ids.push(subnet.id);
		router.interface_ips.push({ subnet_id: subnet.id, ip_address: gw });
		return routerDetail(router.id);
	}
	const routerInterfaceDelete = pathname.match(/^\/api\/v1\/routers\/([^/]+)\/interfaces\/([^/]+)$/);
	if (method === 'DELETE' && routerInterfaceDelete) {
		const [, rId, sId] = routerInterfaceDelete;
		const router = state.topology.routers.find((item) => item.id === rId);
		if (router) {
			router.connected_subnet_ids = router.connected_subnet_ids.filter((id) => id !== sId);
			router.interface_ips = router.interface_ips.filter((item) => item.subnet_id !== sId);
		}
		return { success: true };
	}
	const routerGatewayDelete = pathname.match(/^\/api\/v1\/routers\/([^/]+)\/gateway$/)?.[1];
	if (method === 'DELETE' && routerGatewayDelete) {
		const router = state.topology.routers.find((item) => item.id === routerGatewayDelete);
		if (router) router.external_gateway_network_id = null;
		return { success: true };
	}
	const subnetItem = pathname.match(/^\/api\/v1\/networks\/subnets\/([^/]+)$/)?.[1];
	if (method === 'PUT' && subnetItem) {
		const payload = body as { name?: string; gateway_ip?: string | null; enable_dhcp?: boolean } | null;
		for (const net of state.topology.networks) {
			const sub = net.subnet_details.find((s) => s.id === subnetItem);
			if (sub) {
				if (payload?.name !== undefined) sub.name = payload.name || sub.name;
				if (payload?.gateway_ip !== undefined) sub.gateway_ip = payload.gateway_ip;
				if (payload?.enable_dhcp !== undefined) sub.dhcp_enabled = payload.enable_dhcp;
				return sub;
			}
		}
		return mockUnsupported();
	}
	if (method === 'DELETE' && subnetItem) {
		for (const net of state.topology.networks) {
			net.subnet_details = net.subnet_details.filter((s) => s.id !== subnetItem);
		}
		for (const r of state.topology.routers) {
			r.connected_subnet_ids = r.connected_subnet_ids.filter((id) => id !== subnetItem);
			r.interface_ips = r.interface_ips.filter((item) => item.subnet_id !== subnetItem);
		}
		return { success: true };
	}
	const routerId = pathname.match(/^\/api\/v1\/routers\/([^/]+)$/)?.[1];
	if (method === 'GET' && routerId) return routerDetail(routerId) ?? mockUnsupported();
	const networkId = pathname.match(/^\/api\/v1\/networks\/([^/]+)$/)?.[1];
	if (method === 'DELETE' && networkId) {
		state.topology.networks = state.topology.networks.filter((item) => item.id !== networkId);
		return { success: true };
	}
	if (method === 'PUT' && pathname === '/api/v1/networks/default') {
		const payload = body as { network_id?: string } | null;
		return { network_id: payload?.network_id ?? state.topology.networks[0]?.id };
	}
	if (method === 'GET' && pathname === '/api/v1/networks/default') {
		return { network_id: state.topology.networks[0]?.id ?? 'mock-net-1' };
	}
	if (method === 'GET' && networkId) return networkDetail(networkId) ?? mockUnsupported();

	if (method === 'GET' && pathname === '/api/v1/k3s/clusters') {
		const includeDeleted = params.get('include_deleted') === 'true';
		return state.k3sClusters.filter((cluster) => includeDeleted || !cluster.deleted_at);
	}
	const k3sClusterId = pathname.match(/^\/api\/v1\/k3s\/clusters\/([^/]+)$/)?.[1];
	if (method === 'GET' && k3sClusterId) return state.k3sClusters.find((cluster) => cluster.id === k3sClusterId) ?? mockUnsupported();
	const namespaceClusterId = pathname.match(/^\/api\/v1\/k3s\/clusters\/([^/]+)\/namespaces$/)?.[1];
	if (method === 'GET' && namespaceClusterId) {
		if (!state.k3sClusters.some((cluster) => cluster.id === namespaceClusterId)) return mockUnsupported();
		// Explicit tutorial fixture for the native string-array discovery contract, not a derived namespace.
		return ['tutorial-workloads'];
	}
	const authorityClusterId = pathname.match(/^\/api\/v1\/k3s\/clusters\/([^/]+)\/authorization$/)?.[1];
	if (method === 'GET' && authorityClusterId) {
		if (!state.k3sClusters.some((cluster) => cluster.id === authorityClusterId)) return mockUnsupported();
		// Tutorial clusters model current resource authority; reauthorization stays unsupported in the mockup.
		return { cluster_id: authorityClusterId, authorized: true, active_generation: 1, staged_generations: [], owner_revocation_required: [], credentials: [] };
	}
	if (method === 'GET' && pathname === '/api/v1/admin/k3s-clusters') return state.k3sClusters;
	const adminK3sClusterId = pathname.match(/^\/api\/v1\/admin\/k3s-clusters\/([^/]+)$/)?.[1];
	if (method === 'GET' && adminK3sClusterId) return state.k3sClusters.find((cluster) => cluster.id === adminK3sClusterId) ?? mockUnsupported();
	if (method === 'GET' && pathname === '/api/v1/k3s/cluster-templates') return [{ id: 'mock-template-1', name: 'GPU training baseline', description: '1 master + 2 workers', default_node_count: 2, default_agent_flavor_id: 'mock-flavor-cpu4', os_type: 'ubuntu' }];
	if (method === 'GET' && pathname === '/api/v1/flavors/composer-options') {
		return {
			checked_at: NOW_ISO,
			status: 'available',
			gpu_profiles: [{ id: 'mock-gpu-a10', name: 'A10' }],
			variants: [
				{
					gpu_profile_id: null, gpu_count: 0, status: 'available',
					regions: [{ vcpus: { min: 1, max: 8, step: 1 }, ram_mb: { min: 1024, max: 65536, step: 1024 } }],
					preview: null,
				},
			],
		};
	}
	if (method === 'GET' && pathname === '/api/v1/flavors/compositions') return { items: [] };
	if (method === 'GET' && (pathname === '/api/v1/flavors' || pathname === '/api/v1/admin/instances/flavors-for-project')) {
		return [
			{ id: 'mock-flavor-cpu4', name: 'cpu.4c_8g', vcpus: 4, ram: 8192, disk: 80, is_public: true, extra_specs: {} },
			{ id: 'mock-flavor-gpu', name: 'gpu.8c_64g_a10', vcpus: 8, ram: 65536, disk: 160, is_public: true, extra_specs: { 'pci_passthrough:alias': 'A10:1' } },
		].map(flavor => ({
			...flavor,
			eligibility: {
				selectable: true,
				requirements: { instances: 1, cores: flavor.vcpus, ram_mb: flavor.ram, gpus: flavor.id === 'mock-flavor-gpu' ? { A10: 1 } : {} },
				remaining: { instances: 8, cores: 56, ram_mb: 196608, gpus: { A10: 1 } },
				blockers: [],
				capacity: {
					status: 'available', checked_at: NOW_ISO, candidate_hosts: 1,
					cpu_resource_class: 'VCPU', remaining_vcpus: 32, remaining_ram_mb: 98304,
				},
			},
		}));
	}
	const healthClusterId = pathname.match(/^\/api\/v1\/k3s\/clusters\/([^/]+)\/health(?:\/check)?$/)?.[1];
	if ((method === 'GET' || (method === 'POST' && pathname.endsWith('/health/check'))) && healthClusterId) {
		const cluster = state.k3sClusters.find((item) => item.id === healthClusterId);
		if (!cluster) return mockUnsupported();
		return {
			cluster_id: cluster.id,
			cluster_name: cluster.name,
			status: cluster.status === 'ACTIVE' ? 'HEALTHY' : 'UNKNOWN',
			api_server_reachable: cluster.status === 'ACTIVE',
			healthz_ok: cluster.status === 'ACTIVE',
			nodes: [
				{ name: 'mock-server', role: 'server', ready: cluster.status === 'ACTIVE', conditions: cluster.status === 'ACTIVE' ? ['Ready'] : [], kubelet_version: 'v1.30.4+k3s1' },
				...cluster.agent_vm_ids.map((id, index) => ({ name: `mock-agent-${index + 1}`, role: 'agent', ready: cluster.status === 'ACTIVE', conditions: cluster.status === 'ACTIVE' ? ['Ready'] : [], kubelet_version: 'v1.30.4+k3s1' })),
			],
			checked_at: '2026-07-09T00:00:00Z',
			error: null,
			reachability: cluster.status === 'ACTIVE' ? 'direct' : 'unreachable',
		};
	}
	// Match the native consumer Key Manager array contracts; never expose payloads or simulate writes.
	if (method === 'GET' && pathname === '/api/v1/secret-containers') return MOCK_SECRET_CONTAINER_ITEMS;
	if (method === 'GET' && pathname === '/api/v1/secret-orders') return MOCK_SECRET_ORDER_ITEMS;
	if (method === 'GET' && pathname === '/api/v1/secrets/quota/effective') return MOCK_SECRET_QUOTA;

	if (method === 'GET' && profile === 'admin' && pathname === '/api/v1/admin/overview') return state.admin.overview;
	if (method === 'GET' && profile === 'admin' && pathname === '/api/v1/admin/overview/domains') return state.admin.domains;
	if (method === 'GET' && profile === 'admin' && pathname === '/api/v1/admin/version') return state.admin.version;
	if (method === 'GET' && profile === 'admin' && pathname === '/api/v1/admin/notifications') return state.admin.notifications;
	if (method === 'GET' && profile === 'admin' && pathname === '/api/v1/admin/events' && params.get('limit') === '5' && [...params.keys()].every(key => key === 'limit')) return state.admin.recentEvents.slice(0, 5);
	if (method === 'GET' && profile === 'admin' && pathname === '/api/v1/admin/identity/summary') return state.admin.identitySummary;

	return symbolNoMatch;
}

export async function maybeMockJson<T>(method: string, path: string, body?: unknown, _token?: string, projectId?: string): Promise<T | typeof symbolNoMatch> {
	const profile = getActiveMockupProfile();
	if (!profile) return symbolNoMatch;
	const normalized = normalizePath(path);
	const upperMethod = method.toUpperCase();
	const fixture = jsonFixture(upperMethod, normalized, body, profile, projectId);
	if (fixture !== symbolNoMatch) return cloneMockup(fixture) as T;
	if (normalized.startsWith('/api/v1/') && upperMethod !== 'GET') mockUnsupported();
	if (normalized.startsWith('/api/v1/')) mockUnsupported();
	return symbolNoMatch;
}

export async function maybeMockBlob(method: string, path: string, _token?: string, _projectId?: string): Promise<Blob | typeof symbolNoMatch> {
	if (!getActiveMockupProfile()) return symbolNoMatch;
	const normalized = normalizePath(path);
	if (method.toUpperCase() === 'GET' && /^\/api\/v1\/k3s\/clusters\/[^/]+\/kubeconfig(?:\?grade=(?:user|editor|admin))?$/.test(normalized)) {
		const content = 'apiVersion: v1\nkind: Config\nclusters:\n- name: afterglow-mockup\ncontexts:\n- name: afterglow-mockup\ncurrent-context: afterglow-mockup\n';
		const blob = new Blob([content], { type: 'application/x-yaml' }) as Blob & { text?: () => Promise<string> };
		blob.text ??= async () => content;
		return blob;
	}
	if (method.toUpperCase() === 'GET' && /^\/api\/v1\/k3s\/clusters\/[^/]+\/ca-certificate$/.test(normalized)) {
		const content = '-----BEGIN CERTIFICATE-----\nMIIBmockupCA\n-----END CERTIFICATE-----\n';
		const blob = new Blob([content], { type: 'application/x-pem-file' }) as Blob & { text?: () => Promise<string> };
		blob.text ??= async () => content;
		return blob;
	}
	if (normalized.startsWith('/api/v1/')) mockUnsupported();
	return symbolNoMatch;
}

export async function maybeMockHead(path: string, _token?: string, _projectId?: string): Promise<Response | typeof symbolNoMatch> {
	if (!getActiveMockupProfile()) return symbolNoMatch;
	const normalized = normalizePath(path);
	if (/^\/api\/v1\/k3s\/clusters\/[^/]+\/kubeconfig(?:\?grade=(?:user|editor|admin))?$/.test(normalized)) return new Response(null, { status: 204 });
	if (normalized.startsWith('/api/v1/')) mockUnsupported();
	return symbolNoMatch;
}

async function* progress<T>(messages: T[]): AsyncGenerator<T> {
	for (const message of messages) {
		yield message;
	}
}

export interface MockInstanceProgressMessage {
	step: string;
	progress: number;
	message: string;
	instance_id?: string;
	error?: string;
}

export function maybeMockInstanceCreateStream(path: string, body: unknown): AsyncGenerator<MockInstanceProgressMessage> | null {
	if (!getActiveMockupProfile()) return null;
	const normalized = normalizePath(path);
	if (normalized !== '/api/v1/instances/async' && normalized !== '/api/v1/admin/instances/async') return null;
	const state = getMockupState();
	const payload = body as { name?: string | null; flavor_id?: string; image_id?: string; network_id?: string; key_name?: string | null } | null;
	const id = nextMockId(state.instances.map((item) => item.id), 'mock-instance');
	const flavorName = payload?.flavor_id === 'mock-flavor-gpu' ? 'gpu.8c_64g_a10' : 'cpu.4c_8g';
	const octet = 100 + state.instances.length;
	state.instances.unshift({
		id,
		// Tutorial-created instances carry a unique tut- name and the selected project's ownership.
		name: payload?.name || `tut-${id}`,
		status: 'ACTIVE',
		project_id: state.selectedProjectId,
		image_name: payload?.image_id === 'fixture-image-rocky' ? 'Rocky Linux 9' : 'Ubuntu 24.04 LTS',
		flavor_name: flavorName,
		ip_addresses: [{ addr: `192.0.2.${octet}`, type: 'fixed', network_name: 'sample-private' }],
		created_at: '2026-07-09T00:30:00Z',
		union_libraries: [],
		union_strategy: null,
		metadata: { role: 'sample' },
		image_id: payload?.image_id ?? 'fixture-image-ubuntu',
		flavor_id: payload?.flavor_id ?? 'mock-flavor-cpu4',
		key_name: payload?.key_name ?? 'demo-keypair',
		host: 'sample-hypervisor-a',
	});
	return progress([
		{ step: 'boot_volume_creating', progress: 20, message: '부트 볼륨 생성 완료', instance_id: id },
		{ step: 'server_creating', progress: 60, message: 'Nova 인스턴스 생성 완료', instance_id: id },
		{ step: 'completed', progress: 100, message: '배포 완료', instance_id: id },
	]);
}

export function maybeMockK3sStream(path: string, body: unknown, token?: string, projectId?: string): AsyncGenerator<K3sSseProgressMessage> | null {
	if (!getActiveMockupProfile()) return null;
	const normalized = normalizePath(path);
	const state = getMockupState();
	if (normalized === '/api/v1/k3s/clusters/async') {
		const payload = body as { name?: string; agent_count?: number; network_id?: string; key_name?: string; master_count?: number } | null;
		const id = `mock-k3s-${state.k3sClusters.length + 1}`;
		state.k3sClusters.push({ id, name: payload?.name || 'tutorial-cluster', status: 'ACTIVE', status_reason: null, server_vm_id: 'mock-instance-1', agent_vm_ids: [], agent_count: payload?.agent_count ?? 1, api_address: 'https://192.0.2.90:6443', server_ip: '192.0.2.90', network_id: payload?.network_id ?? 'mock-net-private', key_name: payload?.key_name ?? 'demo-keypair', k3s_version: 'v1.30.4+k3s1', created_at: '2026-07-09T00:10:00Z', updated_at: '2026-07-09T00:10:00Z', deleted_at: null, deleted_by_user_id: null, deleted_reason: null, master_count: payload?.master_count ?? 1 });
		return progress([
			{ step: 'create_vm', progress: 25, message: 'VM 생성 완료', cluster_id: id },
			{ step: 'install_k3s', progress: 70, message: 'k3s 설치 완료', cluster_id: id },
			{ step: 'completed', progress: 100, message: '클러스터 준비 완료', cluster_id: id },
		]);
	}
	const deleteMatch = normalized.match(/^\/api\/v1\/k3s\/clusters\/([^/]+)\/delete-async$/);
	if (deleteMatch) {
		const cluster = state.k3sClusters.find((item) => item.id === deleteMatch[1]);
		if (cluster) {
			cluster.status = 'DELETED';
			cluster.deleted_at = '2026-07-09T00:20:00Z';
			cluster.deleted_reason = 'tutorial delete';
		}
		return progress([
			{ step: 'cordon', progress: 35, message: '노드 cordon 완료', cluster_id: deleteMatch[1] },
			{ step: 'delete', progress: 80, message: '리소스 정리 완료', cluster_id: deleteMatch[1] },
			{ step: 'completed', progress: 100, message: '클러스터 삭제 완료', cluster_id: deleteMatch[1] },
		]);
	}
	if (normalized.startsWith('/api/v1/')) mockUnsupported();
	return null;
}
