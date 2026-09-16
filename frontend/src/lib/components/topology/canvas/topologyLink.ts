import type { SubnetDetail, TopologyNetwork, TopologyRouter } from '$lib/types/topology';
import type { CanvasGraph, CanvasNode, RouterNode, SwitchNode, VmNode } from './types';

export type LinkRequest =
	| { kind: 'vm-net'; instanceId: string; instanceName: string; networkId: string; networkName: string }
	| { kind: 'router-net'; routerId: string; routerName: string; networkId: string; networkName: string }
	| { kind: 'router-gateway'; routerId: string; routerName: string; networkId: string; networkName: string };

/** 핸들을 보일 노드: switch 전부, vm(isDatabase 제외)·router 는 projectId 소유일 때 */
export function canStartLink(graph: CanvasGraph, nodeId: string, projectId: string | null): boolean {
	const node = graph.nodes.get(nodeId);
	if (!node) return false;
	if (node.kind === 'switch') return true;
	if (projectId == null) return false;
	if (node.kind === 'vm') {
		if (node.isDatabase) return false;
		return node.meta.project_id == null || node.meta.project_id === projectId;
	}
	if (node.kind === 'router') {
		return node.raw.project_id == null || node.raw.project_id === projectId;
	}
	return false;
}

/** 순서 무관 쌍 → 요청. 규칙 불충족은 null */
export function resolveLink(
	graph: CanvasGraph,
	aId: string,
	bId: string,
	projectId: string | null
): LinkRequest | null {
	if (aId === bId || projectId == null) return null;
	const a = graph.nodes.get(aId);
	const b = graph.nodes.get(bId);
	if (!a || !b) return null;

	let sw: SwitchNode | null = null;
	let target: VmNode | RouterNode | null = null;

	if (a.kind === 'switch' && (b.kind === 'vm' || b.kind === 'router')) {
		sw = a;
		target = b;
	} else if (b.kind === 'switch' && (a.kind === 'vm' || a.kind === 'router')) {
		sw = b;
		target = a;
	} else {
		return null;
	}

	const net = graph.netById.get(sw.netId);
	if (!net) return null;

	if (target.kind === 'vm') {
		if (target.isDatabase) return null;
		if (target.meta.project_id != null && target.meta.project_id !== projectId) return null;
		if (target.nics.some((n) => n.netId === net.id)) return null;
		return {
			kind: 'vm-net',
			instanceId: target.id,
			instanceName: target.name,
			networkId: net.id,
			networkName: net.name
		};
	}

	if (target.kind === 'router') {
		if (target.raw.project_id != null && target.raw.project_id !== projectId) return null;

		if (net.kind === 'external') {
			if (target.extNetId) return null;
			return {
				kind: 'router-gateway',
				routerId: target.id,
				routerName: target.name,
				networkId: net.id,
				networkName: net.name
			};
		}

		if (net.kind === 'internal') {
			if (net.project_id != null && net.project_id !== projectId) return null;
			if (target.intNetIds.includes(net.id)) return null;
			return {
				kind: 'router-net',
				routerId: target.id,
				routerName: target.name,
				networkId: net.id,
				networkName: net.name
			};
		}

		// shared 네트워크는 게이트웨이 갱신 권한이 없으므로 null
		return null;
	}

	return null;
}

/** resolveLink(source, id) !== null 인 노드 id 집합 */
export function linkTargets(graph: CanvasGraph, sourceId: string, projectId: string | null): Set<string> {
	const targets = new Set<string>();
	if (projectId == null || !graph.nodes.has(sourceId)) return targets;

	for (const id of graph.nodes.keys()) {
		if (id !== sourceId && resolveLink(graph, sourceId, id, projectId) !== null) {
			targets.add(id);
		}
	}
	return targets;
}

/** 라우터에 아직 붙지 않은 서브넷 */
export function attachableSubnets(net: TopologyNetwork, router: TopologyRouter): SubnetDetail[] {
	const connected = new Set(router.connected_subnet_ids);
	return net.subnet_details.filter((s) => !connected.has(s.id));
}
