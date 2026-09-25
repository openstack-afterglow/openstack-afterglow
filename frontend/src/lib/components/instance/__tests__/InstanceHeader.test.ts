import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
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

function renderHeader(overrides: Partial<InstanceDetailController> = {}, props: { adminProjectId?: string | null; canMutate?: boolean; onOpenResizeModal?: () => void } = {}) {
	mockControllerRef.current = {
		instance: activeInstance,
		actioning: null,
		deleting: false,
		consoleOpening: false,
		consoleOpenMessage: '',
		consoleOpenError: '',
		migrationStatus: null,
		openConsole: mockOpenConsole,
		performAction: mockPerformAction,
		deleteInstance: mockDeleteInstance,
		confirmResize: mockConfirmResize,
		revertResize: mockRevertResize,
		forceCompleteMigration: mockForceCompleteMigration,
		abortMigration: mockAbortMigration,
		...overrides,
	} as unknown as InstanceDetailController;

	return render(InstanceHeader, {
		adminProjectId: props.adminProjectId ?? null,
		canMutate: props.canMutate ?? true,
		onOpenMigrateModal: vi.fn(),
		onOpenPasswordModal: vi.fn(),
		onOpenResizeModal: props.onOpenResizeModal ?? vi.fn(),
		onOpenEvacuateModal: vi.fn(),
	});
}

beforeEach(() => {
	vi.clearAllMocks();
});

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
		renderHeader({}, { adminProjectId, onOpenResizeModal });
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
