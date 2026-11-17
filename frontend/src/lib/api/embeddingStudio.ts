import { t } from '$lib/i18n/ns/chat-studio';
import { api, ApiError, fetchWithAuth } from './client';
import { requireLumenCapability } from './lumenAccess';
import type { AvailableModel } from './chatTree';
import type { ExperienceContext } from '$lib/utils/experience';

export interface EmbeddingScope { token: string; projectId: string; experience?: ExperienceContext }
export interface EmbeddingModel extends AvailableModel {
	model_kind: 'embedding';
	provider_api_key_configured: boolean;
}
export interface EmbeddingCapabilities {
	model_id: number;
	model_kind: 'embedding';
	model_capabilities: EmbeddingModel['capabilities'];
	default_dimensions: number | null;
	supports_dimensions: boolean;
	min_dimensions: number | null;
	max_dimensions: number | null;
	max_input_tokens: number | null;
	max_inputs: number;
}
export interface EmbeddingRequest { model_id: number; input: string[]; dimensions?: number }
export interface EmbeddingResult {
	model_id: number;
	model: string;
	dimensions: number;
	embeddings: Array<{ index: number; embedding: number[] }>;
	usage: { prompt_tokens: number; total_tokens: number; estimated: boolean };
	credited_cost: number;
}
const object = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value);
const positiveInteger = (value: unknown): value is number => Number.isSafeInteger(value) && (value as number) > 0;
const nonnegativeInteger = (value: unknown): value is number => Number.isSafeInteger(value) && (value as number) >= 0;
const nullablePositive = (value: unknown) => value === null || positiveInteger(value);
function invalid(): never { throw new Error(t('embeddingStudio.invalidResponse')); }
function validGates(value: unknown): boolean {
	if (!object(value) || !object(value.feature_gates)) return false;
	const gate = value.feature_gates.embeddings;
	return object(gate) && typeof gate.available === 'boolean' && ['native', 'none'].includes(String(gate.mode))
		&& typeof gate.pricing_available === 'boolean' && (gate.reason_code === null || typeof gate.reason_code === 'string');
}
export function parseEmbeddingModels(value: unknown): EmbeddingModel[] {
	if (!Array.isArray(value)) invalid();
	const ids = new Set<number>();
	for (const model of value) {
		if (!object(model) || !positiveInteger(model.id) || ids.has(model.id) || model.model_kind !== 'embedding'
			|| typeof model.model_name !== 'string' || !model.model_name.trim() || typeof model.display_name !== 'string' || !model.display_name.trim()
			|| typeof model.provider_api_key_configured !== 'boolean' || !validGates(model.capabilities)) invalid();
		ids.add(model.id);
	}
	return value as EmbeddingModel[];
}
export function parseEmbeddingCapabilities(value: unknown, modelId: number): EmbeddingCapabilities {
	if (!object(value) || value.model_id !== modelId || value.model_kind !== 'embedding' || !validGates(value.model_capabilities)
		|| typeof value.supports_dimensions !== 'boolean' || !nullablePositive(value.default_dimensions)
		|| !nullablePositive(value.min_dimensions) || !nullablePositive(value.max_dimensions) || !nullablePositive(value.max_input_tokens)
		|| !positiveInteger(value.max_inputs) || value.max_inputs > 16) invalid();
	const result = value as unknown as EmbeddingCapabilities;
	if (result.min_dimensions !== null && result.max_dimensions !== null && result.min_dimensions > result.max_dimensions) invalid();
	if (result.default_dimensions !== null && ((result.min_dimensions !== null && result.default_dimensions < result.min_dimensions)
		|| (result.max_dimensions !== null && result.default_dimensions > result.max_dimensions))) invalid();
	return result;
}
export function embeddingReadiness(model: EmbeddingModel | undefined, capabilities: EmbeddingCapabilities | null): string | null {
	if (!model) return t('embeddingStudio.selectModel');
	if (model.model_kind !== 'embedding' || !positiveInteger(model.id)) return t('embeddingStudio.nativeUnavailable');
	if (!model.provider_api_key_configured) return t('embeddingStudio.providerKeyMissing');
	const listed = model.capabilities?.feature_gates?.embeddings;
	if (!listed || listed.available !== true || listed.mode !== 'native') return t('embeddingStudio.nativeUnavailable');
	if (listed.pricing_available !== true) return t('embeddingStudio.pricingMissing');
	if (!capabilities || capabilities.model_id !== model.id || capabilities.model_kind !== 'embedding') return t('embeddingStudio.unverified');
	const verified = capabilities.model_capabilities?.feature_gates?.embeddings;
	if (!verified || verified.available !== true || verified.mode !== 'native') return t('embeddingStudio.nativeUnavailable');
	if (verified.pricing_available !== true) return t('embeddingStudio.pricingMissing');
	return null;
}
export function parseEmbeddingResult(value: unknown, request: EmbeddingRequest): EmbeddingResult {
	if (!object(value) || value.model_id !== request.model_id || typeof value.model !== 'string' || !value.model.trim()
		|| !positiveInteger(value.dimensions) || (request.dimensions !== undefined && value.dimensions !== request.dimensions)
		|| !Array.isArray(value.embeddings) || value.embeddings.length !== request.input.length
		|| !object(value.usage) || !nonnegativeInteger(value.usage.prompt_tokens) || !nonnegativeInteger(value.usage.total_tokens)
		|| value.usage.total_tokens < value.usage.prompt_tokens || typeof value.usage.estimated !== 'boolean'
		|| typeof value.credited_cost !== 'number' || !Number.isFinite(value.credited_cost) || value.credited_cost < 0) invalid();
	for (const [index, entry] of value.embeddings.entries()) {
		if (!object(entry) || entry.index !== index || !Array.isArray(entry.embedding) || entry.embedding.length !== value.dimensions
			|| !entry.embedding.every((number: unknown) => typeof number === 'number' && Number.isFinite(number))) invalid();
	}
	return value as unknown as EmbeddingResult;
}

/** Scale before squaring so tiny and large finite provider values remain usable. */
export function vectorNorm(vector: readonly number[]): number {
	let scale = 0;
	for (const value of vector) scale = Math.max(scale, Math.abs(value));
	if (!scale) return 0;
	let squares = 0;
	for (const value of vector) squares += (value / scale) ** 2;
	return scale * Math.sqrt(squares);
}
export function cosineSimilarity(left: readonly number[], right: readonly number[]): number | null {
	if (!left.length || left.length !== right.length) return null;
	let leftScale = 0, rightScale = 0;
	for (let index = 0; index < left.length; index++) {
		if (!Number.isFinite(left[index]) || !Number.isFinite(right[index])) return null;
		leftScale = Math.max(leftScale, Math.abs(left[index]));
		rightScale = Math.max(rightScale, Math.abs(right[index]));
	}
	if (!leftScale || !rightScale) return null;
	let dot = 0, leftSquares = 0, rightSquares = 0;
	for (let index = 0; index < left.length; index++) {
		const a = left[index] / leftScale, b = right[index] / rightScale;
		dot += a * b; leftSquares += a * a; rightSquares += b * b;
	}
	return Math.max(-1, Math.min(1, dot / Math.sqrt(leftSquares) / Math.sqrt(rightSquares)));
}
export function cosineMatrix(result: EmbeddingResult): Array<Array<number | null>> {
	return result.embeddings.map((left) => result.embeddings.map((right) => cosineSimilarity(left.embedding, right.embedding)));
}
export const embeddingStudioApi = {
	async models(scope: EmbeddingScope, signal?: AbortSignal): Promise<EmbeddingModel[]> {
		return parseEmbeddingModels(await api.get<unknown>('/api/v1/chat/models?model_kind=embedding', scope.token, scope.projectId, { refresh: true, signal, experience: scope.experience }));
	},
	async capabilities(id: number, scope: EmbeddingScope, signal?: AbortSignal): Promise<EmbeddingCapabilities> {
		return parseEmbeddingCapabilities(await api.get<unknown>(`/api/v1/chat/capabilities?model_id=${id}&model_kind=embedding`, scope.token, scope.projectId, { refresh: true, signal, experience: scope.experience }), id);
	},
	async embed(request: EmbeddingRequest, scope: EmbeddingScope, signal?: AbortSignal): Promise<EmbeddingResult> {
		requireLumenCapability('lumen-chat_user', scope.token, scope.projectId);
		const response = await fetchWithAuth('/api/v1/chat/embeddings', {
			method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request), signal
		}, scope.token, scope.projectId, { experience: scope.experience });
		if (!response.ok) {
			const body: unknown = await response.json().catch(() => null);
			throw new ApiError(response.status, object(body) && typeof body.detail === 'string' ? body.detail : t('embeddingStudio.requestFailed', { status: response.status }));
		}
		return parseEmbeddingResult(await response.json(), request);
	}
};
