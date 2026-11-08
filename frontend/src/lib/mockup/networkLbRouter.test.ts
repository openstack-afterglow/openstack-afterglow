import { describe, expect, it, beforeEach } from 'vitest';
import { ApiError } from '$lib/api/errors';
import { mockNetworkLbRouter } from './networkLbRouter';
import { getMockupState, resetMockupState } from './state';

type Lb = { id: string; name: string; status: string; operating_status: string; vip_address: string | null; vip_subnet_id: string | null };
type Router = { id: string; name: string; external_gateway_network_id: string | null; connected_subnet_ids: string[] };

const lbs = () => mockNetworkLbRouter('GET', '/api/v1/loadbalancers', null) as Lb[];
const routers = () => mockNetworkLbRouter('GET', '/api/v1/routers', null) as Router[];

function rejects(status: number, fn: () => unknown): void {
	try {
		fn();
	} catch (error) {
		expect(error).toBeInstanceOf(ApiError);
		expect((error as ApiError).status).toBe(status);
		return;
	}
	throw new Error('expected ApiError');
}

describe('mockNetworkLbRouter load balancers', () => {
	beforeEach(() => resetMockupState());

	it('lists the seeded load balancer in API shape', () => {
		expect(lbs().map((lb) => [lb.id, lb.status, lb.operating_status])).toEqual([['mock-lb-1', 'ACTIVE', 'ONLINE']]);
	});

	it('creates a pending load balancer on a project subnet that the next read settles', () => {
		const created = mockNetworkLbRouter('POST', '/api/v1/loadbalancers', { name: 'qa-lb', vip_subnet_id: 'mock-subnet-private', description: '' }) as Lb;
		expect(created).toMatchObject({ id: 'mock-lb-2', name: 'qa-lb', status: 'PENDING_CREATE', vip_subnet_id: 'mock-subnet-private', vip_address: '192.0.2.81' });
		expect(mockNetworkLbRouter('GET', `/api/v1/loadbalancers/${created.id}`, null)).toMatchObject({ id: created.id, status: 'ACTIVE', operating_status: 'ONLINE' });
		expect(lbs().map((lb) => lb.name)).toEqual(['sample-web-balancer', 'qa-lb']);
		expect(getMockupState().topology.load_balancers?.some((lb) => lb.id === created.id)).toBe(true);
	});

	it('rejects missing fields and unknown or external subnets', () => {
		rejects(422, () => mockNetworkLbRouter('POST', '/api/v1/loadbalancers', { name: 'qa-lb' }));
		rejects(422, () => mockNetworkLbRouter('POST', '/api/v1/loadbalancers', { vip_subnet_id: 'mock-subnet-private' }));
		rejects(500, () => mockNetworkLbRouter('POST', '/api/v1/loadbalancers', { name: 'qa-lb', vip_subnet_id: 'missing' }));
		rejects(500, () => mockNetworkLbRouter('POST', '/api/v1/loadbalancers', { name: 'qa-lb', vip_subnet_id: 'mock-subnet-public' }));
		expect(lbs()).toHaveLength(1);
	});

	it('refuses to delete while provisioning, then deletes only the created load balancer', () => {
		const created = mockNetworkLbRouter('POST', '/api/v1/loadbalancers', { name: 'qa-lb', vip_subnet_id: 'mock-subnet-data' }) as Lb;
		rejects(500, () => mockNetworkLbRouter('DELETE', `/api/v1/loadbalancers/${created.id}`, null));
		lbs();
		mockNetworkLbRouter('DELETE', `/api/v1/loadbalancers/${created.id}`, null);
		expect(lbs().map((lb) => lb.id)).toEqual(['mock-lb-1']);
		rejects(404, () => mockNetworkLbRouter('DELETE', `/api/v1/loadbalancers/${created.id}`, null));
		rejects(404, () => mockNetworkLbRouter('GET', `/api/v1/loadbalancers/${created.id}`, null));
	});

	it('does not reuse an id after a delete', () => {
		const first = mockNetworkLbRouter('POST', '/api/v1/loadbalancers', { name: 'a', vip_subnet_id: 'mock-subnet-private' }) as Lb;
		const second = mockNetworkLbRouter('POST', '/api/v1/loadbalancers', { name: 'b', vip_subnet_id: 'mock-subnet-private' }) as Lb;
		lbs();
		mockNetworkLbRouter('DELETE', `/api/v1/loadbalancers/${first.id}`, null);
		const third = mockNetworkLbRouter('POST', '/api/v1/loadbalancers', { name: 'c', vip_subnet_id: 'mock-subnet-private' }) as Lb;
		expect(new Set([second.id, third.id]).size).toBe(2);
		expect(third.vip_address).not.toBe(second.vip_address);
	});

	it('serves seeded listeners, pools and members for the detail page', () => {
		expect(mockNetworkLbRouter('GET', '/api/v1/loadbalancers/mock-lb-1/listeners', null)).toEqual([
			{ id: 'mock-listener-1', name: 'sample-https-listener', protocol: 'HTTPS', protocol_port: 443, status: 'ACTIVE', default_pool_id: 'mock-pool-1' },
		]);
		expect(mockNetworkLbRouter('GET', '/api/v1/loadbalancers/mock-lb-1/pools', null)).toMatchObject([{ id: 'mock-pool-1', protocol: 'HTTPS' }]);
		expect(mockNetworkLbRouter('GET', '/api/v1/loadbalancers/mock-lb-1/pools/mock-pool-1/members', null)).toMatchObject([{ id: 'mock-member-1', address: '192.0.2.24' }]);
	});
});

describe('mockNetworkLbRouter routers', () => {
	beforeEach(() => resetMockupState());

	it('creates routers with and without an external gateway and lists them from state', () => {
		const plain = mockNetworkLbRouter('POST', '/api/v1/routers', { name: 'qa-router' }) as Router;
		const edge = mockNetworkLbRouter('POST', '/api/v1/routers', { name: 'qa-edge', external_network_id: 'mock-net-public' }) as Router;
		expect(plain).toMatchObject({ id: 'mock-router-3', name: 'qa-router', external_gateway_network_id: null, connected_subnet_ids: [] });
		expect(edge).toMatchObject({ id: 'mock-router-4', external_gateway_network_id: 'mock-net-public' });
		expect(routers().map((router) => router.name)).toEqual(['sample-edge-router', 'sample-data-router', 'qa-router', 'qa-edge']);
	});

	it('rejects a missing name and a non-external gateway network', () => {
		rejects(422, () => mockNetworkLbRouter('POST', '/api/v1/routers', {}));
		rejects(500, () => mockNetworkLbRouter('POST', '/api/v1/routers', { name: 'qa', external_network_id: 'mock-net-private' }));
		expect(routers()).toHaveLength(2);
	});

	it('deletes the created router, refuses a router with interfaces and never reuses ids', () => {
		const created = mockNetworkLbRouter('POST', '/api/v1/routers', { name: 'qa-router' }) as Router;
		rejects(500, () => mockNetworkLbRouter('DELETE', '/api/v1/routers/mock-router-main', null));
		mockNetworkLbRouter('DELETE', `/api/v1/routers/${created.id}`, null);
		expect(routers().map((router) => router.id)).toEqual(['mock-router-main', 'mock-router-data']);
		rejects(404, () => mockNetworkLbRouter('DELETE', `/api/v1/routers/${created.id}`, null));
		const a = mockNetworkLbRouter('POST', '/api/v1/routers', { name: 'a' }) as Router;
		const b = mockNetworkLbRouter('POST', '/api/v1/routers', { name: 'b' }) as Router;
		expect(a.id).not.toBe(b.id);
	});

	it('returns undefined for paths it does not own', () => {
		expect(mockNetworkLbRouter('GET', '/api/v1/routers/mock-router-main', null)).toBeUndefined();
		expect(mockNetworkLbRouter('DELETE', '/api/v1/routers/mock-router-main/interfaces/mock-subnet-private', null)).toBeUndefined();
		expect(mockNetworkLbRouter('POST', '/api/v1/loadbalancers/mock-lb-1/listeners', {})).toBeUndefined();
		expect(mockNetworkLbRouter('GET', '/api/v1/networks', null)).toBeUndefined();
	});
});
