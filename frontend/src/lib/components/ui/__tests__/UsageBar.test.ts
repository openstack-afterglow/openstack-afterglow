import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/svelte';
import UsageBar from '../UsageBar.svelte';

describe('UsageBar', () => {
	it('maps default thresholds to accent, warning, and danger', () => {
		expect(render(UsageBar, { percent: 79 }).container.querySelector('.usage-fill-accent')).toBeTruthy();
		expect(render(UsageBar, { percent: 80 }).container.querySelector('.usage-fill-warning')).toBeTruthy();
		expect(render(UsageBar, { percent: 95 }).container.querySelector('.usage-fill-danger')).toBeTruthy();
	});

	it('uses custom thresholds', () => {
		expect(render(UsageBar, { percent: 69, thresholds: { warning: 70, danger: 90 } }).container.querySelector('.usage-fill-accent')).toBeTruthy();
		expect(render(UsageBar, { percent: 70, thresholds: { warning: 70, danger: 90 } }).container.querySelector('.usage-fill-warning')).toBeTruthy();
		expect(render(UsageBar, { percent: 90, thresholds: { warning: 70, danger: 90 } }).container.querySelector('.usage-fill-danger')).toBeTruthy();
	});

	it('renders a percentage once when it has no value/max pair', () => {
		const { container } = render(UsageBar, { percent: 79 });
		expect(container.querySelector('.usage-value')?.textContent?.trim()).toBe('79%');
	});

	it('renders a finite zero maximum instead of hiding it', () => {
		const { container } = render(UsageBar, { value: 0, max: 0 });
		expect(container.querySelector('.usage-value')?.textContent).toMatch(/0\s*\/\s*0/);
	});

	it('labels an unlimited maximum without fabricating a percentage or fill', () => {
		const { container } = render(UsageBar, { value: 4, max: -1 });
		expect(container.querySelector('.usage-percent')).toBeNull();
		expect(container.querySelector('.usage-fill')).toBeNull();
		expect(container.querySelector('.usage-track')?.classList.contains('usage-track-unlimited')).toBe(true);
	});

	it('clamps non-finite and out-of-range percentages to the usable range', () => {
		expect(render(UsageBar, { percent: Number.NaN }).container.querySelector('.usage-percent')?.textContent).toBe(
			'0%',
		);
		expect(render(UsageBar, { percent: -1 }).container.querySelector('.usage-percent')?.textContent).toBe('0%');
		expect(render(UsageBar, { percent: 101 }).container.querySelector('.usage-percent')?.textContent).toBe('100%');
	});
});
