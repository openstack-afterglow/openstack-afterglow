import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, render, screen, fireEvent, waitFor, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { fromStore, writable } from 'svelte/store';
import type { Writable } from 'svelte/store';
import { initLocale } from '$lib/i18n/runtime.svelte';
import type { Instance } from '$lib/types/compute';
import type { InstanceDetailController } from '$lib/stores/instanceDetailController.svelte';

const {
	mockControllerRef,
	mockOpenConsole,
	mockPerformAction,
	mockDeleteInstance,
	mockConfirmResize,
	mockRevertResize,
	mockForceCompleteMigration,
	mockAbortMigration,
} = vi.hoisted(() => ({
	mockControllerRef: { current: undefined as unknown },
	mockOpenConsole: vi.fn(),
	mockPerformAction: vi.fn(),
	mockDeleteInstance: vi.fn(),
	mockConfirmResize: vi.fn(),
	mockRevertResize: vi.fn(),
	mockForceCompleteMigration: vi.fn(),
	mockAbortMigration: vi.fn(),
}));

vi.mock('$lib/stores/instanceDetailController.svelte', () => ({
	useInstanceDetailController: () => mockControllerRef.current,
}));

import InstanceHeader from '../InstanceHeader.svelte';

const activeInstance = { id: 'inst-1', name: 'vm-1', status: 'ACTIVE' } as Instance;
let controllerState: Writable<InstanceDetailController>;

function renderHeader(overrides: Partial<InstanceDetailController> = {}, props: { adminProjectId?: string | null; canMutate?: boolean; onOpenResizeModal?: () => void; onOpenPasswordModal?: () => void; onOpenMigrateModal?: (type: 'live' | 'cold') => void; onOpenEvacuateModal?: () => void } = {}) {
	controllerState = writable({
		instance: activeInstance,
		actioning: null,
		deleting: false,
		consoleOpening: false,
		consoleOpenMessage: '',
		consoleOpenError: '',
		migrationStatus: null,
		canChangePassword: false,
		passwordPrecheckLoading: false,
		passwordPrecheck: null,
		passwordPrecheckReason: null,
		passwordPrecheckError: '',
		openConsole: mockOpenConsole,
		performAction: mockPerformAction,
		deleteInstance: mockDeleteInstance,
		confirmResize: mockConfirmResize,
		revertResize: mockRevertResize,
		forceCompleteMigration: mockForceCompleteMigration,
		abortMigration: mockAbortMigration,
		...overrides,
	} as unknown as InstanceDetailController);
	const state = fromStore(controllerState);
	mockControllerRef.current = new Proxy(state.current, {
		get: (_target, key) => state.current[key as keyof InstanceDetailController],
	});

	return render(InstanceHeader, {
		adminProjectId: props.adminProjectId ?? null,
		canMutate: props.canMutate ?? true,
		onOpenMigrateModal: props.onOpenMigrateModal ?? vi.fn(),
		onOpenPasswordModal: props.onOpenPasswordModal ?? vi.fn(),
		onOpenResizeModal: props.onOpenResizeModal ?? vi.fn(),
		onOpenEvacuateModal: props.onOpenEvacuateModal ?? vi.fn(),
	});
}

beforeEach(() => {
	vi.clearAllMocks();
	initLocale('ko');
});

afterEach(() => cleanup());

describe('InstanceHeader console feedback', () => {
	it('renders an enabled console button that opens the console', async () => {
		renderHeader();

		const button = screen.getByRole('button', { name: '콘솔 열기' });
		expect(button.hasAttribute('disabled')).toBe(false);

		await fireEvent.click(button);
		expect(mockOpenConsole).toHaveBeenCalledTimes(1);
	});

	it('renders loading button and status while console URL is requested', () => {
		renderHeader({
			consoleOpening: true,
			consoleOpenMessage: 'Nova에서 noVNC 콘솔 URL을 요청하는 중입니다...',
		});

		const button = screen.getByRole('button', { name: '콘솔 준비 중...' });
		expect(button.hasAttribute('disabled')).toBe(true);
		expect(screen.getByText('콘솔 준비 중...')).toBeTruthy();

		const status = screen.getByRole('status');
		expect(status.textContent).toContain('Nova에서 noVNC 콘솔 URL을 요청하는 중입니다...');
	});

	it('renders console open error as an alert without replacing the button label', () => {
		renderHeader({
			consoleOpenError: '콘솔 URL을 가져올 수 없습니다. 잠시 후 다시 시도하세요.',
		});

		expect(screen.getByRole('button', { name: '콘솔 열기' })).toBeTruthy();
		const alert = screen.getByRole('alert');
		expect(alert.textContent).toContain('콘솔 URL을 가져올 수 없습니다. 잠시 후 다시 시도하세요.');
	});
});

describe('InstanceHeader resize access', () => {
	it.each([null, 'project-admin'])('opens resize for writable %s detail', async adminProjectId => {
		const onOpenResizeModal = vi.fn();
		renderHeader({ instance: { ...activeInstance, status: 'SHUTOFF' } }, { adminProjectId, onOpenResizeModal });
		await fireEvent.click(screen.getByRole('button', { name: '리사이즈' }));
		expect(onOpenResizeModal).toHaveBeenCalledTimes(1);
	});

	it.each([null, 'project-admin'])('shows verify actions for writable %s detail', async adminProjectId => {
		renderHeader({ instance: { ...activeInstance, status: 'VERIFY_RESIZE' } }, { adminProjectId });
		await fireEvent.click(screen.getByRole('button', { name: '리사이즈 확인' }));
		await fireEvent.click(screen.getByRole('button', { name: '되돌리기' }));
		expect(mockConfirmResize).toHaveBeenCalledTimes(1);
		expect(mockRevertResize).toHaveBeenCalledTimes(1);
	});

	it('leaves console visible but hides mutations from a reader in active and verify states', () => {
		const view = renderHeader({}, { canMutate: false });
		expect(screen.getByRole('button', { name: '콘솔 열기' })).toBeTruthy();
		expect(screen.queryByRole('button', { name: '리사이즈' })).toBeNull();
		expect(screen.queryByRole('button', { name: '정지' })).toBeNull();
		expect(screen.queryByRole('button', { name: '삭제' })).toBeNull();
		view.unmount();
		renderHeader({ instance: { ...activeInstance, status: 'VERIFY_RESIZE' } }, { canMutate: false });
		expect(screen.queryByRole('button', { name: '리사이즈 확인' })).toBeNull();
		expect(screen.queryByRole('button', { name: '되돌리기' })).toBeNull();
	});
});

describe('InstanceHeader operation attribution', () => {
	it('only marks the requested action as working and retains the instance status', () => {
		renderHeader({ actioning: 'stop' });
		expect(screen.getByRole('status').textContent?.trim()).toBe('정지 중...');
		expect(screen.getByRole('button', { name: '정지 중...' }).hasAttribute('disabled')).toBe(true);
		expect(screen.queryByText('재부팅 중...')).toBeNull();
		expect(screen.getByText('ACTIVE')).toBeTruthy();
	});

	it('keeps a migration control request busy until its promise settles', async () => {
		let resolve!: () => void;
		mockAbortMigration.mockReturnValueOnce(new Promise<void>((done) => { resolve = done; }));
		renderHeader({ instance: { ...activeInstance, status: 'MIGRATING' } }, { adminProjectId: 'project-a' });
		const abort = screen.getByRole<HTMLButtonElement>('button', { name: '마이그레이션 중단' });
		const complete = screen.getByRole<HTMLButtonElement>('button', { name: '강제 완료' });
		await fireEvent.click(abort);
		expect(mockAbortMigration).toHaveBeenCalledTimes(1);
		expect(within(abort).getByRole('status')).toBeTruthy();
		expect(within(complete).queryByRole('status')).toBeNull();
		expect(abort.disabled).toBe(true);
		expect(complete.disabled).toBe(true);
		resolve();
		await waitFor(() => expect(abort.disabled).toBe(false));
		expect(complete.disabled).toBe(false);
		expect(screen.queryByRole('status')).toBeNull();
	});
});

describe('InstanceHeader stopped lifecycle actions', () => {
	it.each([null, 'project-admin'])('updates ACTIVE to SHUTOFF actions in %s mode', async adminProjectId => {
		const onOpenResizeModal = vi.fn();
		renderHeader({}, { adminProjectId, onOpenResizeModal });
		for (const name of ['시작', '보관', '삭제', '리사이즈']) {
			expect(screen.queryByRole('button', { name })).toBeNull();
		}
		expect(screen.getByRole('button', { name: '정지' })).toBeTruthy();
		controllerState.update(s => ({ ...s, instance: { ...activeInstance, status: 'SHUTOFF' } }));
		await tick();
		expect(screen.queryByRole('button', { name: '정지' })).toBeNull();
		expect(screen.queryByRole('button', { name: '콘솔 열기' })).toBeNull();
		for (const name of ['시작', '보관', '삭제', '리사이즈']) {
			expect(screen.getByRole<HTMLButtonElement>('button', { name }).disabled).toBe(false);
		}
	});

	it.each([null, 'project-admin'])('hides all stopped mutations for readers in %s mode', adminProjectId => {
		renderHeader({ instance: { ...activeInstance, status: 'SHUTOFF' }, canChangePassword: true }, { canMutate: false, adminProjectId });
		expect(screen.queryAllByRole('button')).toHaveLength(0);
	});

	it.each([null, 'project-admin'])('blocks every stopped action while another operation or deletion is busy in %s mode', async adminProjectId => {
		const onOpenResizeModal = vi.fn();
		renderHeader({ instance: { ...activeInstance, status: 'SHUTOFF' }, actioning: 'attach-vol' }, { adminProjectId, onOpenResizeModal });
		for (const name of ['시작', '보관', '삭제', '리사이즈']) {
			const button = screen.getByRole<HTMLButtonElement>('button', { name });
			expect(button.disabled).toBe(true);
		}
		controllerState.update(s => ({ ...s, actioning: null, deleting: true }));
		await tick();
		for (const name of ['시작', '보관', '삭제 중...', '리사이즈']) {
			expect(screen.getByRole<HTMLButtonElement>('button', { name }).disabled).toBe(true);
		}
		controllerState.update(s => ({ ...s, deleting: false, resizeLoading: true }));
		await tick();
		for (const name of ['시작', '보관', '삭제', '리사이즈']) {
			expect(screen.getByRole<HTMLButtonElement>('button', { name }).disabled).toBe(true);
		}
	});

	it.each(['SHELVED', 'SHELVED_OFFLOADED'])('retains unshelve without deletion for %s', async status => {
		renderHeader({ instance: { ...activeInstance, status } });
		expect(screen.getByRole<HTMLButtonElement>('button', { name: '보관 해제' }).disabled).toBe(false);
		expect(screen.queryByRole('button', { name: '삭제' })).toBeNull();
		expect(screen.queryByRole('button', { name: '리사이즈' })).toBeNull();
	});

	it('retains administrator migration and recovery actions without ERROR deletion', async () => {
		const onOpenMigrateModal = vi.fn();
		const onOpenEvacuateModal = vi.fn();
		renderHeader({}, { adminProjectId: 'project-a', onOpenMigrateModal, onOpenEvacuateModal });
		for (const name of ['라이브 마이그레이션', '콜드 마이그레이션', '강제 이주']) {
			expect(screen.getByRole<HTMLButtonElement>('button', { name }).disabled).toBe(false);
		}
		controllerState.update(s => ({ ...s, instance: { ...activeInstance, status: 'ERROR' } }));
		await tick();
		expect(screen.queryByRole('button', { name: '삭제' })).toBeNull();
		expect(screen.getByRole('button', { name: '강제 이주' })).toBeTruthy();
	});

	it.each(['SHELVED', 'SHELVED_OFFLOADED', 'ERROR', 'VERIFY_RESIZE', 'BUILD', 'MIGRATING', 'STOPPED'])('omits archive/delete/resize in both modes for non-SHUTOFF %s', async status => {
		const view = renderHeader({ instance: { ...activeInstance, status } });
		for (const name of ['보관', '삭제', '리사이즈']) {
			expect(screen.queryByRole('button', { name })).toBeNull();
		}
		await view.rerender({ canMutate: true, adminProjectId: 'project-a', onOpenMigrateModal: vi.fn(), onOpenPasswordModal: vi.fn(), onOpenResizeModal: vi.fn(), onOpenEvacuateModal: vi.fn() });
		for (const name of ['보관', '삭제', '리사이즈']) {
			expect(screen.queryByRole('button', { name })).toBeNull();
		}
	});
});

describe('InstanceHeader password precheck', () => {
	it.each([null, 'project-admin'])('keeps visible busy copy and opens only after a supported precheck in %s mode', async adminProjectId => {
		const onOpenPasswordModal = vi.fn();
		renderHeader({ canChangePassword: true, passwordPrecheckLoading: true }, { adminProjectId, onOpenPasswordModal });
		const checking = screen.getByRole<HTMLButtonElement>('button', { name: '점검 중...' });
		expect(checking.textContent?.trim()).toBe('점검 중...');
		expect(checking.disabled).toBe(true);
		expect(checking.getAttribute('aria-busy')).toBe('true');
		controllerState.update(s => ({ ...s, passwordPrecheckLoading: false, passwordPrecheck: { supported: true } as InstanceDetailController['passwordPrecheck'] }));
		await tick();
		const change = screen.getByRole<HTMLButtonElement>('button', { name: '비밀번호 변경' });
		expect(change.disabled).toBe(false);
		controllerState.update(s => ({ ...s, instance: { ...activeInstance, status: 'SHUTOFF' } }));
		await tick();
		expect(screen.getByRole<HTMLButtonElement>('button', { name: '비밀번호 변경' }).disabled).toBe(true);
	});

	it.each([
		{ canChangePassword: false },
		{ canChangePassword: true, passwordPrecheckLoading: true },
		{ canChangePassword: true, passwordPrecheck: null, passwordPrecheckError: 'Precheck unavailable' },
		{ canChangePassword: true, passwordPrecheck: { supported: false } as InstanceDetailController['passwordPrecheck'], passwordPrecheckReason: 'Unsupported guest' },
		{ canChangePassword: true, passwordPrecheck: { supported: true } as InstanceDetailController['passwordPrecheck'], actioning: 'stop' },
		{ canChangePassword: true, passwordPrecheck: { supported: true } as InstanceDetailController['passwordPrecheck'], deleting: true },
		{ canChangePassword: true, passwordPrecheck: { supported: true } as InstanceDetailController['passwordPrecheck'], resizeLoading: true },
	])('does not allow password changes for unavailable permission/precheck/busy state %#', async overrides => {
		const onOpenPasswordModal = vi.fn();
		renderHeader(overrides, { onOpenPasswordModal });
		const button = screen.queryByRole<HTMLButtonElement>('button', { name: /비밀번호 변경|점검 중/ });
		if (overrides.canChangePassword) {
			expect(button).not.toBeNull();
			expect(button!.disabled).toBe(true);
		} else {
			expect(button).toBeNull();
		}
		if ('passwordPrecheckReason' in overrides) expect(screen.getByText(overrides.passwordPrecheckReason!)).toBeTruthy();
		if ('passwordPrecheckError' in overrides) expect(screen.getByText(overrides.passwordPrecheckError!)).toBeTruthy();
	});
});
