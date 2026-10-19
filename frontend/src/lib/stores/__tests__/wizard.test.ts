import { describe, it, expect, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import { wizard, wizardOpen, openWizard, closeWizard, resetWizard } from '../wizard';

describe('wizard store', () => {
	beforeEach(() => {
		resetWizard();
		closeWizard();
	});

	it('초기 wizardOpen 상태는 false', async () => {
		expect(get(wizardOpen)).toBe(false);
	});

	it('openWizard()로 wizardOpen이 true', async () => {
		openWizard();
		expect(get(wizardOpen)).toBe(true);
	});

	it('closeWizard()로 wizardOpen이 false', async () => {
		openWizard();
		closeWizard();
		expect(get(wizardOpen)).toBe(false);
	});


	it('wizard.set으로 상태 업데이트', async () => {
		const current = get(wizard);
		wizard.set({ ...current, step: 2, imageId: 'img-1', imageName: 'Ubuntu 22.04' });
		const updated = get(wizard);
		expect(updated.step).toBe(2);
		expect(updated.imageId).toBe('img-1');
		expect(updated.imageName).toBe('Ubuntu 22.04');
	});

	it('resetWizard()로 초기 상태 복원', async () => {
		const initial = get(wizard);
		wizard.set({ ...initial, step: 5, flavorId: 'flavor-1', instanceName: 'my-vm', autoSnapshot: true, autoBackup: true, volumeProtectionForce: true });
		resetWizard();
		const after = get(wizard);
		expect(after.step).toBe(2);
		expect(after.flavorId).toBeNull();
		expect(after.instanceName).toBe('');
		expect(after).toMatchObject({ autoSnapshot: false, autoBackup: false, volumeProtectionForce: false });
	});

	it('resetWizard restores ordinary volume and data mount selections', async () => {
		wizard.update(w => ({ ...w, bootSource: 'volume', bootVolumeId: 'boot-1', additionalVolumeIds: ['data-1'], dataMounts: [{ fileStorageId: 'share-1', mountPoint: '/data', readOnly: true }] }));
		resetWizard();
		expect(get(wizard)).toMatchObject({ bootSource: 'image', bootVolumeId: null, additionalVolumeIds: [], dataMounts: [] });
	});

	it('wizardOpen subscribe로 변화 감지', async () => {
		const states: boolean[] = [];
		const unsub = wizardOpen.subscribe((v) => states.push(v));
		openWizard();
		closeWizard();
		unsub();
		expect(states).toEqual([false, true, false]);
	});

	it('wizard 단계 변경 이벤트를 detail.step과 함께 한 번만 발행', async () => {
		const events: number[] = [];
		const handler = (event: Event) => {
			events.push((event as CustomEvent<{ step: number }>).detail.step);
		};
		window.addEventListener('afterglow:wizard-step', handler);
		try {
			wizard.update((w) => ({ ...w, step: 5 }));
			wizard.update((w) => ({ ...w, step: 5 }));
			expect(events).toEqual([5]);
		} finally {
			window.removeEventListener('afterglow:wizard-step', handler);
		}
	});
});
