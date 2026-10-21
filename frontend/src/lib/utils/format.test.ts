import { describe, expect, it } from 'vitest';
import { formatSize } from './format';

describe('image size observations', () => {
	it('keeps measured zero distinguishable from an unknown image size', () => {
		expect(formatSize(0)).toBe('0 MB');
		expect(formatSize(null)).toBe('-');
	});
});
