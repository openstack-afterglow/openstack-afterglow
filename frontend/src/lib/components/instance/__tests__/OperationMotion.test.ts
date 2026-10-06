import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';

const { controller } = vi.hoisted(() => ({ controller: { current: {} as Record<string, unknown> } }));
vi.mock('$lib/stores/instanceDetailController.svelte', () => ({
	useInstanceDetailController: () => controller.current,
}));

import PasswordModal from '../PasswordModal.svelte';
import MigrateModal from '../MigrateModal.svelte';
import VolumesSection from '../VolumesSection.svelte';
import ConsoleSection from '../ConsoleSection.svelte';

beforeEach(() => {
	controller.current = {
		instance: { id: 'instance-a', name: 'VM A', union_libraries: [], metadata: {} },
		passwordPrecheck: { supported: true }, passwordPrecheckLoading: false,
		migrateHosts: [], migrateError: '', migrateLoading: false,
		volumes: [], availableVolumes: [], actioning: null,
		consolePollAr: { active: false, intervalSeconds: 30 },
		consoleLog: '', logLoading: false, logFull: false,
	};
});

describe('instance operation feedback', () => {
	it('keeps password mutation busy until its own request finishes, not the precheck', async () => {
		let resolve!: (result: string | null) => void;
		const pending = new Promise<string | null>((done) => { resolve = done; });
		const doSetPassword = vi.fn(() => pending);
		controller.current.doSetPassword = doSetPassword;
		const onClose = vi.fn();
		render(PasswordModal, { onClose });
		await fireEvent.input(screen.getByLabelText('새 비밀번호'), { target: { value: 'password123' } });
		await fireEvent.input(screen.getByLabelText('비밀번호 확인'), { target: { value: 'password123' } });
		await fireEvent.click(screen.getByRole('button', { name: '변경' }));
		expect(screen.getByRole('button', { name: '변경 중...' }).hasAttribute('disabled')).toBe(true);
		expect(screen.getByRole('status').textContent?.trim()).toBe('변경 중...');
		expect(onClose).not.toHaveBeenCalled();
		resolve('게스트 에이전트 연결 실패');
		await screen.findByText('게스트 에이전트 연결 실패');
		expect(screen.getByRole('button', { name: '변경' }).hasAttribute('disabled')).toBe(false);
		expect(doSetPassword).toHaveBeenCalledOnce();
		expect(screen.queryByText('변경 중...')).toBeNull();
	});

	it('labels a migration request as in flight only when the request flag is set', () => {
		controller.current.migrateLoading = true;
		render(MigrateModal, { type: 'live', onClose: vi.fn() });
		expect(screen.getByRole('status').textContent?.trim()).toBe('마이그레이션 중...');
		expect(screen.getByRole('button', { name: '마이그레이션 중...' }).hasAttribute('disabled')).toBe(true);
	});

	it('attributes detach feedback to the requested volume, not every attachment', () => {
		controller.current.volumes = [
			{ volume_id: 'volume-a', name: 'Volume A', status: 'in-use', device: '/dev/vdb' },
			{ volume_id: 'volume-b', name: 'Volume B', status: 'in-use', device: '/dev/vdc' },
		];
		controller.current.actioning = 'detach-volume-b';
		render(VolumesSection);
		expect(screen.getByRole('button', { name: '분리 중...' }).hasAttribute('disabled')).toBe(true);
		expect(screen.getByRole('button', { name: '분리' }).hasAttribute('disabled')).toBe(false);
		expect(screen.getAllByText('in-use')).toHaveLength(2);
	});

	it('keeps initial console loading feedback outside the copyable log content', async () => {
		controller.current.logLoading = true;
		controller.current.loadConsoleLog = vi.fn(async () => {});
		const { container } = render(ConsoleSection);
		await fireEvent.click(screen.getByRole('button', { name: '로그 보기' }));
		await waitFor(() => expect(container.querySelector('pre')?.getAttribute('aria-busy')).toBe('true'));
		const log = container.querySelector('pre')!;
		expect(log.textContent).toBe('');
		const contentFeedback = screen.getAllByRole('status').filter((status) => !status.closest('button'));
		expect(contentFeedback).toHaveLength(1);
		expect(log.contains(contentFeedback[0])).toBe(false);
	});

});
