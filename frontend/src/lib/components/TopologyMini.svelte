<script lang="ts">
	import { t } from '$lib/i18n/ns/topology';
	import { onMount } from 'svelte';
	import type { FloatingIpInfo } from '$lib/types/networks';

	interface SubnetDetail { id: string; name: string; cidr: string; gateway_ip: string | null; dhcp_enabled: boolean; }
	interface TopologyNetwork { id: string; name: string; status: string; is_external: boolean; is_shared: boolean; project_id: string | null; subnet_details: SubnetDetail[]; }
	interface TopologyRouter { id: string; name: string; status: string; external_gateway_network_id: string | null; external_gateway_ips: string[]; interface_ips: { ip_address: string; subnet_id: string }[]; is_distributed: boolean; is_ha: boolean; connected_subnet_ids: string[]; dvr_subnet_ids: string[]; project_id: string | null; }
	interface TopologyInstance { id: string; name: string; status: string; project_id?: string | null; network_names: string[]; ip_addresses: { addr: string; type: string; network_name: string; network_id?: string | null }[]; }
	interface TopologyLBMember { id: string; address: string; protocol_port: number; status: string; subnet_id: string | null; pool_id: string; server_id: string | null; }
	interface TopologyLBListener { id: string; name: string; protocol: string; protocol_port: number; default_pool_id: string | null; }
	interface TopologyLoadBalancer { id: string; name: string; vip_address: string | null; vip_port_id: string | null; vip_subnet_id: string | null; vip_network_id: string | null; provisioning_status: string; operating_status: string; project_id: string | null; listeners: TopologyLBListener[]; members: TopologyLBMember[]; }
	interface TopologyData { networks: TopologyNetwork[]; routers: TopologyRouter[]; instances: TopologyInstance[]; floating_ips: FloatingIpInfo[]; load_balancers?: TopologyLoadBalancer[]; }

	let { data }: { data: TopologyData } = $props();

	let isLight = $state(false);
	onMount(() => {
		isLight = document.documentElement.classList.contains('light');
		const obs = new MutationObserver(() => { isLight = document.documentElement.classList.contains('light'); });
		obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
		return () => obs.disconnect();
	});

	const COL_W = 260; const L_PAD = 60; const TOP_H = 44; const ROW_H = 80;
	const ITEM_W = 130; const ITEM_H = 44; const BAR_W = 6; const BOT_H = 48; const IP_GAP = 100;

	const EXT_COLORS = ['#ea580c', '#f97316'];
	const SHR_COLORS = ['#0d9488', '#14b8a6'];
	const INT_COLORS = ['#3b82f6', '#22c55e', '#a855f7', '#f59e0b', '#06b6d4', '#ec4899', '#ef4444'];

	const orderedNetworks = $derived([
		...data.networks.filter(n => n.is_external).sort((a, b) => a.name.localeCompare(b.name)),
		...data.networks.filter(n => n.is_shared && !n.is_external).sort((a, b) => a.name.localeCompare(b.name)),
		...data.networks.filter(n => !n.is_external && !n.is_shared).sort((a, b) => a.name.localeCompare(b.name)),
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

	const netCX = $derived(new Map(orderedNetworks.map((n, i) => [n.id, L_PAD + i * COL_W])));
	const netIdx = $derived(new Map(orderedNetworks.map((n, i) => [n.id, i])));
	const subnetNetId = $derived(new Map(data.networks.flatMap(n => n.subnet_details.map(s => [s.id, n.id]))));
	const fipNetMap = $derived(new Map(data.floating_ips.map(f => [f.floating_ip_address, f.floating_network_id])));

	const nameToNetworks = $derived.by(() => {
		const m = new Map<string, TopologyNetwork[]>();
		for (const n of data.networks) { const arr = m.get(n.name) ?? []; arr.push(n); m.set(n.name, arr); }
		return m;
	});

	function resolveNetId(networkName: string, ipAddr: string): string | undefined {
		const nets = nameToNetworks.get(networkName);
		if (!nets?.length) return undefined;
		if (nets.length === 1) return nets[0].id;
		for (const net of nets) {
			for (const s of net.subnet_details) {
				const parts = s.cidr.split('/');
				if (parts.length === 2) {
					const mask = parseInt(parts[1]);
					const ipN = ipAddr.split('.').reduce((acc, p) => (acc << 8) | parseInt(p), 0) >>> 0;
					const netN = parts[0].split('.').reduce((acc, p) => (acc << 8) | parseInt(p), 0) >>> 0;
					const maskBits = mask === 0 ? 0 : ((0xFFFFFFFF << (32 - mask)) >>> 0);
					if ((ipN & maskBits) === (netN & maskBits)) return net.id;
				}
			}
		}
		return nets[0].id;
	}

	interface MiniRow { id: string; type: 'router' | 'instance'; name: string; status: string; connectedNetIds: string[]; }

	const rows = $derived.by((): MiniRow[] => {
		const result: MiniRow[] = [];
		for (const r of data.routers) {
			const nets = new Set<string>();
			if (r.external_gateway_network_id) nets.add(r.external_gateway_network_id);
			for (const sid of r.connected_subnet_ids) { const nid = subnetNetId.get(sid); if (nid) nets.add(nid); }
			result.push({ type: 'router', id: r.id, name: r.name, status: r.status, connectedNetIds: [...nets].sort((a, b) => (netIdx.get(a) ?? 0) - (netIdx.get(b) ?? 0)) });
		}
		for (const inst of data.instances) {
			const nets = new Set<string>();
			for (const ip of inst.ip_addresses) {
				if (ip.type === 'floating') continue;
				const nid = ip.network_id || resolveNetId(ip.network_name, ip.addr);
				if (nid) nets.add(nid);
			}
			result.push({ type: 'instance', id: inst.id, name: inst.name, status: inst.status, connectedNetIds: [...nets].sort((a, b) => (netIdx.get(a) ?? 0) - (netIdx.get(b) ?? 0)) });
		}
		result.sort((a, b) => { if (a.type !== b.type) return a.type === 'router' ? -1 : 1; return a.name.localeCompare(b.name); });
		return result;
	});

	const barH = $derived(Math.max(rows.length, 1) * ROW_H + 16);
	const svgW = $derived(Math.max(480, L_PAD + Math.max(0, orderedNetworks.length - 1) * COL_W + IP_GAP + ITEM_W + 32));
	const svgH = $derived(TOP_H + barH + BOT_H);

	function rowCY(i: number) { return TOP_H + i * ROW_H + ITEM_H / 2; }
	function rowY(i: number)  { return TOP_H + i * ROW_H; }
	function itemCX(row: MiniRow): number {
		if (!row.connectedNetIds.length) return svgW / 2;
		const xs = row.connectedNetIds.map(id => netCX.get(id)).filter((x): x is number => x !== undefined);
		if (!xs.length) return svgW / 2;
		return Math.min(...xs) + IP_GAP + ITEM_W / 2;
	}

	function trunc(s: string, n: number) { return s.length > n ? s.slice(0, n - 1) + '…' : s; }
	function statusStroke(s: string) { return s === 'ACTIVE' ? '#22c55e' : s === 'ERROR' || s === 'SHUTOFF' ? '#ef4444' : '#78716c'; }
	function statusFill(s: string) {
		if (isLight) return s === 'ACTIVE' ? '#f0fdf4' : s === 'ERROR' || s === 'SHUTOFF' ? '#fef2f2' : '#f8fafc';
		return s === 'ACTIVE' ? '#052e16' : s === 'ERROR' || s === 'SHUTOFF' ? '#450a0a' : '#1c1917';
	}
</script>

<div class="w-full">
	<svg viewBox="0 0 {svgW} {svgH}" width="100%" height="auto" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg">
		{#each rows as row, i}
			{@const cy = rowCY(i)}
			{@const iy = rowY(i)}
			{@const cx = itemCX(row)}
			{@const ix = cx - ITEM_W / 2}
			{@const stroke = row.type === 'router' ? (row.connectedNetIds.some(id => orderedNetworks.find(n=>n.id===id)?.is_external) ? '#f59e0b' : '#64748b') : statusStroke(row.status)}
			{@const fill = row.type === 'router' ? (isLight ? '#f8fafc' : '#0f172a') : statusFill(row.status)}

			{#each row.connectedNetIds as netId}
				{@const barX = netCX.get(netId) ?? 0}
				{@const col = netColors.get(netId) ?? '#3b82f6'}
				<line x1={barX} y1={cy} x2={ix} y2={cy} stroke={col} stroke-width="1.5" opacity="0.5"/>
			{/each}

			<rect x={ix} y={iy} width={ITEM_W} height={ITEM_H} rx={row.type === 'router' ? '22' : '6'} fill={fill} stroke={stroke} stroke-width="1.2"/>
			<text x={ix + ITEM_W/2} y={cy + 4} text-anchor="middle" fill={stroke} font-size="9" font-weight="600" font-family="ui-sans-serif,sans-serif" style="pointer-events:none">{trunc(row.name, 14)}</text>
		{/each}

		{#each orderedNetworks as net}
			{@const cx = netCX.get(net.id) ?? 0}
			{@const col = netColors.get(net.id) ?? '#3b82f6'}
			<rect x={cx - BAR_W/2} y={TOP_H} width={BAR_W} height={barH} rx="3" fill={col} opacity="0.7"/>
			<text x={cx} y={TOP_H - 6} text-anchor="middle" fill={col} font-size="8" font-weight="600" font-family="ui-sans-serif,sans-serif">{trunc(net.name || net.id, 14)}</text>
		{/each}

		{#if data.networks.length === 0}
			<text x={svgW/2} y={svgH/2} text-anchor="middle" fill="#475569" font-size="12" font-family="ui-sans-serif,sans-serif">{t('empty.networks')}</text>
		{/if}
	</svg>
</div>
