import { get } from 'svelte/store';
import { ApiError } from '$lib/api/errors';
import { getMockupProfile, isMockAuthActive } from '$lib/stores/auth';
import { siteConfig } from '$lib/config/site';
import { buildMockAuth } from '$lib/mockup/auth';
import { MOCK_MCP_CONSENT_TICKET, MOCKUP_QUERY_KEY, MOCKUP_SESSION_KEY, MOCKUP_SERVICE_OVERRIDES, isMockupProfileId } from '$lib/mockup/contracts';
import type { MockupProfileId } from '$lib/mockup/contracts';
import { cloneMockup, getMockupState } from '$lib/mockup/state';
import type { K3sSseProgressMessage } from '$lib/api/k3sSseStream';
import { isTourId } from '$lib/tutorial/tours';

export const symbolNoMatch = Symbol('mockup-no-match');
const UNSUPPORTED = '튜토리얼 모드에서는 이 작업을 아직 지원하지 않습니다.';
const MOCK_EXPIRES_AT_ISO = '2026-12-31T23:59:59Z';
const NOW_ISO = '2026-07-09T00:00:00Z';
const MOCK_IMAGES = [
	{
		id: 'fixture-image-ubuntu',
		name: 'Ubuntu 24.04 LTS',
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

export function mockUnsupported(_message = UNSUPPORTED): never {
	throw new ApiError(409, UNSUPPORTED);
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
	};
}

function instanceMetrics(ids: string[]): Record<string, { cpu_avg: number | null; mem_avg: number | null; underutilized: boolean }> {
	const result: Record<string, { cpu_avg: number | null; mem_avg: number | null; underutilized: boolean }> = {};
	for (const [index, id] of ids.entries()) {
		result[id] = { cpu_avg: 8 + index * 7, mem_avg: 22 + index * 5, underutilized: index % 3 === 0 };
	}
	return result;
}

function metricSeries(scale: number): { ts: number; value: number }[] {
	return [0, 1, 2, 3, 4, 5].map((step) => ({ ts: 1783551600 + step * 600, value: scale + step * 3 }));
}

function dashboardTrend(range: string | null, includeNetwork: boolean): Record<string, unknown> {
	return {
		vcpu: { data: [24, 27, 31, 29, 33, 36], points: 6, available: true },
		memory: { data: [38, 41, 44, 43, 45, 47], points: 6, available: true },
		storage: { data: [16, 18, 19, 20, 21, 23], points: 6, available: true },
		network: includeNetwork
			? { data: [120, 150, 170, 140, 190, 210], points: 6, available: true, unit: 'KiB/s' }
			: { data: [], points: 0, available: false, unit: 'KiB/s' },
		prometheus_available: true,
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

function jsonFixture(method: string, normalized: string, body: unknown, profile: MockupProfileId): unknown | typeof symbolNoMatch {
	const state = getMockupState();
	const [pathname, query = ''] = normalized.split('?');
	const params = new URLSearchParams(query);

	if (method === 'GET' && pathname === '/api/v1/site-config') {
		return { ...get(siteConfig), services: { ...get(siteConfig).services, ...MOCKUP_SERVICE_OVERRIDES } };
	}
	if (method === 'GET' && pathname === '/api/v1/auth/me') {
		const auth = buildMockAuth(profile, profile === 'admin' ? '/admin' : '/dashboard');
		return { user_id: auth.userId, username: auth.username, project_id: auth.projectId, project_name: auth.projectName, roles: auth.roles, is_system_admin: auth.isSystemAdmin, auth_method: 'tutorial' };
	}
	if (method === 'GET' && (pathname === '/api/v1/auth/projects/recent' || pathname === '/api/v1/auth/projects')) return state.projects;
	if (method === 'GET' && pathname === '/api/v1/profile') return { id: 'mock-user-1', name: 'Demo User', email: 'demo@example.com', default_project_id: null };
	if (method === 'GET' && pathname === '/api/v1/tutorials/status') {
		return { statuses: state.tutorialStatuses };
	}
	const tutorialStatusMatch = pathname.match(/^\/api\/v1\/tutorials\/([^/]+)\/status$/);
	if (method === 'POST' && tutorialStatusMatch) {
		const tourId = tutorialStatusMatch[1];
		const status = (body as { status?: unknown } | null)?.status;
		if (!isTourId(tourId) || (status !== 'completed' && status !== 'dismissed')) mockUnsupported();
		state.tutorialStatuses[tourId] = status;
		return { tour_id: tourId, status };
	}

	if (method === 'GET' && pathname === '/api/v1/auth/mcp-tokens') return state.mcpAccess.personalTokens;
	if (method === 'GET' && pathname === '/api/v1/auth/mcp-oauth/grants') return state.mcpAccess.oauthGrants;
	if (method === 'POST' && pathname === '/api/v1/auth/mcp-tokens') {
		const payload = body as { name?: unknown; access_level?: unknown; expires_at?: unknown } | null;
		const name = typeof payload?.name === 'string' ? payload.name.trim() : '';
		const accessLevel = payload?.access_level;
		if (!name || (accessLevel !== 'read' && accessLevel !== 'manage')) mockUnsupported();
		const id = nextMockId(state.mcpAccess.personalTokens.map((record) => record.id), 'mock-mcp-token');
		const record = {
			id,
			grant_id: `mock-mcp-grant-${id}`,
			name,
			source: 'personal_token' as const,
			access_level: accessLevel,
			status: 'active' as const,
			visible_prefix: `mcp_mock_${id.slice(-4)}_`,
			issued_at: NOW_ISO,
			expires_at: typeof payload?.expires_at === 'string' && !Number.isNaN(Date.parse(payload.expires_at)) ? payload.expires_at : MOCK_EXPIRES_AT_ISO,
			last_used_at: null,
			revoked_at: null,
			is_lumen_default: false,
		} satisfies (typeof state.mcpAccess.personalTokens)[number];
		state.mcpAccess.personalTokens.unshift(record);
		return { ...record, token: `sk-afgl-mock-${id}` };
	}
	if (method === 'DELETE' && pathname === '/api/v1/auth/mcp-tokens/lumen-default') {
		for (const record of state.mcpAccess.personalTokens) record.is_lumen_default = false;
		return { lumen_selection_generation: 2 };
	}
	const lumenDefaultTokenId = pathname.match(/^\/api\/v1\/auth\/mcp-tokens\/([^/]+)\/lumen-default$/)?.[1];
	if (method === 'PUT' && lumenDefaultTokenId) {
		const selected = state.mcpAccess.personalTokens.find((record) => record.id === lumenDefaultTokenId && record.status === 'active');
		if (!selected) mockUnsupported();
		for (const record of state.mcpAccess.personalTokens) record.is_lumen_default = record.id === lumenDefaultTokenId;
		return { lumen_selection_generation: 2 };
	}
	const personalTokenId = pathname.match(/^\/api\/v1\/auth\/mcp-tokens\/([^/]+)$/)?.[1];
	if (method === 'DELETE' && personalTokenId) {
		const record = state.mcpAccess.personalTokens.find((item) => item.id === personalTokenId);
		if (!record) mockUnsupported();
		record.status = 'revoked';
		record.revoked_at = NOW_ISO;
		record.is_lumen_default = false;
		return ok204();
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
		};
	}
	const consentDecision = pathname.match(/^\/api\/v1\/auth\/mcp-oauth\/consents\/([^/]+)\/(approve|deny)$/);
	if (method === 'POST' && consentDecision) {
		if (consentDecision[1] !== MOCK_MCP_CONSENT_TICKET) mockUnsupported();
		return { redirect_uri: `/dashboard/account?${MOCKUP_QUERY_KEY}=on` };
	}


	if (profile === 'admin' && method !== 'GET') mockUnsupported();

	if (profile === 'admin' && pathname === '/api/v1/admin/projects/names') {
		return state.projects.map(({ id, name }) => ({ id, name }));
	}
	if (profile === 'admin' && pathname === '/api/v1/admin/all-instances') {
		let items = [...state.admin.instances];
		const name = params.get('name')?.toLowerCase();
		const status = params.get('status')?.toLowerCase();
		const project = params.get('project_id');
		const host = params.get('host')?.toLowerCase();
		if (name) items = items.filter((item) => item.name.toLowerCase().includes(name));
		if (status) items = items.filter((item) => item.status.toLowerCase() === status);
		if (project) items = items.filter((item) => item.project_id === project);
		if (host) items = items.filter((item) => item.host?.toLowerCase() === host);
		return { items, next_marker: null, count: items.length };
	}
	if (profile === 'admin' && pathname === '/api/v1/admin/instances/health') return state.admin.instanceHealth;
	if (profile === 'admin' && pathname === '/api/v1/admin/timeseries/instances') return state.admin.instanceTimeseries;
	if (profile === 'admin' && pathname === '/api/v1/admin/hypervisors') return state.admin.hypervisors;

	if (profile === 'admin' && pathname === '/api/v1/admin/all-volumes') {
		let items = [...state.admin.volumes];
		const name = params.get('name')?.toLowerCase();
		const status = params.get('status')?.toLowerCase();
		const project = params.get('project_id');
		if (name) items = items.filter((item) => item.name.toLowerCase().includes(name));
		if (status) items = items.filter((item) => item.status.toLowerCase() === status);
		if (project) items = items.filter((item) => item.project_id === project);
		return { items, next_marker: null, count: items.length };
	}
	if (profile === 'admin' && pathname === '/api/v1/admin/volumes/status-summary') return state.admin.volumeStatusSummary;
	if (profile === 'admin' && pathname === '/api/v1/admin/timeseries/volumes') return state.admin.volumeTimeseries;
	const adminVolumeId = pathname.match(/^\/api\/v1\/admin\/volumes\/([^/]+)$/)?.[1];
	if (profile === 'admin' && adminVolumeId) return state.admin.volumeDetails[adminVolumeId] ?? mockUnsupported();

	if (profile === 'admin' && pathname === '/api/v1/admin/libraries/base-images') return state.admin.library.baseImages;
	if (profile === 'admin' && pathname === '/api/v1/admin/libraries/artifacts') return state.admin.library.artifacts;
	if (profile === 'admin' && pathname === '/api/v1/admin/libraries/profiles') return state.admin.library.profiles;
	if (profile === 'admin' && pathname === '/api/v1/admin/libraries/builds') return state.admin.library.builds;
	if (profile === 'admin' && pathname === '/api/v1/admin/libraries/imports') return state.admin.library.imports;
	if (profile === 'admin' && pathname === '/api/v1/admin/libraries/consumes') return state.admin.library.consumes;

	if (profile === 'admin' && pathname === '/api/v1/admin/topology') return state.topology;
	if (profile === 'admin' && pathname === '/api/v1/admin/all-containers') return state.admin.containers;
	const adminContainerLogsId = pathname.match(/^\/api\/v1\/admin\/containers\/([^/]+)\/logs$/)?.[1];
	if (profile === 'admin' && adminContainerLogsId) {
		return { logs: state.admin.containerLogs[adminContainerLogsId] ?? '' };
	}
	const adminContainerId = pathname.match(/^\/api\/v1\/admin\/containers\/([^/]+)$/)?.[1];
	if (profile === 'admin' && adminContainerId) return state.admin.containerDetails[adminContainerId] ?? mockUnsupported();
	if (profile === 'admin' && pathname === '/api/v1/admin/key-manager/project-quotas') return state.admin.keyManagerQuotas;
	if (profile === 'admin' && pathname === '/api/v1/admin/monitoring/summary') return state.admin.monitoringSummary;
	if (profile === 'admin' && pathname === '/api/v1/admin/services') {
		const category = params.get('category');
		if (!category || !(category in state.admin.services)) mockUnsupported();
		return { [category]: state.admin.services[category as keyof typeof state.admin.services] };
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
		return { items: page, next_marker: items.length > limit ? page.at(-1)?.id ?? null : null, count: state.admin.users.length };
	}
	if (method === 'POST' && pathname === '/api/v1/auth/token/project') return projectTokenResponse(String((body as { project_id?: string } | null)?.project_id ?? state.projects[0].id), profile);
	if (method === 'POST' && pathname === '/api/v1/networks/ensure-default') return ok204();

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
	if (method === 'GET' && pathname === '/api/v1/instances/metrics-summary-batch') return { prometheus_available: true, instances: instanceMetrics(state.instances.map((item) => item.id)) };
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
	if (method === 'GET' && metricInstanceId) return { prometheus_available: true, stats: { cpu: { min: 4, avg: 18, max: 44 }, memory: { min: 18, avg: 36, max: 61 } }, recommendation: null };
	if (method === 'GET' && /^\/api\/v1\/instances\/[^/]+\/metrics-batch$/.test(pathname)) {
		const keys = (params.get('metrics') ?? 'cpu,memory').split(',');
		return { metrics: Object.fromEntries(keys.map((key, index) => [key, { series: metricSeries(10 + index * 5), error: null }])) };
	}
	if (method === 'GET' && /^\/api\/v1\/instances\/[^/]+\/console$/.test(pathname)) return { url: '/mockup-console.html' };
	if (method === 'GET' && /^\/api\/v1\/instances\/[^/]+\/log$/.test(pathname)) return { output: 'cloud-init finished\nk3s service active\nmock workload healthy\n' };
	if (method === 'GET' && /^\/api\/v1\/instances\/[^/]+\/interfaces$/.test(pathname)) return [{ id: 'mock-port-1', name: 'primary', status: 'ACTIVE', device_owner: 'compute:nova', fixed_ips: [{ ip_address: '192.0.2.24' }], project_id: state.selectedProjectId, security_group_ids: ['mock-sg-default'], mac_address: 'fa:16:3e:00:00:01', network_id: 'mock-net-private' }];
	if (method === 'GET' && /^\/api\/v1\/instances\/[^/]+\/volumes$/.test(pathname)) return [{ id: 'mock-attachment-1', volume_id: 'mock-volume-1', server_id: 'mock-instance-1', device: '/dev/vda', name: 'root-disk', size: 80, status: 'in-use' }];
	if (method === 'GET' && /^\/api\/v1\/instances\/[^/]+\/security-groups$/.test(pathname)) return { ports: [], security_groups: [{ id: 'mock-sg-default', name: 'default', description: 'Mock default SG', rules: [{ id: 'mock-rule-ssh', direction: 'ingress', protocol: 'tcp', port_range_min: 22, port_range_max: 22, remote_ip_prefix: '0.0.0.0/0', ethertype: 'IPv4' }] }] };
	if (method === 'GET' && /^\/api\/v1\/instances\/[^/]+\/owner$/.test(pathname)) return { display: 'Sample Cloud Demo / demo-user' };
	if (method === 'GET' && /^\/api\/v1\/instances\/[^/]+\/storage-attachments$/.test(pathname)) return [{ file_storage_id: 'mock-share-1', name: 'demo-dataset', share_proto: 'CEPHFS', status: 'available' }];

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
	if (method === 'GET' && pathname === '/api/v1/volume-snapshots') return [];
	if (method === 'POST' && pathname === '/api/v1/volumes/backups/auto-backup/configs') return [];

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
	if (method === 'GET' && pathname === '/api/v1/security-groups') return [{ id: 'mock-sg-default', name: 'default', description: 'Mock default SG', rules: [] }];
	if (method === 'GET' && pathname === '/api/v1/networks/default') return { network_id: 'mock-net-private' };
	if (method === 'GET' && pathname === '/api/v1/dashboard/gpu-available') return { gpu_types: [] };

	// 튜토리얼에서 실제 콘솔과 동일한 내비게이션을 제공하기 위한 페이지 픽스처들 (빈/샘플 상태)
	if (method === 'GET' && pathname === '/api/v1/loadbalancers') return state.topology.load_balancers;
	if (method === 'GET' && pathname === '/api/v1/clusters') return [];
	if (method === 'GET' && pathname === '/api/v1/clusters/templates') return [];
	if (method === 'GET' && pathname === '/api/v1/containers') return [];
	if (method === 'GET' && pathname === '/api/v1/database-instances') return [];
	if (method === 'GET' && pathname === '/api/v1/database-instances/backups') return [];
	if (method === 'GET' && pathname === '/api/v1/database-instances/flavors') return [];
	if (method === 'GET' && pathname === '/api/v1/object-storage') return [{ name: 'sample-artifacts', count: 12, bytes: 734003200 }];
	if (method === 'GET' && pathname === '/api/v1/object-storage/account') return { container_count: 1, object_count: 12, bytes_used: 734003200 };
	if (method === 'GET' && pathname === '/api/v1/object-storage/trash/containers') return [];
	if (method === 'GET' && pathname === '/api/v1/file-storage') {
		return [{
			id: 'mock-share-1', name: 'demo-dataset', status: 'available', size: 200, share_proto: 'CEPHFS',
			export_locations: ['192.0.2.10:6789:/volumes/demo-dataset'], metadata: {}, project_id: state.selectedProjectId,
			created_at: NOW_ISO, is_public: false, library_name: null, library_version: null, built_at: null,
			progress: '100%', user_id: 'mock-user-1', user_name: 'demo-user', access_rules_status: 'active',
			host: 'sample-manila-host', availability_zone: 'nova', share_type_name: 'cephfs', share_network_id: null,
			export_location_details: [{ path: '192.0.2.10:6789:/volumes/demo-dataset', preferred: true, share_instance_id: null }],
		}];
	}
	if (method === 'GET' && pathname === '/api/v1/share-networks') return [];
	if (method === 'GET' && pathname === '/api/v1/share-snapshots') return [];
	if (method === 'GET' && pathname === '/api/v1/security-services') return [];
	if (method === 'GET' && /^\/api\/v1\/projects\/[^/]+\/members$/.test(pathname)) {
		return { items: [
			{ user_id: 'mock-user-1', username: 'demo-user', email: 'demo@example.com', is_manager: true, source: 'direct' },
			{ user_id: 'mock-user-2', username: 'sample-researcher', email: 'researcher@example.com', is_manager: false, source: 'direct' },
		] };
	}
	if (method === 'GET' && /^\/api\/v1\/projects\/[^/]+\/invitations$/.test(pathname)) return { items: [] };
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
		return {
			range: params.get('range') ?? '30d',
			start: '2026-06-09T00:00:00Z',
			end: NOW_ISO,
			stats: { instance_hours: 4320, vcpu_hours: 17280, active_instances: 6, total_instances: 8 },
			flavor_hours: [
				{ flavor: 'cpu.4c_8g', instance_count: 4, usage_hours: 2160 },
				{ flavor: 'gpu.8c_64g_a10', instance_count: 1, usage_hours: 720 },
			],
			forecast: { vcpu_pct: 31 },
		};
	}

	if (method === 'GET' && pathname === '/api/v1/networks') return state.topology.networks.map((net) => ({ id: net.id, name: net.name, status: net.status, subnets: net.subnet_details.map((subnet) => subnet.id), is_external: net.is_external, is_shared: net.is_shared }));
	if (method === 'GET' && pathname === '/api/v1/networks/floating-ips') return state.topology.floating_ips;
	if (method === 'GET' && pathname === '/api/v1/networks/topology') return state.topology;
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
	const networkId = pathname.match(/^\/api\/v1\/networks\/([^/]+)$/)?.[1];
	if (method === 'GET' && networkId) return networkDetail(networkId) ?? mockUnsupported();
	if (method === 'GET' && pathname === '/api/v1/routers') return state.topology.routers.map((router) => ({ id: router.id, name: router.name, status: router.status, external_gateway_network_id: router.external_gateway_network_id, connected_subnet_ids: router.connected_subnet_ids }));
	const routerId = pathname.match(/^\/api\/v1\/routers\/([^/]+)$/)?.[1];
	if (method === 'GET' && routerId) return routerDetail(routerId) ?? mockUnsupported();

	if (method === 'GET' && pathname === '/api/v1/k3s/clusters') {
		const includeDeleted = params.get('include_deleted') === 'true';
		return state.k3sClusters.filter((cluster) => includeDeleted || !cluster.deleted_at);
	}
	const k3sClusterId = pathname.match(/^\/api\/v1\/k3s\/clusters\/([^/]+)$/)?.[1];
	if (method === 'GET' && k3sClusterId) return state.k3sClusters.find((cluster) => cluster.id === k3sClusterId) ?? mockUnsupported();
	if (method === 'GET' && pathname === '/api/v1/admin/k3s-clusters') return state.k3sClusters;
	const adminK3sClusterId = pathname.match(/^\/api\/v1\/admin\/k3s-clusters\/([^/]+)$/)?.[1];
	if (method === 'GET' && adminK3sClusterId) return state.k3sClusters.find((cluster) => cluster.id === adminK3sClusterId) ?? mockUnsupported();
	if (method === 'GET' && pathname === '/api/v1/k3s/cluster-templates') return [{ id: 'mock-template-1', name: 'GPU training baseline', description: '1 master + 2 workers', default_node_count: 2, default_agent_flavor_id: 'mock-flavor-cpu4', os_type: 'ubuntu' }];
	if (method === 'GET' && pathname === '/api/v1/flavors') return [{ id: 'mock-flavor-cpu4', name: 'cpu.4c_8g', vcpus: 4, ram: 8192, disk: 80 }, { id: 'mock-flavor-gpu', name: 'gpu.8c_64g_a10', vcpus: 8, ram: 65536, disk: 160, gpu_count: 1 }];
	if (method === 'GET' && pathname === '/api/v1/keypairs') return [{ name: 'demo-keypair' }];
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

	if (method === 'GET' && profile === 'admin' && pathname === '/api/v1/admin/overview') return state.admin.overview;
	if (method === 'GET' && profile === 'admin' && pathname === '/api/v1/admin/overview/projects') return state.admin.projects;
	if (method === 'GET' && profile === 'admin' && pathname === '/api/v1/admin/version') return state.admin.version;
	if (method === 'GET' && profile === 'admin' && pathname === '/api/v1/admin/notifications') return state.admin.notifications;
	if (method === 'GET' && profile === 'admin' && pathname === '/api/v1/admin/identity/summary') return state.admin.identitySummary;

	return symbolNoMatch;
}

export async function maybeMockJson<T>(method: string, path: string, body?: unknown, _token?: string, _projectId?: string): Promise<T | typeof symbolNoMatch> {
	const profile = getActiveMockupProfile();
	if (!profile) return symbolNoMatch;
	const normalized = normalizePath(path);
	const upperMethod = method.toUpperCase();
	const fixture = jsonFixture(upperMethod, normalized, body, profile);
	if (fixture !== symbolNoMatch) return cloneMockup(fixture) as T;
	if (normalized.startsWith('/api/v1/') && upperMethod !== 'GET') mockUnsupported();
	if (normalized.startsWith('/api/v1/')) mockUnsupported();
	return symbolNoMatch;
}

export async function maybeMockBlob(method: string, path: string, _token?: string, _projectId?: string): Promise<Blob | typeof symbolNoMatch> {
	if (!getActiveMockupProfile()) return symbolNoMatch;
	const normalized = normalizePath(path);
	if (method.toUpperCase() === 'GET' && /^\/api\/v1\/k3s\/clusters\/[^/]+\/kubeconfig$/.test(normalized)) {
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
	if (/^\/api\/v1\/k3s\/clusters\/[^/]+\/kubeconfig$/.test(normalized)) return new Response(null, { status: 204 });
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
		name: payload?.name || `tutorial-vm-${state.instances.length + 1}`,
		status: 'ACTIVE',
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
