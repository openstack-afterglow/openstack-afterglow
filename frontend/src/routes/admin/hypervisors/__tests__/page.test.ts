import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import type { HypervisorServer } from '$lib/components/admin/hypervisors/HypervisorDetailPanel.svelte';
import type * as Reactivity from 'svelte/reactivity';

const viewport = vi.hoisted(() => ({ desktop: true }));
vi.mock('svelte/reactivity', async importOriginal => {
	const original = await importOriginal<typeof Reactivity>();
	return { ...original, MediaQuery: class { get current() { return viewport.desktop; } } };
});

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api }));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'admin-token', projectId: 'admin-project' }), authReady: writable(true), projectSwitching: writable(false) }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({ createAutoRefresh: () => ({ active: false, intervalSeconds: 30, intervalOptions: [15, 30, 60] }) }));
import Page from '../+page.svelte';

const server = { id: 'vm-1', name: 'production-vm', status: 'ACTIVE', project_id: 'project-1', flavor: 'small' };
function host(state = 'up', status = 'disabled', servers: HypervisorServer[] = [server]) {
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

beforeEach(() => {
	api.get.mockReset(); api.post.mockReset(); api.put.mockReset();
	viewport.desktop = true;
	Element.prototype.animate = vi.fn().mockReturnValue({ finished: Promise.resolve(), cancel: vi.fn(), play: vi.fn() });
	window.matchMedia = vi.fn().mockImplementation((query: string) => ({
		matches: true, media: query, onchange: null,
		addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
	}));
});
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
		expect(screen.queryByText('중단 (down)')).toBeNull();
		expect(api.put).not.toHaveBeenCalled();
		await fireEvent.click(within(section).getByRole('button', { name: '스케줄링 활성화' }));
		expect(api.put).not.toHaveBeenCalled();
		await fireEvent.click(within(section).getByRole('button', { name: '취소' }));
		expect(api.put).not.toHaveBeenCalled();
		await fireEvent.click(within(section).getByRole('button', { name: '스케줄링 활성화' }));
		await fireEvent.click(within(section).getByRole('button', { name: '스케줄링 활성화 확인' }));
		await waitFor(() => expect(screen.getByRole('cell', { name: '허용 (enabled)' })).toBeTruthy());
		expect(api.put).toHaveBeenCalledExactlyOnceWith('/api/v1/admin/hypervisors/hv-1/service', { status: 'enabled' }, 'admin-token', 'admin-project');
		expect(api.post).not.toHaveBeenCalled();
		expect(within(section).queryByRole('button', { name: '모든 인스턴스 마이그레이션' })).toBeNull();
	});

	it('requires a nonblank disable reason, reports failure, and never schedules migration automatically', async () => {
		serve(host('up', 'enabled'));
		api.put.mockRejectedValueOnce(new Error('Nova denied scheduling'));
		const section = await openHost();
		await fireEvent.click(within(section).getByRole('button', { name: '스케줄링 비활성화' }));
		const confirm = within(section).getByRole('button', { name: '스케줄링 비활성화 확인' }) as HTMLButtonElement;
		expect(confirm.disabled).toBe(true);
		await fireEvent.input(within(section).getByRole('textbox', { name: /^비활성화 사유/ }), { target: { value: '  maintenance  ' } });
		expect(confirm.disabled).toBe(false);
		await fireEvent.click(confirm);
		expect(await within(section).findByRole('alert')).toBeTruthy();
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
		const results = await within(section).findByRole('status', { name: '호스트 이동 요청 결과' });
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
		const submit = within(section).getByRole('button', { name: '대피 요청' }) as HTMLButtonElement;
		expect(submit.disabled).toBe(true);
		await fireEvent.click(within(section).getByRole('checkbox', { name: /펜싱되어 실행되지 않음/ }));
		expect(submit.disabled).toBe(false);
		api.post.mockRejectedValueOnce(new Error('Host not fenced'));
		await fireEvent.click(submit);
		expect(await within(section).findByRole('alert')).toBeTruthy();
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
		let detail = host();
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
		detail = host('up', 'disabled', []);
		pending.resolve({ source_host: 'compute-1', mode: 'migrate', items: [{ id: 'vm-1', name: 'production-vm', action: 'live-migrate', outcome: 'requested' }] });
		expect(await within(section).findByRole('status', { name: '호스트 이동 요청 결과' })).toBeTruthy();
		await waitFor(() => expect(within(section).queryByRole('button', { name: '모든 인스턴스 마이그레이션' })).toBeNull());
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

	it('shows actual domain, project and flavor names with full UUIDs even when names repeat', async () => {
		serve(host('up', 'enabled', [
			{ ...server, project_name: 'Repeated project', domain_id: 'domain-a', domain_name: 'Repeated domain', owner_status: 'known', flavor_id: 'flavor-a', flavor_name: 'Repeated flavor' },
			{ ...server, id: 'vm-2', name: 'second-vm', project_id: 'project-2', project_name: 'Repeated project', domain_id: 'domain-b', domain_name: 'Repeated domain', owner_status: 'known', flavor_id: 'flavor-b', flavor_name: 'Repeated flavor' },
		]));
		await openHost();
		const first = within(await screen.findByRole('group', { name: 'production-vm (vm-1)' }));
		const second = within(screen.getByRole('group', { name: 'second-vm (vm-2)' }));
		for (const [row, domain, project, flavor] of [[first, 'domain-a', 'project-1', 'flavor-a'], [second, 'domain-b', 'project-2', 'flavor-b']] as const) {
			expect(row.getByText('Repeated domain', { exact: false }).textContent).toContain(domain);
			expect(row.getByText('Repeated project', { exact: false }).textContent).toContain(project);
			expect(row.getByText('Repeated flavor', { exact: false }).textContent).toContain(flavor);
		}
		expect(api.get.mock.calls.some(([path]) => path === '/api/v1/admin/projects')).toBe(false);
	});

	it('keeps deleted and unknown ownership explicit, falls back to UUIDs and does not infer a user home', async () => {
		serve(host('up', 'enabled', [
			{ ...server, domain_id: null, domain_name: null, project_name: null, owner_status: 'deleted_project', flavor_id: 'deleted-flavor-id', flavor_name: null },
			{ ...server, id: 'vm-2', name: 'unknown-owner-vm', project_id: '', domain_id: null, domain_name: null, project_name: null, owner_status: 'unknown_owner', flavor_id: null, flavor_name: null, flavor: 'legacy-flavor' },
			{ ...server, id: 'vm-3', name: 'deleted-domain-vm', domain_id: 'deleted-domain-id', domain_name: null, project_name: null, owner_status: 'deleted_domain' },
		]));
		await openHost();
		const deleted = within(await screen.findByRole('group', { name: 'production-vm (vm-1)' }));
		expect(deleted.getByText('삭제된 프로젝트')).toBeTruthy();
		expect(deleted.getByText('project-1')).toBeTruthy();
		expect(deleted.getByText('deleted-flavor-id')).toBeTruthy();
		expect(deleted.queryByText('Project One')).toBeNull();
		const unknown = within(screen.getByRole('group', { name: 'unknown-owner-vm (vm-2)' }));
		expect(unknown.getAllByText('소유자 미확인').length).toBeGreaterThan(0);
		expect(unknown.getByText('legacy-flavor')).toBeTruthy();
		expect((unknown.getByRole('button', { name: 'unknown-owner-vm' }) as HTMLButtonElement).disabled).toBe(true);
		const deletedDomain = within(screen.getByRole('group', { name: 'deleted-domain-vm (vm-3)' }));
		expect(deletedDomain.getByText('삭제된 도메인')).toBeTruthy();
		expect(deletedDomain.getByText('deleted-domain-id')).toBeTruthy();
	});

	it('retains domain/project/flavor UUIDs and per-instance actions in compact host cards', async () => {
		viewport.desktop = false;
		serve(host('up', 'disabled', [{ ...server, domain_id: 'domain-a', domain_name: 'Domain', project_name: 'Project', flavor_id: 'flavor-a', flavor_name: 'Small' }]));
		render(Page);
		await fireEvent.click(await screen.findByRole('button', { name: 'compute-1' }));
		const open = await screen.findByRole('button', { name: 'production-vm' });
		const card = within(open.closest('article')!);
		expect(card.getByText('Domain', { exact: false, selector: 'dd' }).textContent).toContain('domain-a');
		expect(card.getByText('Project', { exact: false, selector: 'dd' }).textContent).toContain('project-1');
		expect(card.getByText('Small', { exact: false, selector: 'dd' }).textContent).toContain('flavor-a');
		expect(card.getByRole('button', { name: '이동' })).toBeTruthy();
	});
});
