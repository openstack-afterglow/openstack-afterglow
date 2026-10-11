import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import WizardFooter from '../WizardFooter.svelte';

describe('WizardFooter', () => {
	it('keeps one tutorial navigation surface with responsive placement', async () => {
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

		const footer = container.querySelector('.wizard-footer');
		expect(footer?.className.split(/\s+/)).toContain('sticky');
		expect(footer?.className).toContain('bottom-0');
		expect(footer?.className).toContain('flex-none');
		expect(footer?.className).toContain('bg-[var(--color-surface-base)]');
		expect(footer?.className).toContain('border-[var(--color-line)]');
		expect(footer?.className).toContain('border-t');
		expect(footer?.className).not.toContain('md:sticky');
		expect(footer?.className).not.toContain('md:order-last');
		expect(container.querySelectorAll('[data-tour="wizard-nav"]')).toHaveLength(1);
		expect(container.querySelector('[data-tour="wizard-cancel"]')?.className).toContain('order-2');
		expect(container.querySelector('[data-tour="wizard-prev"]')?.className).toContain('order-1');
		expect(container.querySelector('[data-tour="wizard-next"]')?.className).toContain('order-3');
		expect(container.querySelectorAll('.pick')).toHaveLength(2);
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
