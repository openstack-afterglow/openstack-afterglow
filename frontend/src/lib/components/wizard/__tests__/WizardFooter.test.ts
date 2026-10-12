import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import WizardFooter from '../WizardFooter.svelte';
import Wrapper from './_WizardConsumerWrapper.svelte';
import { wizard, wizardPassword } from '$lib/stores/wizard';
import type { VmCreateStore } from '$lib/stores/vmCreateStore.svelte';
import { prepareWizardConsumer, wizardResource } from './wizardConsumerFixtures';
import { t } from '$lib/i18n/ns/vm-wizard';

vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$lib/api/client', () => ({
	api: { get: (path: string) => Promise.resolve(wizardResource(path) ?? { history: [], presets: [] }) },
	ApiError: class ApiError extends Error {},
	fetchWithAuth: vi.fn(),
	getBaseUrl: () => '',
}));

afterEach(cleanup);

describe('WizardFooter', () => {
	it('keeps one tutorial navigation surface and invokes actions', async () => {
		const onCancel = vi.fn();
		const onPrev = vi.fn();
		const onNext = vi.fn();
		const onDeploy = vi.fn();
		const { container } = render(WizardFooter, {
			imageDisplay: 'ubuntu:24.04',
			flavorDisplay: 'cpu.2c_4g',
			step: 2,
			totalSteps: 4,
			canPrev: true,
			canNext: true,
			onCancel,
			onPrev,
			onNext,
			onDeploy,
		});

		expect(container.querySelectorAll('[data-tour="wizard-nav"]')).toHaveLength(1);
		expect(screen.getByText('ubuntu:24.04')).toBeTruthy();
		expect(screen.getByText('cpu.2c_4g')).toBeTruthy();
		expect(screen.getByRole('button', { name: '다음 →' })).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: '취소' }));
		await fireEvent.click(screen.getByRole('button', { name: '← 이전' }));
		await fireEvent.click(screen.getByRole('button', { name: '다음 →' }));
		expect(onCancel).toHaveBeenCalledOnce();
		expect(onPrev).toHaveBeenCalledOnce();
		expect(onNext).toHaveBeenCalledOnce();
	});

	it('uses deploy action on the final step', async () => {
		const onDeploy = vi.fn();
		render(WizardFooter, {
			step: 4,
			totalSteps: 4,
			canPrev: true,
			canNext: true,
			onCancel: vi.fn(),
			onPrev: vi.fn(),
			onNext: vi.fn(),
			onDeploy,
		});

		await fireEvent.click(screen.getByRole('button', { name: 'VM 생성' }));
		expect(onDeploy).toHaveBeenCalledOnce();
	});
});

describe('WizardFooter Windows readiness', () => {
	it.each([1, 2, 5, 6])('blocks its action after a supported to unsupported transition on step %s', async step => {
		prepareWizardConsumer(step);
		wizard.update(w => ({ ...w, imageId: 'windows-native', keyName: 'test-keypair' }));
		let store!: VmCreateStore;
		const onNext = vi.fn();
		const onDeploy = vi.fn();
		render(Wrapper, { component: 'footer', onStore: value => { store = value; }, onNext, onDeploy });
		await store.loadBootOptions();
		await store.loadFlavorOptions();
		await tick();
		wizardPassword.set({ password: 'Native-footer-123!', confirmation: 'Native-footer-123!' });
		await tick();
		const action = screen.getByRole('button', { name: step === 6 ? t('footer.create') : t('footer.next') }) as HTMLButtonElement;
		expect(action.disabled).toBe(false);
		await fireEvent.click(action);
		expect(step === 6 ? onDeploy : onNext).toHaveBeenCalledOnce();
		onNext.mockClear();
		onDeploy.mockClear();

		wizard.update(w => ({ ...w, imageId: 'windows-unsupported' }));
		await tick();
		await tick();
		expect(action.disabled).toBe(true);
		action.click();
		expect(onNext).not.toHaveBeenCalled();
		expect(onDeploy).not.toHaveBeenCalled();
		if (step === 1 || step === 2) {
			expect(within(screen.getByTestId('windows-unsupported-footer')).getByRole('alert').textContent?.trim()).toBeTruthy();
		} else {
			expect(screen.queryByTestId('windows-unsupported-footer')).toBeNull();
		}

		wizard.update(w => ({ ...w, imageId: 'image-a' }));
		await tick();
		expect(screen.queryByTestId('windows-unsupported-footer')).toBeNull();
		expect(action.disabled).toBe(false);
	});
});
