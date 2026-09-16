import { describe, expect, it } from 'vitest';
import { buildGraph, switchId } from '../topologyGraph';
import { canLink, linkRequest } from '../link-types';
import { makeFixture, P } from './fixtures';

function graph() {
	return buildGraph(makeFixture(), { projectId: P, showAll: false });
}

describe('topology canvas links', () => {
	it('creates an instance interface request only for a network not already attached', () => {
		const value = graph();
		expect(canLink(value, 'vm-web-01', switchId('net-app'), P)).toBe(true);
		expect(linkRequest(value, 'vm-web-01', switchId('net-app'), P)).toMatchObject({
			url: '/api/v1/instances/vm-web-01/interfaces',
			body: { net_id: 'net-app' },
		});
		expect(canLink(value, 'vm-web-01', switchId('net-web'), P)).toBe(false);
		expect(canLink(value, 'vm-web-01', switchId('net-pub'), P)).toBe(false);
	});

	it('uses the matching router endpoint and rejects duplicate or self links', () => {
		const value = graph();
		expect(linkRequest(value, 'rtr-transit', switchId('net-pub'), P)).toMatchObject({
			url: '/api/v1/routers/rtr-transit/gateway',
			body: { external_network_id: 'net-pub' },
		});
		expect(canLink(value, 'rtr-edge', switchId('net-app'), P)).toBe(false);
		expect(canLink(value, 'rtr-edge', 'rtr-edge', P)).toBe(false);
	});

	it('requires an existing subnet before creating a router interface request', () => {
		const data = makeFixture();
		data.networks.find((network) => network.id === 'net-lab')!.subnet_details = [];
		const value = buildGraph(data, { projectId: P, showAll: false });
		expect(linkRequest(value, 'rtr-transit', switchId('net-lab'), P)).toBeNull();
	});

	it('rejects a network outside the selected project', () => {
		const data = makeFixture();
		data.networks.find((network) => network.id === 'net-lab')!.project_id = 'other-project';
		const value = buildGraph(data, { projectId: P, showAll: false });
		expect(canLink(value, 'vm-web-01', switchId('net-lab'), P)).toBe(false);
	});
});
