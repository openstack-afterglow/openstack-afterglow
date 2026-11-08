import { beforeEach, describe, expect, it } from 'vitest';
import { ApiError } from '$lib/api/errors';
import type { PortInfo } from '$lib/types/networks';
import { mockAdminPorts } from './adminPorts';
import { getMockupState, resetMockupState } from './state';

const none = new URLSearchParams();
const admin = (method: string, path: string, body: unknown = null, params = none) => mockAdminPorts(method, path, params, body, 'admin');
const list = (params = new URLSearchParams({ limit: '100' })) => admin('GET', '/api/v1/admin/all-ports', null, params) as { items: PortInfo[]; next_marker: string | null };

describe('mockAdminPorts', () => {
	beforeEach(() => resetMockupState());

	it('lists device-owned ports from the topology and creates then deletes an unbound port', () => {
		const before = list().items;
		expect(before.length).toBeGreaterThan(0);
		expect(before.every((port) => port.device_owner)).toBe(true);
		const created = admin('POST', '/api/v1/admin/ports', { network_id: 'mock-net-private', name: 'tut-port' }) as PortInfo;
		expect(created).toMatchObject({ name: 'tut-port', device_owner: '', network_id: 'mock-net-private', project_id: getMockupState().selectedProjectId });
		expect(created.fixed_ips[0].ip_address).toMatch(/^192\.0\.2\.\d+$/);
		expect(before.flatMap((port) => port.fixed_ips.map((ip) => ip.ip_address))).not.toContain(created.fixed_ips[0].ip_address);
		expect(list().items.map((port) => port.id)).toEqual([...before.map((port) => port.id), created.id]);
		admin('DELETE', `/api/v1/admin/ports/${created.id}`);
		expect(list().items.map((port) => port.id)).toEqual(before.map((port) => port.id));
	});

	it('honours a requested fixed IP and refuses used or foreign addresses', () => {
		const created = admin('POST', '/api/v1/admin/ports', { network_id: 'mock-net-data', fixed_ip: '198.51.100.200', project_id: 'mock-project-2' }) as PortInfo;
		expect(created).toMatchObject({ fixed_ips: [{ ip_address: '198.51.100.200' }], project_id: 'mock-project-2' });
		expect(() => admin('POST', '/api/v1/admin/ports', { network_id: 'mock-net-data', fixed_ip: '198.51.100.200' })).toThrow(ApiError);
		expect(() => admin('POST', '/api/v1/admin/ports', { network_id: 'mock-net-data', fixed_ip: '192.0.2.200' })).toThrow(ApiError);
		expect(() => admin('POST', '/api/v1/admin/ports', { network_id: 'mock-net-missing' })).toThrow(ApiError);
		expect(() => admin('POST', '/api/v1/admin/ports', {})).toThrow(ApiError);
	});

	it('paginates by marker, filters by scope and keeps device-owned ports', () => {
		const first = list(new URLSearchParams({ limit: '2' }));
		expect(first.items).toHaveLength(2);
		expect(first.next_marker).toBe(first.items[1].id);
		const second = list(new URLSearchParams({ limit: '2', marker: first.next_marker! }));
		expect(second.items[0].id).not.toBe(first.items[0].id);
		expect(list(new URLSearchParams({ project_id: 'nobody' })).items).toEqual([]);
		expect(() => list(new URLSearchParams({ domain_id: 'other' }))).toThrow(ApiError);
		expect(() => admin('DELETE', '/api/v1/admin/ports/mock-port-1')).toThrow(ApiError);
		expect(mockAdminPorts('GET', '/api/v1/admin/all-ports', none, null, 'on')).toBeUndefined();
	});
});
