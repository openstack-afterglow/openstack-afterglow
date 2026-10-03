import { describe, expect, it } from 'vitest';
import { getMockupRevision, getMockupState, resetMockupState } from './state';

describe('mockup fixture privacy', () => {
	it('contains no production-looking identities or infrastructure values', () => {
		const serialized = JSON.stringify(getMockupState());
		const disclosedValues = [
			'dms-cloud',
			'DMS Lab',
			'gitlab-runner-2',
			'117.16.137.',
			'10.12.12.',
			'10.44.0.',
			'172.30.',
			'192.168.',
			'pieroot',
			'konkuk.ac.kr',
			'compute-03',
			'discord-bot',
		];

		for (const value of disclosedValues) {
			expect(serialized.toLowerCase()).not.toContain(value.toLowerCase());
		}
	});

	it('keeps private, data, and external fixture relationships internally consistent', () => {
		const state = getMockupState();
		const privateNetwork = state.topology.networks.find((network) => network.id === 'mock-net-private');
		const dataNetwork = state.topology.networks.find((network) => network.id === 'mock-net-data');
		const externalNetwork = state.topology.networks.find((network) => network.id === 'mock-net-public');

		expect(privateNetwork?.name).toBe('sample-private');
		expect(privateNetwork?.subnet_details[0]?.cidr).toBe('192.0.2.0/24');
		expect(dataNetwork?.subnet_details[0]?.cidr).toBe('198.51.100.0/24');
		expect(externalNetwork?.subnet_details[0]?.cidr).toBe('203.0.113.0/24');
		expect(state.instances.every((instance) => instance.ip_addresses.every((address) => address.type === 'floating'
		? address.addr.startsWith('203.0.113.')
		: address.addr.startsWith('192.0.2.')))).toBe(true);
		expect(state.k3sClusters.filter((cluster) => cluster.server_ip).every((cluster) => cluster.server_ip?.startsWith('192.0.2.'))).toBe(true);
		expect(state.topology.floating_ips.every((floatingIp) => floatingIp.floating_ip_address.startsWith('203.0.113.') && floatingIp.fixed_ip_address?.startsWith('192.0.2.'))).toBe(true);
		expect((state.topology.load_balancers ?? []).every((loadBalancer) => loadBalancer.vip_address?.startsWith('192.0.2.') && loadBalancer.vip_network_id === 'mock-net-private')).toBe(true);
	});

	it('seeds tutorial volumes with an attached root disk and an available volume', () => {
		const state = getMockupState();
		expect(state.volumes.some((volume) => volume.status === 'in-use' && volume.attachments.length > 0)).toBe(true);
		expect(state.volumes.some((volume) => volume.status === 'available' && volume.attachments.length === 0)).toBe(true);
	});

	it('seeds complete, deterministic administrator tour relationships', () => {
		const { admin, tutorialStatuses } = getMockupState();

		expect(admin.instances.map(({ status }) => status)).toEqual(['ACTIVE', 'SHUTOFF', 'ERROR']);
		expect(new Set(admin.instances.map(({ project_id }) => project_id)).size).toBe(3);
		expect(admin.instances.every(({ host }) => Boolean(host))).toBe(true);
		expect(admin.instanceTimeseries).toHaveLength(7);
		expect(admin.volumes.map(({ status }) => status)).toEqual(['available', 'in-use', 'error']);
		expect(Object.keys(admin.volumeDetails)).toEqual(admin.volumes.map(({ id }) => id));
		expect(admin.volumeTimeseries).toHaveLength(7);

		expect(admin.library.profiles[0]).toMatchObject({ is_published: true });
		expect(admin.library.builds[0]).toMatchObject({ status: 'complete' });
		expect(admin.library.imports[0]).toMatchObject({ status: 'complete' });
		expect(admin.library.consumes[0]).toMatchObject({ status: 'deleted', server_id: null });

		expect(admin.containers.map(({ status }) => status)).toEqual(['Running', 'Stopped']);
		expect(Object.keys(admin.containerDetails)).toEqual(admin.containers.map(({ uuid }) => uuid));
		expect(admin.keyManagerQuotas).toHaveLength(2);
		expect(admin.monitoringSummary.compute.instance_stats.total).toBeGreaterThan(0);
		expect(Object.keys(admin.services)).toHaveLength(9);
		expect(admin.services.compute[0]).toMatchObject({ binary: 'nova-compute', state: 'up' });
		expect(admin.services.network[0]).toMatchObject({ agent_type: 'Open vSwitch agent', alive: true });
		expect(admin.services.endpoints).toHaveLength(1);
		expect(admin.services.storage_pools).toHaveLength(1);
		expect(admin.users.filter(({ enabled }) => enabled)).toHaveLength(2);
		expect(admin.users.filter(({ enabled }) => !enabled)).toHaveLength(1);
		expect(admin.userActivity.length).toBeGreaterThanOrEqual(2);
		expect(tutorialStatuses).toEqual({});
	});
});

describe('mockup revision', () => {
	it('increments every time fixture state resets', () => {
		const before = getMockupRevision();
		resetMockupState();
		expect(getMockupRevision()).toBe(before + 1);
		resetMockupState();
		expect(getMockupRevision()).toBe(before + 2);
	});
});
