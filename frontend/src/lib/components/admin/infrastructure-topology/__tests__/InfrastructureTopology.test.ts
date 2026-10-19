import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { get } from 'svelte/store';
import { tick } from 'svelte';
import InfrastructureTopology from '../InfrastructureTopology.svelte';
import RadialWorkspace from '../RadialWorkspace.svelte';
import NicDetails from '../NicDetails.svelte';
import TraceDetails from '../TraceDetails.svelte';
import EvidenceMap from '../EvidenceMap.svelte';
import { ApiError } from '$lib/api/errors';
import type { InfrastructureTopologySnapshot, TopologyTrace } from '$lib/types/infrastructureTopology';
import { buildRadialGraph } from '../radialGraph';
import { edgeLabel } from '../presentation';
import { makeHost, makeMeshSnapshot, makeNetworkHosts, makeSnapshot, makeTrace } from './fixtures';
import { acceptAuthVerification, auth, authReady, getAuthVerificationEpoch, projectSwitching } from '$lib/stores/auth';
import { t } from '$lib/i18n/ns/infra-topology';
import { t as sharedT } from '$lib/i18n/ns/shared';
import { initLocale, intlLocale } from '$lib/i18n/runtime.svelte';

const { read, submit } = vi.hoisted(() => ({ read: vi.fn(), submit: vi.fn() }));
vi.mock('$lib/api/infrastructureTopology', () => ({ getInfrastructureTopology: read, submitInfrastructureTrace: submit }));
function verifyAuthority() {
	// Model root /auth/me acceptance separately from raw token/owner changes.
	expect(acceptAuthVerification(getAuthVerificationEpoch(), {})).toBe(true);
}
beforeEach(() => {
	initLocale('ko'); read.mockReset().mockImplementation(() => Promise.resolve(makeMeshSnapshot())); submit.mockReset().mockResolvedValue(makeTrace('queued'));
	auth.set({ ...get(auth), token: 'token-a', userId: 'user-a', projectId: 'project-a', isSystemAdmin: true }); verifyAuthority(); projectSwitching.set(false);
});
afterEach(() => { cleanup(); initLocale('ko'); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); });
const diagram = () => screen.getByRole('region', { name: t('workspace.diagram') });

describe('one radial workspace and integrated inspector', () => {
	it.each(['ko', 'en', 'ja', 'zh-CN'] as const)('shows real peer/port observations and localized NIC diagnostics in %s', async locale => {
		initLocale(locale); const view = render(InfrastructureTopology);
		await vi.waitFor(() => expect(screen.getByRole('heading', { name: `${t('details')} · eno1` })).toBeTruthy());
		expect(screen.getByRole('heading', { name: t('workspace.title') })).toBeTruthy(); expect(screen.getByText(t('workspace.coreHelp'))).toBeTruthy();
		expect(view.container.querySelectorAll('[data-edge-kind="flow"]')).toHaveLength(1); expect(view.container.querySelectorAll('[data-node-kind="switch"]')).toHaveLength(2); expect(view.container.querySelectorAll('[data-node-kind="port"]')).toHaveLength(3);
		expect(screen.getByText(t('bytes', { value: (8).toLocaleString(intlLocale()), unit: 'KiB' }))).toBeTruthy(); expect(screen.getByRole('combobox', { name: t('target') })).toBeTruthy();
		expect(screen.getByText('192.168.0.2')).toBeTruthy(); expect(screen.getByText(t('workspace.management'))).toBeTruthy();
	});
	it('switches from packets/s to bytes/s using the actual flow field without double counting receiver observations', async () => {
		const snapshot = makeMeshSnapshot(), select = vi.fn(); const view = render(RadialWorkspace, { graph: buildRadialGraph(snapshot, true), selection: null, onselect: select });
		const line = () => view.container.querySelector('[data-edge-kind="flow"]')!;
		expect(line().getAttribute('data-rate')).toBe('12');
		await fireEvent.click(within(screen.getByRole('group', { name: t('workspace.metric') })).getByRole('button', { name: t('workspace.Bps') }));
		expect(line().getAttribute('data-rate')).toBe('3072'); expect(line().getAttribute('data-rate')).not.toBe('5376');
	});
	it('supports native keyboard-list edge selection and retains both endpoint observations in the inspector', async () => {
		const snapshot = makeMeshSnapshot(), graph = buildRadialGraph(snapshot, true), flow = graph.edges.find(edge => edge.flow)!;
		read.mockResolvedValue(snapshot); const view = render(InfrastructureTopology);
		await vi.waitFor(() => expect(diagram()).toBeTruthy());
		const list = view.container.querySelector('.evidence-list')!;
		await fireEvent.click(list.querySelector('summary')!);
		await fireEvent.click(within(list as HTMLElement).getByRole('button', { name: edgeLabel(flow, graph, 'pps') }));
		const table = screen.getByRole('table', { name: t('workspace.observations') });
		expect(within(table).getAllByRole('row')).toHaveLength(3); expect(within(table).getByText(t('workspace.drawn'))).toBeTruthy();
		expect(within(table).getByText(t('packetsRate', { value: '12' }))).toBeTruthy(); expect(within(table).getByText(t('packetsRate', { value: '9' }))).toBeTruthy(); expect(within(table).queryByText(t('packetsRate', { value: '21' }))).toBeNull();
	});
	it('selects switch and port nodes into actual IF-MIB inventory/counters, then returns to host trace controls', async () => {
		render(InfrastructureTopology); await vi.waitFor(() => expect(diagram()).toBeTruthy());
		await fireEvent.click(within(diagram()).getByRole('button', { name: 'switch-a' }));
		const ports = screen.getByRole('table', { name: t('workspace.ports') }); expect(within(ports).getAllByRole('row')).toHaveLength(3);
		await fireEvent.click(within(ports).getByRole('button', { name: 'Ethernet6' }));
		expect(screen.getByRole('table', { name: t('workspace.portRates') })).toBeTruthy(); expect(screen.getByText(t('workspace.snmpNotice'))).toBeTruthy();
		await fireEvent.click(within(diagram()).getByRole('button', { name: 'node-c' })); expect(screen.getByRole('combobox', { name: t('target') })).toBeTruthy(); expect(screen.getByRole('heading', { name: `${t('details')} · eno1` })).toBeTruthy();
	});
	it('keeps passive LLDP switches/ports unknown without using high host NIC quantities as switch rates', async () => {
		const snapshot = makeMeshSnapshot(); snapshot.fabric.state = 'unconfigured'; snapshot.fabric.ports = []; for (const link of snapshot.fabric.links) link.target_port_id = null;
		snapshot.hosts[0].observation!.interfaces[0].rates.rx_packets = 999; read.mockResolvedValue(snapshot); const view = render(InfrastructureTopology);
		await vi.waitFor(() => expect(view.container.querySelector('[data-node-kind="switch"]')).toBeTruthy());
		for (const line of view.container.querySelectorAll('[data-edge-kind="physical"]')) expect(line.getAttribute('data-rate')).toBe('unknown');
		await fireEvent.click(within(diagram()).getByRole('button', { name: 'switch-a' })); expect(screen.getByText(t('workspace.portUnknown'))).toBeTruthy(); expect(screen.queryByRole('table', { name: t('workspace.portRates') })).toBeNull();
	});
	it.each(['ko', 'en', 'ja', 'zh-CN'] as const)('preserves counter-reset rate provenance in %s', async locale => {
		initLocale(locale); const snapshot = makeMeshSnapshot(); snapshot.flows = [{ ...snapshot.flows[0], packets_per_second: null, bytes_per_second: null, window_seconds: null, state: 'unmeasured', reason: 'counter_reset' }]; read.mockResolvedValue(snapshot);
		const view = render(InfrastructureTopology); await vi.waitFor(() => expect(diagram()).toBeTruthy());
		const graph = buildRadialGraph(snapshot, true), flow = graph.edges.find(edge => edge.flow)!;
		const list = view.container.querySelector('.evidence-list') as HTMLElement;
		await fireEvent.click(list.querySelector('summary')!);
		await fireEvent.click(within(list).getByRole('button', { name: edgeLabel(flow, graph, 'pps') }));
		expect(screen.getByRole('table', { name: t('workspace.observations') }).textContent).toContain(t('workspace.reason.counter_reset'));
		expect(view.container.querySelector('[data-edge-kind="flow"]')?.getAttribute('data-rate')).toBe('unknown');
	});
	it('keeps flow/physical/route/probe/trace layers independent without moving host layout', async () => {
		const snapshot = makeMeshSnapshot(); snapshot.hosts[0].traces = [makeTrace()]; snapshot.hosts[0].peer_probes = [{ target_host_id: snapshot.hosts[2].id, address: '10.0.0.30', port: 443, status: 'up', checked_at: 1, latency_ms: 2, error: null }];
		const view = render(RadialWorkspace, { graph: buildRadialGraph(snapshot, true), selection: null, onselect: vi.fn() });
		const host = view.container.querySelector('[data-node-id="host:compute:node-a"]') as HTMLElement, before = host.style.transform;
		expect(view.container.querySelectorAll('[data-edge-kind="trace"], [data-edge-kind="probe"], [data-edge-kind="route"]')).toHaveLength(0);
		for (const layer of ['trace', 'probe', 'route'] as const) await fireEvent.click(within(screen.getByRole('group', { name: t('workspace.layers') })).getByRole('button', { name: t(`workspace.layer.${layer}`) }));
		expect(view.container.querySelectorAll('[data-edge-kind="trace"]').length).toBeGreaterThan(0); expect(view.container.querySelectorAll('[data-edge-kind="probe"]')).toHaveLength(1); expect(view.container.querySelectorAll('[data-edge-kind="route"]')).toHaveLength(3); expect(host.style.transform).toBe(before);
	});
	it('renders the workspace and host inspector when an observer repeats a route from several kernel tables', async () => {
		// Production observers read every kernel table; identical route tuples are the same evidence.
		const snapshot = makeMeshSnapshot(), repeated = { interface: 'eno1', destination: 'fe80::/64', gateway: null, metric: 256 };
		for (const host of snapshot.hosts) host.observation!.routes = [repeated, { ...repeated }, { interface: 'eno1', destination: 'default', gateway: '10.0.0.1', metric: 100 }];
		read.mockResolvedValue(snapshot); const view = render(InfrastructureTopology);
		await vi.waitFor(() => expect(screen.getByRole('heading', { name: `${t('details')} · eno1` })).toBeTruthy());
		await fireEvent.click(within(screen.getByRole('group', { name: t('workspace.layers') })).getByRole('button', { name: t('workspace.layer.route') }));
		const routes = [...view.container.querySelectorAll('[data-edge-kind="route"]')].map(line => line.getAttribute('data-edge-id'));
		expect(routes).toHaveLength(snapshot.hosts.length * 2); expect(new Set(routes).size).toBe(routes.length);
	});
	it('pans, zooms and fits through keyboard controls while retaining selection', async () => {
		const snapshot = makeMeshSnapshot(), select = vi.fn(), graph = buildRadialGraph(snapshot, true); const view = render(RadialWorkspace, { graph, selection: { kind: 'node', id: 'host:compute:node-a' }, onselect: select });
		const host = view.container.querySelector('[data-node-id="host:compute:node-a"]') as HTMLElement, before = host.style.transform;
		await fireEvent.keyDown(diagram(), { key: 'ArrowRight' }); expect(host.style.transform).not.toBe(before);
		await fireEvent.keyDown(diagram(), { key: '+' }); const zoomed = host.style.transform;
		await fireEvent.keyDown(diagram(), { key: '0' }); expect(host.style.transform).not.toBe(zoomed);
		expect(within(diagram()).getByRole('button', { name: 'node-a' }).getAttribute('aria-pressed')).toBe('true'); expect(select).not.toHaveBeenCalled();
	});
	it('allows touch dragging from an edge, pinch zoom and explicit edge tapping without accidental selection', async () => {
		const select = vi.fn(), graph = buildRadialGraph(makeMeshSnapshot(), true);
		const view = render(RadialWorkspace, { graph, selection: null, onselect: select });
		const edge = view.container.querySelector('[data-edge-hit]')!, host = view.container.querySelector('[data-node-id="host:compute:node-a"]') as HTMLElement;
		async function pointer(target: Element, type: string, id: number, x: number, y: number) {
			const event = new MouseEvent(type, { bubbles: true, button: 0, clientX: x, clientY: y });
			Object.defineProperties(event, { pointerId: { value: id }, pointerType: { value: 'touch' } });
			await fireEvent(target, event);
		}
		const before = host.style.transform;
		await pointer(edge, 'pointerdown', 1, 100, 100); await pointer(diagram(), 'pointermove', 1, 130, 120); await pointer(diagram(), 'pointerup', 1, 130, 120);
		expect(host.style.transform).not.toBe(before); expect(select).not.toHaveBeenCalled();
		await pointer(diagram(), 'pointerdown', 2, 100, 100); await pointer(diagram(), 'pointerdown', 3, 200, 100);
		const panned = host.style.transform; await pointer(diagram(), 'pointermove', 3, 240, 100); expect(host.style.transform).not.toBe(panned);
		await pointer(diagram(), 'pointerup', 2, 100, 100); await pointer(diagram(), 'pointerup', 3, 240, 100); expect(select).not.toHaveBeenCalled();
		await pointer(edge, 'pointerdown', 4, 100, 100); await pointer(diagram(), 'pointerup', 4, 100, 100);
		expect(select).toHaveBeenCalledWith({ kind: 'edge', id: edge.getAttribute('data-edge-hit') });
	});
	it('uses the shared mobile modal inspector, closes on Escape and restores node focus', async () => {
		vi.stubGlobal('matchMedia', vi.fn((query: string) => ({ matches: query.includes('max-width: 767px'), media: query, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
		render(InfrastructureTopology); await vi.waitFor(() => expect(diagram()).toBeTruthy());
		const opener = within(diagram()).getByRole('button', { name: 'node-c' }); opener.focus(); await fireEvent.click(opener);
		const dialog = await screen.findByRole('dialog', { name: t('workspace.inspector') }); expect(dialog.getAttribute('aria-modal')).toBe('true'); expect(within(dialog).getByRole('combobox', { name: t('target') })).toBeTruthy();
		const close = within(dialog).getByRole('button', { name: sharedT('slidePanel.closeButton') }); await vi.waitFor(() => expect(document.activeElement).toBe(close));
		await fireEvent.keyDown(close, { key: 'Escape' }); await vi.waitFor(() => expect(screen.queryByRole('dialog')).toBeNull()); expect(document.activeElement).toBe(opener);
	});
});

describe('retained host diagnostics and authorization lifecycle', () => {
	it('submits exactly the selected host and configured target, then displays the actual returned job state', async () => {
		render(InfrastructureTopology); await vi.waitFor(() => expect(screen.getByRole('button', { name: t('submit') })).toBeTruthy());
		await fireEvent.click(within(diagram()).getByRole('button', { name: 'node-c' }));
		const next = makeMeshSnapshot(); next.hosts[2].traces = [makeTrace('running')]; read.mockResolvedValue(next);
		await fireEvent.click(screen.getByRole('button', { name: t('submit') }));
		await vi.waitFor(() => expect(submit).toHaveBeenCalledWith('storage:node-c', '203.0.113.9', expect.objectContaining({ projectId: 'project-a', token: 'token-a' }), expect.any(AbortSignal)));
		await vi.waitFor(() => expect(screen.getByText(t('trace.running'))).toBeTruthy());
	});
	it('clears graph and inspector immediately on authority transition and ignores late results', async () => {
		render(InfrastructureTopology); await vi.waitFor(() => expect(diagram()).toBeTruthy());
		const pending = Promise.withResolvers<unknown>(); read.mockImplementationOnce(() => pending.promise); await fireEvent.click(screen.getByRole('button', { name: t('refresh') })); projectSwitching.set(true);
		await vi.waitFor(() => expect(screen.queryByRole('region', { name: t('workspace.diagram') })).toBeNull());
		pending.resolve(makeMeshSnapshot()); await Promise.resolve(); expect(screen.queryByRole('heading', { name: `${t('details')} · eno1` })).toBeNull();
	});
	it('does not request observations without verified system-admin authority and reactively clears data on loss', async () => {
		auth.update(state => ({ ...state, isSystemAdmin: false })); render(InfrastructureTopology); await Promise.resolve(); expect(read).not.toHaveBeenCalled(); expect(screen.getByText(t('denied'))).toBeTruthy();
		auth.update(state => ({ ...state, isSystemAdmin: true })); await vi.waitFor(() => expect(diagram()).toBeTruthy()); expect(screen.queryByText(t('denied'))).toBeNull();
		auth.update(state => ({ ...state, isSystemAdmin: false })); await vi.waitFor(() => expect(screen.getByText(t('denied'))).toBeTruthy()); expect(screen.queryByRole('region', { name: t('workspace.diagram') })).toBeNull();
	});
	it('retains fresh observer diagnostics when inventory alone is unavailable', async () => {
		const snapshot = makeMeshSnapshot(); snapshot.inventory_error = 'monitoring_disabled'; read.mockResolvedValue(snapshot); const view = render(InfrastructureTopology);
		await vi.waitFor(() => expect(screen.getByText(t('inventoryWarning'))).toBeTruthy()); expect((screen.getByRole('button', { name: t('submit') }) as HTMLButtonElement).disabled).toBe(false); expect(view.container.querySelector('[data-edge-kind="flow"]')?.getAttribute('data-rate')).toBe('12');
	});
	it.each(['ko', 'en', 'ja', 'zh-CN'] as const)('disables discovery-only host diagnostics and discloses collection omissions in %s', async locale => {
		initLocale(locale); const snapshot = makeMeshSnapshot(); snapshot.hosts[0].observer_configured = false; snapshot.hosts[0].observation!.interfaces_omitted = 17; snapshot.hosts[0].observation!.evidence_omitted = 53; read.mockResolvedValue(snapshot);
		render(InfrastructureTopology); await vi.waitFor(() => expect(screen.getByText(t('observerNotConfigured'))).toBeTruthy());
		expect((screen.getByRole('button', { name: t('submit') }) as HTMLButtonElement).disabled).toBe(true); expect((screen.getByRole('combobox', { name: t('target') }) as HTMLSelectElement).disabled).toBe(true);
		expect(screen.getByText(t('omittedNotice', { interfaces: (17).toLocaleString(intlLocale()), evidence: (53).toLocaleString(intlLocale()) }))).toBeTruthy(); expect(submit).not.toHaveBeenCalled();
	});
	it('stops page polling while hidden and permanently after unmount', async () => {
		vi.useFakeTimers(); let visibility: DocumentVisibilityState = 'visible'; vi.spyOn(document, 'visibilityState', 'get').mockImplementation(() => visibility);
		const view = render(InfrastructureTopology); await vi.advanceTimersByTimeAsync(0); expect(read).toHaveBeenCalledTimes(1);
		visibility = 'hidden'; document.dispatchEvent(new Event('visibilitychange')); await vi.advanceTimersByTimeAsync(30_000); expect(read).toHaveBeenCalledTimes(1);
		visibility = 'visible'; document.dispatchEvent(new Event('visibilitychange')); await vi.advanceTimersByTimeAsync(0); expect(read).toHaveBeenCalledTimes(2);
		view.unmount(); await vi.advanceTimersByTimeAsync(30_000); expect(read).toHaveBeenCalledTimes(2);
	});
	it('keeps verified rate data during a pending poll, expires it at thirty seconds and recovers on a fresh snapshot', async () => {
		vi.useFakeTimers(); const view = render(InfrastructureTopology); await vi.advanceTimersByTimeAsync(0); const rate = () => view.container.querySelector('[data-edge-kind="flow"]')?.getAttribute('data-rate'); expect(rate()).toBe('12');
		const pending = Promise.withResolvers<unknown>(); read.mockImplementationOnce(() => pending.promise); await vi.advanceTimersByTimeAsync(10_000); expect(rate()).toBe('12');
		await vi.advanceTimersByTimeAsync(19_999); expect(rate()).toBe('12'); await vi.advanceTimersByTimeAsync(1); expect(rate()).toBe('unknown');
		pending.resolve(makeMeshSnapshot()); await vi.advanceTimersByTimeAsync(0); expect(rate()).toBe('12');
	});
	it('renders a store failure with unmeasured evidence rather than crashing or showing zero flow', async () => {
		const snapshot = makeSnapshot(); snapshot.error = 'topology_store_unavailable'; for (const host of snapshot.hosts) { host.observation = null; host.observation_state = 'unmeasured'; host.peer_probes = []; } read.mockResolvedValue(snapshot);
		const view = render(InfrastructureTopology); await vi.waitFor(() => expect(screen.getByText(t('unavailable'))).toBeTruthy()); expect(screen.getByText(t('noNics'))).toBeTruthy(); expect(view.container.querySelectorAll('[data-edge-kind="flow"]')).toHaveLength(0);
		expect(screen.getByText(t('source.flows')).parentElement?.querySelector('dd')?.textContent).toBe(t('state.unmeasured'));
	});
	it.each([false, true])('distinguishes absent observations from explicit unsupported collection: observed=%s', async observed => {
		const snapshot = makeSnapshot();
		if (!observed) { snapshot.hosts[0].observation = null; snapshot.hosts[0].observation_state = 'unmeasured'; }
		read.mockResolvedValue(snapshot); render(InfrastructureTopology);
		await vi.waitFor(() => expect(screen.getAllByText(t('source.flows'))[0].parentElement?.querySelector('dd')?.textContent).toBe(t(observed ? 'state.unsupported' : 'state.unmeasured')));
	});
	it('keeps cumulative NIC counters separate from unknown stale rates and does not add per-neighbor volume', () => {
		const host = makeHost(); host.observation_state = 'stale'; render(NicDetails, { host, name: 'eno1', verified: true });
		const table = screen.getByRole('table', { name: t('counters') }), row = within(table).getByRole('row', { name: new RegExp(t('metric.rx_bytes')) });
		expect(within(row).getByText(t('bytes', { value: (8).toLocaleString(intlLocale()), unit: 'KiB' }))).toBeTruthy(); expect(within(row).getByText(t('unknown'))).toBeTruthy();
		const neighbors = screen.getByRole('table', { name: t('neighbors') }); expect(within(neighbors).getAllByRole('columnheader')).toHaveLength(3); expect(within(neighbors).queryByText(t('rate'))).toBeNull();
		expect(within(neighbors).queryByText(t('total'))).toBeNull();
	});
	it('preserves outbound hop gaps and actual NIC selection in the trace inspector', async () => {
		const host = makeHost(); host.traces = [makeTrace()]; const select = vi.fn(), view = render(TraceDetails, { host, verified: true, onselectnic: select });
		expect(view.container.querySelector('[data-hop="2"]')?.textContent).toContain('*'); expect(view.container.querySelector('[data-hop="3"]')?.textContent).toContain('203.0.113.9');
		const table = screen.getByRole('table', { name: `${t('outbound')} · 203.0.113.9` });
		expect(within(table).getAllByRole('row')).toHaveLength(4); expect(within(table).getAllByText('*')).toHaveLength(2);
		expect(screen.queryByText(t('trace.stale'))).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: 'eno1' })); expect(select).toHaveBeenCalledWith('eno1'); await view.rerender({ host, verified: false, onselectnic: select }); expect(screen.getByText(t('trace.stale'))).toBeTruthy();
	});
	it.each(['queued', 'running', 'expired', 'unsupported', 'error'] as const)('retains trace %s without fabricated hops', status => {
		const host = makeHost(); host.traces = [makeTrace(status)]; const view = render(TraceDetails, { host, verified: true, onselectnic: vi.fn() });
		expect(screen.getByText(t(`trace.${status}`))).toBeTruthy(); expect(view.container.querySelectorAll('[data-hop]')).toHaveLength(0);
	});
});

describe('retained NIC evidence consumers', () => {
	it('moves only measured host↔NIC RX and removes motion on stale or unverified rerender', async () => {
		const host = makeHost(), view = render(EvidenceMap, { host, verified: true, selectedNic: 'eno1', onselect: vi.fn() });
		expect(view.container.querySelectorAll('[data-flow="rx"]')).toHaveLength(1); expect(view.container.querySelectorAll('[data-flow="tx"]')).toHaveLength(0);
		expect(view.container.querySelectorAll('[data-edge-kind="lldp"] .motion-flow')).toHaveLength(0);
		await view.rerender({ host: { ...host, observation_state: 'stale' }, verified: true, selectedNic: 'eno1', onselect: vi.fn() }); expect(view.container.querySelectorAll('.motion-flow')).toHaveLength(0);
		await view.rerender({ host, verified: false, selectedNic: 'eno1', onselect: vi.fn() }); expect(view.container.querySelectorAll('.motion-flow')).toHaveLength(0);
	});
	it.each([[0.5, 0.5, 'B'], [0, 0, 'B'], [1536, 1.5, 'KiB'], [3 * 1024 ** 3, 3, 'GiB']] as const)('formats the observed byte rate %s without invalid unit indexing', (rate, value, unit) => {
		const host = makeHost(); host.observation!.interfaces[0].rates.rx_bytes = rate;
		render(NicDetails, { host, name: 'eno1', verified: true });
		const row = within(screen.getByRole('table', { name: t('counters') })).getByRole('row', { name: new RegExp(t('metric.rx_bytes')) });
		expect(within(row).getByText(t('bytesRate', { value: value.toLocaleString(intlLocale(), { maximumFractionDigits: 2 }), unit }))).toBeTruthy();
	});
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
	it.each(['stale', 'unmeasured', 'unverified', 'nonfinite', 'negative'] as const)('shows honest %s NIC quantities with neutral dashed edges', state => {
		const host = makeHost();
		if (state === 'stale') host.observation_state = 'stale';
		if (state === 'unmeasured') host.observation!.sources.counters = 'error';
		if (state === 'nonfinite') host.observation!.interfaces[0].rates = { rx_bytes: NaN, tx_bytes: Infinity, rx_packets: NaN, tx_packets: Infinity };
		if (state === 'negative') host.observation!.interfaces[0].rates = { rx_bytes: -1, tx_bytes: -1, rx_packets: -1, tx_packets: -1 };
		const view = render(EvidenceMap, { host, verified: state !== 'unverified', selectedNic: 'eno1', onselect: vi.fn() });
		for (const label of view.container.querySelectorAll('[data-rate]')) expect(label.textContent).toContain(t('unknown'));
		expect(view.container.querySelectorAll('.unknown')).toHaveLength(2); expect(view.container.querySelectorAll('[data-flow]')).toHaveLength(0);
		if (state === 'unverified') expect(screen.queryByText(t('nicHistory', { nic: 'eno1' }))).toBeNull();
	});
	it('keeps partially unknown quantities static without hiding independently measured values', () => {
		const host = makeHost(); host.observation!.interfaces[0].rates.rx_bytes = null;
		const view = render(EvidenceMap, { host, verified: true, selectedNic: 'eno1', onselect: vi.fn() });
		expect(view.container.querySelector('[data-rate="rx"]')?.textContent).toContain(t('packetsRate', { value: '2' }));
		expect(view.container.querySelector('[data-rate="rx"]')?.textContent).toContain(t('unknown'));
		expect(view.container.querySelector('.rx-line.unknown')).toBeTruthy(); expect(view.container.querySelector('[data-flow="rx"]')).toBeNull();
	});
});

describe('network evidence migrated to the radial workspace', () => {
	it.each(['ko', 'en', 'ja', 'zh-CN'] as const)('merges shared responding IPs but keeps trace-local gaps and real host selection in %s', async locale => {
		initLocale(locale); const snapshot = makeMeshSnapshot(); snapshot.hosts = makeNetworkHosts(); read.mockResolvedValue(snapshot);
		const view = render(InfrastructureTopology); await vi.waitFor(() => expect(diagram()).toBeTruthy());
		await fireEvent.click(within(screen.getByRole('group', { name: t('workspace.layers') })).getByRole('button', { name: t('workspace.layer.trace') }));
		expect(view.container.querySelectorAll('[data-node-kind="router"]')).toHaveLength(1);
		expect(view.container.querySelectorAll('[data-node-kind="gap"]')).toHaveLength(2);
		await fireEvent.click(within(diagram()).getByRole('button', { name: '10.0.0.1' })); expect(screen.getByText(`${t('traceNotice')} ${t('network.shared')}`)).toBeTruthy();
		await fireEvent.click(within(diagram()).getByRole('button', { name: snapshot.hosts[1].name }));
		expect(within(diagram()).getByRole('button', { name: snapshot.hosts[1].name }).getAttribute('aria-pressed')).toBe('true');
		expect(screen.getByRole('table', { name: `${t('outbound')} · ${snapshot.hosts[1].traces[0].target}` })).toBeTruthy();
	});
	it.each(['ko', 'en', 'ja', 'zh-CN'] as const)('preserves directed TCP-only probe meaning and stale outcomes in %s', async locale => {
		initLocale(locale); const snapshot = makeMeshSnapshot(), host = snapshot.hosts[0]; host.observation_state = 'stale';
		host.peer_probes = [{ target_host_id: 'storage:outside', address: '10.0.0.50', port: 443, status: 'up', checked_at: 1_800_000_000, latency_ms: 2, error: null }]; read.mockResolvedValue(snapshot);
		const view = render(InfrastructureTopology); await vi.waitFor(() => expect(diagram()).toBeTruthy());
		await fireEvent.click(within(screen.getByRole('group', { name: t('workspace.layers') })).getByRole('button', { name: t('workspace.layer.probe') }));
		const graph = buildRadialGraph(snapshot, true), probe = graph.edges.find(edge => edge.probe)!;
		expect(probe.probe).toMatchObject({ source: host.id, targetInInventory: false, status: 'unknown', latency_ms: null });
		expect(view.container.querySelectorAll('[data-edge-kind="probe"]')).toHaveLength(1); expect(view.container.querySelectorAll('[data-node-kind="peer"]')).toHaveLength(1);
		const list = view.container.querySelector('.evidence-list') as HTMLElement; await fireEvent.click(list.querySelector('summary')!);
		await fireEvent.click(within(list).getByRole('button', { name: edgeLabel(probe, graph, 'pps') }));
		expect(screen.getAllByText(t('probeNotice')).length).toBeGreaterThan(0); expect(screen.getAllByText(t('probeError.probe_stale')).length).toBeGreaterThan(0);
		expect(screen.queryByText(t('probe.up'))).toBeNull(); expect(view.container.querySelectorAll('[data-edge-kind="probe"] .motion-flow')).toHaveLength(0);
	});
	it('renders an observed failed service-port probe without a reverse or moving edge', async () => {
		const snapshot = makeSnapshot(), host = snapshot.hosts[0];
		host.peer_probes = [{ target_host_id: 'storage:outside', address: '10.0.0.50', port: 443, status: 'down', checked_at: 1_800_000_000, latency_ms: null, error: 'connection_refused' }]; read.mockResolvedValue(snapshot);
		const view = render(InfrastructureTopology); await vi.waitFor(() => expect(diagram()).toBeTruthy());
		await fireEvent.click(within(screen.getByRole('group', { name: t('workspace.layers') })).getByRole('button', { name: t('workspace.layer.probe') }));
		const graph = buildRadialGraph(snapshot, true), probes = graph.edges.filter(edge => edge.probe);
		expect(probes).toHaveLength(1); expect(probes[0].probe).toMatchObject({ source: host.id, target_host_id: 'storage:outside', targetInInventory: false, status: 'down', error: 'connection_refused' });
		expect(view.container.querySelectorAll('[data-edge-kind="probe"]')).toHaveLength(1); expect(view.container.querySelectorAll('[data-edge-kind="probe"] .motion-flow')).toHaveLength(0);
		const list = view.container.querySelector('.evidence-list') as HTMLElement; await fireEvent.click(list.querySelector('summary')!);
		await fireEvent.click(within(list).getByRole('button', { name: edgeLabel(probes[0], graph, 'pps') }));
		expect(screen.getAllByText(t('probeError.connection_refused')).length).toBeGreaterThan(0);
	});
});

const authorityTransitions = ['token', 'userId', 'projectId', 'admin', 'ready', 'switching'] as const;
type AuthorityTransition = typeof authorityTransitions[number];
function changeAuthority(field: AuthorityTransition) {
	if (field === 'ready') authReady.set(false);
	else if (field === 'switching') projectSwitching.set(true);
	else if (field === 'admin') auth.update(state => ({ ...state, isSystemAdmin: false }));
	else auth.update(state => ({ ...state, [field]: `${field}-other` }));
}
function restoreAuthority() {
	auth.set({ ...get(auth), token: 'token-a', userId: 'user-a', projectId: 'project-a', isSystemAdmin: true }); verifyAuthority(); projectSwitching.set(false);
}

describe('rendered private owner and ABA fences', () => {
	it.each(authorityTransitions)('masks graph and inspector during %s transition and rejects an obsolete read', async field => {
		const initial = makeMeshSnapshot(); initial.hosts[0].name = 'private-owner-a'; read.mockResolvedValueOnce(initial);
		const view = render(InfrastructureTopology); await vi.waitFor(() => expect(diagram()).toBeTruthy());
		expect(within(screen.getByRole('region', { name: t('workspace.inspector') })).getByRole('heading', { name: 'private-owner-a', level: 3 })).toBeTruthy();
		const obsolete = Promise.withResolvers<InfrastructureTopologySnapshot>(), current = Promise.withResolvers<InfrastructureTopologySnapshot>();
		read.mockImplementationOnce(() => obsolete.promise).mockImplementationOnce(() => current.promise);
		await fireEvent.click(screen.getByRole('button', { name: t('refresh') })); const signal = read.mock.calls.at(-1)![1] as AbortSignal;
		const oldEpoch = getAuthVerificationEpoch();
		changeAuthority(field);
		await vi.waitFor(() => expect(screen.queryByRole('region', { name: t('workspace.diagram') })).toBeNull());
		expect(view.container.textContent).not.toContain('private-owner-a'); expect(screen.queryByRole('region', { name: t('workspace.inspector') })).toBeNull(); expect(signal.aborted).toBe(true);
		const old = makeMeshSnapshot(); old.hosts[0].name = 'obsolete-private-response'; obsolete.resolve(old);
		await obsolete.promise; await tick();
		expect(view.container.textContent).not.toContain('obsolete-private-response');
		expect(screen.queryByRole('region', { name: t('workspace.diagram') })).toBeNull();
		expect(screen.queryByRole('region', { name: t('workspace.inspector') })).toBeNull();
		if (field === 'admin' || field === 'ready' || field === 'switching') restoreAuthority();
		else {
			// Raw credentials cannot inherit the preceding owner's readiness.
			expect(get(authReady)).toBe(false);
			expect(acceptAuthVerification(oldEpoch, {})).toBe(false);
			verifyAuthority();
		}
		await tick();
		expect(screen.queryByRole('region', { name: t('workspace.diagram') })).toBeNull();
		expect(screen.queryByRole('region', { name: t('workspace.inspector') })).toBeNull();
		const fresh = makeMeshSnapshot(); fresh.hosts[0].name = 'current-private-owner'; current.resolve(fresh);
		await vi.waitFor(() => expect(within(diagram()).getByRole('button', { name: 'current-private-owner' })).toBeTruthy());
		expect(read).toHaveBeenLastCalledWith(expect.objectContaining({ token: get(auth).token, userId: get(auth).userId, projectId: get(auth).projectId, admin: true, ready: true }), expect.any(AbortSignal));
		expect(within(screen.getByRole('region', { name: t('workspace.inspector') })).getByRole('heading', { name: 'current-private-owner', level: 3 })).toBeTruthy();
		expect(view.container.textContent).not.toContain('private-owner-a');
		expect(view.container.textContent).not.toContain('obsolete-private-response');
	});
	it.each(authorityTransitions)('does not reveal retained or late private data after same-tick %s ABA', async field => {
		const initial = makeMeshSnapshot(); initial.hosts[0].name = 'private-before-aba'; read.mockResolvedValueOnce(initial);
		const view = render(InfrastructureTopology); await vi.waitFor(() => expect(diagram()).toBeTruthy());
		const obsolete = Promise.withResolvers<InfrastructureTopologySnapshot>(), current = Promise.withResolvers<InfrastructureTopologySnapshot>();
		read.mockImplementationOnce(() => obsolete.promise).mockImplementationOnce(() => current.promise);
		await fireEvent.click(screen.getByRole('button', { name: t('refresh') })); const signal = read.mock.calls.at(-1)![1] as AbortSignal;
		changeAuthority(field); restoreAuthority();
		await vi.waitFor(() => expect(screen.queryByRole('region', { name: t('workspace.diagram') })).toBeNull());
		expect(signal.aborted).toBe(true); expect(view.container.textContent).not.toContain('private-before-aba');
		expect(screen.queryByRole('region', { name: t('workspace.inspector') })).toBeNull();
		const old = makeMeshSnapshot(); old.hosts[0].name = 'obsolete-after-aba'; obsolete.resolve(old);
		await obsolete.promise; await tick();
		expect(screen.queryByRole('region', { name: t('workspace.diagram') })).toBeNull(); expect(view.container.textContent).not.toContain('obsolete-after-aba');
		expect(screen.queryByRole('region', { name: t('workspace.inspector') })).toBeNull();
		const fresh = makeMeshSnapshot(); fresh.hosts[0].name = 'fresh-after-aba'; current.resolve(fresh);
		await vi.waitFor(() => expect(within(diagram()).getByRole('button', { name: 'fresh-after-aba' })).toBeTruthy());
		expect(read).toHaveBeenLastCalledWith(expect.objectContaining({ token: 'token-a', userId: 'user-a', projectId: 'project-a', admin: true, ready: true }), expect.any(AbortSignal));
		expect(within(screen.getByRole('region', { name: t('workspace.inspector') })).getByRole('heading', { name: 'fresh-after-aba', level: 3 })).toBeTruthy();
		expect(view.container.textContent).not.toContain('private-before-aba');
		expect(view.container.textContent).not.toContain('obsolete-after-aba');
	});
	it.each(authorityTransitions.flatMap(field => [false, true].map(failure => ({ field, failure }))))('ignores late trace completion after $field ABA with failure=$failure', async ({ field, failure }) => {
		render(InfrastructureTopology); await vi.waitFor(() => expect(screen.getByRole('button', { name: t('submit') })).toBeTruthy());
		const pending = Promise.withResolvers<TopologyTrace>(), current = Promise.withResolvers<InfrastructureTopologySnapshot>();
		submit.mockImplementationOnce(() => pending.promise); read.mockImplementationOnce(() => current.promise);
		await fireEvent.click(screen.getByRole('button', { name: t('submit') })); const signal = submit.mock.calls[0][3] as AbortSignal;
		changeAuthority(field); restoreAuthority();
		await vi.waitFor(() => expect(screen.queryByRole('region', { name: t('workspace.diagram') })).toBeNull()); expect(signal.aborted).toBe(true);
		if (failure) pending.reject(new ApiError(503, 'unavailable')); else pending.resolve(makeTrace('queued'));
		await pending.promise.catch(() => undefined); await tick();
		current.resolve(makeMeshSnapshot()); await vi.waitFor(() => expect(screen.getByRole('button', { name: t('submit') })).toBeTruthy());
		expect(screen.queryByText(t('trace.queued'))).toBeNull(); expect(screen.queryByText(t('traceUnavailable'))).toBeNull(); expect(read).toHaveBeenCalledTimes(2);
	});
	it.each([false, true])('ignores late trace completion after host-selection ABA with failure=%s', async failure => {
		render(InfrastructureTopology); await vi.waitFor(() => expect(screen.getByRole('button', { name: t('submit') })).toBeTruthy());
		const pending = Promise.withResolvers<TopologyTrace>(); submit.mockImplementationOnce(() => pending.promise);
		await fireEvent.click(screen.getByRole('button', { name: t('submit') })); const signal = submit.mock.calls[0][3] as AbortSignal;
		await fireEvent.click(within(diagram()).getByRole('button', { name: 'node-c' })); await fireEvent.click(within(diagram()).getByRole('button', { name: 'node-a' })); expect(signal.aborted).toBe(true);
		if (failure) pending.reject(new ApiError(503, 'unavailable')); else pending.resolve(makeTrace('queued'));
		await pending.promise.catch(() => undefined); await tick();
		await vi.waitFor(() => expect(screen.getByRole('button', { name: t('submit') })).toBeTruthy());
		expect(screen.queryByText(t('trace.queued'))).toBeNull(); expect(screen.queryByText(t('traceUnavailable'))).toBeNull(); expect(read).toHaveBeenCalledTimes(1);
	});
});

describe('radial trace states and bounded gaps', () => {
	it.each([false, true])('renders a target-IP partial reply once without a self-edge, stale=%s', async stale => {
		const snapshot = makeSnapshot(), host = snapshot.hosts[0]; host.traces = [makeTrace()]; host.traces[0].result!.reached = false;
		if (stale) host.observation_state = 'stale';
		const graph = buildRadialGraph(snapshot, true), view = render(RadialWorkspace, { graph, selection: null, onselect: vi.fn() });
		await fireEvent.click(within(screen.getByRole('group', { name: t('workspace.layers') })).getByRole('button', { name: t('workspace.layer.trace') }));
		expect(view.container.querySelectorAll('[data-node-id="ip:203.0.113.9"]')).toHaveLength(1);
		const traces = [...view.container.querySelectorAll('[data-edge-kind="trace"]')]; expect(traces).toHaveLength(3);
		expect(traces.at(-1)?.getAttribute('data-edge-state')).toBe(stale ? 'stale' : 'unconfirmed');
		expect(traces.every(edge => edge.classList.contains('diagnostic') && edge.getAttribute('data-rate') === 'unknown')).toBe(true);
		expect(graph.edges.filter(edge => edge.layer === 'trace').every(edge => edge.source !== edge.target)).toBe(true);
	});
	it('keeps a long no-reply run trace-local and an observer-less host explicitly unmeasured', async () => {
		const snapshot = makeSnapshot(), host = snapshot.hosts[0], missing = snapshot.hosts[1]; host.traces = [makeTrace()];
		missing.observation = null; missing.observation_state = 'unmeasured';
		host.traces[0].result!.reached = false;
		host.traces[0].result!.hops = [{ hop: 1, ip: '10.0.0.1', rtt_ms: 0.2 }, ...Array.from({ length: 15 }, (_, index) => ({ hop: index + 2, ip: null, rtt_ms: null }))];
		read.mockResolvedValue(snapshot); const view = render(InfrastructureTopology); await vi.waitFor(() => expect(diagram()).toBeTruthy());
		await fireEvent.click(within(screen.getByRole('group', { name: t('workspace.layers') })).getByRole('button', { name: t('workspace.layer.trace') }));
		expect(view.container.querySelectorAll('[data-node-kind="gap"]')).toHaveLength(1); expect(within(diagram()).getByRole('button', { name: '* 2–16' })).toBeTruthy();
		await fireEvent.click(within(diagram()).getByRole('button', { name: '* 2–16' })); expect(screen.getByText(`${t('traceNotice')} ${t('network.gapHelp')}`)).toBeTruthy();
		await fireEvent.click(within(diagram()).getByRole('button', { name: missing.name }));
		const details = screen.getByRole('region', { name: t('host') }); expect(within(details).getAllByText(t('state.unmeasured')).length).toBeGreaterThan(0); expect(within(details).getByText(t('noNics'))).toBeTruthy();
	});
	it.each(['queued', 'running', 'error', 'unsupported'] as const)('renders %s diagnosis as a static destination edge without intermediate nodes', async status => {
		const snapshot = makeSnapshot(); snapshot.hosts[0].traces = [makeTrace(status)];
		const view = render(RadialWorkspace, { graph: buildRadialGraph(snapshot, true), selection: null, onselect: vi.fn() });
		await fireEvent.click(within(screen.getByRole('group', { name: t('workspace.layers') })).getByRole('button', { name: t('workspace.layer.trace') }));
		expect(view.container.querySelectorAll('[data-node-kind="router"], [data-node-kind="gap"]')).toHaveLength(0);
		const edge = view.container.querySelector('[data-edge-kind="trace"]')!;
		expect(view.container.querySelectorAll('[data-edge-kind="trace"]')).toHaveLength(1); expect(edge.getAttribute('data-edge-state')).toBe(status); expect(edge.getAttribute('data-rate')).toBe('unknown'); expect(edge.classList.contains('diagnostic')).toBe(true);
	});
});
