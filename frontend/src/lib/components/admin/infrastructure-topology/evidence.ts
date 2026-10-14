import type { InterfaceCounters, PeerProbe, TopologyHost, TraceResult } from '$lib/types/infrastructureTopology';
import { t } from '$lib/i18n/ns/infra-topology';
import { intlLocale } from '$lib/i18n/runtime.svelte';

const byteUnits = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB'];
export function quantity(value: number | null, key: keyof InterfaceCounters, rate = false): string {
	if (value === null || !Number.isFinite(value) || value < 0) return t('unknown');
	if (key.endsWith('bytes')) {
		const power = value < 1 ? 0 : Math.min(byteUnits.length - 1, Math.floor(Math.log(value) / Math.log(1024)));
		return t(rate ? 'bytesRate' : 'bytes', { value: (value / 1024 ** power).toLocaleString(intlLocale(), { maximumFractionDigits: 2 }), unit: byteUnits[power] });
	}
	return t(rate ? 'packetsRate' : 'packets', { value: value.toLocaleString(intlLocale(), { maximumFractionDigits: rate ? 2 : 0 }) });
}
export const safeRate = (value: number | null): number | null => value !== null && Number.isFinite(value) && value >= 0 ? value : null;
export function nicHistory(host: TopologyHost, name: string, verified: boolean) {
	if (!verified || host.observation?.sources.counters !== 'measured') return [];
	return (host.observation.interfaces.find(nic => nic.name === name)?.history ?? []).map(sample => ({
		timestamp: sample.ts * 1000, rxRate: safeRate(sample.rates.rx_bytes), txRate: safeRate(sample.rates.tx_bytes),
	}));
}
export interface PeerProbeEdge extends PeerProbe {
	source: string; sourceName: string; targetName: string; targetInInventory: boolean;
}
/** TCP success proves only this directed service-port observation, not volume or reverse reachability. */
export function buildPeerProbeEdges(hosts: TopologyHost[], verified: boolean): PeerProbeEdge[] {
	const inventory = new Map(hosts.map(host => [host.id, host]));
	return hosts.flatMap(host => host.peer_probes.map<PeerProbeEdge>(probe => ({
		...probe, source: host.id, sourceName: host.name,
		targetName: inventory.get(probe.target_host_id)?.name ?? probe.target_host_id,
		targetInInventory: inventory.has(probe.target_host_id),
		status: verified && host.observation_state === 'fresh' ? probe.status : 'unknown',
		latency_ms: verified && host.observation_state === 'fresh' ? probe.latency_ms : null,
		error: host.observation_state === 'unmeasured' ? probe.error ?? 'probe_unmeasured' : !verified || host.observation_state === 'stale' ? 'probe_stale' : probe.error,
	})));
}
export type CollapsedHop = { kind: 'hop'; hop: TraceResult['hops'][number] } | { kind: 'gap'; from: number; to: number; count: number };
/** Gaps remain trace-local; they are not inferred routers or fault locations. */
export function collapseHops(hops: TraceResult['hops']): CollapsedHop[] {
	const items: CollapsedHop[] = [];
	for (const hop of [...hops].sort((a, b) => a.hop - b.hop)) {
		const previous = items.at(-1);
		if (hop.ip !== null) items.push({ kind: 'hop', hop });
		else if (previous?.kind === 'gap' && previous.to + 1 === hop.hop) { previous.to = hop.hop; previous.count += 1; }
		else items.push({ kind: 'gap', from: hop.hop, to: hop.hop, count: 1 });
	}
	return items;
}
