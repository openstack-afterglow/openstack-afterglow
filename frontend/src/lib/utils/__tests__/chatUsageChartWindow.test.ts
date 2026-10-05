// @vitest-environment node
import { describe, expect, it } from 'vitest';

import { usageChartWindow } from '../chatUsageChartWindow';

describe('usageChartWindow', () => {
	it.each([
		['day', 30 * 24 * 60 * 60 * 1000],
		['hour', 48 * 60 * 60 * 1000],
		['15m', 12 * 60 * 60 * 1000],
		['5m', 4 * 60 * 60 * 1000]
	])('limits %s charts to the requested window', (bucket, milliseconds) => {
		expect(usageChartWindow(bucket)?.milliseconds).toBe(milliseconds);
	});

	it('keeps month controlled by the date range filter', () => {
		expect(usageChartWindow('month')).toBeNull();
	});
});
