import type { CanvasGraph, CanvasNode } from './types';

export type TopologyLinkRequest = {
	method: 'POST';
	url: string;
	body: Record<string, string | boolean>;
	label: string;
};

function node(graph: CanvasGraph, id: string): CanvasNode | null {
	return graph.nodes.get(id) ?? null;
}

/** Returns whether a topology interaction maps to an existing, project-scoped OpenStack mutation. */
export function canLink(graph: CanvasGraph, sourceId: string, targetId: string, projectId: string | null | undefined): boolean {
	if (!projectId || sourceId === targetId) return false;
	const source = node(graph, sourceId);
	const target = node(graph, targetId);
	if (!source || !target || target.kind !== 'switch') return false;
	const network = graph.netById.get(target.netId);
	if (!network || network.status !== 'ACTIVE' || network.kind === 'shared') return false;
	const sourceProjectId = source.kind === 'vm' ? source.meta.project_id : source.kind === 'router' ? source.raw.project_id : null;
	if (sourceProjectId !== projectId || (network.kind === 'internal' && network.project_id !== projectId)) return false;

	if (source.kind === 'vm') {
		return !source.isDatabase && network.kind !== 'external' && !source.nics.some((nic) => nic.netId === target.netId);
	}
	if (source.kind === 'router') {
		if (network.kind === 'external') return source.extNetId == null;
		return network.raw.subnet_details.length > 0 && !source.intNetIds.includes(target.netId);
	}
	return false;
}

/** Converts a valid graph link into the exact existing API request; invalid pairs have no mutation. */
export function linkRequest(
	graph: CanvasGraph,
	sourceId: string,
	targetId: string,
	projectId: string | null | undefined,
): TopologyLinkRequest | null {
	if (!canLink(graph, sourceId, targetId, projectId)) return null;
	const source = node(graph, sourceId);
	const target = node(graph, targetId);
	if (!source || !target || target.kind !== 'switch') return null;
	const network = graph.netById.get(target.netId);
	if (!network) return null;

	if (source.kind === 'vm') {
		return {
			method: 'POST',
			url: `/api/v1/instances/${encodeURIComponent(source.id)}/interfaces`,
			body: { net_id: target.netId },
			label: `${source.name} 인스턴스를 ${network.name} 네트워크에 연결`,
		};
	}
	if (network.kind === 'external') {
		return {
			method: 'POST',
			url: `/api/v1/routers/${encodeURIComponent(source.id)}/gateway`,
			body: { external_network_id: target.netId },
			label: `${source.name} 라우터의 외부 게이트웨이 설정`,
		};
	}
	const subnet = network.raw.subnet_details[0];
	if (!subnet) return null;
	return {
		method: 'POST',
		url: `/api/v1/routers/${encodeURIComponent(source.id)}/interfaces`,
		body: { subnet_id: subnet.id, auto_gateway: !subnet.gateway_ip },
		label: `${source.name} 라우터를 ${network.name} 네트워크에 연결`,
	};
}
