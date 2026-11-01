import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/svelte';
import QuotaDonut from '../QuotaDonut.svelte';

describe('QuotaDonut observations', () => {
	it('keeps a fractional overrun visible with exact numeric accessibility', () => {
		const view = render(QuotaDonut, { label: 'CPU', used: 100.04, limit: 100 });
		expect(view.getByText('100.1%')).toBeTruthy();
		expect(Number(view.getByRole('meter').getAttribute('aria-valuenow'))).toBeCloseTo(100.04);
	});
	it('keeps overcommit visible and allows informational treatment', () => {
		const view = render(QuotaDonut, { label: 'CPU', used: 256, limit: 212, tone: 'info' });
		const meter = view.getByRole('meter');
		expect(Number(meter.getAttribute('aria-valuenow'))).toBeCloseTo(256 / 212 * 100);
		expect(meter.getAttribute('aria-valuetext')).toContain('120.8%');
		expect(meter.getAttribute('data-tone')).toBe('info');
	});

	it.each([null, undefined, Number.NaN, 0, -1])('does not fabricate a ratio for limit %s', (limit) => {
		const view = render(QuotaDonut, { label: 'CPU', used: 4, limit });
		expect(view.queryByRole('meter')).toBeNull();
		expect(view.getByRole('group').textContent).not.toContain('%');
	});

	it('does not publish missing usage as measured zero', () => {
		const view = render(QuotaDonut, { label: 'CPU', used: null, limit: 20 });
		expect(view.queryByRole('meter')).toBeNull();
		expect(view.getByRole('group').textContent).not.toContain('0%');
	});
});
