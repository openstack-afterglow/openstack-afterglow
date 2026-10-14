import { t } from '$lib/i18n/ns/infra-topology';
import type source from '$lib/i18n/messages/ko/infra-topology.json';
import { intlLocale } from '$lib/i18n/runtime.svelte';
import type { FlowMetric, RadialEdge, RadialGraph } from './radialGraph';
import { edgeRate, edgeWindow, magnitude } from './radialGraph';
import { quantity } from './evidence';

const STATE_KEYS: Record<string, keyof typeof source> = {
	fresh: 'state.fresh', stale: 'state.stale', unmeasured: 'state.unmeasured', measured: 'state.measured', error: 'state.error', unsupported: 'state.unsupported',
	up: 'state.up', down: 'state.down', unknown: 'state.unknown', queued: 'trace.queued', running: 'trace.running', complete: 'trace.complete', expired: 'trace.expired', unconfirmed: 'network.unconfirmed',
};
export function stateLabel(state: string) { return t(STATE_KEYS[state] ?? 'state.unknown'); }
export function timestamp(value: number | null) { return value !== null && Number.isFinite(value) ? new Date(value * 1000).toLocaleString(intlLocale()) : t('unknown'); }
export function windowLabel(value: number | null) { return value !== null && Number.isFinite(value) && value > 0 ? t('workspace.window', { seconds: value.toLocaleString(intlLocale(), { maximumFractionDigits: 2 }) }) : t('workspace.windowUnknown'); }
export function rateLabel(value: number | null, metric: FlowMetric) { return quantity(value, metric === 'pps' ? 'tx_packets' : 'tx_bytes', true); }
export function edgeLabel(edge: RadialEdge, graph: RadialGraph, metric: FlowMetric) {
	const from = graph.nodes.find(node => node.id === edge.source)?.label ?? edge.source;
	const to = graph.nodes.find(node => node.id === edge.target)?.label ?? edge.target;
	let detail = t(`workspace.layer.${edge.layer}`);
	if (edge.flow || edge.port) {
		const scaled = magnitude(edgeRate(edge, metric), edge.state, metric);
		detail += ` · ${rateLabel(scaled.rate, metric)} · ${scaled.zero ? t('workspace.zero') : scaled.unknown && edge.state === 'fresh' ? t('workspace.rateUnknown') : stateLabel(edge.state)} · ${windowLabel(edgeWindow(edge))}`;
		if (edge.flow) detail += ` · ${edge.flow.interface} · ${t(edge.receiverOnly ? 'workspace.receiver' : 'workspace.sender')}`;
		if (edge.port) detail += ` · ${edge.port.name} · ${t(edge.portDirection === 'rx' ? 'rx' : 'tx')}`;
		const reason = edge.flow?.reason ?? edge.port?.reason;
		if (reason) detail += ` · ${t(`workspace.reason.${reason}`)}`;
	} else if (edge.probe) detail += ` · TCP ${edge.probe.port} · ${t(`probe.${edge.probe.status}`)}`;
	else if (edge.trace) detail += ` · ${edge.state === 'unconfirmed' ? t('network.unconfirmed') : edge.state === 'stale' ? t('trace.stale') : t(`trace.${edge.trace.status}`)}`;
	else detail += ` · ${stateLabel(edge.state)}${edge.link ? ` · ${t('workspace.portUnknown')}` : ''}`;
	return `${from} → ${to} · ${detail}`;
}
const FABRIC_ERRORS: Record<string, keyof typeof source> = {
	snmp_timeout: 'workspace.fabricError.snmp_timeout', snmp_authentication: 'workspace.fabricError.snmp_authentication', snmp_network_unreachable: 'workspace.fabricError.snmp_network_unreachable', snmp_unsupported: 'workspace.fabricError.snmp_unsupported',
	snmp_dependency_unavailable: 'workspace.fabricError.snmp_dependency_unavailable', snmp_collector_error: 'workspace.fabricError.snmp_collector_error', snmp_cardinality_exceeded: 'workspace.fabricError.snmp_cardinality_exceeded',
	snmp_invalid_response: 'workspace.fabricError.snmp_invalid_response', snmp_missing_counters: 'workspace.fabricError.snmp_missing_counters', snmp_missing_lldp: 'workspace.fabricError.snmp_missing_lldp', snmp_missing_uptime: 'workspace.fabricError.snmp_missing_uptime',
	snmp_identity_mismatch: 'workspace.fabricError.snmp_identity_mismatch', snmp_counter_overflow: 'workspace.fabricError.snmp_counter_overflow', snmp_stale_sample: 'workspace.fabricError.snmp_stale_sample', snmp_duplicate_sample: 'workspace.fabricError.snmp_duplicate_sample',
	snmp_unmeasured: 'workspace.fabricError.snmp_unmeasured', snmp_configuration_pending: 'workspace.fabricError.snmp_configuration_pending', snmp_store_unavailable: 'workspace.fabricError.snmp_store_unavailable',
};
/** The API emits sorted comma-separated safe codes, never agent exception text. */
export function fabricErrorMessages(error: string | null): string[] {
	if (!error) return [];
	return error.split(',').map(code => t(Object.hasOwn(FABRIC_ERRORS, code) ? FABRIC_ERRORS[code] : 'workspace.fabricError.snmp_collector_error'));
}
