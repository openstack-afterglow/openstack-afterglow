import { getInfrastructureTopology, submitInfrastructureTrace } from '$lib/api/infrastructureTopology';
import { ApiError } from '$lib/api/errors';
import type { InfrastructureTopologySnapshot, TopologyAuthority, TopologySelection } from '$lib/types/infrastructureTopology';

export type TraceSubmissionError = 'denied' | 'conflict' | 'rateLimited' | 'targetDenied' | 'observerNotConfigured' | 'unavailable' | '';
export interface InfrastructureTopologyController {
	readonly snapshot: InfrastructureTopologySnapshot | null;
	readonly loading: boolean; readonly busy: boolean; readonly verified: boolean; readonly allowed: boolean;
	readonly error: 'denied' | 'unavailable' | ''; readonly traceError: TraceSubmissionError;
	readonly selectedId: string; readonly selection: TopologySelection | null;
	selectedNic: string; target: string;
	setAuthority(next: TopologyAuthority): void; setVisible(next: boolean): void;
	selectHost(id: string): void; selectElement(next: TopologySelection, hostId?: string): void;
	load(): Promise<void>; submitTrace(): Promise<void>; dispose(): void;
}

export function createInfrastructureTopologyController(): InfrastructureTopologyController {
	let authority = $state<TopologyAuthority>({ admin: false, ready: false });
	let disposed = $state(false), visible = $state(true);
	let epoch = 0, pendingReload = false;
	let timer: number | undefined, expiryTimer: number | undefined;
	let readAbort: AbortController | null = null, traceAbort: AbortController | null = null;
	let snapshot = $state<InfrastructureTopologySnapshot | null>(null);
	let selectedId = $state(''), selectedNic = $state(''), target = $state('');
	let selection = $state<TopologySelection | null>(null);
	let loading = $state(false), busy = $state(false), verified = $state(false);
	let error = $state<'denied' | 'unavailable' | ''>('');
	let traceError = $state<TraceSubmissionError>('');
	const allowed = () => !disposed && authority.admin && authority.ready && !!authority.token && !!authority.userId && !!authority.projectId;
	function stop() {
		clearTimeout(timer); timer = undefined;
		clearTimeout(expiryTimer); expiryTimer = undefined;
		readAbort?.abort(); traceAbort?.abort();
		verified = false; busy = false; traceError = '';
	}
	function setAuthority(next: TopologyAuthority) {
		if (next.token === authority.token && next.userId === authority.userId && next.projectId === authority.projectId && next.admin === authority.admin && next.ready === authority.ready) return;
		++epoch; stop(); authority = { ...next };
		snapshot = null; selection = null; selectedId = ''; selectedNic = ''; target = ''; error = ''; loading = false;
		pendingReload = allowed() && visible;
		if (pendingReload) void load();
	}
	function setVisible(next: boolean) {
		if (visible === next || disposed) return;
		visible = next; ++epoch; stop();
		pendingReload = next && allowed();
		if (pendingReload) void load();
	}
	function selectHost(id: string) {
		selection = id ? { kind: 'node', id: `host:${id}` } : null;
		if (selectedId === id) return;
		selectedId = id; selectedNic = snapshot?.hosts.find(host => host.id === id)?.observation?.interfaces[0]?.name ?? '';
		traceAbort?.abort(); traceAbort = null; busy = false; traceError = '';
	}
	function selectElement(next: TopologySelection, hostId?: string) {
		const changed = selection?.kind !== next.kind || selection.id !== next.id;
		if (changed) { traceAbort?.abort(); traceAbort = null; busy = false; traceError = ''; }
		if (hostId && snapshot?.hosts.some(host => host.id === hostId)) selectHost(hostId);
		selection = next;
	}
	async function load() {
		if (!allowed() || !visible) return;
		if (readAbort) return;
		pendingReload = false; clearTimeout(timer);
		const generation = epoch, captured = { ...authority }, abort = new AbortController();
		readAbort = abort; loading = true;
		try {
			const result = await getInfrastructureTopology(captured, abort.signal);
			if (disposed || generation !== epoch || !visible || abort.signal.aborted) return;
			snapshot = result; verified = result.enabled && !result.error; error = '';
			clearTimeout(expiryTimer);
			// The backend expires observations after 30 seconds. A pending poll must
			// not flicker a verified snapshot, but cannot keep it live indefinitely.
			expiryTimer = verified ? window.setTimeout(() => { verified = false; }, 30_000) : undefined;
			if (!result.hosts.some(host => host.id === selectedId)) selectHost(result.hosts[0]?.id ?? '');
			const host = result.hosts.find(host => host.id === selectedId);
			if (!host?.observation?.interfaces.some(nic => nic.name === selectedNic)) selectedNic = host?.observation?.interfaces[0]?.name ?? '';
			if (!result.trace_targets.includes(target)) target = result.trace_targets[0] ?? '';
		} catch (failure) {
			if (generation === epoch && !disposed && visible && !abort.signal.aborted) {
				verified = false; error = failure instanceof ApiError && (failure.status === 401 || failure.status === 403) ? 'denied' : 'unavailable';
				if (error === 'denied') { snapshot = null; selection = null; }
			}
		} finally {
			if (readAbort === abort) readAbort = null;
			if (generation === epoch && !disposed) loading = false;
			if (allowed() && visible) {
				if (pendingReload) void load();
				else timer = window.setTimeout(() => void load(), 10_000);
			}
		}
	}
	async function submitTrace() {
		const host = snapshot?.hosts.find(item => item.id === selectedId);
		if (!allowed() || !visible || !verified || busy || !host?.observer_configured || !snapshot?.trace_targets.includes(target) || host.traces.some(trace => trace.status === 'queued' || trace.status === 'running')) return;
		const generation = epoch, hostId = selectedId, captured = { ...authority }, abort = new AbortController();
		traceAbort = abort; busy = true; traceError = '';
		try {
			const job = await submitInfrastructureTrace(hostId, target, captured, abort.signal);
			if (disposed || generation !== epoch || traceAbort !== abort || abort.signal.aborted || selectedId !== hostId) return;
			const current = snapshot?.hosts.find(item => item.id === hostId);
			if (current) current.traces = [{ ...job, result: null }, ...current.traces.filter(trace => trace.id !== job.id)].slice(0, 20);
			++epoch; readAbort?.abort();
			pendingReload = true; void load();
		} catch (failure) {
			if (generation === epoch && traceAbort === abort && !abort.signal.aborted && !disposed) {
				const code = failure instanceof ApiError ? failure.code : undefined;
				traceError = code === 'trace_rate_limited' ? 'rateLimited' : code === 'trace_target_not_allowed' ? 'targetDenied' : code === 'observer_not_configured' ? 'observerNotConfigured' : code === 'trace_already_active' ? 'conflict' : failure instanceof ApiError && (failure.status === 401 || failure.status === 403) ? 'denied' : failure instanceof ApiError && failure.status === 409 ? 'conflict' : 'unavailable';
				if (traceError === 'denied') { verified = false; snapshot = null; selection = null; }
			}
		} finally {
			if (traceAbort === abort) { traceAbort = null; busy = false; }
		}
	}
	function dispose() {
		disposed = true; ++epoch; pendingReload = false; stop(); snapshot = null; selection = null;
	}
	return {
		get snapshot() { return snapshot; }, get loading() { return loading; }, get busy() { return busy; },
		get verified() { return verified && visible && allowed(); }, get error() { return error; }, get traceError() { return traceError; },
		get allowed() { return allowed(); }, get selectedId() { return selectedId; }, get selectedNic() { return selectedNic; },
		get selection() { return selection; }, selectElement,
		set selectedNic(value: string) { selectedNic = value; }, get target() { return target; }, set target(value: string) { target = value; traceError = ''; },
		setAuthority, setVisible, selectHost, load, submitTrace, dispose,
	};
}
