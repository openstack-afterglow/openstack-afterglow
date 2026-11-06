// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { serviceTimestamp } from '../serviceList';

describe('native service timestamp projection', () => {
	it('compares actual instants across native timestamp formats and timezones', () => {
		expect(serviceTimestamp('2026-09-14T10:00:00+09:00')).toBe(Date.parse('2026-09-14T01:00:00Z'));
		expect(serviceTimestamp('2026-09-14 04:00:00')).toBe(Date.parse('2026-09-14T04:00:00Z'));
		expect(serviceTimestamp('2026-09-14T08:00:00Z')).toBe(Date.parse('2026-09-14T08:00:00Z'));
	});
	it('keeps missing and invalid native timestamps unknown', () => {
		for (const value of [null, undefined, '', 'not-a-date']) expect(serviceTimestamp(value)).toBeNull();
	});
});
