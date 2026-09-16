import { render } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import UsageRing from '../UsageRing.svelte';

describe('UsageRing', () => {
	it('exposes a clamped, text-equivalent quantitative meter', () => {
		const view = render(UsageRing, {
			percent: 130,
			label: '컨텍스트 입력 예산 사용률',
			valueText: '약 11,000 / 9,856 토큰 · 112%'
		});
		const meter = view.getByRole('meter', { name: '컨텍스트 입력 예산 사용률' });

		expect(meter.getAttribute('aria-valuenow')).toBe('100');
		expect(meter.getAttribute('aria-valuetext')).toBe('약 11,000 / 9,856 토큰 · 112%');
		expect(meter.getAttribute('data-tone')).toBe('danger');
	});

	it('uses caller-supplied thresholds', () => {
		const view = render(UsageRing, {
			percent: 70,
			thresholds: { warning: 70, danger: 90 },
			label: '사용률',
			valueText: '70%'
		});

		expect(view.getByRole('meter').getAttribute('data-tone')).toBe('warning');
	});
});
