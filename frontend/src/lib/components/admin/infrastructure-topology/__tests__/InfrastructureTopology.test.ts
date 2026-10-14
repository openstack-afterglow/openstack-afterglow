import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { get } from 'svelte/store';
import InfrastructureTopology from '../InfrastructureTopology.svelte';
import EvidenceMap from '../EvidenceMap.svelte';
import NicDetails from '../NicDetails.svelte';
import TraceDetails from '../TraceDetails.svelte';
import PeerProbeMap from '../PeerProbeMap.svelte';
import NetworkMap from '../NetworkMap.svelte';
import { makeHost, makeNetworkHosts, makeSnapshot, makeTrace } from './fixtures';
import { auth, authReady, projectSwitching } from '$lib/stores/auth';
import { t } from '$lib/i18n/ns/infra-topology';
import { initLocale, intlLocale } from '$lib/i18n/runtime.svelte';

const { read, submit } = vi.hoisted(() => ({ read: vi.fn(), submit: vi.fn() }));
vi.mock('$lib/api/infrastructureTopology', () => ({ getInfrastructureTopology: read, submitInfrastructureTrace: submit }));
beforeEach(() => {
	initLocale('ko'); read.mockReset().mockImplementation(() => Promise.resolve(makeSnapshot())); submit.mockReset().mockResolvedValue(makeTrace('queued'));
	auth.set({ ...get(auth), token: 'token-a', userId: 'user-a', projectId: 'project-a', isSystemAdmin: true }); authReady.set(true); projectSwitching.set(false);
});
afterEach(() => { cleanup(); initLocale('ko'); vi.restoreAllMocks(); vi.useRealTimers(); });

describe('rendered infrastructure evidence', () => {
	it.each(['ko', 'en', 'ja', 'zh-CN'] as const)('renders localized labels, actual counts and NIC metrics in %s', async locale => {
		initLocale(locale); render(InfrastructureTopology);
		await vi.waitFor(() => expect(screen.getByRole('heading', { name: t('details') + ' · eno1' })).toBeTruthy());
		expect(screen.getByRole('heading', { name: t('role.storage') })).toBeTruthy();
		expect(screen.getByRole('heading', { name: t('role.controller') })).toBeTruthy();
		expect(screen.getByText(t('bytes', { value: (8).toLocaleString(intlLocale()), unit: 'KiB' }))).toBeTruthy();
		expect(screen.getByText(t('packetsRate', { value: (2).toLocaleString(intlLocale()) }))).toBeTruthy();
		expect(screen.getByRole('combobox', { name: t('target') })).toBeTruthy();
		expect(screen.queryByText(t('denied'))).toBeNull();
	});
	it('moves only measured host↔NIC RX and removes motion on stale or unverified rerender', async () => {
		const host = makeHost(), view = render(EvidenceMap, { host, verified: true, selectedNic: 'eno1', onselect: vi.fn() });
		expect(view.container.querySelectorAll('[data-flow="rx"]')).toHaveLength(1); expect(view.container.querySelectorAll('[data-flow="tx"]')).toHaveLength(0);
		expect(view.container.querySelectorAll('[data-edge-kind="lldp"] .motion-flow')).toHaveLength(0);
		await view.rerender({ host: { ...host, observation_state: 'stale' }, verified: true, selectedNic: 'eno1', onselect: vi.fn() }); expect(view.container.querySelectorAll('.motion-flow')).toHaveLength(0);
		await view.rerender({ host, verified: false, selectedNic: 'eno1', onselect: vi.fn() }); expect(view.container.querySelectorAll('.motion-flow')).toHaveLength(0);
	});
	it('shows cumulative counters separately from unknown stale rates and no per-neighbor traffic columns', () => {
		const host = makeHost(); host.observation_state = 'stale'; render(NicDetails, { host, name: 'eno1', verified: true });
		const counterTable = screen.getByRole('table', { name: t('counters') }); const rxRow = within(counterTable).getByRole('row', { name: new RegExp(t('metric.rx_bytes')) });
		expect(within(rxRow).getByText(t('bytes', { value: (8).toLocaleString(intlLocale()), unit: 'KiB' }))).toBeTruthy(); expect(within(rxRow).getByText(t('unknown'))).toBeTruthy();
		const neighbors = screen.getByRole('table', { name: t('neighbors') }); expect(within(neighbors).getAllByRole('columnheader')).toHaveLength(3);
		expect(within(neighbors).queryByText(t('total'))).toBeNull(); expect(within(neighbors).queryByText(t('rate'))).toBeNull();
	});
	it.each([[0.5, 0.5, 'B'], [0, 0, 'B'], [1536, 1.5, 'KiB'], [3 * 1024 ** 3, 3, 'GiB']] as const)('formats the observed byte rate %s without invalid unit indexing', (rate, value, unit) => {
		const host = makeHost(); host.observation!.interfaces[0].rates.rx_bytes = rate;
		render(NicDetails, { host, name: 'eno1', verified: true });
		const row = within(screen.getByRole('table', { name: t('counters') })).getByRole('row', { name: new RegExp(t('metric.rx_bytes')) });
		expect(within(row).getByText(t('bytesRate', { value: value.toLocaleString(intlLocale(), { maximumFractionDigits: 2 }), unit }))).toBeTruthy();
	});
	it('renders each outbound hop, preserves * gaps and selects the actual route NIC', async () => {
		const host = makeHost(); host.traces = [makeTrace()]; const select = vi.fn();
		const view = render(TraceDetails, { host, verified: true, onselectnic: select });
		expect(view.container.querySelector('[data-hop="2"]')?.textContent).toContain('*'); expect(view.container.querySelector('[data-hop="3"]')?.textContent).toContain('203.0.113.9');
		const table = screen.getByRole('table', { name: `${t('outbound')} · 203.0.113.9` }); expect(within(table).getAllByRole('row')).toHaveLength(4);
		expect(within(table).getAllByText('*')).toHaveLength(2); expect(screen.queryByText(t('trace.stale'))).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: 'eno1' })); expect(select).toHaveBeenCalledWith('eno1');
		await view.rerender({ host, verified: false, onselectnic: select }); expect(screen.getByText(t('trace.stale'))).toBeTruthy();
	});
	it.each(['queued', 'running', 'expired', 'unsupported', 'error'] as const)('renders diagnostic %s without fabricated hops', status => {
		const host = makeHost(); host.traces = [makeTrace(status)]; const view = render(TraceDetails, { host, verified: true, onselectnic: vi.fn() });
		expect(screen.getByText(t(`trace.${status}`))).toBeTruthy(); expect(view.container.querySelectorAll('[data-hop]')).toHaveLength(0);
	});
	it('renders a directed service-port edge including an outside-inventory target and no reverse or moving edge', () => {
		const host = makeHost(); host.peer_probes = [{ target_host_id: 'storage:outside', address: '10.0.0.50', port: 443, status: 'down', checked_at: 1_800_000_000, latency_ms: null, error: 'connection_refused' }];
		const view = render(PeerProbeMap, { hosts: [host], verified: true, selectedId: host.id, onselect: vi.fn() });
		expect(view.container.querySelectorAll('[data-probe-source]')).toHaveLength(1); expect(view.container.querySelector('[data-probe-source="compute:node-a"][data-probe-target="storage:outside"]')).toBeTruthy();
		expect(screen.getByText(t('probeOutside'))).toBeTruthy(); expect(screen.getAllByText(t('probe.down'))).toHaveLength(2); expect(screen.getByText(t('probeError.connection_refused'))).toBeTruthy();
		expect(view.container.querySelectorAll('.motion-flow')).toHaveLength(0); expect(view.container.querySelector('[data-probe-source="storage:outside"]')).toBeNull();
	});
	it.each(['ko', 'en', 'ja', 'zh-CN'] as const)('localizes TCP-only meaning and stale probe outcomes in %s', locale => {
		initLocale(locale); const host = makeHost(); host.observation_state = 'stale';
		host.peer_probes = [{ target_host_id: 'controller:node-b', address: '10.0.0.20', port: 443, status: 'up', checked_at: 1_800_000_000, latency_ms: 2, error: null }];
		render(PeerProbeMap, { hosts: [host], verified: true, selectedId: host.id, onselect: vi.fn() });
		expect(screen.getByText(t('probeNotice'))).toBeTruthy(); expect(screen.getAllByText(t('probe.unknown'))).toHaveLength(2);
		expect(screen.queryByText(t('probe.up'))).toBeNull(); expect(screen.getByText(t('probeError.probe_stale'))).toBeTruthy();
	});
});

describe('connected page interactions and authorization', () => {
	it('submits exactly the selected host and configured target and displays returned job state', async () => {
		const snapshot = makeSnapshot(); read.mockResolvedValue(snapshot); render(InfrastructureTopology);
		await vi.waitFor(() => expect(screen.getByRole('button', { name: t('submit') })).toBeTruthy());
		await fireEvent.click(within(screen.getByRole('region', { name: t('network.diagram') })).getByRole('button', { name: 'node-c' }));
		const next = makeSnapshot(); next.hosts[2].traces = [makeTrace('running')]; read.mockResolvedValue(next);
		await fireEvent.click(screen.getByRole('button', { name: t('submit') }));
		await vi.waitFor(() => expect(submit).toHaveBeenCalledWith('storage:node-c', '203.0.113.9', expect.objectContaining({ projectId: 'project-a', token: 'token-a' }), expect.any(AbortSignal)));
		await vi.waitFor(() => expect(screen.getAllByText(t('trace.running')).length).toBeGreaterThan(0));
	});
	it('clears rendered host evidence immediately when authority becomes unready and ignores late result', async () => {
		render(InfrastructureTopology); await vi.waitFor(() => expect(screen.getAllByText('switch-a', { exact: false }).length).toBeGreaterThan(0));
		const pending = Promise.withResolvers<unknown>(); read.mockImplementationOnce(() => pending.promise);
		await fireEvent.click(screen.getByRole('button', { name: t('refresh') })); projectSwitching.set(true);
		await vi.waitFor(() => expect(screen.queryByRole('heading', { name: t('details') + ' · eno1' })).toBeNull());
		pending.resolve(makeSnapshot()); await Promise.resolve(); expect(screen.queryByRole('heading', { name: t('details') + ' · eno1' })).toBeNull();
	});
	it('does not request observations without verified system-admin authority', async () => {
		auth.update(state => ({ ...state, isSystemAdmin: false })); render(InfrastructureTopology); await Promise.resolve();
		expect(read).not.toHaveBeenCalled(); expect(screen.getByText(t('denied'))).toBeTruthy();
	});
	it('reactively removes the denied warning for an admin and restores it on authority loss', async () => {
		render(InfrastructureTopology); await vi.waitFor(() => expect(screen.getByRole('heading', { name: t('details') + ' · eno1' })).toBeTruthy()); expect(screen.queryByText(t('denied'))).toBeNull();
		auth.update(state => ({ ...state, isSystemAdmin: false })); await vi.waitFor(() => expect(screen.getByText(t('denied'))).toBeTruthy());
		expect(screen.queryByRole('heading', { name: t('details') + ' · eno1' })).toBeNull();
	});
	it('keeps fresh observer diagnostics usable when only inventory health is unavailable', async () => {
		const snapshot = makeSnapshot(); snapshot.inventory_error = 'monitoring_disabled'; read.mockResolvedValue(snapshot);
		const view = render(InfrastructureTopology); await vi.waitFor(() => expect(screen.getByText(t('inventoryWarning'))).toBeTruthy());
		expect((screen.getByRole('button', { name: t('submit') }) as HTMLButtonElement).disabled).toBe(false);
		expect(view.container.querySelectorAll('[data-flow="rx"]')).toHaveLength(1);
		expect(screen.getAllByText(t('state.up'))).toHaveLength(2);
	});
	it.each(['ko', 'en', 'ja', 'zh-CN'] as const)('disables discovery-only host diagnostics with observer context in %s', async locale => {
		initLocale(locale); const snapshot = makeSnapshot(); snapshot.hosts[0].observer_configured = false; read.mockResolvedValue(snapshot);
		render(InfrastructureTopology); await vi.waitFor(() => expect(screen.getByText(t('observerNotConfigured'))).toBeTruthy());
		expect((screen.getByRole('button', { name: t('submit') }) as HTMLButtonElement).disabled).toBe(true);
		expect((screen.getByRole('combobox', { name: t('target') }) as HTMLSelectElement).disabled).toBe(true); expect(submit).not.toHaveBeenCalled();
	});
	it.each(['ko', 'en', 'ja', 'zh-CN'] as const)('discloses bounded NIC and evidence omissions in %s', async locale => {
		initLocale(locale); const snapshot = makeSnapshot(); snapshot.hosts[0].observation!.interfaces_omitted = 17; snapshot.hosts[0].observation!.evidence_omitted = 53; read.mockResolvedValue(snapshot);
		render(InfrastructureTopology); await vi.waitFor(() => expect(screen.getByText(t('omittedNotice', { interfaces: (17).toLocaleString(intlLocale()), evidence: (53).toLocaleString(intlLocale()) }))).toBeTruthy());
		expect(screen.getByRole('combobox', { name: t('nic') }).querySelectorAll('option')).toHaveLength(1);
	});
	it('stops actual page polling while hidden and permanently on unmount', async () => {
		vi.useFakeTimers(); let visibility: DocumentVisibilityState = 'visible';
		vi.spyOn(document, 'visibilityState', 'get').mockImplementation(() => visibility);
		const view = render(InfrastructureTopology); await vi.advanceTimersByTimeAsync(0); expect(read).toHaveBeenCalledTimes(1);
		visibility = 'hidden'; document.dispatchEvent(new Event('visibilitychange')); await vi.advanceTimersByTimeAsync(30_000); expect(read).toHaveBeenCalledTimes(1);
		visibility = 'visible'; document.dispatchEvent(new Event('visibilitychange')); await vi.advanceTimersByTimeAsync(0); expect(read).toHaveBeenCalledTimes(2);
		view.unmount(); await vi.advanceTimersByTimeAsync(30_000); expect(read).toHaveBeenCalledTimes(2);
	});
	it('keeps RX flow visible during a pending poll, then expires it after thirty seconds', async () => {
		vi.useFakeTimers(); const view = render(InfrastructureTopology); await vi.advanceTimersByTimeAsync(0); expect(view.container.querySelectorAll('.motion-flow')).toHaveLength(1);
		const pending = Promise.withResolvers<unknown>(); read.mockImplementationOnce(() => pending.promise);
		await vi.advanceTimersByTimeAsync(10_000); expect(view.container.querySelectorAll('.motion-flow')).toHaveLength(1);
		await vi.advanceTimersByTimeAsync(19_999); expect(view.container.querySelectorAll('.motion-flow')).toHaveLength(1);
		await vi.advanceTimersByTimeAsync(1); expect(view.container.querySelectorAll('.motion-flow')).toHaveLength(0);
		pending.resolve(makeSnapshot()); await vi.advanceTimersByTimeAsync(0); expect(view.container.querySelectorAll('.motion-flow')).toHaveLength(1);
	});
	it('renders store-unavailable hosts with empty peer evidence instead of crashing the derived graph', async () => {
		const snapshot = makeSnapshot(); snapshot.error = 'topology_store_unavailable'; for (const host of snapshot.hosts) { host.observation = null; host.observation_state = 'unmeasured'; host.peer_probes = []; } read.mockResolvedValue(snapshot);
		const view = render(InfrastructureTopology); await vi.waitFor(() => expect(screen.getByText(t('unavailable'))).toBeTruthy());
		expect(screen.getByText(t('probeEmpty'))).toBeTruthy(); expect(view.container.querySelectorAll('.motion-flow')).toHaveLength(0);
	});
});

describe('integrated network map and per-NIC quantities', () => {
	it.each(['ko', 'en', 'ja', 'zh-CN'] as const)('renders separate RX/TX byte and packet quantities in %s', locale => {
		initLocale(locale); const host = makeHost();
		host.observation!.interfaces[0].rates = { rx_bytes: 1024, tx_bytes: 512, rx_packets: 7, tx_packets: 3 };
		const view = render(EvidenceMap, { host, verified: true, selectedNic: 'eno1', onselect: vi.fn() });
		const rx = view.container.querySelector('[data-rate="rx"]')!, tx = view.container.querySelector('[data-rate="tx"]')!;
		expect(rx.textContent).toContain(t('rx')); expect(rx.textContent).toContain(t('bytesRate', { value: '1', unit: 'KiB' })); expect(rx.textContent).toContain(t('packetsRate', { value: '7' }));
		expect(tx.textContent).toContain(t('tx')); expect(tx.textContent).toContain(t('bytesRate', { value: '512', unit: 'B' })); expect(tx.textContent).toContain(t('packetsRate', { value: '3' }));
		expect(view.container.querySelectorAll('[data-flow]')).toHaveLength(2);
		expect(screen.getByText(t('nicHistory', { nic: 'eno1' }))).toBeTruthy();
	});
	it.each(['stale', 'unmeasured', 'unverified', 'nonfinite'] as const)('shows honest %s NIC quantities with neutral dashed edges', state => {
		const host = makeHost();
		if (state === 'stale') host.observation_state = 'stale';
		if (state === 'unmeasured') host.observation!.sources.counters = 'error';
		if (state === 'nonfinite') host.observation!.interfaces[0].rates = { rx_bytes: NaN, tx_bytes: Infinity, rx_packets: NaN, tx_packets: Infinity };
		const view = render(EvidenceMap, { host, verified: state !== 'unverified', selectedNic: 'eno1', onselect: vi.fn() });
		for (const label of view.container.querySelectorAll('[data-rate]')) expect(label.textContent).toContain(t('unknown'));
		expect(view.container.querySelectorAll('.unknown')).toHaveLength(2); expect(view.container.querySelectorAll('[data-flow]')).toHaveLength(0);
		if (state === 'unverified') expect(screen.queryByText(t('nicHistory', { nic: 'eno1' }))).toBeNull();
	});
	it.each(['ko', 'en', 'ja', 'zh-CN'] as const)('merges routers once and provides selectable host buttons and ordered path details in %s', async locale => {
		initLocale(locale); const hosts = makeNetworkHosts(), select = vi.fn();
		const view = render(NetworkMap, { hosts, verified: true, selectedId: hosts[0].id, onselect: select });
		const region = screen.getByRole('region', { name: t('network.diagram') });
		expect(region.getAttribute('tabindex')).toBe('0');
		expect(view.container.querySelectorAll('[data-node-kind="router"]')).toHaveLength(1);
		expect(view.container.querySelectorAll('[data-node-kind="gap"]')).toHaveLength(2);
		expect(within(region).getByRole('button', { name: hosts[0].name }).getAttribute('aria-pressed')).toBe('true');
		await fireEvent.click(within(region).getByRole('button', { name: hosts[1].name })); expect(select).toHaveBeenCalledWith(hosts[1].id);
		const list = screen.getByRole('list', { name: t('network.pathLabel', { host: hosts[0].name, target: hosts[0].traces[0].target }) });
		expect(within(list).getAllByRole('listitem')).toHaveLength(4);
		expect(list.textContent).toContain('10.0.0.1'); expect(list.textContent).toContain('*'); expect(list.textContent).toContain('203.0.113.9');
		expect(screen.getByText(t('network.shared'))).toBeTruthy(); expect(screen.getByText(t('network.gapHelp'))).toBeTruthy();
	});
	it('shows target-IP partial replies as an unconfirmed destination and visibly stale paths', () => {
		const hosts = makeNetworkHosts(); hosts[0].traces[0].result!.reached = false; hosts[0].observation_state = 'stale';
		const view = render(NetworkMap, { hosts, verified: true, selectedId: hosts[0].id, onselect: vi.fn() });
		expect(view.container.querySelectorAll('[data-node-id="ip:203.0.113.9"]')).toHaveLength(1);
		expect(view.container.querySelector('[data-edge-state="unconfirmed"] .dashed')).toBeTruthy();
		expect(view.container.querySelector('[data-edge-state="unconfirmed"]')?.textContent).toContain(t('trace.stale'));
		const path = view.container.querySelector(`[data-path-id="${hosts[0].id}:trace-a"]`)!;
		expect(path.textContent).toContain(t('unreached')); expect(path.textContent).toContain(t('trace.stale'));
	});
	it('labels an observer-less host as unmeasured and lists a long no-reply run once', () => {
		const hosts = makeNetworkHosts(); hosts[1].observation_state = 'unmeasured'; hosts[1].observation = null; hosts[1].traces = [];
		const trace = hosts[0].traces[0]; trace.result!.reached = false;
		trace.result!.hops = [{ hop: 1, ip: '10.0.0.1', rtt_ms: 0.2 }, ...Array.from({ length: 15 }, (_, index) => ({ hop: index + 2, ip: null, rtt_ms: null }))];
		const view = render(NetworkMap, { hosts, verified: true, selectedId: hosts[0].id, onselect: vi.fn() });
		const second = view.container.querySelector(`[data-node-id="host:${hosts[1].id}"]`)!;
		expect(second.textContent).toContain(`${t('host')} · ${t('state.unmeasured')}`); expect(second.textContent).not.toContain(t('trace.stale'));
		const run = t('network.gapRun', { from: 2, to: 16, count: 15 });
		expect(view.container.querySelectorAll('[data-node-kind="gap"]')).toHaveLength(1);
		const list = screen.getByRole('list', { name: t('network.pathLabel', { host: hosts[0].name, target: trace.target }) });
		expect(within(list).getAllByRole('listitem')).toHaveLength(4); expect(list.textContent).toContain(run);
	});
	it.each(['queued', 'running', 'error', 'unsupported'] as const)('renders %s diagnosis without intermediate nodes', status => {
		const host = makeHost(); host.traces = [makeTrace(status)];
		const view = render(NetworkMap, { hosts: [host], verified: true, selectedId: host.id, onselect: vi.fn() });
		expect(view.container.querySelectorAll('[data-node-kind="router"], [data-node-kind="gap"]')).toHaveLength(0);
		expect(view.container.querySelector(`[data-edge-state="${status}"] .dashed`)).toBeTruthy();
		const list = screen.getByRole('list', { name: t('network.pathLabel', { host: host.name, target: host.traces[0].target }) });
		expect(within(list).getAllByRole('listitem')).toHaveLength(2);
	});
	it('keeps partially unknown quantities static without hiding independently measured values', () => {
		const host = makeHost(); host.observation!.interfaces[0].rates.rx_bytes = null;
		const view = render(EvidenceMap, { host, verified: true, selectedNic: 'eno1', onselect: vi.fn() });
		expect(view.container.querySelector('[data-rate="rx"]')?.textContent).toContain(t('packetsRate', { value: '2' }));
		expect(view.container.querySelector('[data-rate="rx"]')?.textContent).toContain(t('unknown'));
		expect(view.container.querySelector('.rx-line.unknown')).toBeTruthy();
		expect(view.container.querySelector('[data-flow="rx"]')).toBeNull();
	});
});
