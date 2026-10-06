import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { writable } from 'svelte/store';

const { api, autoRefreshCallback } = vi.hoisted(() => ({
	api: { get: vi.fn(), post: vi.fn(), put: vi.fn() },
	autoRefreshCallback: { current: null as (() => Promise<unknown>) | null },
}));
vi.mock('$lib/api/client', () => ({ api }));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'admin-token', projectId: 'admin-project' }) }));
vi.mock('$lib/stores/projectNames', () => ({
	projectNames: { subscribe: writable(new Map([['project-1', 'Project One']])).subscribe, load: vi.fn() },
}));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: (callback: () => Promise<unknown>) => {
		autoRefreshCallback.current = callback;
		return { active: false, intervalSeconds: 30, intervalOptions: [15, 30, 60] };
	},
}));
import { auth } from '$lib/stores/auth';
import Page from '../+page.svelte';
import type { RemovalInspection, RemovalResult } from '$lib/components/admin/hypervisors/removal';

const labels = {
	region: '호스트 제거 검토',
	check: '제거 점검 새로고침',
	metadata: '제거 메타데이터를 모두 검토했습니다',
	stopped: 'nova-compute 프로세스를 실제로 중지했고 계속 중지 상태로 유지합니다',
	hostname: '정확한 호스트명',
	reason: '제거 사유',
	remove: '호스트 등록 제거',
};

function host(id = 'hv-1', name = 'compute-1') {
	return {
		id, name, hypervisor_hostname: name, state: 'down', status: 'disabled', servers: [],
		service_id: `service-${id}`, service_host: name, service_state: 'down',
		service_updated_at: '2026-10-05T10:00:00Z', forced_down: false,
		hypervisor_type: 'QEMU', hypervisor_version: 1, host_ip: '10.0.0.1', host_time: '', uptime: '',
		vcpus: 16, vcpus_used: 0, vcpus_allowed: 16, memory_mb: 32768, memory_mb_used: 0,
		memory_allowed_mb: 32768, memory_size_mb: 32768, memory_used_mb: 0,
		local_gb: 100, local_gb_used: 0, local_disk_gb: 100, local_disk_used_gb: 0,
		running_vms: 0, cpu_info: null, cpu_model: null,
	};
}

function inspection(id = 'hv-1', hostname = 'compute-1', reviewToken = 'review-one'): RemovalInspection {
	return {
		report: {
			hypervisor_id: id, hostname, checked_at: new Date().toISOString(),
			service: {
				id: `service-${id}`, host: hostname, binary: 'nova-compute', state: 'down', status: 'disabled',
				updated_at: '2026-10-05T10:00:00Z', forced_down: false, disabled_reason: 'retired', zone: 'nova',
			},
			uptime: { status: 'unavailable', value: null, host_time: null },
			servers: [],
			history: {
				deleted_servers: [{ id: 'retained-vm', name: 'reviewed-retained-workload', status: 'DELETED', project_id: 'project-1', created_at: null }],
				migrations: [], note: 'Retained history is not proof that this host was never used.',
			},
			placement: { providers: [{ uuid: 'provider-1', name: hostname, parent_provider_uuid: null, generation: 4, allocations: {} }] },
			checks: [{ code: 'heartbeat', label: 'Heartbeat review', state: 'pass', detail: 'Heartbeat timed out without forced_down.' }],
			eligible: true,
		},
		review_token: reviewToken,
		expires_at: new Date(Date.now() + 300_000).toISOString(),
	};
}

function removalResult(status: RemovalResult['status'] = 'removal_unverified', verified = false): RemovalResult {
	return {
		status, verified, hypervisor_id: 'hv-1', hostname: 'compute-1', service_id: 'service-hv-1',
		detail: verified ? 'Registration absence verified.' : 'Provider absence could not be verified.',
		checks: [{ code: 'placement_absent', label: 'Provider absence', state: verified ? 'pass' : 'unknown', detail: verified ? 'Absent.' : 'Provider still visible.' }],
	};
}

function serve(first = host(), second = host('hv-2', 'compute-2')) {
	const inventory = { first, second, removed: false };
	api.get.mockImplementation(async (path: string) => {
		if (path === '/api/v1/admin/hypervisors') return inventory.removed ? [inventory.second] : [inventory.first, inventory.second];
		if (path === '/api/v1/admin/hypervisors/hv-1') return inventory.first;
		if (path === '/api/v1/admin/hypervisors/hv-2') return inventory.second;
		if (path === '/api/v1/admin/gpu-hosts') return { aggregated_hosts: [], gpu_types: [] };
		throw new Error(`Unexpected GET ${path}`);
	});
	api.post.mockImplementation(async (path: string) => {
		if (path.endsWith('/removal-check')) return path.includes('/hv-2/') ? inspection('hv-2', 'compute-2', 'review-two') : inspection();
		if (path.endsWith('/remove')) return removalResult();
		throw new Error(`Unexpected POST ${path}`);
	});
	return inventory;
}

function review() { return screen.getByRole('region', { name: labels.region }); }
function submit() { return within(review()).getByRole('button', { name: labels.remove }) as HTMLButtonElement; }
function removeCalls() { return api.post.mock.calls.filter(([path]) => path.endsWith('/remove')); }
function checkCalls() { return api.post.mock.calls.filter(([path]) => path.endsWith('/removal-check')); }

async function openHost(name = 'compute-1') {
	render(Page);
	await fireEvent.click(await screen.findByRole('button', { name }));
	await screen.findByRole('region', { name: labels.region });
}
async function checkHost() {
	await fireEvent.click(within(review()).getByRole('button', { name: labels.check }));
	await within(review()).findByText('reviewed-retained-workload', { exact: false });
	await waitFor(() => expect((within(review()).getByRole('button', { name: labels.check }) as HTMLButtonElement).disabled).toBe(false));
	await tick();
}
async function approve(values: Partial<{ metadata: boolean; stopped: boolean; hostname: string; reason: string }> = {}) {
	const desired = { metadata: true, stopped: true, hostname: 'compute-1', reason: 'Retiring drained compute host', ...values };
	for (const key of ['metadata', 'stopped'] as const) {
		const checkbox = within(review()).getByRole('checkbox', { name: labels[key] }) as HTMLInputElement;
		if (checkbox.checked !== desired[key]) await fireEvent.click(checkbox);
	}
	await fireEvent.input(within(review()).getByRole('textbox', { name: labels.hostname }), { target: { value: desired.hostname } });
	await fireEvent.input(within(review()).getByRole('textbox', { name: labels.reason }), { target: { value: desired.reason } });
}
function expectCannotRemove() {
	const button = within(review()).queryByRole('button', { name: labels.remove }) as HTMLButtonElement | null;
	if (button) expect(button.disabled).toBe(true);
}
function expectApprovalReset() {
	for (const label of [labels.metadata, labels.stopped]) {
		const checkbox = within(review()).queryByRole('checkbox', { name: label }) as HTMLInputElement | null;
		if (checkbox) expect(checkbox.checked).toBe(false);
	}
	for (const label of [labels.hostname, labels.reason]) {
		const input = within(review()).queryByRole('textbox', { name: label }) as HTMLInputElement | HTMLTextAreaElement | null;
		if (input) expect(input.value).toBe('');
	}
	expectCannotRemove();
}
async function backgroundRefresh() {
	expect(autoRefreshCallback.current).not.toBeNull();
	await autoRefreshCallback.current!();
	await tick();
}

beforeEach(() => {
	Element.prototype.animate = vi.fn().mockReturnValue({ finished: Promise.resolve(), cancel: vi.fn(), play: vi.fn() });
	window.matchMedia = vi.fn().mockImplementation((query: string) => ({
		matches: true, media: query, onchange: null,
		addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
	}));
	api.get.mockReset(); api.post.mockReset(); api.put.mockReset();
	autoRefreshCallback.current = null;
	auth.update(current => ({ ...current, token: 'admin-token', projectId: 'admin-project' }));
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

describe('admin hypervisor reviewed removal safety', () => {
	it.each([
		['metadata review', { metadata: false }],
		['actual stopped-process confirmation', { stopped: false }],
		['exact hostname', { hostname: 'COMPUTE-1' }],
		['nonblank reason', { reason: '   \n  ' }],
	] as const)('requires independent %s approval, not merely an eligible report', async (_name, missing) => {
		serve();
		await openHost();
		expect(checkCalls()).toHaveLength(0);
		await checkHost();
		await approve(missing);
		expect(submit().disabled).toBe(true);
		await fireEvent.click(submit());
		expect(removeCalls()).toHaveLength(0);
		await approve();
		expect(submit().disabled).toBe(false);
		// An eligible report and completed approvals still never automatically submit.
		expect(removeCalls()).toHaveLength(0);
	});

	it.each(['compute-1 ', ' compute-1', 'compute-2'])('rejects hostname %j even with both attestations and a reason', async hostname => {
		serve(); await openHost(); await checkHost(); await approve({ hostname });
		expect(submit().disabled).toBe(true);
		await fireEvent.click(submit());
		expect(removeCalls()).toHaveLength(0);
	});

	it.each(['blocked', 'unknown'] as const)('shows %s inspection evidence and cannot approve removal, even if a token is present', async state => {
		serve();
		const checked = inspection();
		checked.report.eligible = false;
		checked.report.checks = [{ code: 'placement', label: 'Placement evidence', state, detail: 'Allocations could not be cleared safely.' }];
		api.post.mockResolvedValueOnce(checked);
		await openHost(); await checkHost();
		expect(within(review()).getByText('Allocations could not be cleared safely.', { exact: false })).toBeTruthy();
		expectCannotRemove();
		expect(removeCalls()).toHaveLength(0);
	});

	it('resets all approvals at expiry and requires a fresh check before another approval', async () => {
		serve(); await openHost(); vi.useFakeTimers(); await checkHost(); await approve();
		expect(submit().disabled).toBe(false);
		await vi.advanceTimersByTimeAsync(300_001);
		await tick();
		expectApprovalReset();
		expect(removeCalls()).toHaveLength(0);
		vi.useRealTimers();
		await approve();
		expectCannotRemove();
		await fireEvent.click(submit());
		expect(removeCalls()).toHaveLength(0);
		await checkHost();
		expectApprovalReset();
		await approve();
		expect(submit().disabled).toBe(false);
	});

	it('excludes repeated checks, scheduling, refresh, host switching and close while inspection is pending', async () => {
		const inventory = serve();
		const pending = Promise.withResolvers<RemovalInspection>();
		api.post.mockReturnValueOnce(pending.promise);
		await openHost();
		const check = within(review()).getByRole('button', { name: labels.check });
		const refresh = screen.getByTitle('지금 새로고침');
		await fireEvent.click(check); await fireEvent.click(check);
		inventory.first = { ...inventory.first, state: 'up', status: 'enabled' };
		await fireEvent.click(screen.getByRole('button', { name: '스케줄링 활성화' }));
		await fireEvent.click(refresh);
		await fireEvent.click(screen.getByRole('button', { name: 'compute-2' }));
		await fireEvent.click(screen.getByRole('button', { name: '패널 닫기 버튼' }));
		await backgroundRefresh();
		expect(checkCalls()).toHaveLength(1);
		expect(api.put).not.toHaveBeenCalled();
		expect(removeCalls()).toHaveLength(0);
		expect(screen.getByRole('heading', { name: 'compute-1' })).toBeTruthy();
		expect(screen.queryByRole('heading', { name: 'compute-2' })).toBeNull();
		expect(within(screen.getByRole('button', { name: 'compute-1' }).closest('tr')!).getByRole('cell', { name: '중단 (down)' })).toBeTruthy();
		expect(screen.queryByRole('group', { name: '호스트 작업 확인' })).toBeNull();
		pending.resolve(inspection());
		await within(review()).findByText('reviewed-retained-workload', { exact: false });
		expectApprovalReset();
	});

	it('submits once, excludes other host operations while pending, and consumes approval before the response', async () => {
		const inventory = serve(); await openHost(); await checkHost(); await approve();
		const pending = Promise.withResolvers<RemovalResult>();
		api.post.mockReturnValueOnce(pending.promise);
		const button = submit();
		const refresh = screen.getByTitle('지금 새로고침');
		await fireEvent.click(button); await fireEvent.click(button);
		inventory.first = { ...inventory.first, state: 'up', status: 'enabled' };
		await fireEvent.click(within(review()).getByRole('button', { name: labels.check }));
		await fireEvent.click(screen.getByRole('button', { name: '스케줄링 활성화' }));
		await fireEvent.click(refresh);
		await fireEvent.click(screen.getByRole('button', { name: 'compute-2' }));
		await fireEvent.click(screen.getByRole('button', { name: '패널 닫기 버튼' }));
		await backgroundRefresh();
		expect(removeCalls()).toHaveLength(1);
		expect(checkCalls()).toHaveLength(1);
		expect(api.put).not.toHaveBeenCalled();
		expect(screen.getByRole('heading', { name: 'compute-1' })).toBeTruthy();
		expect(within(screen.getByRole('button', { name: 'compute-1' }).closest('tr')!).getByRole('cell', { name: '중단 (down)' })).toBeTruthy();
		expect(screen.queryByRole('group', { name: '호스트 작업 확인' })).toBeNull();
		expectCannotRemove();
		pending.resolve(removalResult());
		await within(review()).findByText('Provider absence could not be verified.', { exact: false });
		expectApprovalReset();
		expect(removeCalls()).toHaveLength(1);
	});

	it.each(['Review fingerprint changed; check again.', 'Removal request failed.'])('consumes a stale or failed token (%s) and permits retry only after a new check and new approvals', async failure => {
		serve(); await openHost(); await checkHost(); await approve();
		api.post.mockRejectedValueOnce(new Error(failure));
		await fireEvent.click(submit());
		await screen.findByText(failure, { exact: false });
		expectApprovalReset();
		expect(within(review()).getByText('reviewed-retained-workload', { exact: false })).toBeTruthy();
		await approve();
		expectCannotRemove();
		const retry = within(review()).queryByRole('button', { name: labels.remove });
		if (retry) await fireEvent.click(retry);
		expect(removeCalls()).toHaveLength(1);
		api.post.mockResolvedValueOnce(inspection('hv-1', 'compute-1', 'replacement-review'));
		await checkHost();
		expectApprovalReset();
		await approve(); await fireEvent.click(submit());
		await within(review()).findByText('Provider absence could not be verified.', { exact: false });
		expect(removeCalls()).toHaveLength(2);
		// Token identity matters here: the previously consumed approval must never be retried.
		expect(removeCalls().map(([, body]) => body.review_token)).toEqual(['review-one', 'replacement-review']);
	});

	it('rechecking resets prior approvals immediately and never reuses them for the new report', async () => {
		serve(); await openHost(); await checkHost(); await approve();
		const pending = Promise.withResolvers<RemovalInspection>();
		api.post.mockReturnValueOnce(pending.promise);
		await fireEvent.click(within(review()).getByRole('button', { name: labels.check }));
		expectApprovalReset();
		const fresh = inspection('hv-1', 'compute-1', 'replacement-review');
		fresh.report.history.deleted_servers[0].name = 'fresh-reviewed-workload';
		pending.resolve(fresh);
		await within(review()).findByText('fresh-reviewed-workload', { exact: false });
		expectApprovalReset();
		expect(removeCalls()).toHaveLength(0);
	});

	it('a failed reinspection retains evidence but invalidates the previously usable token', async () => {
		serve(); await openHost(); await checkHost(); await approve();
		api.post.mockRejectedValueOnce(new Error('Inspection source unavailable.'));
		await fireEvent.click(within(review()).getByRole('button', { name: labels.check }));
		await screen.findByText('Inspection source unavailable.', { exact: false });
		expectApprovalReset();
		expect(within(review()).getByText('reviewed-retained-workload', { exact: false })).toBeTruthy();
		await approve();
		expectCannotRemove();
		await fireEvent.click(submit());
		expect(removeCalls()).toHaveLength(0);
		await checkHost();
		expectApprovalReset();
		await approve();
		expect(submit().disabled).toBe(false);
		expect(removeCalls()).toHaveLength(0);
	});

	it('manual list refresh invalidates approval and refreshes the selected detail', async () => {
		const inventory = serve(); await openHost(); await checkHost(); await approve();
		inventory.first = { ...inventory.first, state: 'up', service_state: 'up' };
		await fireEvent.click(screen.getByTitle('지금 새로고침'));
		await waitFor(() => expect(screen.getByRole('cell', { name: '정상 (up)' })).toBeTruthy());
		expectApprovalReset();
		expect(screen.getByRole('heading', { name: 'compute-1' })).toBeTruthy();
		expect(removeCalls()).toHaveLength(0);
	});

	it('never carries a reviewed report or approvals to another host or back to the original host', async () => {
		serve(); await openHost(); await checkHost(); await approve();
		await fireEvent.click(screen.getByRole('button', { name: 'compute-2' }));
		await screen.findByRole('heading', { name: 'compute-2' });
		expect(within(review()).queryByText('reviewed-retained-workload', { exact: false })).toBeNull();
		expectApprovalReset();
		await checkHost(); await approve({ hostname: 'compute-2' });
		expect(submit().disabled).toBe(false);
		await fireEvent.click(screen.getByRole('button', { name: 'compute-1' }));
		await screen.findByRole('heading', { name: 'compute-1' });
		expectApprovalReset();
		expect(removeCalls()).toHaveLength(0);
	});

	it('clears report and approval on a project switch, including when the same host exists in the new project', async () => {
		serve(); await openHost(); await checkHost(); await approve();
		auth.update(current => ({ ...current, projectId: 'other-project' }));
		await waitFor(() => expect(screen.queryByRole('region', { name: labels.region })).toBeNull());
		await fireEvent.click(await screen.findByRole('button', { name: 'compute-1' }));
		await screen.findByRole('region', { name: labels.region });
		expect(within(review()).queryByText('reviewed-retained-workload', { exact: false })).toBeNull();
		expectApprovalReset();
		expect(removeCalls()).toHaveLength(0);
	});

	it.each([
		['liveness', { state: 'up' }],
		['scheduling', { status: 'enabled' }],
		['compute identity', { service_id: 'replacement-service' }],
		['service heartbeat', { service_updated_at: '2026-10-05T10:01:00Z' }],
		['service liveness', { service_state: 'up' }],
		['forced down', { forced_down: true }],
		['workload count', { running_vms: 1 }],
	] as const)('background changes to %s invalidate approvals in the visible selected detail', async (_name, changed) => {
		const inventory = serve(); await openHost(); await checkHost(); await approve();
		inventory.first = { ...inventory.first, ...changed };
		await backgroundRefresh();
		expectApprovalReset();
		expect(screen.getByRole('heading', { name: 'compute-1' })).toBeTruthy();
		expect(removeCalls()).toHaveLength(0);
	});

	it('background workload changes invalidate approval even if the reported VM count is unchanged', async () => {
		const inventory = serve(); await openHost(); await checkHost(); await approve();
		const changed = { ...inventory.first, servers: [{ id: 'new-vm', name: 'newly-discovered-workload', status: 'ACTIVE', project_id: 'project-1', flavor: 'small' }] };
		api.get.mockImplementation(async (path: string) => {
			if (path === '/api/v1/admin/hypervisors') return [changed, inventory.second];
			if (path === '/api/v1/admin/hypervisors/hv-1') return changed;
			if (path === '/api/v1/admin/gpu-hosts') return { aggregated_hosts: [], gpu_types: [] };
			throw new Error(`Unexpected GET ${path}`);
		});
		await backgroundRefresh();
		expect(screen.getByRole('button', { name: 'newly-discovered-workload' })).toBeTruthy();
		expectApprovalReset();
		expect(removeCalls()).toHaveLength(0);
	});

	it('incidental uptime and host-clock sampling preserve review and approvals without automatically checking or removing', async () => {
		const inventory = serve(); await openHost(); await checkHost(); await approve();
		inventory.first = { ...inventory.first, uptime: 'up 42 days', host_time: '10:42:00' };
		await backgroundRefresh();
		expect(within(review()).getByText('reviewed-retained-workload', { exact: false })).toBeTruthy();
		expect((within(review()).getByRole('checkbox', { name: labels.metadata }) as HTMLInputElement).checked).toBe(true);
		expect((within(review()).getByRole('checkbox', { name: labels.stopped }) as HTMLInputElement).checked).toBe(true);
		expect((within(review()).getByRole('textbox', { name: labels.hostname }) as HTMLInputElement).value).toBe('compute-1');
		expect((within(review()).getByRole('textbox', { name: labels.reason }) as HTMLTextAreaElement).value).toBe('Retiring drained compute host');
		expect(submit().disabled).toBe(false);
		expect(checkCalls()).toHaveLength(1);
		expect(removeCalls()).toHaveLength(0);
	});

	it.each([
		['removal_unverified', false],
		['removed', false],
		['removal_unverified', true],
	] as const)('does not close or claim removal for status=%s verified=%s, retains evidence, and never automatically resubmits', async (status, verified) => {
		serve(); await openHost(); await checkHost(); await approve();
		api.post.mockResolvedValueOnce(removalResult(status, verified));
		await fireEvent.click(submit());
		const outcome = await within(review()).findByRole('region', { name: '호스트 등록 제거 결과' });
		const visibleStatus = within(outcome).getByRole('status');
		expect(visibleStatus.classList.contains('alert-warning')).toBe(true);
		expect(visibleStatus.classList.contains('alert-success')).toBe(false);
		expectApprovalReset();
		expect(screen.getByRole('heading', { name: 'compute-1' })).toBeTruthy();
		expect(screen.getByRole('button', { name: 'compute-1' })).toBeTruthy();
		expect(within(review()).getByText('reviewed-retained-workload', { exact: false })).toBeTruthy();
		await approve();
		expectCannotRemove();
		const retry = within(review()).queryByRole('button', { name: labels.remove });
		if (retry) await fireEvent.click(retry);
		await tick();
		expect(removeCalls()).toHaveLength(1);
		await checkHost();
		expectApprovalReset();
		// Reinspection must not erase the preceding removal outcome evidence.
		expect(within(review()).getByText(verified ? 'Registration absence verified.' : 'Provider absence could not be verified.', { exact: false })).toBeTruthy();
		expect(removeCalls()).toHaveLength(1);
	});

	it('closes the selected host and refetches the visible inventory only for verified=true with status=removed', async () => {
		const inventory = serve(); await openHost(); await checkHost(); await approve();
		api.post.mockImplementationOnce(async () => {
			inventory.removed = true;
			return removalResult('removed', true);
		});
		await fireEvent.click(submit());
		await waitFor(() => expect(screen.queryByRole('region', { name: labels.region })).toBeNull());
		await waitFor(() => expect(screen.queryByRole('button', { name: 'compute-1' })).toBeNull());
		expect(screen.getByRole('button', { name: 'compute-2' })).toBeTruthy();
		expect(removeCalls()).toHaveLength(1);
	});

	it.each(['inspection', 'removal', 'detail refresh'] as const)('ignores a late %s response from the previous project, even after reopening the same host', async kind => {
		const inventory = serve(); await openHost();
		const lateCheck = Promise.withResolvers<RemovalInspection>();
		const lateRemove = Promise.withResolvers<RemovalResult>();
		const lateDetail = Promise.withResolvers<unknown>();
		let refreshing: Promise<unknown> | undefined;
		if (kind === 'inspection') {
			api.post.mockReturnValueOnce(lateCheck.promise);
			await fireEvent.click(within(review()).getByRole('button', { name: labels.check }));
		} else {
			await checkHost(); await approve();
			if (kind === 'removal') {
				api.post.mockReturnValueOnce(lateRemove.promise);
				await fireEvent.click(submit());
			} else {
				const normalGet = api.get.getMockImplementation()!;
				api.get.mockImplementation((path: string, ...args: unknown[]) => path === '/api/v1/admin/hypervisors/hv-1' ? lateDetail.promise : normalGet(path, ...args));
				refreshing = autoRefreshCallback.current!();
			}
		}
		auth.update(current => ({ ...current, projectId: 'other-project' }));
		await waitFor(() => expect(screen.queryByRole('region', { name: labels.region })).toBeNull());
		// New-project responses must be independently renderable while the old request is outstanding.
		serve();
		await fireEvent.click(await screen.findByRole('button', { name: 'compute-1' }));
		await screen.findByRole('region', { name: labels.region });
		await checkHost(); await approve();
		lateCheck.resolve(inspection('hv-1', 'old-project-host', 'obsolete-token'));
		lateRemove.resolve(removalResult('removed', true));
		lateDetail.resolve({ ...host(), state: 'up', service_state: 'up' });
		if (refreshing) await refreshing;
		await tick();
		expect(screen.getByRole('heading', { name: 'compute-1' })).toBeTruthy();
		expect(within(review()).queryByText('old-project-host', { exact: false })).toBeNull();
		expect(submit().disabled).toBe(false);
		expect((within(review()).getByRole('textbox', { name: labels.hostname }) as HTMLInputElement).value).toBe('compute-1');
		expect(removeCalls()).toHaveLength(kind === 'removal' ? 1 : 0);
	});

	it('ignores a late detail response after selecting another host', async () => {
		const inventory = serve();
		const pending = Promise.withResolvers<unknown>();
		api.get.mockImplementation(async (path: string) => {
			if (path === '/api/v1/admin/hypervisors') return [inventory.first, inventory.second];
			if (path === '/api/v1/admin/hypervisors/hv-1') return pending.promise;
			if (path === '/api/v1/admin/hypervisors/hv-2') return inventory.second;
			if (path === '/api/v1/admin/gpu-hosts') return { aggregated_hosts: [], gpu_types: [] };
			throw new Error(`Unexpected GET ${path}`);
		});
		render(Page);
		await fireEvent.click(await screen.findByRole('button', { name: 'compute-1' }));
		await fireEvent.click(screen.getByRole('button', { name: 'compute-2' }));
		await screen.findByRole('heading', { name: 'compute-2' });
		await checkHost(); await approve({ hostname: 'compute-2' });
		pending.resolve(inventory.first);
		await tick();
		expect(screen.getByRole('heading', { name: 'compute-2' })).toBeTruthy();
		expect(screen.queryByRole('heading', { name: 'compute-1' })).toBeNull();
		expect(submit().disabled).toBe(false);
		expect(removeCalls()).toHaveLength(0);
	});
});
