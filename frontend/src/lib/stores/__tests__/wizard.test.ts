import { describe, it, expect, beforeEach, vi } from 'vitest';
import { get } from 'svelte/store';

describe('wizard store', () => {
	beforeEach(() => {
		vi.resetModules();
	});

	it('초기 wizardOpen 상태는 false', async () => {
		const { wizardOpen } = await import('../wizard');
		expect(get(wizardOpen)).toBe(false);
	});

	it('openWizard()로 wizardOpen이 true', async () => {
		const { wizardOpen, openWizard } = await import('../wizard');
		openWizard();
		expect(get(wizardOpen)).toBe(true);
	});

	it('closeWizard()로 wizardOpen이 false', async () => {
		const { wizardOpen, openWizard, closeWizard } = await import('../wizard');
		openWizard();
		closeWizard();
		expect(get(wizardOpen)).toBe(false);
	});

	it('wizard 초기 상태에 필수 필드 존재', async () => {
		const { wizard } = await import('../wizard');
		const state = get(wizard);
		expect(state.step).toBe(1);
		expect(state.imageId).toBeNull();
		expect(state.flavorId).toBeNull();
		expect(state.libraries).toEqual([]);
		expect(state.strategy).toBeNull();
		expect(state.squashfsMode).toBeNull();
		expect(state.layerProfileName).toBeNull();
		expect(state.layerArtifactIds).toEqual([]);
		expect(state.instanceName).toBe('');
		expect(state.deleteBootVolumeOnTermination).toBe(false);
		expect(state.additionalVolumeIds).toEqual([]);
		expect(state.newVolumes).toEqual([]);
	});

	it('wizard.set으로 상태 업데이트', async () => {
		const { wizard } = await import('../wizard');
		const current = get(wizard);
		wizard.set({ ...current, step: 2, imageId: 'img-1', imageName: 'Ubuntu 22.04' });
		const updated = get(wizard);
		expect(updated.step).toBe(2);
		expect(updated.imageId).toBe('img-1');
		expect(updated.imageName).toBe('Ubuntu 22.04');
	});

	it('resetWizard()로 초기 상태 복원', async () => {
		const { wizard, resetWizard } = await import('../wizard');
		const initial = get(wizard);
		wizard.set({ ...initial, step: 3, flavorId: 'flavor-1', instanceName: 'my-vm' });
		resetWizard();
		const after = get(wizard);
		expect(after.step).toBe(1);
		expect(after.flavorId).toBeNull();
		expect(after.instanceName).toBe('');
	});

	it('resetWizard는 선택한 라이브러리를 빈 배열로 복원', async () => {
		const { wizard, resetWizard } = await import('../wizard');
		const initial = get(wizard);
		// 새 배열 인스턴스로 교체하면 reset 후에도 초기값 빈 배열로 복원됨
		wizard.set({ ...initial, libraries: ['lib-a'] });
		resetWizard();
		expect(get(wizard).libraries).toEqual([]);
	});

	it('wizardOpen subscribe로 변화 감지', async () => {
		const { wizardOpen, openWizard, closeWizard } = await import('../wizard');
		const states: boolean[] = [];
		const unsub = wizardOpen.subscribe((v) => states.push(v));
		openWizard();
		closeWizard();
		unsub();
		expect(states).toEqual([false, true, false]);
	});

	it('wizard 단계 변경 이벤트를 detail.step과 함께 한 번만 발행', async () => {
		const { wizard } = await import('../wizard');
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
