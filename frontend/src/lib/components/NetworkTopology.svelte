<script lang="ts">
	import { t } from '$lib/i18n/ns/topology';
	import type { NetworkDetail } from '$lib/types/networks';

	let { network }: { network: NetworkDetail } = $props();

	// Layout constants
	const NODE_W = 200;
	const NODE_H = 64;
	const NET_H = 72;
	const SUBNET_H = 72;
	const ROUTER_H = 56;
	const H_GAP = 32;
	const V_GAP = 60;

	const subnets = $derived(network.subnet_details);
	const routers = $derived(network.routers);

	const totalW = $derived(Math.max(
		NODE_W + 80,
		subnets.length * (NODE_W + H_GAP) + H_GAP
	));

	const netX = $derived((totalW - NODE_W) / 2);
	const netY = 20;
	const netCX = $derived(netX + NODE_W / 2);
	const netCY = $derived(netY + NET_H);

	const subnetXs = $derived(() => {
		const total = subnets.length * NODE_W + Math.max(0, subnets.length - 1) * H_GAP;
		const startX = (totalW - total) / 2;
		return subnets.map((_, i) => startX + i * (NODE_W + H_GAP));
	});

	const subnetTY = netY + NET_H + V_GAP;
	const subnetBY = netY + NET_H + V_GAP + SUBNET_H;
	const routerY = netY + NET_H + V_GAP + SUBNET_H + V_GAP;

	const svgHeight = $derived(
		routers.length > 0
			? routerY + ROUTER_H + 20
			: subnets.length > 0
				? subnetTY + SUBNET_H + 20
				: netY + NET_H + 20
	);

	// Computed colors (not inside template)
	const nc = $derived(
		network.is_external
			? { fill: '#431407', stroke: '#ea580c', text: '#fb923c' }
			: network.is_shared
				? { fill: '#042f2e', stroke: '#0d9488', text: '#2dd4bf' }
				: { fill: '#0f172a', stroke: '#3b82f6', text: '#93c5fd' }
	);
	const sc = { fill: '#0f172a', stroke: '#6366f1', text: '#a5b4fc' };

	const routerPositions = $derived(
		routers.map((r) => {
			const connectedIdx = subnets.findIndex((s) => r.connected_subnet_ids.includes(s.id));
			const sx = connectedIdx >= 0 ? subnetXs()[connectedIdx] : netX;
			return {
				router: r,
				x: sx,
				y: routerY,
				isExternal: !!r.external_gateway_network_id,
			};
		})
	);
</script>

<div class="w-full overflow-x-auto">
	<svg
		viewBox="0 0 {totalW} {svgHeight}"
		class="w-full"
		style="min-height: {svgHeight}px; max-height: 500px;"
	>
		<!-- Network node -->
		<rect
			x={netX}
			y={netY}
			width={NODE_W}
			height={NET_H}
			rx="8"
			fill={nc.fill}
			stroke={nc.stroke}
			stroke-width="1.5"
		/>
		<text
			x={netCX}
			y={netY + 26}
			text-anchor="middle"
			fill={nc.text}
			font-size="13"
			font-weight="600"
			font-family="ui-sans-serif, system-ui, sans-serif"
		>
			{network.name || network.id.slice(0, 12) + '…'}
		</text>
		<text
			x={netCX}
			y={netY + 46}
			text-anchor="middle"
			fill={nc.stroke}
			font-size="10"
			font-family="ui-monospace, monospace"
		>
			{network.is_external ? t('network.external') : network.is_shared ? t('network.shared') : t('network.internal')}
		</text>

		<!-- Subnet nodes and lines from network -->
		{#each subnets as subnet, i}
			<line
				x1={netCX}
				y1={netCY}
				x2={subnetXs()[i] + NODE_W / 2}
				y2={subnetTY}
				stroke="#334155"
				stroke-width="1.5"
				stroke-dasharray="4 3"
			/>
			<rect
				x={subnetXs()[i]}
				y={subnetTY}
				width={NODE_W}
				height={SUBNET_H}
				rx="6"
				fill={sc.fill}
				stroke={sc.stroke}
				stroke-width="1.5"
			/>
			<text
				x={subnetXs()[i] + NODE_W / 2}
				y={subnetTY + 22}
				text-anchor="middle"
				fill={sc.text}
				font-size="11"
				font-weight="600"
				font-family="ui-sans-serif, system-ui, sans-serif"
			>
				{subnet.name || subnet.cidr}
			</text>
			<text
				x={subnetXs()[i] + NODE_W / 2}
				y={subnetTY + 40}
				text-anchor="middle"
				fill="#64748b"
				font-size="10"
				font-family="ui-monospace, monospace"
			>
				{subnet.cidr}
			</text>
			{#if subnet.gateway_ip}
				<text
					x={subnetXs()[i] + NODE_W / 2}
					y={subnetTY + 56}
					text-anchor="middle"
					fill="#475569"
					font-size="9"
					font-family="ui-monospace, monospace"
				>
					GW: {subnet.gateway_ip}
				</text>
			{/if}
		{/each}

		<!-- Router nodes -->
		{#each routerPositions as pos}
			{#each pos.router.connected_subnet_ids as sid}
				{@const sidx = subnets.findIndex((s) => s.id === sid)}
				{#if sidx >= 0}
					<line
						x1={subnetXs()[sidx] + NODE_W / 2}
						y1={subnetBY}
						x2={pos.x + NODE_W / 2}
						y2={pos.y}
						stroke="#334155"
						stroke-width="1.5"
						stroke-dasharray="4 3"
					/>
				{/if}
			{/each}
			<rect
				x={pos.x}
				y={pos.y}
				width={NODE_W}
				height={ROUTER_H}
				rx="6"
				fill="#0f172a"
				stroke={pos.isExternal ? '#f59e0b' : '#64748b'}
				stroke-width="1.5"
			/>
			<text
				x={pos.x + NODE_W / 2}
				y={pos.y + 22}
				text-anchor="middle"
				fill={pos.isExternal ? '#fcd34d' : '#94a3b8'}
				font-size="11"
				font-weight="600"
				font-family="ui-sans-serif, system-ui, sans-serif"
			>
				{pos.router.name || pos.router.id.slice(0, 12) + '…'}
			</text>
			<text
				x={pos.x + NODE_W / 2}
				y={pos.y + 40}
				text-anchor="middle"
				fill={pos.isExternal ? '#f59e0b' : '#475569'}
				font-size="9"
				font-family="ui-sans-serif, system-ui, sans-serif"
			>
				{pos.isExternal ? t('network.externalGateway') : t('network.internalRouter')}
			</text>
		{/each}

		<!-- Empty state -->
		{#if subnets.length === 0}
			<text
				x={totalW / 2}
				y={netY + NET_H + 40}
				text-anchor="middle"
				fill="#475569"
				font-size="12"
				font-family="ui-sans-serif, system-ui, sans-serif"
			>
				{t('empty.subnets')}
			</text>
		{/if}
	</svg>
</div>
