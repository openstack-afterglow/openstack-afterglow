import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/svelte';
import { createK3sProgress, type K3sProgressController } from '$lib/stores/k3sProgress.svelte';
import { K3S_CREATE_STEPS, K3S_DELETE_STEPS } from '$lib/components/k3sSteps';

import K3sProgressModal from '../K3sProgressModal.svelte';

let controller: K3sProgressController | null = null;

function begin(mode: 'create' | 'delete' = 'create'): K3sProgressController {
	controller = createK3sProgress();
	controller.begin(mode, '시작');
	return controller;
}

function renderModal(progress: K3sProgressController) {
	return render(K3sProgressModal, {
		controller: progress,
		activeSteps: progress.mode === 'delete' ? K3S_DELETE_STEPS : K3S_CREATE_STEPS,
		onClose: vi.fn(),
		onViewCluster: vi.fn(),
	});
}

function stepStates(steps = K3S_CREATE_STEPS): Record<string, string | null> {
	const list = screen.getByRole('list');
	const items = within(list).getAllByRole('listitem');
	expect(items).toHaveLength(steps.length);
	return Object.fromEntries(steps.map((step, index) => [
		step.id,
		items[index].getAttribute('data-state'),
	]));
}

afterEach(() => {
	controller?.end();
	controller = null;
	cleanup();
});

describe('K3sProgressModal', () => {
	it.each(['create', 'delete'] as const)('does not invent stage or percentage progress before a %s report', (mode) => {
		const progress = begin(mode);
		renderModal(progress);
		const steps = mode === 'delete' ? K3S_DELETE_STEPS : K3S_CREATE_STEPS;
		expect(Object.values(stepStates(steps))).toEqual(steps.map(() => 'pending'));
		const bar = screen.getByRole('progressbar');
		expect(bar.hasAttribute('aria-valuenow')).toBe(false);
		expect(bar.getAttribute('data-active')).toBe('true');
		expect(screen.queryByRole('alert')).toBeNull();
	});

	it('keeps running progress announcements outside a busy subtree', () => {
		const progress = begin();
		progress.apply({ step: 'server_volume', progress: 30, message: '서버 볼륨 준비 중', elapsed_seconds: 4 });
		renderModal(progress);
		const message = screen.getByRole('status');
		expect(message.textContent).toContain('서버 볼륨 준비 중');
		expect(message.closest('[aria-busy="true"]')).toBeNull();
		expect(stepStates().server_volume).toBe('active');
		expect(screen.getByRole('progressbar').getAttribute('data-active')).toBe('true');
	});

	it('attributes a delete failure using delete stages rather than create stages', () => {
		const progress = begin('delete');
		progress.apply({ step: 'delete_agent_vms', progress: 60, message: '에이전트 VM 정리', elapsed_seconds: 4 });
		progress.failWith('삭제 실패');
		renderModal(progress);
		expect(stepStates(K3S_DELETE_STEPS)).toEqual({
			delete_init: 'done',
			delete_lb_cleanup: 'done',
			delete_app_credential: 'done',
			delete_k8s_nodes: 'done',
			delete_agent_vms: 'failed',
			delete_server_vm: 'pending',
			delete_security_group: 'pending',
			delete_record: 'pending',
			completed: 'pending',
		});
		expect(screen.getByRole('progressbar').getAttribute('data-tone')).toBe('danger');
		expect(screen.getByRole('alert').textContent).toContain('삭제 실패');
	});
	it('attributes a stream failure to the last step reached, not to a later or the first step', () => {
		const progress = begin();
		progress.apply({ step: 'security_group', progress: 10, message: '보안 그룹', elapsed_seconds: 1 });
		progress.apply({ step: 'server_volume', progress: 30, message: '볼륨', elapsed_seconds: 4 });
		progress.apply({ step: 'server_ha_join', progress: 30, message: 'HA join', elapsed_seconds: 5 });
		progress.apply({ step: 'failed', progress: 30, message: '실패', error: 'quota exceeded', elapsed_seconds: 6 });

		renderModal(progress);

		expect(stepStates()).toEqual({
			security_group: 'done',
			server_volume: 'failed',
			server_creating: 'pending',
			waiting_callback: 'pending',
			completed: 'pending',
		});
		expect(screen.getByRole('progressbar').getAttribute('data-tone')).toBe('danger');
		expect(screen.getByRole('alert').textContent).toContain('quota exceeded');
	});

	it('attributes failWith after an unlisted HA substep to the last represented stage', () => {
		const progress = begin();
		progress.apply({ step: 'server_volume', progress: 30, message: '볼륨', elapsed_seconds: 4 });
		progress.apply({ step: 'server_ha_join', progress: 30, message: 'HA join', elapsed_seconds: 5 });
		progress.failWith('연결 종료');
		renderModal(progress);
		expect(stepStates().server_volume).toBe('failed');
		expect(stepStates().server_creating).toBe('pending');
		expect(screen.getByRole('alert').textContent).toContain('연결 종료');
	});

	it('marks no step failed when the request fails before any step is reported', () => {
		const progress = begin();
		progress.failWith('네트워크 오류');

		renderModal(progress);

		expect(Object.values(stepStates())).toEqual(['pending', 'pending', 'pending', 'pending', 'pending']);
		expect(screen.getByRole('progressbar').getAttribute('data-tone')).toBe('danger');
		expect(screen.getByRole('progressbar').getAttribute('data-active')).toBeNull();
	});

	it('shows every step done and stops the in-flight sheen once completed', () => {
		const progress = begin();
		progress.apply({ step: 'waiting_callback', progress: 80, message: '초기화', elapsed_seconds: 30 });
		progress.apply({ step: 'completed', progress: 100, message: '완료', cluster_id: 'cluster-1', elapsed_seconds: 42 });

		renderModal(progress);

		expect(Object.values(stepStates())).toEqual(['done', 'done', 'done', 'done', 'done']);
		const bar = screen.getByRole('progressbar');
		expect(bar.getAttribute('data-tone')).toBe('success');
		expect(bar.getAttribute('data-active')).toBeNull();
		expect(bar.getAttribute('aria-valuenow')).toBe('100');
	});
});
