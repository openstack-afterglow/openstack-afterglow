import { describe, expect, it } from 'vitest';
import { buildGraph } from '../topologyGraph';
import { attachableSubnets, canStartLink, linkTargets, resolveLink } from '../topologyLink';
import { makeFixture, mkNet, P } from './fixtures';

describe('topologyLink 연결 규칙', () => {
	it('vm-web-01 ↔ sw:net-app 는 vm-net 연결 요청을 반환한다', () => {
		const g = buildGraph(makeFixture(), { projectId: P, showAll: false });
		const req = resolveLink(g, 'vm-web-01', 'sw:net-app', P);
		expect(req).toEqual({
			kind: 'vm-net',
			instanceId: 'vm-web-01',
			instanceName: 'web-01',
			networkId: 'net-app',
			networkName: 'app-net'
		});

		// 순서 무관
		const reverseReq = resolveLink(g, 'sw:net-app', 'vm-web-01', P);
		expect(reverseReq).toEqual(req);
	});

	it('이미 해당 망에 NIC이 있는 vm-web-01 ↔ sw:net-web 는 null을 반환한다 (중복 방지)', () => {
		const g = buildGraph(makeFixture(), { projectId: P, showAll: false });
		expect(resolveLink(g, 'vm-web-01', 'sw:net-web', P)).toBeNull();
	});

	it('외부 게이트웨이가 이미 설정된 rtr-edge ↔ sw:net-pub 는 null을 반환한다', () => {
		const g = buildGraph(makeFixture(), { projectId: P, showAll: false });
		expect(resolveLink(g, 'rtr-edge', 'sw:net-pub', P)).toBeNull();
	});

	it('외부 게이트웨이가 없는 라우터 ↔ sw:net-pub 는 router-gateway 요청을 반환한다', () => {
		const data = makeFixture();
		data.routers.push({
			id: 'rtr-no-gw',
			name: 'no-gw-router',
			status: 'ACTIVE',
			external_gateway_network_id: null,
			external_gateway_ips: [],
			interface_ips: [],
			is_distributed: false,
			is_ha: false,
			connected_subnet_ids: [],
			dvr_subnet_ids: [],
			project_id: P,
			enable_snat: false,
			routes: []
		});
		const g = buildGraph(data, { projectId: P, showAll: false });
		const req = resolveLink(g, 'rtr-no-gw', 'sw:net-pub', P);
		expect(req).toEqual({
			kind: 'router-gateway',
			routerId: 'rtr-no-gw',
			routerName: 'no-gw-router',
			networkId: 'net-pub',
			networkName: 'public'
		});
	});

	it('라우터 ↔ 미연결 tenant 스위치는 router-net 요청을 반환한다', () => {
		const g = buildGraph(makeFixture(), { projectId: P, showAll: false });
		// rtr-edge는 net-mgmt(mgmt-isolated)에 연결되어 있지 않음
		const req = resolveLink(g, 'rtr-edge', 'sw:net-mgmt', P);
		expect(req).toEqual({
			kind: 'router-net',
			routerId: 'rtr-edge',
			routerName: 'edge-router',
			networkId: 'net-mgmt',
			networkName: 'mgmt-isolated'
		});
	});

	it('라우터 ↔ 이미 연결된 tenant 스위치는 null을 반환한다', () => {
		const g = buildGraph(makeFixture(), { projectId: P, showAll: false });
		// rtr-edge는 net-web에 이미 연결되어 있음
		expect(resolveLink(g, 'rtr-edge', 'sw:net-web', P)).toBeNull();
	});

	it('vm ↔ vm, vm ↔ router, lb ↔ switch 는 null을 반환한다', () => {
		const g = buildGraph(makeFixture(), { projectId: P, showAll: false });
		expect(resolveLink(g, 'vm-web-01', 'vm-web-02', P)).toBeNull();
		expect(resolveLink(g, 'vm-web-01', 'rtr-edge', P)).toBeNull();
		expect(resolveLink(g, 'lb-web', 'sw:net-web', P)).toBeNull();
	});

	it('projectId 불일치 시 null을 반환한다', () => {
		const g = buildGraph(makeFixture(), { projectId: P, showAll: false });
		expect(resolveLink(g, 'vm-web-01', 'sw:net-app', 'other-project')).toBeNull();
	});

	it('canStartLink 는 규칙에 따라 핸들 표시 여부를 반환한다', () => {
		const g = buildGraph(makeFixture(), { projectId: P, showAll: false });
		expect(canStartLink(g, 'sw:net-web', P)).toBe(true);
		expect(canStartLink(g, 'vm-web-01', P)).toBe(true);
		expect(canStartLink(g, 'rtr-edge', P)).toBe(true);
		expect(canStartLink(g, 'lb-web', P)).toBe(false);

		// 타 프로젝트인 경우
		expect(canStartLink(g, 'vm-web-01', 'other-project')).toBe(false);
		expect(canStartLink(g, 'rtr-edge', 'other-project')).toBe(false);
	});

	it('linkTargets 는 resolveLink 가 유효한 노드 집합을 반환한다', () => {
		const g = buildGraph(makeFixture(), { projectId: P, showAll: false });
		const targets = linkTargets(g, 'vm-web-01', P);
		expect(targets.has('sw:net-app')).toBe(true);
		expect(targets.has('sw:net-web')).toBe(false);
		expect(targets.has('rtr-edge')).toBe(false);
		expect(targets.has('vm-web-02')).toBe(false);
	});

	it('attachableSubnets 는 이미 라우터에 연결된 서브넷을 제외하고 반환한다', () => {
		const net = mkNet('net-multi', 'multi-net', '10.0.0.0/16', '10.0.0.1');
		net.subnet_details.push({
			id: 'sn-multi-2',
			name: 'multi-net-subnet-2',
			cidr: '10.0.1.0/24',
			gateway_ip: '10.0.1.1',
			dhcp_enabled: true
		});

		const router = {
			id: 'rtr-test',
			name: 'test-router',
			status: 'ACTIVE',
			external_gateway_network_id: null,
			external_gateway_ips: [],
			interface_ips: [],
			is_distributed: false,
			is_ha: false,
			connected_subnet_ids: ['sn-multi'],
			dvr_subnet_ids: [],
			project_id: P,
			enable_snat: false,
			routes: []
		};

		const available = attachableSubnets(net, router);
		expect(available.map((s) => s.id)).toEqual(['sn-multi-2']);
	});
});
