import { beforeEach, describe, expect, it } from 'vitest';
import { ApiError } from '$lib/api/errors';
import type { Project } from '$lib/types/project';
import type { Flavor } from '$lib/types/flavor';
import type { AdminNetwork, AdminRouter } from '$lib/types/networks';
import { mockAdminResources } from './adminResources';
import { getMockupState, resetMockupState } from './state';

const domain = new URLSearchParams({ domain_id: 'mock-domain' });
const none = new URLSearchParams();
const admin = (method: string, path: string, body: unknown = null, params = none) => mockAdminResources(method, path, params, body, 'admin');

describe('mockAdminResources projects', () => {
	beforeEach(() => resetMockupState());

	function projects(): Project[] {
		// The mock returns the backend paged shape for this route.
		const page = admin('GET', '/api/v1/admin/projects', null, new URLSearchParams({ domain_id: 'mock-domain', limit: '20' })) as { items: Project[] };
		return page.items;
	}

	it('creates a project in the selected domain and deletes it after an empty check', () => {
		const created = admin('POST', '/api/v1/admin/projects', { name: 'tut-project', description: null, enabled: true, domain_id: 'mock-domain' }, domain) as Project;
		expect(created).toMatchObject({ name: 'tut-project', enabled: true, domain_id: 'mock-domain' });
		expect(projects().some((item) => item.id === created.id)).toBe(true);
		const check = admin('GET', `/api/v1/admin/projects/${created.id}/deletion-check`, null, domain) as { can_delete: boolean; project_id: string };
		expect(check).toMatchObject({ can_delete: true, project_id: created.id });
		admin('DELETE', `/api/v1/admin/projects/${created.id}`, null, domain);
		expect(projects().some((item) => item.id === created.id)).toBe(false);
	});

	it('refuses seeded projects that still own resources and keeps them', () => {
		const selected = getMockupState().selectedProjectId;
		const check = admin('GET', `/api/v1/admin/projects/${selected}/deletion-check`, null, domain) as { can_delete: boolean };
		expect(check.can_delete).toBe(false);
		expect(() => admin('DELETE', `/api/v1/admin/projects/${selected}`, null, domain)).toThrow(ApiError);
		expect(projects().some((item) => item.id === selected)).toBe(true);
	});

	it('requires the selected domain, a unique non-reserved name and ignores the names endpoint', () => {
		expect(() => admin('GET', '/api/v1/admin/projects')).toThrow(ApiError);
		expect(() => admin('GET', '/api/v1/admin/projects', null, new URLSearchParams({ domain_id: 'other' }))).toThrow(ApiError);
		for (const name of ['', 'Default', 'sample-project-alpha']) {
			expect(() => admin('POST', '/api/v1/admin/projects', { name, domain_id: 'mock-domain' }, domain)).toThrow(ApiError);
		}
		expect(admin('GET', '/api/v1/admin/projects/names')).toBeUndefined();
		expect(mockAdminResources('GET', '/api/v1/admin/projects', domain, null, 'on')).toBeUndefined();
	});
});

describe('mockAdminResources flavors', () => {
	beforeEach(() => resetMockupState());

	function flavors(): Flavor[] {
		const page = admin('GET', '/api/v1/admin/flavors') as { items: Flavor[] };
		return page.items;
	}

	it('creates and deletes an unmanaged flavor', () => {
		const created = admin('POST', '/api/v1/admin/flavors', { name: 'tut-flavor', vcpus: 1, ram: 512, disk: 0, is_public: true }) as Flavor;
		expect(created).toMatchObject({ name: 'tut-flavor', vcpus: 1, ram: 512, disk: 0, is_public: true, extra_specs: {} });
		expect(flavors().map((item) => item.id)).toContain(created.id);
		admin('DELETE', `/api/v1/admin/flavors/${created.id}`);
		expect(flavors().map((item) => item.id)).not.toContain(created.id);
	});

	it('rejects duplicate names, invalid sizes and managed flavor deletion', () => {
		for (const payload of [
			{ name: 'sample.2c_4g', vcpus: 1, ram: 512, disk: 0 },
			{ name: 'tut-flavor', vcpus: 0, ram: 512, disk: 0 },
			{ name: 'tut-flavor', vcpus: 1, ram: 512, disk: -1 },
			{ name: '', vcpus: 1, ram: 512, disk: 0 },
		]) expect(() => admin('POST', '/api/v1/admin/flavors', payload)).toThrow(ApiError);
		expect(() => admin('DELETE', '/api/v1/admin/flavors/mock-managed-cpu-4')).toThrow(ApiError);
		expect(flavors()).toHaveLength(2);
	});
});

describe('mockAdminResources routers', () => {
	beforeEach(() => resetMockupState());

	function routers(): AdminRouter[] {
		return admin('GET', '/api/v1/admin/all-routers') as AdminRouter[];
	}

	it('lists external networks and creates a router with a gateway, then deletes it', () => {
		const external = (admin('GET', '/api/v1/admin/all-networks') as AdminNetwork[]).filter((net) => net.is_external);
		expect(external.map((net) => net.id)).toEqual(['mock-net-public']);
		const created = admin('POST', '/api/v1/admin/routers', { name: 'tut-router', external_network_id: 'mock-net-public' }) as AdminRouter;
		expect(created).toMatchObject({ name: 'tut-router', status: 'ACTIVE', external_gateway_network_id: 'mock-net-public' });
		expect(routers().map((item) => item.id)).toContain(created.id);
		expect(getMockupState().topology.routers.some((item) => item.id === created.id)).toBe(true);
		admin('DELETE', `/api/v1/admin/routers/${created.id}`);
		expect(routers().map((item) => item.id)).not.toContain(created.id);
	});

	it('refuses routers with interfaces, unknown gateways and foreign domain scopes', () => {
		expect(() => admin('DELETE', '/api/v1/admin/routers/mock-router-main')).toThrow(ApiError);
		expect(() => admin('POST', '/api/v1/admin/routers', { name: 'tut-router', external_network_id: 'mock-net-private' })).toThrow(ApiError);
		expect(() => admin('GET', '/api/v1/admin/all-routers', null, new URLSearchParams({ domain_id: 'other' }))).toThrow(ApiError);
		expect(routers()).toHaveLength(2);
	});
});

describe('mockAdminResources networks', () => {
	beforeEach(() => resetMockupState());

	function networks(): AdminNetwork[] {
		return admin('GET', '/api/v1/admin/all-networks') as AdminNetwork[];
	}

	it('creates a network with an automatic subnet and deletes it', () => {
		const created = admin('POST', '/api/v1/admin/networks', { name: 'tut-network', cidr: '10.20.0.0/24', is_external: false, is_shared: false, enable_dhcp: true }) as AdminNetwork;
		expect(created).toMatchObject({ name: 'tut-network', status: 'ACTIVE', is_external: false, is_shared: false, subnets: [`${created.id}-subnet`] });
		expect(networks().map((item) => item.id)).toContain(created.id);
		admin('DELETE', `/api/v1/admin/networks/${created.id}`);
		expect(networks().map((item) => item.id)).not.toContain(created.id);
	});

	it('rejects a blank name or invalid CIDR and refuses networks still in use', () => {
		expect(() => admin('POST', '/api/v1/admin/networks', { name: '', cidr: null })).toThrow(ApiError);
		expect(() => admin('POST', '/api/v1/admin/networks', { name: 'tut-network', cidr: '10.20.0.0' })).toThrow(ApiError);
		expect(() => admin('DELETE', '/api/v1/admin/networks/mock-net-private')).toThrow(ApiError);
		expect(() => admin('DELETE', '/api/v1/admin/networks/mock-net-public')).toThrow(ApiError);
		expect(networks()).toHaveLength(3);
	});
});
