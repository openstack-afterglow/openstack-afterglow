import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { writable } from 'svelte/store';
const mocks = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: { get: mocks.get }, getBaseUrl: () => 'http://fixture.invalid' }));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'one', sessionId: 'login', userId: 'user', identityDomainId: 'home', domainId: 'domain', projectId: 'project', roles: ['member'], canWrite: true }), authReady: writable(true), projectSwitching: writable(false), logoutInProgress: writable(false) }));
import { projectPermissions, refreshProjectPermissions } from '$lib/stores/servicePermissions';
import { auth, authReady, projectSwitching } from '$lib/stores/auth';
import { createK3sOperations } from './k3sOperations.svelte';
import { createK3sProgress, type K3sProgressController } from './k3sProgress.svelte';
import { K3S_CREATE_STEPS, k3sStagePercent, k3sProgressState } from '$lib/components/k3sSteps';

const stops: (() => void)[] = [];
const controllers: K3sProgressController[] = [];
const operation = { id: 'op', project_id: 'project', cluster_id: 'cluster', kind: 'create', status: 'WAITING_CALLBACK' };
const grant = { is_owner: false, is_manager: false, can_write: true, service_permissions: { drover: ['drover-inventory_reader', 'drover-clusters_editor'] } };
function start() {
	stops.push(projectPermissions.subscribe(() => {}));
	const tracker = createK3sOperations();
	stops.push(tracker.mount());
	const progress = createK3sProgress(); controllers.push(progress);
	tracker.track(progress, 'Cluster'); progress.begin('create');
	return { tracker, progress };
}
beforeEach(() => {
	vi.useFakeTimers(); vi.clearAllMocks(); sessionStorage.clear();
	auth.update(state => ({ ...state, token: 'one', projectId: 'project', roles: ['member'], canWrite: true }));
	authReady.set(true); projectSwitching.set(false);
	mocks.get.mockImplementation(async (path: string) => path.includes('/permissions') ? grant : path.includes('/events') ? [] : operation);
});
afterEach(() => { stops.splice(0).forEach(stop => stop()); controllers.splice(0).forEach(p => p.end()); vi.useRealTimers(); });

describe('Drover stage progress', () => {
	it('projects only observed stages and labels its independent raw provider percentage', () => {
		const p = createK3sProgress(); controllers.push(p); p.begin('create');
		expect(k3sStagePercent(p.step, p.stepTimings, K3S_CREATE_STEPS)).toBeNull();
		p.apply({ step: 'server_creating', progress: 10, message: 'VM', sequence: 3 });
		expect(k3sStagePercent(p.step, p.stepTimings, K3S_CREATE_STEPS)).toBe(50);
		expect(p.pct).toBe(10);
		p.apply({ step: 'security_group', progress: 5, message: 'late', sequence: 2 });
		expect(p.step).toBe('server_creating');
		p.apply({ step: 'server_ha_join', progress: 10, message: 'HA', sequence: 4 });
		expect(k3sProgressState(p.step, p.stepTimings, K3S_CREATE_STEPS).current).toBe('server_creating');
		expect(k3sStagePercent(p.step, p.stepTimings, K3S_CREATE_STEPS)).toBe(50);
		p.apply({ step: 'waiting_callback', progress: 10, message: 'initializing', sequence: 5 });
		expect(k3sStagePercent(p.step, p.stepTimings, K3S_CREATE_STEPS)).toBe(75);
		p.disconnect('network'); expect(p.isTerminal).toBe(false);
		expect(p.uncertain).toBe(true);
		p.apply({ step: 'completed', progress: 100, message: 'ready', sequence: 6 });
		expect(k3sStagePercent(p.step, p.stepTimings, K3S_CREATE_STEPS)).toBe(100);
		p.apply({ step: 'failed', progress: 0, message: 'stale', sequence: 7 });
		expect(p.step).toBe('completed');
	});
});

describe('Drover durable observation', () => {
	it('cannot dismiss ongoing/unknown operations and does not turn EOF into terminal', async () => {
		const { tracker, progress } = start();
		progress.apply({ step: 'waiting_callback', progress: 10, message: 'installing', operation_id: 'op', cluster_id: 'cluster', sequence: 1 });
		const id = tracker.entries[0].id;
		tracker.dismiss(id); expect(tracker.entries).toHaveLength(1);
		tracker.handoff(progress); await vi.advanceTimersByTimeAsync(1);
		expect(progress.isTerminal).toBe(false); expect(progress.uncertain).toBe(false);
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/k3s/operations/op', 'one', 'project', { refresh: true });
		mocks.get.mockImplementation(async (path: string) => path.includes('/events') ? [] : { ...operation, status: 'SUCCEEDED' });
		await tracker.refresh(); expect(progress.isTerminal).toBe(true);
		tracker.dismiss(id); expect(tracker.entries).toHaveLength(0);
	});
	it('keeps unavailable or missing operation lookup unknown, including 404', async () => {
		const { tracker, progress } = start();
		progress.apply({ step: 'server_creating', progress: 48, message: 'creating', operation_id: 'op', cluster_id: 'cluster' });
		mocks.get.mockRejectedValue(new Error('HTTP 404'));
		tracker.handoff(progress); await vi.advanceTimersByTimeAsync(1);
		expect(progress.isTerminal).toBe(false); expect(progress.uncertain).toBe(true);
		expect(progress.error).toContain('404');
		tracker.dismiss(tracker.entries[0].id); expect(tracker.entries).toHaveLength(1);
	});
	it('restores only tab observation metadata and resumes with GET rather than replaying POST', async () => {
		const { tracker, progress } = start();
		progress.apply({ step: 'waiting_callback', progress: 10, message: 'private log', operation_id: 'op', cluster_id: 'cluster', sequence: 4 });
		expect(sessionStorage.getItem('afterglow_drover_operations_v1')).not.toContain('private log');
		expect(sessionStorage.getItem('afterglow_drover_operations_v1')).not.toContain('"token"');
		const restored = createK3sOperations(); stops.push(restored.mount());
		await vi.advanceTimersByTimeAsync(1);
		expect(restored.entries).toHaveLength(1); controllers.push(restored.entries[0].progress);
		expect(restored.entries[0].progress.operationId).toBe('op');
		expect(restored.entries[0].progress.isTerminal).toBe(false);
		expect(mocks.get.mock.calls.every(([path]) => path.includes('/operations/') || path.endsWith('/permissions'))).toBe(true);
		tracker.dismiss(tracker.entries[0].id); expect(tracker.entries).toHaveLength(1);
	});
	it('discards a late native result across project ABA and hides the foreign-project dock', async () => {
		const { tracker, progress } = start();
		progress.apply({ step: 'waiting_callback', progress: 10, message: 'pending', operation_id: 'op', cluster_id: 'cluster' });
		const pending = Promise.withResolvers<typeof operation>(); mocks.get.mockReturnValueOnce(pending.promise);
		tracker.handoff(progress);
		projectSwitching.set(true); auth.update(state => ({ ...state, projectId: 'other' })); projectSwitching.set(false);
		expect(tracker.entries).toHaveLength(0);
		auth.update(state => ({ ...state, projectId: 'project' })); authReady.set(true);
		pending.resolve({ ...operation, status: 'SUCCEEDED' }); await vi.advanceTimersByTimeAsync(1);
		expect(progress.isTerminal).toBe(false); expect(tracker.owns(progress)).toBe(false);
	});
	it('preserves same-owner bearer refresh but hides revoked/reader authority and clears logout metadata', () => {
		const { tracker, progress } = start();
		auth.update(state => ({ ...state, token: 'renewed' }));
		expect(tracker.entries).toHaveLength(1); expect(tracker.owns(progress)).toBe(true);
		auth.update(state => ({ ...state, roles: ['reader'], canWrite: false }));
		expect(tracker.entries).toHaveLength(0); expect(tracker.owns(progress)).toBe(false);
		auth.update(state => ({ ...state, token: null }));
		expect(sessionStorage.getItem('afterglow_drover_operations_v1')).toBe('[]');
	});
});

it('preserves the stream and dock through real permission loading/error during same-owner bearer renewal', async () => {
	const { tracker, progress } = start();
	await vi.advanceTimersByTimeAsync(1);
	expect(tracker.owns(progress)).toBe(true);
	const loading = Promise.withResolvers<typeof grant>();
	mocks.get.mockReturnValueOnce(loading.promise);
	auth.update(state => ({ ...state, token: 'renewed' }));
	expect(tracker.entries).toHaveLength(1);
	expect(tracker.owns(progress)).toBe(true);
	loading.resolve(grant);
	await vi.advanceTimersByTimeAsync(1);
	expect(tracker.owns(progress)).toBe(true);
	const failed = Promise.withResolvers<typeof grant>();
	mocks.get.mockReturnValueOnce(failed.promise);
	auth.update(state => ({ ...state, token: 'renewed-again' }));
	expect(tracker.entries).toHaveLength(1);
	failed.reject(new Error('temporary policy lookup unavailable'));
	await vi.advanceTimersByTimeAsync(1);
	expect(tracker.entries).toHaveLength(1);
	expect(tracker.owns(progress)).toBe(true);
	mocks.get.mockResolvedValueOnce({ ...grant, service_permissions: { drover: [] } });
	await refreshProjectPermissions();
	expect(tracker.entries).toHaveLength(0);
	expect(tracker.owns(progress)).toBe(false);
});

it('restores confirmed quota refusal facts without storing raw diagnostics or adding unknown-outcome warnings', async () => {
	const { progress } = start();
	progress.failWith('synthetic-secret-diagnostic-not-for-storage', undefined, {
		reason: 'security_group_quota_exceeded', quota: { resource: 'security_group_rule', required: 7, available: 2 },
	});
	const saved = sessionStorage.getItem('afterglow_drover_operations_v1')!;
	expect(saved).not.toContain('synthetic-secret');
	expect(JSON.parse(saved)[0].refusalSummary).toEqual({
		reason: 'security_group_quota_exceeded', quota: { resource: 'security_group_rule', required: 7, available: 2 },
	});
	const restored = createK3sOperations(); stops.push(restored.mount());
	const recovered = restored.entries[0].progress; controllers.push(recovered);
	expect(recovered.isTerminal).toBe(true);
	expect(recovered.uncertain).toBe(false);
	expect(recovered.error).toContain('필요 7개, 사용 가능 2개');
	expect(recovered.error).toContain('관리자');
	expect(recovered.error).not.toContain('synthetic-secret');
});

it.each(['SUCCEEDED', 'FAILED'] as const)('re-reads exact terminal %s operation after reload and never marks the saved terminal unknown', async status => {
	const { progress } = start();
	progress.apply({ step: status === 'SUCCEEDED' ? 'completed' : 'failed', progress: status === 'SUCCEEDED' ? 100 : 48,
		message: 'terminal', error: 'raw-private-failure-not-for-storage', operation_id: 'op', cluster_id: 'cluster', sequence: 4 });
	expect(sessionStorage.getItem('afterglow_drover_operations_v1')).not.toContain('raw-private-failure');
	mocks.get.mockImplementation(async (path: string) => path.includes('/permissions') ? grant : path.includes('/events') ? [] : { ...operation, status, error: 'Native confirmed terminal failure' });
	const restored = createK3sOperations(); stops.push(restored.mount());
	const recovered = restored.entries[0].progress; controllers.push(recovered);
	expect(recovered.isTerminal).toBe(true);
	expect(recovered.uncertain).toBe(false);
	await vi.advanceTimersByTimeAsync(1);
	expect(mocks.get).toHaveBeenCalledWith('/api/v1/k3s/operations/op', 'one', 'project', { refresh: true });
	if (status === 'FAILED') expect(recovered.error).toBe('Native confirmed terminal failure');
	else expect(recovered.error).toBe('');
	expect(recovered.uncertain).toBe(false);
});
