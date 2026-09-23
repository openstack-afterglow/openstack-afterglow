// @vitest-environment node
import { describe, expect, it } from 'vitest';

import { usageChartWindow } from '../chatUsageChartWindow';

describe('usageChartWindow', () => {
	it.each([
		['day', 30 * 24 * 60 * 60 * 1000, '최근 30일'],
		['hour', 48 * 60 * 60 * 1000, '최근 48시간'],
		['15m', 12 * 60 * 60 * 1000, '최근 12시간'],
		['5m', 4 * 60 * 60 * 1000, '최근 4시간']
	])('limits %s charts to the requested window', (bucket, milliseconds, label) => {
		expect(usageChartWindow(bucket)).toEqual({ milliseconds, label });
	});

	it('keeps month controlled by the date range filter', () => {
		expect(usageChartWindow('month')).toBeNull();
	});
});
