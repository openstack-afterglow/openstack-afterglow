import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/svelte';
import { t } from '$lib/i18n/ns/vm-wizard';

const state = vi.hoisted(() => ({
	progressSteps: [
		{ id: 'boot_volume_creating', label: '부트 볼륨', description: 'OS 이미지 볼륨 생성' },
		{ id: 'server_creating', label: 'VM 생성', description: 'Nova 인스턴스 생성' },
		{ id: 'completed', label: '완료', description: '배포 완료' },
		{ id: 'failed', label: '실패', description: '배포 실패' },
	],
	currentStep: 'manila_preparing',
	progress: 0,
	progressMessage: '배포 시작...',
	elapsedSeconds: null as number | null,
	stepElapsedSeconds: {} as Record<string, number>,
}));
vi.mock('$lib/stores/vmCreateStore.svelte', () => ({ useVmCreate: () => state }));
import VmDeployProgress from '../VmDeployProgress.svelte';

afterEach(cleanup);
beforeEach(() => {
	state.currentStep = 'manila_preparing';
	state.progress = 0;
	state.progressMessage = '배포 시작...';
	state.elapsedSeconds = null;
	state.stepElapsedSeconds = {};
});

describe('VmDeployProgress', () => {
	it('does not guess a started stage when the initial Manila step is absent and omits failure', () => {
		render(VmDeployProgress);
		const list = screen.getByRole('list', { name: t('progress.stages') });
		expect(Array.from(list.children).map(item => item.getAttribute('data-state'))).toEqual(['pending', 'pending', 'pending']);
		expect(list.textContent).not.toContain('실패');
		expect(screen.getByRole('progressbar', { name: t('progress.percentage') }).getAttribute('aria-valuenow')).toBeNull();
	});

	it('shows whole-second total and per-stage durations with the reported stage and live message', () => {
		state.currentStep = 'server_creating';
		state.progress = 60;
		state.elapsedSeconds = 12.9;
		state.stepElapsedSeconds = { boot_volume_creating: 3.2, server_creating: 4.8 };
		state.progressMessage = 'Nova 인스턴스 생성 중';
		render(VmDeployProgress);
		const list = screen.getByRole('list', { name: t('progress.stages') });
		expect(Array.from(list.children).map(item => item.getAttribute('data-state'))).toEqual(['done', 'active', 'pending']);
		expect(screen.getByRole('progressbar', { name: t('progress.percentage') }).getAttribute('aria-valuenow')).toBe('60');
		expect(screen.getByText(t('progress.elapsed', { seconds: 12 }))).toBeTruthy();
		expect(within(list.children[0] as HTMLElement).getByText(t('progress.stageDuration', { seconds: 3 }))).toBeTruthy();
		expect(within(list.children[1] as HTMLElement).getByText(t('progress.stageElapsed', { seconds: 4 }))).toBeTruthy();
		const message = screen.getByRole('status');
		expect(message.textContent).toContain(state.progressMessage);
		expect(message.closest('[aria-busy="true"]')).toBeNull();
	});
});
