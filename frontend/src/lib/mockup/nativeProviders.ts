import { ApiError } from '$lib/api/errors';
import type { MockupProfileId } from './contracts';
import { onMockupRevisionChange } from './state';

/** Synthetic registry and Decisions fixtures. No provider or native IAM request runs. */
const version = '2026-11-17';
const catalogEntry = {
	id: 'gpt-6-luna', aliases: [], kind: 'text', display_name: 'GPT-6 Luna', status: 'active',
	context_window: 1048576, max_output_tokens: 65536,
	input_modalities: ['text', 'image'], output_modalities: ['text'],
	capabilities: { vision: true, tool_call: true, reasoning: true, prompt_caching: true, structured_output: true, web_search: false, decisions: true },
	token_pricing: { input: '0.10', output: '0.50', cache_read: '0.01', cache_write: '0.125', cache_write_ttl: '30m', cache_write_long: null, cache_write_long_ttl: null, long_context: { threshold_tokens: 272000, input: '0.20', output: '0.75', cache_read: '0.02', cache_write: '0.25', cache_write_long: null } },
	media_pricing: null, source_urls: ['https://developers.openai.com/api/docs/pricing'], verified_at: version,
	notes: 'Synthetic tutorial fixture; not live provider verification.',
};
const nativeCatalog = {
	schema_version: 1, catalog_version: version,
	providers: [{ provider_type: 'openai', display_name: 'OpenAI', pricing_sources: catalogEntry.source_urls, models: [catalogEntry] }],
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
	if (method === 'GET' && path === '/api/v1/chat/models' && params.get('model_kind') === 'text') {
		return [{ id: 43, provider_id: 7, provider_type: 'openai', provider_family: 'native', model_name: 'gpt-6-luna', api_model_name: 'gpt-6-luna', api_provider: 'openai', model_kind: 'text', display_name: 'GPT-6 Luna · Tutorial', provider: 'OpenAI', provider_api_key_configured: true, price_origin: 'native_catalog', catalog_version: version, capabilities: { ...catalogEntry.capabilities, feature_gates: { decisions: { available: true, mode: 'native', pricing_available: true, reason_code: null } } } }];
	}
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
