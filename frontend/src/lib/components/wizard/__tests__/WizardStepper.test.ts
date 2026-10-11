import { render } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import WizardStepper from '../WizardStepper.svelte';

describe('WizardStepper', () => {
	it('hides the desktop stepper on mobile because the header already names the current step', () => {
		const { container } = render(WizardStepper, {
			cur: 2,
			totalSteps: 4,
			stepLabels: ['이미지', '플레이버', '설정', '검토'],
			goTo: vi.fn(),
		});

		const stepper = container.querySelector('.stepper-container');
		expect(stepper?.className).toContain('hidden');
		expect(stepper?.className).toContain('md:block');
		expect(container.querySelector('[role="progressbar"]')).toBeNull();
		expect(container.querySelector('.full-stepper')?.className).toContain('py-2.5');
		expect(container.querySelector('.step-dot-current')?.className).toContain('w-7');
	});
});
