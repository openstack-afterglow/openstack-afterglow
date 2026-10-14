<script lang="ts">
	import type { InfrastructureTopologySnapshot, SwitchPort, TopologySelection } from '$lib/types/infrastructureTopology';
	import type { InfrastructureTopologyController } from '$lib/stores/infrastructureTopologyController.svelte';
	import { t } from '$lib/i18n/ns/infra-topology';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import NicDetails from './NicDetails.svelte';
	import TraceDetails from './TraceDetails.svelte';
	import { buildPeerProbeEdges } from './evidence';
	import { naturalId, type RadialGraph } from './radialGraph';
	import { edgeLabel, rateLabel, timestamp, windowLabel } from './presentation';
	let { ctrl, graph, snapshot, onselect }: { ctrl: InfrastructureTopologyController; graph: RadialGraph; snapshot: InfrastructureTopologySnapshot; onselect: (next: TopologySelection) => void } = $props();
	const node = $derived(ctrl.selection?.kind === 'node' ? graph.nodes.find(item => item.id === ctrl.selection?.id) : undefined);
	const edge = $derived(ctrl.selection?.kind === 'edge' ? graph.edges.find(item => item.id === ctrl.selection?.id) : undefined);
	const port = $derived(node?.portId ? snapshot.fabric.ports.find(item => item.id === node.portId) : ctrl.selection?.kind === 'node' && ctrl.selection.id.startsWith('port:') ? snapshot.fabric.ports.find(item => `port:${item.id}` === ctrl.selection?.id) : edge?.port);
	const device = $derived(snapshot.fabric.devices.find(item => item.id === (node?.deviceId ?? port?.device_id)));
	const host = $derived(snapshot.hosts.find(item => item.id === (node?.hostId ?? edge?.hostId)));
	const adjacent = $derived(graph.edges.filter(item => !item.membership && (item.source === node?.id || item.target === node?.id)));
	const probes = $derived(host ? buildPeerProbeEdges(snapshot.hosts, ctrl.verified).filter(probe => probe.source === host.id) : []);
	const activeTrace = $derived(host?.traces.some(trace => trace.status === 'queued' || trace.status === 'running') ?? false);
	const devicePorts = $derived(snapshot.fabric.ports.filter(item => item.device_id === device?.id).sort((a, b) => a.ifindex - b.ifindex || naturalId(a.id, b.id)));
	function currentRate(item: SwitchPort, value: number | null) { return ctrl.verified && item.state === 'fresh' ? value : null; }
</script>

{#snippet portMetrics(item: SwitchPort)}
	<section class="space-y-3" aria-label={t('workspace.portRates')}>
		<h3 class="font-semibold">{item.name}</h3>
		<div class="flex flex-wrap gap-2"><Pill tone={ctrl.verified && item.state === 'fresh' ? 'success' : item.state === 'error' ? 'danger' : 'neutral'}>{t(`state.${ctrl.verified ? item.state : 'stale'}`)}</Pill><span class="text-xs">{t('operstate')}: {t(`workspace.operstate.${item.operstate}`)}</span></div>
		<p class="text-xs text-ink-2">IF-MIB · ifIndex {item.ifindex.toLocaleString(intlLocale(), { useGrouping: false })} · {windowLabel(item.window_seconds)} · {timestamp(item.captured_at)}</p>
		{#if item.reason}<p class="text-xs text-ink-2">{t(`workspace.reason.${item.reason}`)}</p>{/if}
		<p class="text-xs text-ink-2">{t('workspace.snmpNotice')}</p>
		<TableShell><table><caption>{t('workspace.portRates')}</caption><thead><tr><th scope="col">{t('metric')}</th><th scope="col">{t('workspace.pps')}</th><th scope="col">{t('workspace.Bps')}</th></tr></thead><tbody>
			<tr><th scope="row">{t('rx')}</th><td>{rateLabel(currentRate(item, item.rx_packets_per_second), 'pps')}</td><td>{rateLabel(currentRate(item, item.rx_bytes_per_second), 'Bps')}</td></tr>
			<tr><th scope="row">{t('tx')}</th><td>{rateLabel(currentRate(item, item.tx_packets_per_second), 'pps')}</td><td>{rateLabel(currentRate(item, item.tx_bytes_per_second), 'Bps')}</td></tr>
		</tbody></table></TableShell>
	</section>
{/snippet}

<section class="inspector" aria-label={t('workspace.inspector')}>
	<header><p class="text-xs text-ink-2">{t('workspace.inspector')}</p><h2 class="text-lg font-semibold break-all">{node?.label ?? port?.name ?? (edge ? t(`workspace.layer.${edge.layer}`) : t('workspace.select'))}</h2></header>
	{#if !ctrl.verified}<Alert tone="warning">{t('workspace.retained')}</Alert>{/if}
	{#if edge}
		<p class="text-sm break-all">{edgeLabel(edge, graph, 'pps')}</p>
		{#if edge.flow}
			<p class="text-xs text-ink-2">{t('workspace.flowNotice')}</p>
			<dl class="metadata"><div><dt>{t('workspace.reportingHost')}</dt><dd>{edge.flow.reporting_host_id}</dd></div><div><dt>{t('nic')}</dt><dd>{edge.flow.interface}</dd></div><div><dt>{t('captured')}</dt><dd>{timestamp(edge.flow.captured_at)}</dd></div><div><dt>{t('workspace.measurement')}</dt><dd>{t('workspace.skb')}</dd></div></dl>
			<p class="text-xs">{t(edge.receiverOnly ? 'workspace.receiver' : 'workspace.sender')} · {windowLabel(edge.flow.window_seconds)}</p>
			<TableShell><table><caption>{t('workspace.observations')}</caption><thead><tr><th scope="col">{t('workspace.reportingHost')}</th><th scope="col">{t('nic')}</th><th scope="col">{t('workspace.direction')}</th><th scope="col">{t('workspace.pps')}</th><th scope="col">{t('workspace.Bps')}</th><th scope="col">{t('workspace.measurement')}</th></tr></thead>
				<tbody>{#each edge.observations ?? [edge.flow] as row (row.id)}<tr data-observation-id={row.id}><th scope="row">{row.reporting_host_id}{#if row.id === edge.flow.id}<p class="text-xs">{t('workspace.drawn')}</p>{/if}</th><td>{row.interface}</td><td>{t(row.direction === 'egress' ? 'workspace.sender' : 'workspace.receiver')}</td><td>{rateLabel(ctrl.verified && row.state === 'fresh' ? row.packets_per_second : null, 'pps')}</td><td>{rateLabel(ctrl.verified && row.state === 'fresh' ? row.bytes_per_second : null, 'Bps')}</td><td>{t(`state.${ctrl.verified ? row.state : 'stale'}`)}{#if row.reason}<p class="text-xs">{t(`workspace.reason.${row.reason}`)}</p>{/if}<p class="text-xs">{windowLabel(row.window_seconds)}</p><p class="text-xs">{timestamp(row.captured_at)}</p></td></tr>{/each}</tbody>
			</table></TableShell>
		{/if}
		{#if edge.link}
			<p class="text-xs text-ink-2">{t('workspace.physicalNotice')}</p>
			<dl class="metadata"><div><dt>{t('sources')}</dt><dd>LLDP</dd></div><div><dt>{t('captured')}</dt><dd>{timestamp(edge.link.captured_at)}</dd></div><div><dt>{t('probeSource')}</dt><dd>{edge.link.source.id} · {edge.link.source.port}</dd></div><div><dt>{t('probeTarget')}</dt><dd>{edge.link.target.id} · {edge.link.target.port}</dd></div></dl>
			{#if !port}<Alert tone="info">{t('workspace.portUnknown')}</Alert>{/if}
			<div class="flex flex-wrap gap-2">{#each [edge.link.source, edge.link.target] as endpoint}<Button variant="secondary" onclick={() => onselect({ kind: 'node', id: endpoint.kind === 'host' ? `host:${endpoint.id}` : `switch:${endpoint.id}` })}>{endpoint.id}</Button>{/each}</div>
		{/if}
		{#if edge.probe}<p class="text-xs text-ink-2">{t('probeNotice')}</p><dl class="metadata"><div><dt>{t('ip')}</dt><dd>{edge.probe.address}:{edge.probe.port}</dd></div><div><dt>{t('probeTime')}</dt><dd>{timestamp(edge.probe.checked_at)}</dd></div><div><dt>{t('probeLatency')}</dt><dd>{edge.probe.latency_ms === null ? t('unknown') : t('rttValue', { value: edge.probe.latency_ms.toLocaleString(intlLocale(), { maximumFractionDigits: 2 }) })}</dd></div></dl>{#if edge.probe.error}<p>{t(`probeError.${edge.probe.error}`)}</p>{/if}{/if}
		{#if edge.route}<p class="text-xs text-ink-2">{t('workspace.routeNotice')}</p><dl class="metadata"><div><dt>{t('nic')}</dt><dd>{edge.route.interface}</dd></div><div><dt>{t('destination')}</dt><dd>{edge.route.destination}</dd></div><div><dt>{t('gateway')}</dt><dd>{edge.route.gateway ?? t('unknown')}</dd></div><div><dt>{t('metricPriority')}</dt><dd>{edge.route.metric?.toLocaleString(intlLocale()) ?? t('unknown')}</dd></div></dl>{/if}
	{/if}
	{#if device}
		<dl class="metadata"><div><dt>{t('system')}</dt><dd>{device.name}</dd></div><div><dt>{t('chassis')}</dt><dd>{device.chassis_id}</dd></div><div><dt>{t('workspace.fabric')}</dt><dd>{t(`workspace.fabricState.${snapshot.fabric.state}`)}</dd></div></dl>
		<p class="text-xs text-ink-2">{t('workspace.physicalNotice')} {t('workspace.snmpNotice')}</p>
		{#if !devicePorts.length}<Alert tone="info">{t('workspace.portUnknown')}</Alert>{/if}
	{/if}
	{#if port}{@render portMetrics(port)}{/if}
	{#if device && !port && devicePorts.length}<TableShell><table><caption>{t('workspace.ports')}</caption><thead><tr><th scope="col">{t('port')}</th><th scope="col">{t('operstate')}</th><th scope="col">{t('rx')}</th><th scope="col">{t('tx')}</th><th scope="col">{t('workspace.measurement')}</th></tr></thead><tbody>
		{#each devicePorts as item (item.id)}<tr><th scope="row"><Button variant="ghost" onclick={() => onselect({ kind: 'node', id: `port:${item.id}` })}>{item.name}</Button></th><td>{t(`workspace.operstate.${item.operstate}`)}</td><td>{rateLabel(currentRate(item, item.rx_packets_per_second), 'pps')}<p>{rateLabel(currentRate(item, item.rx_bytes_per_second), 'Bps')}</p></td><td>{rateLabel(currentRate(item, item.tx_packets_per_second), 'pps')}<p>{rateLabel(currentRate(item, item.tx_bytes_per_second), 'Bps')}</p></td><td>{t(`state.${ctrl.verified ? item.state : 'stale'}`)}{#if item.reason}<p>{t(`workspace.reason.${item.reason}`)}</p>{/if}<p>{windowLabel(item.window_seconds)}</p></td></tr>{/each}
	</tbody></table></TableShell>{/if}
	{#if adjacent.length}<section class="space-y-2"><h3 class="font-semibold">{t('workspace.related')}</h3>{#each adjacent as item (item.id)}<Button variant="ghost" class="w-full" onclick={() => onselect({ kind: 'edge', id: item.id })}>{edgeLabel(item, graph, 'pps')}</Button>{/each}</section>{/if}
	{#if node && (node.kind === 'gap' || node.kind === 'router' || node.kind === 'destination')}<p class="text-xs text-ink-2">{t('traceNotice')} {node.kind === 'gap' ? t('network.gapHelp') : t('network.shared')}</p>{/if}
	{#if host}
		<section class="space-y-4" aria-label={t('host')}>
			<div class="flex flex-wrap items-center gap-2"><h3 class="font-semibold font-mono break-all">{host.name}</h3><Pill tone={ctrl.verified && host.observation_state === 'fresh' ? 'success' : 'neutral'}>{t(`state.${ctrl.verified ? host.observation_state : 'stale'}`)}</Pill><span class="text-xs">{t(`role.${host.role}`)}</span></div>
			<dl class="metadata"><div><dt>{t('ip')}</dt><dd>{host.address ?? t('unknown')}</dd></div><div><dt>{t('reachability')}</dt><dd>{t(`state.${ctrl.verified ? host.reachability.status : 'unknown'}`)}</dd></div><div><dt>{t('heartbeat')}</dt><dd>{t(`state.${ctrl.verified ? host.heartbeat.status : 'unknown'}`)}</dd></div><div><dt>{t('captured')}</dt><dd>{timestamp(host.observation?.captured_at ?? null)}</dd></div><div><dt>{t('source.flows')}</dt><dd>{t(`state.${host.observation?.sources.flows ?? 'unmeasured'}`)}</dd></div></dl>
			{#if host.observation && ((host.observation.interfaces_omitted ?? 0) > 0 || (host.observation.evidence_omitted ?? 0) > 0)}<Alert tone="warning">{t('omittedNotice', { interfaces: (host.observation.interfaces_omitted ?? 0).toLocaleString(intlLocale()), evidence: (host.observation.evidence_omitted ?? 0).toLocaleString(intlLocale()) })}</Alert>{/if}
			{#if host.observation?.interfaces.length}<Field label={t('nic')} for="infra-nic"><SelectInput id="infra-nic" bind:value={ctrl.selectedNic}>{#each host.observation.interfaces as nic (nic.name)}<option value={nic.name}>{nic.name}</option>{/each}</SelectInput></Field><NicDetails {host} name={ctrl.selectedNic} verified={ctrl.verified} />{:else}<p class="text-sm text-ink-2">{t('noNics')}</p>{/if}
			<details><summary>{t('peers')} · {probes.length.toLocaleString(intlLocale())}</summary><p class="text-xs text-ink-2">{t('probeNotice')}</p>
				{#each probes as probe}<div class="probe-record"><strong>{probe.sourceName} → {probe.targetName}</strong><p class="font-mono">{probe.address}:{probe.port} · {t(`probe.${probe.status}`)}</p><p>{timestamp(probe.checked_at)} · {probe.latency_ms === null ? t('unknown') : t('rttValue', { value: probe.latency_ms.toLocaleString(intlLocale(), { maximumFractionDigits: 2 }) })}</p>{#if probe.error}<p>{t(`probeError.${probe.error}`)}</p>{/if}</div>{:else}<p>{t('probeEmpty')}</p>{/each}
			</details>
			<section aria-label={t('trace')} class="space-y-3"><h3 class="font-semibold">{t('trace')}</h3><p class="text-xs text-ink-2">{t('traceNotice')}</p>
				{#if !host.observer_configured}<Alert tone="warning">{t('observerNotConfigured')}</Alert>{/if}
				{#if ctrl.traceError}<Alert>{t(ctrl.traceError === 'unavailable' ? 'traceUnavailable' : ctrl.traceError)}</Alert>{/if}
				{#if snapshot.trace_targets.length}<form class="space-y-3" onsubmit={(event) => { event.preventDefault(); void ctrl.submitTrace(); }}><Field label={t('target')} for="infra-target"><SelectInput id="infra-target" bind:value={ctrl.target} disabled={ctrl.busy || !ctrl.verified || !host.observer_configured}>{#each snapshot.trace_targets as target}<option value={target}>{target}</option>{/each}</SelectInput></Field><Button type="submit" variant="primary" disabled={!ctrl.verified || ctrl.busy || activeTrace || !ctrl.target || !host.observer_configured}>{t(ctrl.busy ? 'submitting' : 'submit')}</Button></form>{:else}<p class="text-sm text-ink-2">{t('noTargets')}</p>{/if}
				<TraceDetails {host} verified={ctrl.verified} onselectnic={(nic) => { ctrl.selectedNic = nic; }} />
			</section>
		</section>
	{/if}
	{#if !node && !edge && !port}<p class="text-sm text-ink-2">{t('workspace.select')}</p>{/if}
</section>
<style>
	.inspector { display: grid; grid-template-columns: minmax(0, 1fr); gap: 1rem; min-width: 0; }
	.metadata { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.75rem; font-size: 0.75rem; }
	dt { color: var(--color-ink-2); }
	dd { overflow-wrap: anywhere; }
	caption { text-align: start; font-weight: 600; padding-block-end: 0.5rem; }
	.probe-record { padding-block: 0.75rem; border-bottom: 1px solid var(--color-line); font-size: 0.75rem; overflow-wrap: anywhere; }
	summary { min-height: 44px; cursor: pointer; padding-block: 0.75rem; }
	summary:focus-visible { outline: none; box-shadow: var(--focus-ring); }
	.inspector :global(button) { min-width: 0; max-width: 100%; min-height: 44px; white-space: normal; overflow-wrap: anywhere; }
</style>
