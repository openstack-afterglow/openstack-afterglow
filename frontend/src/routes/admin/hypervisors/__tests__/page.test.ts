import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { writable } from 'svelte/store';

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api }));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'admin-token', projectId: 'admin-project' }) }));
vi.mock('$lib/stores/projectNames', () => ({ projectNames: { subscribe: writable(new Map([['project-1', 'Project One']])).subscribe, load: vi.fn() } }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({ createAutoRefresh: () => ({ active: false, intervalSeconds: 30, intervalOptions: [15, 30, 60] }) }));
import Page from '../+page.svelte';

const server = { id: 'vm-1', name: 'production-vm', status: 'ACTIVE', project_id: 'project-1', flavor: 'small' };
function host(state = 'up', status = 'disabled', servers = [server]) {
	return {
		id: 'hv-1', name: 'compute-1', hypervisor_hostname: 'compute-1', state, status, servers,
		hypervisor_type: 'QEMU', hypervisor_version: 1, host_ip: '10.0.0.1', host_time: '', uptime: '', service_host: 'compute-1',
		vcpus: 16, vcpus_used: 4, vcpus_allowed: 16, memory_mb: 32768, memory_mb_used: 8192, memory_allowed_mb: 32768,
		memory_size_mb: 32768, memory_used_mb: 8192, local_gb: 100, local_gb_used: 20,
		local_disk_gb: 100, local_disk_used_gb: 20, running_vms: servers.length, cpu_info: null, cpu_model: null,
	};
}
function serve(detail = host()) {
	api.get.mockImplementation(async (path: string) => {
		if (path === '/api/v1/admin/hypervisors') return [{ ...detail, name: 'compute-1' }];
		if (path === '/api/v1/admin/hypervisors/hv-1') return detail;
		if (path === '/api/v1/admin/gpu-hosts') return { aggregated_hosts: [], gpu_types: [] };
		throw new Error(`Unexpected GET ${path}`);
	});
}
async function openHost() {
	render(Page);
	await fireEvent.click(await screen.findByRole('button', { name: 'compute-1' }));
	return screen.findByRole('region', { name: '호스트 운영 작업' });
}

beforeEach(() => { api.get.mockReset(); api.post.mockReset(); api.put.mockReset(); });
afterEach(cleanup);

describe('admin hypervisor host controls', () => {
	it('separates an up host from disabled scheduling; enabling requires an explicit confirmation and refreshes both views without moving VMs', async () => {
		let detail = host();
		serve(detail);
		api.get.mockImplementation(async (path: string) => path === '/api/v1/admin/gpu-hosts' ? { aggregated_hosts: [], gpu_types: [] }
			: path === '/api/v1/admin/hypervisors' ? [{ ...detail, name: 'compute-1' }] : detail);
		api.put.mockImplementation(async () => { detail = host('up', 'enabled'); return { status: 'enabled', service_host: 'compute-1' }; });
		const section = await openHost();
		expect(screen.getByRole('cell', { name: '정상 (up)' })).toBeTruthy();
		expect(screen.getByRole('cell', { name: '차단 (disabled)' })).toBeTruthy();
		// Detail panel repeats both independent states; up+disabled is not rendered as a host failure.
		expect(screen.getAllByText('정상 (up)')).toHaveLength(2);
		expect(screen.getAllByText('차단 (disabled)')).toHaveLength(2);
		expect(screen.queryByText('중단 (down)')).toBeNull();
		expect(api.put).not.toHaveBeenCalled();
		await fireEvent.click(within(section).getByRole('button', { name: '스케줄링 활성화' }));
		expect(api.put).not.toHaveBeenCalled();
		await fireEvent.click(within(section).getByRole('button', { name: '취소' }));
		expect(api.put).not.toHaveBeenCalled();
		await fireEvent.click(within(section).getByRole('button', { name: '스케줄링 활성화' }));
		await fireEvent.click(within(section).getByRole('button', { name: '스케줄링 활성화 확인' }));
		await waitFor(() => expect(screen.getByRole('cell', { name: '허용 (enabled)' })).toBeTruthy());
		expect(screen.getAllByText('허용 (enabled)')).toHaveLength(2);
		expect(api.put).toHaveBeenCalledExactlyOnceWith('/api/v1/admin/hypervisors/hv-1/service', { status: 'enabled' }, 'admin-token', 'admin-project');
		expect(api.post).not.toHaveBeenCalled();
		expect(api.get.mock.calls.filter(([path]) => path === '/api/v1/admin/hypervisors')).toHaveLength(2);
		expect(api.get.mock.calls.filter(([path]) => path === '/api/v1/admin/hypervisors/hv-1')).toHaveLength(2);
		expect(within(section).queryByRole('button', { name: '모든 인스턴스 마이그레이션' })).toBeNull();
	});

	it('requires a nonblank disable reason, reports failure, and never schedules migration automatically', async () => {
		serve(host('up', 'enabled'));
		api.put.mockRejectedValueOnce(new Error('Nova denied scheduling'));
		const section = await openHost();
		await fireEvent.click(within(section).getByRole('button', { name: '스케줄링 비활성화' }));
		const confirm = within(section).getByRole('button', { name: '스케줄링 비활성화 확인' }) as HTMLButtonElement;
		expect(confirm.disabled).toBe(true);
		await fireEvent.input(within(section).getByLabelText('비활성화 사유 (필수)'), { target: { value: '  maintenance  ' } });
		expect(confirm.disabled).toBe(false);
		await fireEvent.click(confirm);
		expect((await within(section).findByRole('alert')).textContent?.trim()).toBe('Nova denied scheduling');
		expect(api.put).toHaveBeenCalledExactlyOnceWith('/api/v1/admin/hypervisors/hv-1/service', { status: 'disabled', reason: 'maintenance' }, 'admin-token', 'admin-project');
		expect(api.post).not.toHaveBeenCalled();
	});

	it('offers whole-host migration only for up+disabled with instances and lists asynchronous server outcomes without claiming completion', async () => {
		serve();
		const pending = Promise.withResolvers<unknown>();
		api.post.mockReturnValueOnce(pending.promise);
		const section = await openHost();
		await fireEvent.click(within(section).getByRole('button', { name: '모든 인스턴스 마이그레이션' }));
		expect(api.post).not.toHaveBeenCalled();
		await fireEvent.click(within(section).getByRole('button', { name: '마이그레이션 요청' }));
		await waitFor(() => expect(api.post).toHaveBeenCalledOnce());
		expect((within(section).getByRole('button', { name: '요청 중...' }) as HTMLButtonElement).disabled).toBe(true);
		pending.resolve({ source_host: 'compute-1', mode: 'migrate', items: [
			{ id: 'vm-1', name: 'production-vm', action: 'live-migrate', outcome: 'requested' },
			{ id: 'vm-2', name: 'failed-vm', action: 'cold-migrate', outcome: 'failed', detail: 'No valid host' },
			{ id: 'vm-3', name: 'skipped-vm', action: null, outcome: 'skipped', detail: 'status ERROR' },
		] });
		expect(await within(section).findByText(/요청 1건 · 실패 1건 · 건너뜀 1건/)).toBeTruthy();
		const results = within(section).getByRole('status', { name: '호스트 이동 요청 결과' });
		expect(within(results).getByText(/production-vm \(vm-1\): 요청됨 · 라이브 마이그레이션/)).toBeTruthy();
		expect(within(results).getByText(/failed-vm \(vm-2\): 실패 · 콜드 마이그레이션 · No valid host/)).toBeTruthy();
		expect(within(results).getByText(/skipped-vm \(vm-3\): 건너뜀 · status ERROR/)).toBeTruthy();
		// Existing per-instance migration control remains available beside the bulk action.
		expect(screen.getByRole('button', { name: '이동' })).toBeTruthy();
		expect(within(section).getByText(/인스턴스 이동 완료를 의미하지 않습니다/)).toBeTruthy();
		expect(api.post).toHaveBeenCalledExactlyOnceWith('/api/v1/admin/hypervisors/hv-1/relocate', { mode: 'migrate' }, 'admin-token', 'admin-project');
	});

	it('requires positive fencing acknowledgement for down-host evacuation and hides bulk actions when empty', async () => {
		serve(host('down', 'disabled'));
		const section = await openHost();
		expect(within(section).queryByRole('button', { name: '모든 인스턴스 마이그레이션' })).toBeNull();
		await fireEvent.click(within(section).getByRole('button', { name: '모든 인스턴스 대피' }));
		expect(within(section).getByText('split-brain 위험')).toBeTruthy();
		const submit = within(section).getByRole('button', { name: '대피 요청' }) as HTMLButtonElement;
		expect(submit.disabled).toBe(true);
		await fireEvent.click(within(section).getByRole('checkbox', { name: /펜싱되어 실행되지 않음/ }));
		expect(submit.disabled).toBe(false);
		api.post.mockRejectedValueOnce(new Error('Host not fenced'));
		await fireEvent.click(submit);
		expect((await within(section).findByRole('alert')).textContent?.trim()).toBe('Host not fenced');
		expect(api.post).toHaveBeenCalledExactlyOnceWith('/api/v1/admin/hypervisors/hv-1/relocate', { mode: 'evacuate', fenced: true }, 'admin-token', 'admin-project');
		cleanup();
		serve(host('down', 'disabled', []));
		const empty = await openHost();
		expect(within(empty).queryByRole('button', { name: '모든 인스턴스 대피' })).toBeNull();
	});
	it('offers evacuation on a down host even if its scheduling status was enabled', async () => {
		serve(host('down', 'enabled'));
		const section = await openHost();
		expect(within(section).queryByRole('button', { name: '모든 인스턴스 마이그레이션' })).toBeNull();
		await fireEvent.click(within(section).getByRole('button', { name: '모든 인스턴스 대피' }));
		const submit = within(section).getByRole('button', { name: '대피 요청' }) as HTMLButtonElement;
		expect(submit.disabled).toBe(true);
		await fireEvent.click(within(section).getByRole('checkbox', { name: /펜싱되어 실행되지 않음/ }));
		await fireEvent.click(submit);
		await waitFor(() => expect(api.post).toHaveBeenCalledExactlyOnceWith(
			'/api/v1/admin/hypervisors/hv-1/relocate', { mode: 'evacuate', fenced: true }, 'admin-token', 'admin-project',
		));
	});

	it('submits a whole-host request once, blocks host switching while pending, then refreshes', async () => {
		const other = { ...host('up', 'enabled'), id: 'hv-2', name: 'compute-2', hypervisor_hostname: 'compute-2' };
		const detail = host();
		api.get.mockImplementation(async (path: string) => {
			if (path === '/api/v1/admin/hypervisors') return [{ ...detail, name: 'compute-1' }, other];
			if (path === '/api/v1/admin/gpu-hosts') return { aggregated_hosts: [], gpu_types: [] };
			if (path === '/api/v1/admin/hypervisors/hv-2') return other;
			return detail;
		});
		const pending = Promise.withResolvers<unknown>();
		api.post.mockReturnValueOnce(pending.promise);
		const section = await openHost();
		await fireEvent.click(within(section).getByRole('button', { name: '모든 인스턴스 마이그레이션' }));
		const submit = within(section).getByRole('button', { name: '마이그레이션 요청' });
		await fireEvent.click(submit);
		await fireEvent.click(submit);
		await fireEvent.click(screen.getByRole('button', { name: 'compute-2' }));
		expect(api.post).toHaveBeenCalledOnce();
		expect((within(section).getByRole('button', { name: '요청 중...' }) as HTMLButtonElement).disabled).toBe(true);
		expect(api.get.mock.calls.some(([path]) => path === '/api/v1/admin/hypervisors/hv-2')).toBe(false);
		const listCalls = api.get.mock.calls.filter(([path]) => path === '/api/v1/admin/hypervisors').length;
		pending.resolve({ source_host: 'compute-1', mode: 'migrate', items: [{ id: 'vm-1', name: 'production-vm', action: 'live-migrate', outcome: 'requested' }] });
		expect(await within(section).findByText(/요청 1건 · 실패 0건 · 건너뜀 0건/)).toBeTruthy();
		expect(api.get.mock.calls.filter(([path]) => path === '/api/v1/admin/hypervisors')).toHaveLength(listCalls + 1);
		expect(api.get.mock.calls.filter(([path]) => path === '/api/v1/admin/hypervisors/hv-1')).toHaveLength(2);
		expect(api.post).toHaveBeenCalledOnce();
	});

	it('does not carry a fencing acknowledgement from one down host to another', async () => {
		const first = host('down', 'disabled');
		const second = { ...host('down', 'disabled'), id: 'hv-2', name: 'compute-2', hypervisor_hostname: 'compute-2' };
		api.get.mockImplementation(async (path: string) => {
			if (path === '/api/v1/admin/hypervisors') return [first, second];
			if (path === '/api/v1/admin/gpu-hosts') return { aggregated_hosts: [], gpu_types: [] };
			return path.endsWith('hv-2') ? second : first;
		});
		const section = await openHost();
		await fireEvent.click(within(section).getByRole('button', { name: '모든 인스턴스 대피' }));
		await fireEvent.click(within(section).getByRole('checkbox', { name: /펜싱되어 실행되지 않음/ }));
		await fireEvent.click(screen.getByRole('button', { name: 'compute-2' }));
		const next = await screen.findByRole('region', { name: '호스트 운영 작업' });
		await waitFor(() => expect(screen.getByRole('heading', { name: 'compute-2' })).toBeTruthy());
		expect(within(next).queryByRole('button', { name: '대피 요청' })).toBeNull();
		await fireEvent.click(within(next).getByRole('button', { name: '모든 인스턴스 대피' }));
		expect((within(next).getByRole('checkbox', { name: /펜싱되어 실행되지 않음/ }) as HTMLInputElement).checked).toBe(false);
		expect((within(next).getByRole('button', { name: '대피 요청' }) as HTMLButtonElement).disabled).toBe(true);
		expect(api.post).not.toHaveBeenCalled();
	});
});
