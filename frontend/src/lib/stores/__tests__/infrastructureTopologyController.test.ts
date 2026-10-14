import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createInfrastructureTopologyController } from '../infrastructureTopologyController.svelte';
import { makeSnapshot, makeTrace } from '$lib/components/admin/infrastructure-topology/__tests__/fixtures';
import { ApiError } from '$lib/api/errors';
import type { InfrastructureTopologySnapshot, TopologyAuthority } from '$lib/types/infrastructureTopology';

const { read, submit } = vi.hoisted(() => ({ read: vi.fn(), submit: vi.fn() }));
vi.mock('$lib/api/infrastructureTopology', () => ({ getInfrastructureTopology: read, submitInfrastructureTrace: submit }));
const authority: TopologyAuthority = { token: 'token-a', userId: 'user-a', projectId: 'project-a', admin: true, ready: true };
const controllers: { dispose: () => void }[] = [];
function controller() {
	const ctrl = createInfrastructureTopologyController(); controllers.push(ctrl); ctrl.setAuthority(authority); return ctrl;
}
beforeEach(() => { vi.useFakeTimers(); read.mockReset().mockImplementation(() => Promise.resolve(makeSnapshot())); submit.mockReset().mockResolvedValue(makeTrace('queued')); });
afterEach(() => { controllers.splice(0).forEach(ctrl => ctrl.dispose()); vi.useRealTimers(); });

describe('infrastructure observation polling lifecycle', () => {
	it('loads once, waits ten seconds after completion and never overlaps reads', async () => {
		const pending = Promise.withResolvers<InfrastructureTopologySnapshot>(); read.mockImplementationOnce(() => pending.promise);
		const ctrl = controller(); await ctrl.load(); await vi.advanceTimersByTimeAsync(30_000);
		expect(read).toHaveBeenCalledTimes(1); expect(ctrl.loading).toBe(true);
		pending.resolve(makeSnapshot()); await vi.advanceTimersByTimeAsync(0);
		expect(ctrl.snapshot?.hosts).toHaveLength(3); expect(ctrl.verified).toBe(true);
		await vi.advanceTimersByTimeAsync(9_999); expect(read).toHaveBeenCalledTimes(1);
		await vi.advanceTimersByTimeAsync(1); expect(read).toHaveBeenCalledTimes(2);
	});
	it.each(['token', 'userId', 'projectId', 'admin', 'ready'] as const)('fences late reads across %s ABA transitions', async field => {
		const pending = Promise.withResolvers<InfrastructureTopologySnapshot>(); read.mockImplementationOnce(() => pending.promise);
		const ctrl = controller(); const signal = read.mock.calls[0][1] as AbortSignal;
		ctrl.setAuthority({ ...authority, [field]: field === 'admin' || field === 'ready' ? false : 'other' });
		ctrl.setAuthority(authority); expect(signal.aborted).toBe(true); expect(ctrl.snapshot).toBeNull();
		expect(read).toHaveBeenCalledTimes(1); // New scope waits for the obsolete read to settle.
		const old = makeSnapshot(); old.hosts[0].name = 'obsolete'; pending.resolve(old);
		await vi.advanceTimersByTimeAsync(0);
		expect(read).toHaveBeenCalledTimes(2); expect(ctrl.snapshot?.hosts[0].name).toBe('node-a');
	});
	it('does not reset selection or poll again for an identical authority', async () => {
		const ctrl = controller(); await vi.advanceTimersByTimeAsync(0); ctrl.selectHost('storage:node-c');
		ctrl.setAuthority({ ...authority }); expect(read).toHaveBeenCalledTimes(1); expect(ctrl.selectedId).toBe('storage:node-c');
	});
	it('preserves non-host graph selection across polling and clears it immediately on authority loss', async () => {
		const ctrl = controller(); await vi.advanceTimersByTimeAsync(0);
		ctrl.selectElement({ kind: 'node', id: 'switch:switch:sw-a' }); await ctrl.load();
		expect(ctrl.selection).toEqual({ kind: 'node', id: 'switch:switch:sw-a' });
		ctrl.setAuthority({ ...authority, ready: false }); expect(ctrl.selection).toBeNull(); expect(ctrl.snapshot).toBeNull();
	});
	it('retains verified live observations during the next poll rather than flickering stale', async () => {
		const ctrl = controller(); await vi.advanceTimersByTimeAsync(0); expect(ctrl.verified).toBe(true);
		const pending = Promise.withResolvers<InfrastructureTopologySnapshot>(); read.mockImplementationOnce(() => pending.promise);
		await vi.advanceTimersByTimeAsync(10_000); expect(ctrl.loading).toBe(true); expect(ctrl.verified).toBe(true);
		await vi.advanceTimersByTimeAsync(19_999); expect(read).toHaveBeenCalledTimes(2); expect(ctrl.verified).toBe(true);
		await vi.advanceTimersByTimeAsync(1); expect(ctrl.verified).toBe(false);
		pending.resolve(makeSnapshot()); await vi.advanceTimersByTimeAsync(0); expect(ctrl.verified).toBe(true);
	});
	it('aborts hidden reads, publishes no late result, resumes once and stops at disposal', async () => {
		const pending = Promise.withResolvers<InfrastructureTopologySnapshot>(); read.mockImplementationOnce(() => pending.promise);
		const ctrl = controller(); ctrl.setVisible(false); expect(read.mock.calls[0][1].aborted).toBe(true);
		pending.resolve(makeSnapshot()); await vi.advanceTimersByTimeAsync(30_000);
		expect(ctrl.snapshot).toBeNull(); expect(read).toHaveBeenCalledTimes(1);
		ctrl.setVisible(true); await vi.advanceTimersByTimeAsync(0); expect(read).toHaveBeenCalledTimes(2);
		ctrl.dispose(); await vi.advanceTimersByTimeAsync(60_000); expect(read).toHaveBeenCalledTimes(2); expect(ctrl.snapshot).toBeNull();
	});
	it('marks retained data unverified after failure and recovers on a subsequent read', async () => {
		const ctrl = controller(); await vi.advanceTimersByTimeAsync(0);
		read.mockRejectedValueOnce(new ApiError(503, 'unavailable')); await ctrl.load();
		expect(ctrl.snapshot?.hosts).toHaveLength(3); expect(ctrl.verified).toBe(false); expect(ctrl.error).toBe('unavailable');
		await ctrl.load(); expect(ctrl.verified).toBe(true); expect(ctrl.error).toBe('');
	});
	it('renders global source errors as unverified rather than empty healthy data', async () => {
		const snapshot = makeSnapshot(); snapshot.error = 'topology_store_unavailable'; read.mockResolvedValueOnce(snapshot);
		const ctrl = controller(); await vi.advanceTimersByTimeAsync(0); expect(ctrl.verified).toBe(false); expect(ctrl.snapshot?.error).toBe('topology_store_unavailable');
	});
});

describe('configured-target trace lifecycle', () => {
	it('rejects targets outside the server allowlist without making a request', async () => {
		const ctrl = controller(); await vi.advanceTimersByTimeAsync(0); ctrl.target = '169.254.169.254'; await ctrl.submitTrace(); expect(submit).not.toHaveBeenCalled();
	});
	it.each([false, true])('requires observer configuration, not a NIC sample, with configured=%s', async configured => {
		const snapshot = makeSnapshot(); snapshot.hosts[0].observer_configured = configured; snapshot.hosts[0].observation = null; snapshot.hosts[0].observation_state = 'unmeasured'; read.mockResolvedValue(snapshot);
		const ctrl = controller(); await vi.advanceTimersByTimeAsync(0); await ctrl.submitTrace(); expect(submit).toHaveBeenCalledTimes(configured ? 1 : 0);
	});
	it.each([
		[422, 'trace_target_not_allowed', 'targetDenied'],
		[429, 'trace_rate_limited', 'rateLimited'],
		[404, 'observer_not_configured', 'observerNotConfigured'],
		[409, 'trace_already_active', 'conflict'],
		[503, 'topology_request_failed', 'unavailable'],
	] as const)('maps %s backend detail %s without invalidating the verified snapshot', async (status, code, expected) => {
		const ctrl = controller(); await vi.advanceTimersByTimeAsync(0); submit.mockRejectedValueOnce(new ApiError(status, code, code)); await ctrl.submitTrace();
		expect(ctrl.traceError).toBe(expected); expect(ctrl.verified).toBe(true); expect(ctrl.snapshot?.hosts[0].observation_state).toBe('fresh');
		await ctrl.load(); expect(ctrl.traceError).toBe(expected); ctrl.target = '203.0.113.9'; expect(ctrl.traceError).toBe('');
	});
	it.each(['queued', 'running'] as const)('does not submit while a trace is %s', async status => {
		const snapshot = makeSnapshot(); snapshot.hosts[0].traces = [makeTrace(status)]; read.mockResolvedValueOnce(snapshot);
		const ctrl = controller(); await vi.advanceTimersByTimeAsync(0); await ctrl.submitTrace(); expect(submit).not.toHaveBeenCalled();
	});
	it('publishes queued → running → complete → expired from actual snapshots', async () => {
		const ctrl = controller(); await vi.advanceTimersByTimeAsync(0);
		for (const status of ['queued', 'running', 'complete', 'expired'] as const) {
			const snapshot = makeSnapshot(); snapshot.hosts[0].traces = [makeTrace(status)]; read.mockResolvedValueOnce(snapshot); await ctrl.load();
			expect(ctrl.snapshot?.hosts[0].traces[0].status).toBe(status);
		}
	});
	it('fences a pre-submission read so it cannot erase the returned queued job', async () => {
		const ctrl = controller(); await vi.advanceTimersByTimeAsync(0);
		const old = Promise.withResolvers<InfrastructureTopologySnapshot>(); read.mockImplementationOnce(() => old.promise); const loading = ctrl.load();
		await ctrl.submitTrace(); expect(ctrl.snapshot?.hosts[0].traces[0].status).toBe('queued'); expect(read.mock.calls[1][1].aborted).toBe(true);
		const after = makeSnapshot(); after.hosts[0].traces = [makeTrace('running')]; read.mockResolvedValueOnce(after);
		old.resolve(makeSnapshot()); await loading; await vi.advanceTimersByTimeAsync(0);
		expect(ctrl.snapshot?.hosts[0].traces[0].status).toBe('running');
	});
	it.each(['scope', 'selection', 'hidden', 'dispose'] as const)('ignores late submission after %s changes', async transition => {
		const ctrl = controller(); await vi.advanceTimersByTimeAsync(0); const pending = Promise.withResolvers<unknown>(); submit.mockImplementationOnce(() => pending.promise);
		const saving = ctrl.submitTrace(); expect(ctrl.busy).toBe(true);
		if (transition === 'scope') { ctrl.setAuthority({ ...authority, projectId: 'other' }); ctrl.setAuthority(authority); }
		else if (transition === 'selection') { ctrl.selectHost('controller:node-b'); ctrl.selectHost('compute:node-a'); }
		else if (transition === 'hidden') ctrl.setVisible(false);
		else ctrl.dispose();
		pending.resolve(makeTrace('queued')); await saving; await vi.advanceTimersByTimeAsync(0);
		expect(ctrl.snapshot?.hosts[0].traces ?? []).toEqual([]); expect(ctrl.busy).toBe(false);
	});
	it('ignores a late trace submission when an edge on the same reporting host is selected', async () => {
		const ctrl = controller(); await vi.advanceTimersByTimeAsync(0);
		const pending = Promise.withResolvers<unknown>(); submit.mockImplementationOnce(() => pending.promise);
		const saving = ctrl.submitTrace();
		ctrl.selectElement({ kind: 'edge', id: 'flow:observed-edge' }, 'compute:node-a');
		expect(ctrl.busy).toBe(false); expect(submit.mock.calls[0][3].aborted).toBe(true);
		pending.resolve(makeTrace('queued')); await saving;
		expect(ctrl.snapshot?.hosts[0].traces).toEqual([]); expect(ctrl.selection).toEqual({ kind: 'edge', id: 'flow:observed-edge' });
	});
	it('exposes unsupported and conflict without fabricating a successful path', async () => {
		const snapshot = makeSnapshot(); snapshot.hosts[0].traces = [{ ...makeTrace('unsupported'), result: { status: 'unsupported', hops: [], reached: false, error: 'traceroute_missing', source_interface: null, next_hop: null, completed_at: 1_800_000_000 } }];
		read.mockResolvedValueOnce(snapshot); const ctrl = controller(); await vi.advanceTimersByTimeAsync(0);
		expect(ctrl.snapshot?.hosts[0].traces[0].result?.hops).toEqual([]);
		submit.mockRejectedValueOnce(new ApiError(409, 'busy')); await ctrl.submitTrace(); expect(ctrl.traceError).toBe('conflict');
	});
});
