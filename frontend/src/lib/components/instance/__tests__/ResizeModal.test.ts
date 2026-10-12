import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import type { InstanceDetailController } from '$lib/stores/instanceDetailController.svelte';
import type { Instance } from '$lib/types/compute';

const { mockControllerRef } = vi.hoisted(() => ({
	mockControllerRef: { current: undefined as unknown },
}));

vi.mock('$lib/stores/instanceDetailController.svelte', () => ({
	useInstanceDetailController: () => mockControllerRef.current,
}));


import ResizeModal from '../ResizeModal.svelte';

function renderModal(overrides: Partial<InstanceDetailController> = {}) {
	const doResize = vi.fn().mockResolvedValue(true);
	mockControllerRef.current = {
		resizeFlavors: [
			{ id: 'flavor-1', name: 'cpu.1c_2g', vcpus: 1, ram: 2048, disk: 20 },
			{ id: 'flavor-2', name: 'cpu.2c_4g', vcpus: 2, ram: 4096, disk: 40 },
		],
		instance: { id: 'vm', flavor_id: 'flavor-1', status: 'SHUTOFF' } as Instance,
		resizeLoading: false,
		resizeFlavorsLoading: false,
		resizeError: '',
		doResize,
		...overrides,
	} as unknown as InstanceDetailController;

	const onClose = vi.fn();
	return {
		onClose,
		doResize,
		...render(ResizeModal, {
			props: {
				preselectFlavorId: 'flavor-2',
				onClose,
			},
		}),
	};
}

beforeEach(() => {
	vi.clearAllMocks();
});

describe('ResizeModal', () => {

	it('closes on a successful controller-confirmed resize', async () => {
		const { doResize, onClose } = renderModal();

		await fireEvent.click(screen.getByRole('button', { name: '리사이즈' }));

		await waitFor(() => {
			expect(doResize).toHaveBeenCalledWith('flavor-2');
			expect(onClose).toHaveBeenCalledTimes(1);
		});
	});

	it('keeps the modal open when the controller declines or fails resize', async () => {
		const doResize = vi.fn().mockResolvedValue(false);
		const onClose = vi.fn();
		mockControllerRef.current = {
			resizeFlavors: [
				{ id: 'flavor-1', name: 'cpu.1c_2g', vcpus: 1, ram: 2048, disk: 20 },
				{ id: 'flavor-2', name: 'cpu.2c_4g', vcpus: 2, ram: 4096, disk: 40 },
			],
			resizeLoading: false,
			resizeError: '',
			doResize,
		} as unknown as InstanceDetailController;

		render(ResizeModal, {
			props: {
				preselectFlavorId: 'flavor-2',
				onClose,
			},
		});

		await fireEvent.click(screen.getByRole('button', { name: '리사이즈' }));

		await waitFor(() => {
			expect(doResize).toHaveBeenCalledWith('flavor-2');
		});
		expect(onClose).not.toHaveBeenCalled();
	});

	it('blocks overlapping submissions while controller confirmation is pending', async () => {
		const pending = Promise.withResolvers<boolean>();
		const doResize = vi.fn().mockReturnValue(pending.promise);
		renderModal({ doResize });

		const button = screen.getByRole('button', { name: '리사이즈' });
		await fireEvent.click(button);
		await fireEvent.click(button);

		await waitFor(() => {
			expect(doResize).toHaveBeenCalledTimes(1);
			expect((screen.getByRole('button', { name: '확인 대기 중...' }) as HTMLButtonElement).disabled).toBe(true);
		});
		pending.resolve(false);
		await waitFor(() => {
			expect((screen.getByRole('button', { name: '리사이즈' }) as HTMLButtonElement).disabled).toBe(false);
		});
		expect(doResize).toHaveBeenCalledTimes(1);
	});

	it('disables current flavor and non-quota ineligible flavors with their reasons', async () => {
		const { doResize } = renderModal({
			resizeFlavors: [
				{ id: 'flavor-1', name: 'current', vcpus: 1, ram: 2048, disk: 20, is_public: true },
				{ id: 'flavor-2', name: 'smaller disk', vcpus: 2, ram: 4096, disk: 10, is_public: true,
					eligibility: { selectable: false, blockers: [{ code: 'disk_shrink' }], requirements: { instances: 0, cores: 0, ram_mb: 0, gpus: {} }, remaining: { instances: 0, cores: 0, ram_mb: 0, gpus: {} } } },
			],
		});
		const options = screen.getAllByRole('option') as HTMLOptionElement[];
		expect(options[1].disabled).toBe(true);
		expect(options[2].disabled).toBe(true);
		const button = screen.getByRole('button', { name: '리사이즈' }) as HTMLButtonElement;
		expect(button.disabled).toBe(true);
		await fireEvent.change(screen.getByRole('combobox'), { target: { value: 'flavor-1' } });
		expect(button.disabled).toBe(true);
		await fireEvent.click(button);
		expect(doResize).not.toHaveBeenCalled();
	});

	it('shows flavor-loading and request errors without submitting', () => {
		renderModal({ resizeFlavorsLoading: true, resizeError: '플레이버 목록을 가져올 수 없습니다' });
		expect(screen.getByText('플레이버 목록을 가져올 수 없습니다')).toBeTruthy();
		expect((screen.getByRole('button', { name: '리사이즈' }) as HTMLButtonElement).disabled).toBe(true);
		expect((screen.getByRole('combobox') as HTMLSelectElement).disabled).toBe(true);
	});
});
