import { describe, expect, it } from 'vitest';
import { effectiveBasis, pricingDraft, pricingError, pricingPayload } from '../modelPricing';

describe('embedding model pricing', () => {
	it('uses input-token pricing without media reservations or output rates', () => {
		const draft = pricingDraft();
		expect(effectiveBasis('embedding', draft)).toBe('tokens');
		expect(pricingError('embedding', draft)).toBeUndefined();
		expect(pricingPayload('embedding', draft)).toBeNull();
	});

	it('discards stale hidden media fields when switching a candidate to embedding', () => {
		const draft = pricingDraft({ billing_basis: 'tokens', reservation_usd: '2', token_rates: { image: { output_per_million: '30' } } });
		draft.rates.audio_per_character = 'invalid hidden value';
		draft.variants = [{ id: 0, name: 'unfinished', price: '' }];
		expect(pricingError('embedding', draft)).toBeUndefined();
		expect(pricingPayload('embedding', draft)).toBeNull();
		expect(pricingPayload('embedding', draft, { image_per_unit: '0.04' })).toBeNull();
	});

	it('keeps existing media prices intact for non-embedding edits', () => {
		const baseline = { billing_basis: 'unit' as const, image_per_unit: '0.04', future_rate: '3' };
		const draft = pricingDraft(baseline);
		draft.rates.image_per_unit = '0.08';
		expect(pricingPayload('image', draft, baseline)).toEqual({ ...baseline, image_per_unit: '0.08' });
	});
});
