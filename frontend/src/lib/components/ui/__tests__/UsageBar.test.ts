import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/svelte';
import UsageBar from '../UsageBar.svelte';

describe('UsageBar', () => {
	it('keeps a fractional overrun above the limit in readable text', () => {
		const view = render(UsageBar, { percent: 100.04 });
		expect(view.getByText('100.1%')).toBeTruthy();
		expect(view.getByRole('meter').getAttribute('aria-valuenow')).toBe('100.04');
	});

	it('marks positive usage against a known zero quota without inventing a percentage', () => {
		const view = render(UsageBar, { value: 4, max: 0 });
		expect(view.queryByRole('meter')).toBeNull();
		expect(view.getByRole('group').getAttribute('data-tone')).toBe('danger');
		expect(view.getByRole('group').textContent).toMatch(/4\s*\/\s*0/);
		expect(view.getByRole('group').textContent).not.toContain('%');
	});
	it('retains an observed percentage above the quota in text and accessibility', () => {
		const view = render(UsageBar, { value: 125, max: 100 });
		expect(view.getByText('125%')).toBeTruthy();
		const meter = view.getByRole('meter');
		expect(meter.getAttribute('aria-valuenow')).toBe('125');
		expect(meter.getAttribute('aria-valuetext')).toContain('125%');
	});

	it('does not manufacture a ratio for a zero or missing denominator', () => {
		const view = render(UsageBar, { value: 0, max: 0 });
		expect(view.queryByRole('meter')).toBeNull();
		expect(view.getByRole('group').textContent).toMatch(/0\s*\/\s*0/);
		expect(view.getByRole('group').textContent).not.toContain('%');
	});

	it('labels unlimited capacity without inventing a percentage', () => {
		const view = render(UsageBar, { value: 4, max: -1 });
		expect(view.queryByRole('meter')).toBeNull();
		expect(view.getByRole('group').textContent).not.toContain('%');
	});

	it('does not reinterpret invalid observations as measured zero', () => {
		const view = render(UsageBar, { percent: Number.NaN });
		expect(view.queryByRole('meter')).toBeNull();
		expect(view.getByRole('group').textContent).not.toContain('0%');
	});

	it('allows physical allocation to use a caller-chosen informational tone', () => {
		const view = render(UsageBar, { percent: 150, tone: 'info' });
		expect(view.getByRole('meter').getAttribute('data-tone')).toBe('info');
		expect(view.getByRole('meter').getAttribute('aria-valuenow')).toBe('150');
	});
});
