import { beforeEach, describe, expect, it } from 'vitest';
import { ApiError } from '$lib/api/errors';
import type { FloatingIp } from '$lib/types/networks';
import { mockAdminFloatingIps } from './adminFloatingIps';
import { getMockupState, resetMockupState } from './state';

const none = new URLSearchParams();
const admin = (method: string, path: string, body: unknown = null, params = none) => mockAdminFloatingIps(method, path, params, body, 'admin');
const list = (params = none) => admin('GET', '/api/v1/admin/all-floating-ips', null, params) as FloatingIp[];

describe('mockAdminFloatingIps', () => {
	beforeEach(() => resetMockupState());

	it('allocates an unassigned address on an external network and deletes only it', () => {
		const before = list().map((fip) => fip.id);
		const created = admin('POST', '/api/v1/admin/floating-ips', { floating_network_id: 'mock-net-public' }) as FloatingIp;
		expect(created).toMatchObject({ port_id: null, fixed_ip_address: null, project_id: getMockupState().selectedProjectId });
		expect(created.floating_ip_address).toMatch(/^203\.0\.113\.\d+$/);
		expect(before).not.toContain(created.id);
		expect(list().map((fip) => fip.id)).toEqual([...before, created.id]);
		admin('DELETE', `/api/v1/admin/floating-ips/${created.id}`);
		expect(list().map((fip) => fip.id)).toEqual(before);
	});

	it('refuses non-external networks and filters by scope', () => {
		expect(() => admin('POST', '/api/v1/admin/floating-ips', { floating_network_id: 'mock-net-private' })).toThrow(ApiError);
		expect(() => admin('POST', '/api/v1/admin/floating-ips', {})).toThrow(ApiError);
		expect(list(new URLSearchParams({ project_id: 'nobody' }))).toEqual([]);
		expect(() => list(new URLSearchParams({ domain_id: 'other' }))).toThrow(ApiError);
	});

	it('ignores other profiles and paths', () => {
		expect(mockAdminFloatingIps('GET', '/api/v1/admin/all-floating-ips', none, null, 'on')).toBeUndefined();
		expect(admin('GET', '/api/v1/admin/all-routers')).toBeUndefined();
	});
});
