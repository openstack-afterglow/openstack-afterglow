import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/svelte';
import UsageBar from '../UsageBar.svelte';

describe('UsageBar', () => {
	it('renders a percentage once when it has no value/max pair', () => {
		const view = render(UsageBar, { percent: 79 });
		expect(view.getByText('79%')).toBeTruthy();
		expect(view.getByRole('meter').getAttribute('aria-valuenow')).toBe('79');
	});

	it('renders a finite zero maximum instead of hiding it', () => {
		const view = render(UsageBar, { value: 0, max: 0 });
		expect(view.getByRole('meter').textContent).toMatch(/0\s*\/\s*0/);
		expect(view.getByRole('meter').getAttribute('aria-valuenow')).toBe('0');
	});

	it('labels an unlimited maximum without fabricating a percentage or fill', () => {
		const view = render(UsageBar, { value: 4, max: -1 });
		expect(view.getByRole('group').textContent).toMatch(/4\s*\/\s*무제한/);
		expect(view.getByRole('group').textContent).not.toContain('%');
		expect(view.queryByRole('meter')).toBeNull();
	});

	it.each([[Number.NaN, 0], [-1, 0], [101, 100]])(
		'clamps percentage %s to %s',
		(percent, expected) => {
			const view = render(UsageBar, { percent });
			expect(view.getByText(`${expected}%`)).toBeTruthy();
			expect(view.getByRole('meter').getAttribute('aria-valuenow')).toBe(String(expected));
		},
	);
});
