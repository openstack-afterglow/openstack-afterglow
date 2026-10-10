import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';

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
		const submit = screen.getByRole('button', { name: '변경' }) as HTMLButtonElement;
		expect(submit.disabled).toBe(false);
		expect(screen.queryByRole('status')).toBeNull();
		await fireEvent.click(submit);
		expect(submit.disabled).toBe(true);
		expect(within(submit).getByRole('status').textContent?.trim()).toBe('변경 중...');
		expect(onClose).not.toHaveBeenCalled();
		resolve('게스트 에이전트 연결 실패');
		await screen.findByText('게스트 에이전트 연결 실패');
		expect(submit.disabled).toBe(false);
		expect(doSetPassword).toHaveBeenCalledOnce();
		expect(doSetPassword).toHaveBeenCalledWith('password123');
		expect(screen.queryByRole('status')).toBeNull();
		expect(onClose).not.toHaveBeenCalled();
	});

	it('labels a migration request as in flight only when the request flag is set', () => {
		controller.current.migrateLoading = true;
		render(MigrateModal, { type: 'live', onClose: vi.fn() });
		const status = screen.getByRole('status');
		expect(status.textContent?.trim()).toBe('마이그레이션 중...');
		const submit = status.closest('button') as HTMLButtonElement;
		expect(submit.disabled).toBe(true);
	});

	it('does not show migration activity when the request flag is clear', () => {
		render(MigrateModal, { type: 'live', onClose: vi.fn() });
		expect(screen.queryByRole('status')).toBeNull();
		expect((screen.getByRole('button', { name: '마이그레이션' }) as HTMLButtonElement).disabled).toBe(false);
	});

	it('attributes detach feedback to the requested volume, not every attachment', async () => {
		controller.current.volumes = [
			{ volume_id: 'volume-a', name: 'Volume A', status: 'in-use', device: '/dev/vdb' },
			{ volume_id: 'volume-b', name: 'Volume B', status: 'in-use', device: '/dev/vdc' },
		];
		controller.current.actioning = 'detach-volume-b';
		const detachVolume = vi.fn();
		controller.current.detachVolume = detachVolume;
		render(VolumesSection);
		const volumeA = screen.getByRole('link', { name: 'Volume A' }).closest('div')!.parentElement!;
		const volumeB = screen.getByRole('link', { name: 'Volume B' }).closest('div')!.parentElement!;
		const busy = within(volumeB).getByRole('status').closest('button') as HTMLButtonElement;
		expect(within(volumeB).getByRole('status').textContent?.trim()).toBe('분리 중...');
		expect(busy.disabled).toBe(true);
		const other = within(volumeA).getByRole('button', { name: '분리' }) as HTMLButtonElement;
		expect(other.disabled).toBe(false);
		expect(within(volumeA).queryByRole('status')).toBeNull();
		await fireEvent.click(other);
		expect(detachVolume).toHaveBeenCalledOnce();
		expect(detachVolume).toHaveBeenCalledWith('volume-a');
		expect(screen.getAllByText('in-use')).toHaveLength(2);
	});

	it('keeps initial console loading feedback outside the copyable log content', async () => {
		controller.current.logLoading = true;
		controller.current.loadConsoleLog = vi.fn(async () => {});
		const { container } = render(ConsoleSection);
		await fireEvent.click(screen.getByRole('button', { name: '로그 보기' }));
		await waitFor(() => expect(screen.getAllByRole('status')).toHaveLength(2));
		const statuses = screen.getAllByRole('status');
		const log = container.querySelector('pre')!;
		expect(statuses.some((status) => !status.closest('button'))).toBe(true);
		for (const status of statuses) expect(log.contains(status)).toBe(false);
		expect(log.textContent).toBe('');
		expect(log.getAttribute('aria-busy')).toBe('true');
		expect(controller.current.loadConsoleLog).toHaveBeenCalledWith(false);
		expect(controller.current.consolePollAr).toMatchObject({ active: true });
		expect(statuses.filter((status) => !status.closest('button'))).toHaveLength(1);
	});

});
