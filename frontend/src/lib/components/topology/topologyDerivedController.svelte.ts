import type { TopologyData, TopologyTraffic, TopologyNetwork, ItemRow, LBItem, Anchor } from './types.ts';
import { EXT_COLORS, SHR_COLORS, INT_COLORS, LANE_W, LANE_GAP, LANE_PAD, SIDEBAR_W, _ipv4InCidr, edgeIntensity, NO_TELEMETRY_STYLE } from './topologyHelpers.ts';

export interface ConnectionSpec {
	key: string; netId: string; color: string; opacity: number; width: number;
}

export interface LBCurve {
	key: string; x1: number; y1: number; x2: number; y2: number;
}

export interface TopologyDerivedControllerOpts {
	data: () => TopologyData;
	projectId: () => string | null | undefined;
	showAll: () => boolean;
	traffic: () => TopologyTraffic | null;
	selectedId: () => string | null;
	hoveredId: () => string | null;
	anchors: () => Map<string, Anchor>;
	sidebarHeight: () => number;
	searchTerm: () => string;
}

export function createTopologyDerivedController(opts: TopologyDerivedControllerOpts) {
	const visibleNetworks = $derived(
		opts.showAll()
			? opts.data().networks
			: opts.data().networks.filter(n =>
				n.is_external || n.is_shared || (opts.projectId() != null && n.project_id === opts.projectId())
			)
	);

	const orderedNetworks: TopologyNetwork[] = $derived([
		...visibleNetworks.filter(n => n.is_external).sort((a, b) => a.name.localeCompare(b.name)),
		...visibleNetworks.filter(n => n.is_shared && !n.is_external).sort((a, b) => a.name.localeCompare(b.name)),
		...visibleNetworks.filter(n => !n.is_external && !n.is_shared).sort((a, b) => a.name.localeCompare(b.name)),
	]);

	const netColors = $derived.by(() => {
		const m = new Map<string, string>();
		let eI = 0, sI = 0, iI = 0;
		for (const n of orderedNetworks) {
			if (n.is_external) m.set(n.id, EXT_COLORS[eI++ % EXT_COLORS.length]);
			else if (n.is_shared) m.set(n.id, SHR_COLORS[sI++ % SHR_COLORS.length]);
			else m.set(n.id, INT_COLORS[iI++ % INT_COLORS.length]);
		}
		return m;
	});

	const netIdx = $derived(new Map(orderedNetworks.map((n, i) => [n.id, i])));

	const nameToNetworks = $derived.by(() => {
		const m = new Map<string, TopologyNetwork[]>();
		for (const n of opts.data().networks) {
			const arr = m.get(n.name) ?? [];
			arr.push(n);
			m.set(n.name, arr);
		}
		return m;
	});

	const subnetNetId = $derived(new Map(
		opts.data().networks.flatMap(n => n.subnet_details.map(s => [s.id, n.id] as [string, string]))
	));

	const subnetById = $derived(new Map(
		opts.data().networks.flatMap(n => n.subnet_details.map(s => [s.id, s]))
	));

	const fipNetMap = $derived(new Map(
		opts.data().floating_ips.map(f => [f.floating_ip_address, f.floating_network_id])
	));

	const fipFixedMap = $derived(new Map(
		opts.data().floating_ips
			.filter(f => f.fixed_ip_address)
			.map(f => [f.floating_ip_address, f.fixed_ip_address as string])
	));

	function resolveNetId(networkName: string, ipAddr: string): string | undefined {
		const nets = nameToNetworks.get(networkName);
		if (!nets?.length) return undefined;
		if (nets.length === 1) return nets[0].id;
		for (const net of nets)
			for (const s of net.subnet_details)
				if (_ipv4InCidr(ipAddr, s.cidr)) return net.id;
		return nets[0].id;
	}

	const rows = $derived.by((): ItemRow[] => {
		const result: ItemRow[] = [];
		const data = opts.data();
		const pid = opts.projectId();

		for (const router of data.routers.filter(r => pid == null || r.project_id === pid)) {
			const netSet = new Set<string>();
			const netIps = new Map<string, string[]>();
			if (router.external_gateway_network_id) {
				netSet.add(router.external_gateway_network_id);
				if (router.external_gateway_ips?.length)
					netIps.set(router.external_gateway_network_id, [...router.external_gateway_ips]);
			}
			for (const sid of router.connected_subnet_ids) {
				const nid = subnetNetId.get(sid);
				if (!nid) continue;
				netSet.add(nid);
				const subnet = subnetById.get(sid);
				if (subnet?.gateway_ip) {
					const ips = netIps.get(nid) ?? [];
					if (!ips.includes(subnet.gateway_ip)) ips.push(subnet.gateway_ip);
					netIps.set(nid, ips);
				}
			}
			const connectedNetIds = [...netSet].sort((a, b) => (netIdx.get(a) ?? 0) - (netIdx.get(b) ?? 0));
			const indices = connectedNetIds.map(id => netIdx.get(id) ?? 0);
			result.push({
				type: 'router', id: router.id, name: router.name, status: router.status,
				connectedNetIds, netIps, floatingNetIps: new Map(),
				leftIdx: indices.length ? Math.min(...indices) : 0,
				rightIdx: indices.length ? Math.max(...indices) : 0,
			});
		}

		for (const inst of data.instances.filter(i => pid == null || i.project_id === pid)) {
			const netSet = new Set<string>();
			const netIps = new Map<string, string[]>();
			const floatingNetIps = new Map<string, string[]>();
			const fixedIpToNetId = new Map<string, string>();

			for (const ipInfo of inst.ip_addresses) {
				if (ipInfo.type === 'floating') continue;
				const nid = ipInfo.network_id || resolveNetId(ipInfo.network_name, ipInfo.addr);
				if (!nid) continue;
				netSet.add(nid);
				const ips = netIps.get(nid) ?? [];
				if (!ips.includes(ipInfo.addr)) ips.push(ipInfo.addr);
				netIps.set(nid, ips);
				fixedIpToNetId.set(ipInfo.addr, nid);
			}

			for (const ipInfo of inst.ip_addresses) {
				if (ipInfo.type !== 'floating') continue;
				const fixedAddr = fipFixedMap.get(ipInfo.addr);
				const mappedNetId = fixedAddr ? fixedIpToNetId.get(fixedAddr) : undefined;
				// 매핑된 fixed IP 의 tenant 네트워크 줄에 합쳐 표시, 실패 시 외부 네트워크로 fallback
				const targetNetId = mappedNetId ?? fipNetMap.get(ipInfo.addr);
				if (!targetNetId) continue;
				const fips = floatingNetIps.get(targetNetId) ?? [];
				if (!fips.includes(ipInfo.addr)) fips.push(ipInfo.addr);
				floatingNetIps.set(targetNetId, fips);
			}

			const connectedNetIds = [...netSet].sort((a, b) => (netIdx.get(a) ?? 0) - (netIdx.get(b) ?? 0));
			const indices = connectedNetIds.map(id => netIdx.get(id) ?? 0);
			result.push({
				type: 'instance', id: inst.id, name: inst.name, status: inst.status,
				connectedNetIds, netIps, floatingNetIps,
				leftIdx: indices.length ? Math.min(...indices) : 0,
				rightIdx: indices.length ? Math.max(...indices) : 0,
			});
		}

		result.sort((a, b) => {
			if (a.type !== b.type) return a.type === 'router' ? -1 : 1;
			if (a.leftIdx !== b.leftIdx) return a.leftIdx - b.leftIdx;
			return a.name.localeCompare(b.name);
		});
		return result;
	});

	const lbItems = $derived.by((): LBItem[] => {
		const pid = opts.projectId();
		const lbs = (opts.data().load_balancers ?? []).filter(lb => pid == null || lb.project_id === pid);
		return lbs.map(lb => {
			const vipNetId = lb.vip_network_id && netIdx.has(lb.vip_network_id)
				? lb.vip_network_id
				: lb.vip_subnet_id ? (subnetNetId.get(lb.vip_subnet_id) ?? null) : null;
			return { lb, vipNetId };
		});
	});

	const instNetBps = $derived.by(() => {
		const m = new Map<string, { rx_bps: number; tx_bps: number }>();
		const t = opts.traffic();
		if (!t?.interfaces) return m;
		for (const ifc of Object.values(t.interfaces)) {
			const key = `${ifc.instance_id}|${ifc.network_id}`;
			const cur = m.get(key);
			if (cur) { cur.rx_bps += ifc.rx_bps; cur.tx_bps += ifc.tx_bps; }
			else m.set(key, { rx_bps: ifc.rx_bps, tx_bps: ifc.tx_bps });
		}
		return m;
	});

	const filteredRows = $derived.by(() => {
		const q = opts.searchTerm().trim().toLowerCase();
		if (!q) return rows;
		return rows.filter(r =>
			r.name.toLowerCase().includes(q) ||
			[...r.netIps.values()].flat().some(ip => ip.includes(q)) ||
			[...r.floatingNetIps.values()].flat().some(ip => ip.includes(q))
		);
	});

	const filteredLbItems = $derived.by(() => {
		const q = opts.searchTerm().trim().toLowerCase();
		if (!q) return lbItems;
		return lbItems.filter(({ lb }) =>
			lb.name.toLowerCase().includes(q) || (lb.vip_address ?? '').includes(q)
		);
	});

	const routerRows = $derived(filteredRows.filter(r => r.type === 'router'));
	const instanceRows = $derived(filteredRows.filter(r => r.type === 'instance'));

	const totalTraffic = $derived.by(() => {
		let rx = 0, tx = 0;
		const t = opts.traffic();
		if (!t?.interfaces) return { rx, tx };
		const visibleIds = new Set(instanceRows.map(r => r.id));
		for (const ifc of Object.values(t.interfaces)) {
			if (visibleIds.has(ifc.instance_id)) { rx += ifc.rx_bps; tx += ifc.tx_bps; }
		}
		return { rx, tx };
	});

	const connections = $derived.by((): ConnectionSpec[] => {
		const result: ConnectionSpec[] = [];
		for (const row of filteredRows) {
			const allNets = [
				...row.connectedNetIds,
				...[...row.floatingNetIps.keys()].filter(id => !row.connectedNetIds.includes(id)),
			];
			for (const netId of allNets) {
				const color = netColors.get(netId) ?? '#3b82f6';
				const bpsPair = row.type === 'instance' ? instNetBps.get(`${row.id}|${netId}`) : undefined;
				// 계측이 없으면 0 으로 뭉개지 않는다 — 0 bps 는 "쟀더니 0" 이라 강도 하한으로 그려야 하고,
				// "잴 수 없었다" 는 NO_TELEMETRY_STYLE 로 따로 그려야 둘이 구분된다.
				const ei = bpsPair ? edgeIntensity(bpsPair.rx_bps + bpsPair.tx_bps) : NO_TELEMETRY_STYLE;
				const isFloating = !row.connectedNetIds.includes(netId);
				result.push({
					key: `${row.id}|${netId}`,
					netId,
					color,
					opacity: isFloating ? ei.opacity * 0.6 : ei.opacity,
					width: isFloating ? 1.5 : ei.width,
				});
			}
		}
		for (const { lb, vipNetId } of filteredLbItems) {
			if (vipNetId) {
				const color = netColors.get(vipNetId) ?? '#06b6d4';
				result.push({ key: `lb|${lb.id}|${vipNetId}`, netId: vipNetId, color, opacity: 0.75, width: 2 });
			}
		}
		return result;
	});

	const lbCurves = $derived.by((): LBCurve[] => {
		const activeLbId = opts.selectedId() || opts.hoveredId();
		if (!activeLbId) return [];
		const lbItem = filteredLbItems.find(({ lb }) => lb.id === activeLbId);
		if (!lbItem) return [];

		const lbAnchorKey = lbItem.vipNetId ? `lb|${lbItem.lb.id}|${lbItem.vipNetId}` : null;
		const lbAnchor = lbAnchorKey ? opts.anchors().get(lbAnchorKey) : null;
		if (!lbAnchor) return [];

		const result: LBCurve[] = [];
		for (const member of lbItem.lb.members) {
			if (!member.server_id) continue;
			const row = instanceRows.find(r => r.id === member.server_id);
			if (!row) continue;
			const firstNetId = row.connectedNetIds[0];
			if (!firstNetId) continue;
			const instAnchor = opts.anchors().get(`${row.id}|${firstNetId}`);
			if (!instAnchor) continue;
			result.push({
				key: `lb-curve|${lbItem.lb.id}|${member.id}`,
				x1: lbAnchor.x, y1: lbAnchor.y,
				x2: instAnchor.x, y2: instAnchor.y,
			});
		}
		return result;
	});

	const canvasContentW = $derived(
		LANE_PAD * 2 + orderedNetworks.length * LANE_W + Math.max(0, orderedNetworks.length - 1) * LANE_GAP
	);

	const laneXMap = $derived.by(() => {
		const m = new Map<string, number>();
		orderedNetworks.forEach((n, i) => {
			m.set(n.id, SIDEBAR_W + LANE_PAD + i * (LANE_W + LANE_GAP) + LANE_W / 2);
		});
		return m;
	});

	const laneHeight = $derived(Math.max(400, opts.sidebarHeight()));

	return {
		get orderedNetworks() { return orderedNetworks; },
		get netColors() { return netColors; },
		get filteredRows() { return filteredRows; },
		get filteredLbItems() { return filteredLbItems; },
		get routerRows() { return routerRows; },
		get instanceRows() { return instanceRows; },
		get instNetBps() { return instNetBps; },
		get totalTraffic() { return totalTraffic; },
		get connections() { return connections; },
		get lbCurves() { return lbCurves; },
		get canvasContentW() { return canvasContentW; },
		get laneXMap() { return laneXMap; },
		get laneHeight() { return laneHeight; },
	};
}

export type TopologyDerivedController = ReturnType<typeof createTopologyDerivedController>;
