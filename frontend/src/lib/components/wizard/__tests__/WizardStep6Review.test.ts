import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { t } from '$lib/i18n/ns/vm-wizard';

const state = vi.hoisted(() => ({
	flavors: [{
		id: 'flavor-a',
		vcpus: 4,
		ram: 8192,
		disk: 40,
		extra_specs: { 'pci_passthrough:alias': 'gpu-a:1,audio:1' },
	}],
	fileStorages: [{ id: 'storage-a', name: 'project-data' }],
	deployError: '',
	goTo: vi.fn(),
}));
vi.mock('$lib/stores/vmCreateStore.svelte', () => ({ useVmCreate: () => state }));

import WizardStep6Review from '../WizardStep6Review.svelte';
import { resetWizard, wizard } from '$lib/stores/wizard';

afterEach(cleanup);
beforeEach(() => {
	resetWizard();
	state.goTo.mockReset();
	state.deployError = '';
	wizard.update(w => ({
		...w,
		step: 6,
		instanceName: 'ordinary-vm',
		imageId: 'image-a',
		imageName: 'Ubuntu 24.04',
		flavorId: 'flavor-a',
		flavorName: 'gpu.4c_8g',
		keyName: 'project-key',
		networkName: 'private-net',
		bootVolumeSizeGb: 64,
	}));
});

function reviewRow(label: string): HTMLElement {
	return screen.getByText(label).parentElement as HTMLElement;
}

describe('WizardStep6Review ordinary VM', () => {
	it.each([false, true])('preserves image root disk size and delete-with-VM setting %s', deleteWithVm => {
		wizard.update(w => ({ ...w, deleteBootVolumeOnTermination: deleteWithVm }));
		render(WizardStep6Review);

		expect(screen.getByText('ordinary-vm')).toBeTruthy();
		expect(screen.getByText('Ubuntu 24.04')).toBeTruthy();
		expect(screen.getByText('gpu.4c_8g')).toBeTruthy();
		expect(screen.getByText('project-key')).toBeTruthy();
		expect(screen.getByText('private-net')).toBeTruthy();
		expect(screen.getByText('gpu-a × 1')).toBeTruthy();
		const rootDisk = reviewRow(t('review.rootDisk.label'));
		expect(rootDisk.textContent).toContain('64 GB');
		expect(within(rootDisk).getByText(t('review.rootDisk.retention', { deleteWithVm }))).toBeTruthy();
	});

	it('routes every ordinary review edit to the retained step IDs', async () => {
		const { container } = render(WizardStep6Review);
		const editButtons = screen.getAllByRole('button', { name: t('review.edit') });
		expect(editButtons).toHaveLength(6);
		expect(container.querySelectorAll('.review-edit-btn')).toHaveLength(6);
		for (const button of editButtons) await fireEvent.click(button);
		expect(state.goTo.mock.calls.map(([step]) => step)).toEqual([5, 1, 2, 5, 5, 5]);
	});

	it.each(['existing-root', null])('reviews the existing boot volume with name %s without image-only root disk settings', async volumeName => {
		wizard.update(w => ({
			...w,
			bootSource: 'volume',
			bootVolumeId: 'volume-a',
			bootVolumeName: volumeName,
		}));
		render(WizardStep6Review);

		const bootVolume = reviewRow(t('review.bootVolume'));
		expect(within(bootVolume).getByText(volumeName ?? 'volume-a')).toBeTruthy();
		expect(screen.queryByText('Ubuntu 24.04')).toBeNull();
		expect(screen.queryByText(t('review.rootDisk.label'))).toBeNull();
		expect(screen.getAllByRole('button', { name: t('review.edit') })).toHaveLength(5);
		await fireEvent.click(within(bootVolume).getByRole('button', { name: t('review.edit') }));
		expect(state.goTo).toHaveBeenCalledWith(1);
	});

	it('keeps ordinary file storage mounts in review and routes their edit to config', async () => {
		wizard.update(w => ({
			...w,
			dataMounts: [{ fileStorageId: 'storage-a', mountPoint: '/mnt/data', readOnly: true }],
		}));
		render(WizardStep6Review);

		const mounts = reviewRow(t('review.mounts'));
		expect(within(mounts).getByText('project-data')).toBeTruthy();
		expect(within(mounts).getByText('/mnt/data')).toBeTruthy();
		expect(within(mounts).getByText('ro')).toBeTruthy();
		expect(screen.getByText(t('review.rootDisk.label'))).toBeTruthy();
		await fireEvent.click(within(mounts).getByRole('button', { name: t('review.edit') }));
		expect(state.goTo).toHaveBeenCalledWith(5);
	});
});
