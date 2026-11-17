import { describe, expect, it } from 'vitest';
import { effectiveBasis, pricingDraft, pricingError, pricingPayload } from '../modelPricing';

describe('embedding model pricing', () => {
	it('uses input-token pricing without media reservations or output rates', () => {
		const draft = pricingDraft();
		expect(effectiveBasis('embedding', draft)).toBe('tokens');
		expect(pricingError('embedding', draft)).toBeUndefined();
		expect(pricingPayload(draft)).toBeNull();
	});
});
