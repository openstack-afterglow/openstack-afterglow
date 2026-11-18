import { ApiError } from '$lib/api/errors';
import type { MockupProfileId } from './contracts';
import { onMockupRevisionChange } from './state';
import type { NativeCatalog, NativeCatalogEntry } from '$lib/api/nativeCatalog';

/** Synthetic registry and Decisions fixtures. No provider or native IAM request runs. */
const version = '2026-11-17';
const catalogEntry: NativeCatalogEntry = {
	id: 'gpt-6-luna', aliases: [], kind: 'text', display_name: 'GPT-6 Luna', status: 'active',
	context_window: 1048576, max_output_tokens: 65536,
	input_modalities: ['text', 'image'], output_modalities: ['text'],
	capabilities: { vision: true, tool_call: true, reasoning: true, prompt_caching: true, structured_output: true, web_search: false, decisions: true },
	token_pricing: { input: '0.10', output: '0.50', cache_read: '0.01', cache_write: '0.125', cache_write_ttl: '30m', cache_write_long: null, cache_write_long_ttl: null, long_context: { threshold_tokens: 272000, input: '0.20', output: '0.75', cache_read: '0.02', cache_write: '0.25', cache_write_long: null } },
	media_pricing: null, source_urls: ['https://developers.openai.com/api/docs/pricing'], verified_at: version,
	notes: 'Synthetic tutorial fixture; not live provider verification.',
};
const embeddingDimensions = { default_dimensions: 1536, supports_dimensions: true, min_dimensions: 1, max_dimensions: 1536, allowed_dimensions: null };
const embeddingEntry: NativeCatalogEntry = {
	...catalogEntry, id: 'text-embedding-3-small', display_name: 'Text Embedding 3 Small · Tutorial', kind: 'embedding',
	context_window: 8191, max_output_tokens: null, input_modalities: ['text'], capabilities: {},
	token_pricing: { input: '0.02' },
	embedding: embeddingDimensions,
};
/** Public-looking tutorial examples are display fixtures, not a second model catalog. */
function tutorialEntry(id: string, displayName: string, source: string, overrides: Partial<NativeCatalogEntry> = {}): NativeCatalogEntry {
	return { ...catalogEntry, id, display_name: displayName, source_urls: [source], capabilities: { tool_call: true }, ...overrides };
}
const nativeCatalog: NativeCatalog = {
	schema_version: 1, catalog_version: version,
	providers: [
		{ provider_type: 'openai', display_name: 'OpenAI', pricing_sources: catalogEntry.source_urls, models: [
			catalogEntry, embeddingEntry,
			tutorialEntry('gpt-image-1.5', 'GPT Image · Tutorial', catalogEntry.source_urls[0], { kind: 'image', token_pricing: null, media_pricing: { billing_basis: 'unit', image_per_unit: '0.04', reservation_usd: '0.10' } }),
			tutorialEntry('tutorial-openai-preview', 'Preview · Synthetic', catalogEntry.source_urls[0], { status: 'preview' }),
			tutorialEntry('tutorial-openai-deprecated', 'Deprecated · Synthetic', catalogEntry.source_urls[0], { status: 'deprecated' }),
			tutorialEntry('tutorial-openai-page-two', 'Additional model · Synthetic', catalogEntry.source_urls[0]),
		] },
		{ provider_type: 'anthropic', display_name: 'Anthropic', pricing_sources: ['https://platform.claude.com/docs/en/about-claude/pricing'], models: [
			tutorialEntry('claude-sonnet-5', 'Claude Sonnet · Tutorial', 'https://platform.claude.com/docs/en/about-claude/pricing', { token_pricing: { input: '3', output: '15', cache_read: '0.30', cache_write: '3.75', cache_write_ttl: '5m', cache_write_long: '6', cache_write_long_ttl: '1h', long_context: { threshold_tokens: 200000, input: '6', output: '22.50', cache_read: '0.60', cache_write: '7.50', cache_write_long: '12' } } }),
			tutorialEntry('tutorial-claude-preview', 'Claude Preview · Synthetic', 'https://platform.claude.com/docs/en/about-claude/pricing', { status: 'preview' }),
			tutorialEntry('tutorial-claude-deprecated', 'Claude Deprecated · Synthetic', 'https://platform.claude.com/docs/en/about-claude/pricing', { status: 'deprecated' }),
		] },
		{ provider_type: 'gemini', display_name: 'Google Gemini', pricing_sources: ['https://ai.google.dev/gemini-api/docs/pricing'], models: [
			tutorialEntry('gemini-3.1-pro-preview', 'Gemini Pro · Tutorial', 'https://ai.google.dev/gemini-api/docs/pricing', { status: 'preview', token_pricing: { input: '2', output: '12', cache_read: '0.20', long_context: { threshold_tokens: 200000, input: '4', output: '18', cache_read: '0.40' } } }),
			tutorialEntry('gemini-embedding-001', 'Gemini Embedding · Tutorial', 'https://ai.google.dev/gemini-api/docs/pricing', { kind: 'embedding', input_modalities: ['text'], max_output_tokens: null, token_pricing: { input: '0.15' }, embedding: { default_dimensions: 3072, supports_dimensions: true, min_dimensions: 128, max_dimensions: 3072, allowed_dimensions: null } }),
			tutorialEntry('tutorial-gemini-image', 'Gemini Image · Synthetic', 'https://ai.google.dev/gemini-api/docs/pricing', { kind: 'image', token_pricing: null, media_pricing: { billing_basis: 'unit', image_per_unit: '0.03', reservation_usd: '0.10' } }),
		] },
		{ provider_type: 'perplexity', display_name: 'Perplexity', pricing_sources: ['https://docs.perplexity.ai/guides/pricing'], models: [
			tutorialEntry('sonar', 'Sonar · Tutorial', 'https://docs.perplexity.ai/guides/pricing', { token_pricing: { input: '1', output: '1' } }),
			tutorialEntry('tutorial-sonar-preview', 'Sonar Preview · Synthetic', 'https://docs.perplexity.ai/guides/pricing', { status: 'preview' }),
			tutorialEntry('tutorial-sonar-deprecated', 'Sonar Deprecated · Synthetic', 'https://docs.perplexity.ai/guides/pricing', { status: 'deprecated' }),
		] },
	],
};
const providers = [
	{ id: 7, name: 'OpenAI · Tutorial', provider_type: 'openai', provider_family: 'native', api_provider: 'openai', sort_order: 0, api_base: null, auth_mode: 'api_key', has_api_key: true, has_credentials: true, auth_status: 'configured', is_active: true, margin_multiplier: 1, billing_capability: 'openai_admin_usage', has_billing_admin_key: false },
	{ id: 8, name: 'Compatible · Tutorial', provider_type: 'openai', provider_family: 'compatible', api_provider: 'tutorial-compatible', sort_order: 1, api_base: 'https://compatible.example.invalid/v1', auth_mode: 'api_key', has_api_key: true, has_credentials: true, auth_status: 'configured', is_active: true, margin_multiplier: 1, billing_capability: null, has_billing_admin_key: false },
];
function initialModels(): Record<string, unknown>[] {
	return [
		{ id: 43, provider_id: 7, provider_family: 'native', api_provider: 'openai', sort_order: 0, model_name: 'gpt-6-luna', api_model_name: 'gpt-6-luna', display_name: 'GPT-6 Luna · Tutorial', model_kind: 'text', is_active: true, is_title_model: false, is_memory_model: false, input_price_per_million: null, output_price_per_million: null, cache_read_price_per_million: null, cache_write_price_per_million: null, cache_write_1h_price_per_million: null, effective_input_price_per_million: '0.10', effective_output_price_per_million: '0.50', effective_price_source: 'native_catalog', price_source: null, price_origin: 'native_catalog', catalog_version: version, catalog_entry: { id: catalogEntry.id, status: catalogEntry.status, verified_at: version, source_urls: catalogEntry.source_urls }, media_pricing: null, capabilities: null, effective_capabilities: catalogEntry.capabilities, capability_source: null, effective_capability_source: 'native_catalog' },
		{ id: 44, provider_id: 8, provider_family: 'compatible', api_provider: 'tutorial-compatible', sort_order: 0, model_name: 'tutorial-custom-model', api_model_name: 'tutorial-custom-model', display_name: 'Compatible model · Tutorial', model_kind: 'text', is_active: true, is_title_model: false, is_memory_model: false, input_price_per_million: '1.00', output_price_per_million: '2.00', cache_read_price_per_million: null, cache_write_price_per_million: null, cache_write_1h_price_per_million: null, effective_input_price_per_million: '1.00', effective_output_price_per_million: '2.00', effective_price_source: 'manual', price_source: 'manual', price_origin: 'manual', catalog_version: null, catalog_entry: null, media_pricing: null, capabilities: null, effective_capabilities: { tool_call: false, vision: false, decisions: false }, capability_source: null, effective_capability_source: 'default' },
	];
}
let models = initialModels();
onMockupRevisionChange(() => { models = initialModels(); });
export function mockNativeProviders(method: string, path: string, params: URLSearchParams, body: unknown, profile: MockupProfileId): unknown | undefined {
	if (path.startsWith('/api/v1/chat/admin/')) {
		if (profile !== 'admin') throw new ApiError(403, 'Forbidden');
		if (path.startsWith('/api/v1/chat/admin/models/pricing/models-dev')) throw new ApiError(404, 'Not found');
		if (path === '/api/v1/chat/admin/models/native-catalog') {
			if (method !== 'GET') throw new ApiError(405, 'Method not allowed');
			return { ...nativeCatalog, providers: nativeCatalog.providers.filter(provider => !params.has('provider_type') || provider.provider_type === params.get('provider_type')) };
		}
		if (method === 'GET' && path === '/api/v1/chat/admin/providers') return providers;
		if (method === 'GET' && path === '/api/v1/chat/admin/models') return models;
		if (method === 'GET' && path === '/api/v1/chat/admin/providers/billing') return [];
		const modelId = path.match(/^\/api\/v1\/chat\/admin\/models\/(\d+)$/)?.[1];
		if (method === 'PATCH' && modelId) {
			const model = models.find(item => item.id === Number(modelId));
			if (!model) throw new ApiError(404, 'Not found');
			if (!body || typeof body !== 'object' || Array.isArray(body)) throw new ApiError(422, 'Invalid model');
			const next = { ...model, ...body };
			if (next.provider_family === 'compatible' && (next.input_price_per_million == null || next.output_price_per_million == null)) {
				throw new ApiError(422, 'compatible_provider_requires_manual_pricing');
			}
			Object.assign(model, body);
			const manual = model.input_price_per_million !== null || model.output_price_per_million !== null;
			model.price_origin = manual ? 'manual' : model.provider_family === 'native' ? 'native_catalog' : null;
			model.effective_price_source = model.price_origin;
			model.effective_input_price_per_million = model.input_price_per_million ?? (model.provider_family === 'native' ? '0.10' : null);
			model.effective_output_price_per_million = model.output_price_per_million ?? (model.provider_family === 'native' ? '0.50' : null);
			return model;
		}
	}
	if (method === 'GET' && path === '/api/v1/chat/models' && params.get('model_kind') === 'embedding') {
		return [{ id: 42, provider_id: 7, provider_type: 'openai', model_name: embeddingEntry.id, api_model_name: embeddingEntry.id, api_provider: 'openai', model_kind: 'embedding', display_name: embeddingEntry.display_name, provider: 'OpenAI', provider_api_key_configured: true, embedding: embeddingDimensions, capabilities: { embedding: embeddingDimensions, feature_gates: { embeddings: { available: true, mode: 'native', pricing_available: true, reason_code: null } } } }];
	}
	if (method === 'GET' && path === '/api/v1/chat/capabilities' && params.get('model_kind') === 'embedding') {
		if (params.get('model_id') !== '42') throw new ApiError(404, 'Not found');
		return { model_id: 42, model_kind: 'embedding', model_capabilities: { embedding: embeddingDimensions, feature_gates: { embeddings: { available: true, mode: 'native', pricing_available: true, reason_code: null } } }, embedding: embeddingDimensions, ...embeddingDimensions, max_input_tokens: embeddingEntry.context_window, max_inputs: 16 };
	}
	if (method === 'POST' && path === '/api/v1/chat/embeddings') {
		const payload = body as { model_id?: number; input?: string[]; dimensions?: number } | null;
		const dimension = payload?.dimensions ?? embeddingDimensions.default_dimensions;
		if (payload?.model_id !== 42 || !Number.isSafeInteger(dimension) || dimension < embeddingDimensions.min_dimensions || dimension > embeddingDimensions.max_dimensions || !payload.input?.length || payload.input.length > 16) throw new ApiError(422, 'Invalid embeddings request');
		const tokens = payload.input.reduce((sum, text) => sum + text.length, 0);
		return { model_id: 42, model: embeddingEntry.id, dimensions: dimension, embeddings: payload.input.map((_, index) => ({ index, embedding: Array.from({ length: dimension }, (_, axis) => axis === index ? 1 : 0) })), usage: { prompt_tokens: tokens, total_tokens: tokens, estimated: true }, credited_cost: 0 };
	}
	if (method === 'GET' && path === '/api/v1/chat/models' && params.get('model_kind') === 'text') {
		return [{ id: 43, provider_id: 7, provider_type: 'openai', provider_family: 'native', model_name: 'gpt-6-luna', api_model_name: 'gpt-6-luna', api_provider: 'openai', model_kind: 'text', display_name: 'GPT-6 Luna · Tutorial', provider: 'OpenAI', provider_api_key_configured: true, price_origin: 'native_catalog', catalog_version: version, capabilities: { ...catalogEntry.capabilities, feature_gates: { decisions: { available: true, mode: 'native', pricing_available: true, reason_code: null } } } }];
	}
	if (method === 'GET' && path === '/api/v1/chat/models' && params.get('model_kind') === 'decision') return [];
	if (method === 'GET' && path === '/api/v1/chat/capabilities' && params.get('model_kind') === 'text') {
		if (params.get('model_id') !== '43') throw new ApiError(404, 'Not found');
		return { model_id: 43, model_kind: 'text', model_capabilities: { ...catalogEntry.capabilities, feature_gates: { decisions: { available: true, mode: 'native', pricing_available: true, reason_code: null } } } };
	}
	if (method === 'POST' && path === '/api/v1/chat/decisions') {
		const payload = body as { model?: string; questions?: { type: string; name?: string; choices?: { value: string }[]; levels?: { label: string }[] }[] } | null;
		if (!payload?.questions?.length || payload.questions.length > 400) throw new ApiError(422, 'Invalid questions');
		return {
			model: payload.model, answers: payload.questions.map(question => ({
				type: question.type, name: question.name ?? null,
				...(question.type === 'predicate' ? { probability: 0.92 } : question.type === 'choice' ? { choice: question.choices?.[0]?.value, confidence: 0.9, probabilities: question.choices?.map((choice, index, choices) => ({ value: choice.value, probability: index === 0 ? 0.9 : 0.1 / (choices.length - 1) })) } : { score: 0.8, confidence: 0.85, probabilities: question.levels?.map((level, index, levels) => ({ value: index, label: level.label, probability: index === levels.length - 1 ? 0.85 : 0.15 / (levels.length - 1) })) }),
			})), usage: { input_tokens: 120, input_tokens_details: { cached_tokens: 0, cache_write_tokens: 0 }, output_tokens: 0, output_tokens_details: { reasoning_tokens: 0 }, total_tokens: 120 }, cost_usd: 0.000012, credited_cost: 0.000012, usage_log_id: '00000000-0000-4000-8000-000000000001',
		};
	}
	return undefined;
}
