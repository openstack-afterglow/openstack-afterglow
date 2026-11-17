import { describe, expect, it } from 'vitest';
import {
	cosineMatrix,
	cosineSimilarity,
	embeddingReadiness,
	parseEmbeddingCapabilities,
	parseEmbeddingModels,
	parseEmbeddingResult,
	vectorNorm,
	type EmbeddingCapabilities,
	type EmbeddingModel,
	type EmbeddingResult
} from '../embeddingStudio';
import { t } from '$lib/i18n/ns/chat-studio';

const gate = (overrides: Record<string, unknown> = {}) => ({ feature_gates: { embeddings: { available: true, mode: 'native', reason_code: null, pricing_available: true, ...overrides } } });
const model = (overrides: Partial<EmbeddingModel> = {}): EmbeddingModel => ({
	id: 7, provider_id: 1, provider_type: 'openai', provider_sort_order: 0, sort_order: 0,
	model_name: 'text-embedding-3-small', display_name: 'Small embeddings', model_kind: 'embedding',
	provider_api_key_configured: true, capabilities: gate() as EmbeddingModel['capabilities'], ...overrides
});
const capabilities = (overrides: Partial<EmbeddingCapabilities> = {}): EmbeddingCapabilities => ({
	model_id: 7, model_kind: 'embedding', model_capabilities: gate() as EmbeddingModel['capabilities'],
	default_dimensions: 1536, supports_dimensions: true, min_dimensions: 1, max_dimensions: 1536, max_input_tokens: 8191, max_inputs: 16, ...overrides
});
const request = { model_id: 7, input: ['alpha', 'beta'] };
const result = (overrides: Record<string, unknown> = {}) => ({
	model_id: 7, model: 'text-embedding-3-small', dimensions: 3,
	embeddings: [{ index: 0, embedding: [1, 0, 0] }, { index: 1, embedding: [0, 2, 0] }],
	usage: { prompt_tokens: 4, total_tokens: 4, estimated: false }, credited_cost: 0.00001, ...overrides
});

describe('embeddingReadiness', () => {
	it.each([
		['no model', undefined, capabilities(), 'embeddingStudio.selectModel'],
		['provider key missing', model({ provider_api_key_configured: false }), capabilities(), 'embeddingStudio.providerKeyMissing'],
		['listed gate unavailable', model({ capabilities: gate({ available: false }) as EmbeddingModel['capabilities'] }), capabilities(), 'embeddingStudio.nativeUnavailable'],
		['listed gate managed rather than native', model({ capabilities: gate({ mode: 'none' }) as EmbeddingModel['capabilities'] }), capabilities(), 'embeddingStudio.nativeUnavailable'],
		['listed pricing missing', model({ capabilities: gate({ pricing_available: false }) as EmbeddingModel['capabilities'] }), capabilities(), 'embeddingStudio.pricingMissing'],
		['capabilities not loaded', model(), null, 'embeddingStudio.unverified'],
		['capabilities for another model', model(), capabilities({ model_id: 8 }), 'embeddingStudio.unverified'],
		['current gate unavailable', model(), capabilities({ model_capabilities: gate({ available: false }) as EmbeddingModel['capabilities'] }), 'embeddingStudio.nativeUnavailable'],
		['current pricing missing', model(), capabilities({ model_capabilities: gate({ pricing_available: false }) as EmbeddingModel['capabilities'] }), 'embeddingStudio.pricingMissing']
	] as const)('blocks when %s', (_case, selected, verified, key) => {
		expect(embeddingReadiness(selected, verified)).toBe(t(key));
	});

	it('is ready only with listed and exact-model verified native priced gates', () => {
		expect(embeddingReadiness(model(), capabilities())).toBeNull();
	});
});

describe('response validation', () => {
	it('accepts a well-formed result in input order', () => {
		expect(parseEmbeddingResult(result(), request).embeddings.map((entry) => entry.index)).toEqual([0, 1]);
	});

	it.each([
		['a different model id', result({ model_id: 8 })],
		['an embedding count that differs from the input count', result({ embeddings: [{ index: 0, embedding: [1, 0, 0] }] })],
		['dimensions that differ from the vector length', result({ dimensions: 4 })],
		['out-of-order indexes', result({ embeddings: [{ index: 1, embedding: [0, 2, 0] }, { index: 0, embedding: [1, 0, 0] }] })],
		['a non-finite value', result({ embeddings: [{ index: 0, embedding: [1, Number.NaN, 0] }, { index: 1, embedding: [0, 2, 0] }] })],
		['a string value', result({ embeddings: [{ index: 0, embedding: [1, '0', 0] }, { index: 1, embedding: [0, 2, 0] }] })],
		['negative credited cost', result({ credited_cost: -1 })],
		['non-integer prompt tokens', result({ usage: { prompt_tokens: 1.5, total_tokens: 4, estimated: false } })],
		['missing estimated flag', result({ usage: { prompt_tokens: 4, total_tokens: 4 } })],
		['total below prompt tokens', result({ usage: { prompt_tokens: 4, total_tokens: 3, estimated: false } })]
	])('rejects %s', (_case, payload) => {
		expect(() => parseEmbeddingResult(payload, request)).toThrow(t('embeddingStudio.invalidResponse'));
	});

	it('rejects dimensions that do not match the requested dimensions', () => {
		expect(() => parseEmbeddingResult(result(), { ...request, dimensions: 2 })).toThrow(t('embeddingStudio.invalidResponse'));
	});

	it('rejects capabilities for another model, impossible bounds and more than 16 inputs', () => {
		expect(() => parseEmbeddingCapabilities(capabilities(), 8)).toThrow(t('embeddingStudio.invalidResponse'));
		expect(() => parseEmbeddingCapabilities(capabilities({ min_dimensions: 10, max_dimensions: 5 }), 7)).toThrow(t('embeddingStudio.invalidResponse'));
		expect(() => parseEmbeddingCapabilities(capabilities({ default_dimensions: 2048 }), 7)).toThrow(t('embeddingStudio.invalidResponse'));
		expect(() => parseEmbeddingCapabilities(capabilities({ max_inputs: 17 }), 7)).toThrow(t('embeddingStudio.invalidResponse'));
		expect(parseEmbeddingCapabilities(capabilities(), 7).max_inputs).toBe(16);
	});

	it('preserves flattened catalog dimension ranges and explicit allowed choices', () => {
		const published = capabilities({ default_dimensions: 768, min_dimensions: 256, max_dimensions: 768, allowed_dimensions: [256, 768] });
		expect(parseEmbeddingCapabilities(published, 7)).toEqual(published);
		expect(parseEmbeddingCapabilities(capabilities({ allowed_dimensions: null }), 7).allowed_dimensions).toBeNull();
	});

	it.each([
		[], [0, 1536], [1.5, 1536], [256, 256, 1536], [256, 1537], [256, 768]
	])('rejects malformed, out-of-range or default-missing dimension choices %j', (...allowed) => {
		expect(() => parseEmbeddingCapabilities(capabilities({ allowed_dimensions: allowed }), 7)).toThrow(t('embeddingStudio.invalidResponse'));
	});

	it('rejects model lists with duplicate ids or non-embedding kinds', () => {
		expect(() => parseEmbeddingModels([model(), model()])).toThrow(t('embeddingStudio.invalidResponse'));
		expect(() => parseEmbeddingModels([{ ...model(), model_kind: 'chat' }])).toThrow(t('embeddingStudio.invalidResponse'));
		expect(parseEmbeddingModels([model(), model({ id: 8 })]).map((item) => item.id)).toEqual([7, 8]);
	});
});

describe('vector math', () => {
	it('computes L2 norm without overflowing or underflowing finite values', () => {
		expect(vectorNorm([3, 4])).toBe(5);
		expect(vectorNorm([0, 0])).toBe(0);
		expect(vectorNorm([1e200, 1e200])).toBeCloseTo(Math.SQRT2 * 1e200, -186);
		expect(vectorNorm([3e-200, 4e-200])).toBeCloseTo(5e-200, 210);
	});

	it('computes cosine similarity as dot product over norms', () => {
		expect(cosineSimilarity([1, 2, 3], [2, 4, 6])).toBeCloseTo(1, 12);
		expect(cosineSimilarity([1, 0], [-1, 0])).toBeCloseTo(-1, 12);
		expect(cosineSimilarity([1, 0], [0, 5])).toBeCloseTo(0, 12);
		expect(cosineSimilarity([1, 2], [3, 4])).toBeCloseTo(11 / (Math.sqrt(5) * 5), 12);
		expect(cosineSimilarity([1e200, 0], [1e200, 1e200])).toBeCloseTo(Math.SQRT1_2, 12);
	});

	it('leaves zero vectors and mismatched lengths undefined instead of inventing a value', () => {
		expect(cosineSimilarity([0, 0], [1, 0])).toBeNull();
		expect(cosineSimilarity([1, 0], [1, 0, 0])).toBeNull();
	});

	it('builds a symmetric matrix with a unit diagonal', () => {
		const matrix = cosineMatrix(result({ embeddings: [{ index: 0, embedding: [1, 0, 0] }, { index: 1, embedding: [1, 1, 0] }, { index: 2, embedding: [0, 0, 3] }] }) as EmbeddingResult);
		expect(matrix.map((row, index) => row[index])).toEqual([1, 1, 1].map((value) => expect.closeTo(value, 12)));
		expect(matrix[0][1]).toBeCloseTo(Math.SQRT1_2, 12);
		expect(matrix[1][0]).toBeCloseTo(matrix[0][1]!, 12);
		expect(matrix[0][2]).toBeCloseTo(0, 12);
	});
});
