import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { get } from 'svelte/store';
import InfrastructureTopology from '../InfrastructureTopology.svelte';
import RadialWorkspace from '../RadialWorkspace.svelte';
import NicDetails from '../NicDetails.svelte';
import TraceDetails from '../TraceDetails.svelte';
import { buildRadialGraph } from '../radialGraph';
import { edgeLabel } from '../presentation';
import { makeHost, makeMeshSnapshot, makeSnapshot, makeTrace } from './fixtures';
import { auth, authReady, projectSwitching } from '$lib/stores/auth';
import { t } from '$lib/i18n/ns/infra-topology';
import { t as sharedT } from '$lib/i18n/ns/shared';
import { initLocale, intlLocale } from '$lib/i18n/runtime.svelte';

const { read, submit } = vi.hoisted(() => ({ read: vi.fn(), submit: vi.fn() }));
vi.mock('$lib/api/infrastructureTopology', () => ({ getInfrastructureTopology: read, submitInfrastructureTrace: submit }));
beforeEach(() => {
	initLocale('ko'); read.mockReset().mockImplementation(() => Promise.resolve(makeMeshSnapshot())); submit.mockReset().mockResolvedValue(makeTrace('queued'));
	auth.set({ ...get(auth), token: 'token-a', userId: 'user-a', projectId: 'project-a', isSystemAdmin: true }); authReady.set(true); projectSwitching.set(false);
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
	});
	it('preserves outbound hop gaps and actual NIC selection in the trace inspector', async () => {
		const host = makeHost(); host.traces = [makeTrace()]; const select = vi.fn(), view = render(TraceDetails, { host, verified: true, onselectnic: select });
		expect(view.container.querySelector('[data-hop="2"]')?.textContent).toContain('*'); expect(view.container.querySelector('[data-hop="3"]')?.textContent).toContain('203.0.113.9');
		await fireEvent.click(screen.getByRole('button', { name: 'eno1' })); expect(select).toHaveBeenCalledWith('eno1'); await view.rerender({ host, verified: false, onselectnic: select }); expect(screen.getByText(t('trace.stale'))).toBeTruthy();
	});
	it.each(['queued', 'running', 'expired', 'unsupported', 'error'] as const)('retains trace %s without fabricated hops', status => {
		const host = makeHost(); host.traces = [makeTrace(status)]; const view = render(TraceDetails, { host, verified: true, onselectnic: vi.fn() });
		expect(screen.getByText(t(`trace.${status}`))).toBeTruthy(); expect(view.container.querySelectorAll('[data-hop]')).toHaveLength(0);
	});
});
