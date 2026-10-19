import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { get } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { t } from '$lib/i18n/ns/vm-wizard';

vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$lib/api/client', () => ({
	api: { get: (path: string) => Promise.resolve(wizardResource(path) ?? { history: [], presets: [] }) },
	ApiError: class ApiError extends Error {},
	fetchWithAuth: vi.fn(),
	getBaseUrl: () => '',
}));

import Wrapper from './_WizardConsumerWrapper.svelte';
import { wizard, wizardPassword } from '$lib/stores/wizard';
import type { VmCreateStore } from '$lib/stores/vmCreateStore.svelte';
import { prepareWizardConsumer, wizardResource } from './wizardConsumerFixtures';

async function renderReview() {
	let store!: VmCreateStore;
	const view = render(Wrapper, { component: 'review', onStore: value => { store = value; } });
	await store.loadBootOptions();
	await store.loadFlavorOptions();
	await tick();
	return { ...view, store };
}

afterEach(cleanup);
beforeEach(() => {
	prepareWizardConsumer(6);
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
	it.each([false, true])('preserves image root disk size and delete-with-VM setting %s', async deleteWithVm => {
		wizard.update(w => ({ ...w, deleteBootVolumeOnTermination: deleteWithVm }));
		await renderReview();

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
		await renderReview();
		const editButtons = screen.getAllByRole('button', { name: t('review.edit') });
		expect(editButtons).toHaveLength(7);
		const destinations = [];
		for (const button of editButtons) {
			await fireEvent.click(button);
			destinations.push(get(wizard).step);
		}
		expect(destinations).toEqual([5, 2, 1, 5, 5, 5, 5]);
	});

	it.each(['existing-root', null])('reviews the existing boot volume with name %s without image-only root disk settings', async volumeName => {
		wizard.update(w => ({
			...w,
			bootSource: 'volume',
			bootVolumeId: 'volume-a',
			bootVolumeName: volumeName,
		}));
		await renderReview();

		const bootVolume = reviewRow(t('review.bootVolume'));
		expect(within(bootVolume).getByText(volumeName ?? 'volume-a')).toBeTruthy();
		expect(screen.queryByText('Ubuntu 24.04')).toBeNull();
		expect(screen.queryByText(t('review.rootDisk.label'))).toBeNull();
		expect(screen.getAllByRole('button', { name: t('review.edit') })).toHaveLength(5);
		await fireEvent.click(within(bootVolume).getByRole('button', { name: t('review.edit') }));
		expect(get(wizard).step).toBe(1);
	});

	it('returns to configuration with independent protection choices intact', async () => {
		wizard.update(w => ({ ...w, autoSnapshot: true, autoBackup: false, volumeProtectionForce: true }));
		await renderReview();
		const protection = reviewRow(t('config.protection.title'));
		expect(within(protection).getByText(t('review.protection.snapshot', { enabled: 'yes' }))).toBeTruthy();
		expect(within(protection).getByText(t('review.protection.backup', { enabled: 'no' }))).toBeTruthy();
		await fireEvent.click(within(protection).getByRole('button', { name: t('review.edit') }));
		expect(get(wizard)).toMatchObject({ step: 5, autoSnapshot: true, autoBackup: false, volumeProtectionForce: true });
	});

	it('keeps ordinary file storage mounts in review and routes their edit to config', async () => {
		wizard.update(w => ({
			...w,
			dataMounts: [{ fileStorageId: 'storage-a', mountPoint: '/mnt/data', readOnly: true }],
		}));
		await renderReview();

		const mounts = reviewRow(t('review.mounts'));
		expect(within(mounts).getByText('project-data')).toBeTruthy();
		expect(within(mounts).getByText('/mnt/data')).toBeTruthy();
		expect(within(mounts).getByText('ro')).toBeTruthy();
		expect(screen.getByText(t('review.rootDisk.label'))).toBeTruthy();
		await fireEvent.click(within(mounts).getByRole('button', { name: t('review.edit') }));
		expect(get(wizard).step).toBe(5);
	});
});

describe('WizardStep6Review Windows consumers', () => {
	it.each(['image', 'volume'] as const)('removes native %s readiness and never shows SSH or secrets after becoming unsupported', async bootSource => {
		wizard.update(w => ({ ...w, bootSource, imageId: 'windows-native', bootVolumeId: 'windows-native' }));
		const { container } = await renderReview();
		const secret = 'Review-never-reveals-123!';
		wizardPassword.set({ password: secret, confirmation: secret });
		await tick();
		expect(screen.getByTestId('windows-password-review').textContent).toContain('GuestAdmin');
		expect(screen.getByText(t('review.ready'))).toBeTruthy();
		expect(screen.queryByText(t('review.ssh.label'))).toBeNull();
		expect(screen.queryByText('project-key')).toBeNull();
		expect(container.textContent).not.toContain(secret);
		expect(container.innerHTML).not.toContain(secret);

		wizard.update(w => ({ ...w, imageId: 'windows-unsupported', bootVolumeId: 'windows-unsupported', cloudInit: 'stale-userdata-secret', dataMounts: [{ fileStorageId: 'storage-a', mountPoint: '/mnt/stale', readOnly: false }] }));
		await tick();
		await tick();
		const unsupported = screen.getByTestId('windows-unsupported-review');
		expect(within(unsupported).getByRole('alert').textContent?.trim()).toBeTruthy();
		expect(screen.queryByTestId('windows-password-review')).toBeNull();
		expect(screen.queryByText(t('review.ssh.label'))).toBeNull();
		expect(screen.queryByText('project-key')).toBeNull();
		expect(screen.queryByText(t('review.ready'))).toBeNull();
		expect(screen.queryByText(t('review.mounts'))).toBeNull();
		expect(screen.queryByText('/mnt/stale')).toBeNull();
		expect(container.textContent).not.toContain('stale-userdata-secret');
		expect(container.textContent).not.toContain(secret);
		expect(container.innerHTML).not.toContain(secret);
		expect(container.querySelector('input[type="password"]')).toBeNull();
		expect((screen.getByRole('button', { name: t('footer.create') }) as HTMLButtonElement).disabled).toBe(true);

		wizard.update(w => ({ ...w, bootSource: 'image', imageId: 'image-a' }));
		await tick();
		expect(screen.queryByTestId('windows-unsupported-review')).toBeNull();
		expect(screen.getByText(t('review.ssh.label'))).toBeTruthy();
		expect(screen.getByText('project-key')).toBeTruthy();
		expect(screen.getByText('/mnt/stale')).toBeTruthy();
		expect(screen.getByText(t('review.ready'))).toBeTruthy();
	});
});
