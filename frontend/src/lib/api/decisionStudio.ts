import { get } from 'svelte/store';
import { auth, authReady, projectSwitching } from '$lib/stores/auth';
import { serviceCapabilities } from '$lib/stores/servicePermissions';
import { sessionScopeKey } from '$lib/utils/authSession';
import { t } from '$lib/i18n/ns/decision-studio';
import { api, ApiError, fetchWithAuth } from './client';
import { requireLumenCapability } from './lumenAccess';
import type { AvailableModel } from './chatTree';
import type { ExperienceContext } from '$lib/utils/experience';

/** Studio limits stay below the native endpoint's 16 MiB body ceiling. */
export const MAX_DECISION_IMAGE_BYTES = 4 * 1024 * 1024;
export const MAX_DECISION_REQUEST_BYTES = 8 * 1024 * 1024;
export const MAX_DECISION_JSON_BYTES = 256 * 1024;
export const DECISION_IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/webp', 'image/gif'] as const;
export interface DecisionScope { token: string; projectId: string; experience?: ExperienceContext }
export interface DecisionModel extends AvailableModel {
	model_kind: 'text';
	provider_api_key_configured: boolean;
}
export interface DecisionCapabilities {
	model_id: number;
	model_kind: 'text';
	model_capabilities: NonNullable<DecisionModel['capabilities']>;
}
export type DecisionPart = { type: 'input_text'; text: string }
	| { type: 'input_json'; data: Record<string, unknown> | Record<string, unknown>[] }
	| { type: 'input_image'; image_url: string; detail?: 'auto' | 'low' | 'high' | 'original' };
export type DecisionQuestion = { name?: string; instructions: string | DecisionPart[] } & (
	{ type: 'predicate' }
	| { type: 'choice'; choices: Array<{ value: string | boolean; description: string }> }
	| { type: 'score'; levels: Array<{ label: string; description: string }> }
);
export interface DecisionRequest {
	model: string;
	input: string | Array<{ role: 'user' | 'developer' | 'system' | 'assistant'; content: DecisionPart[] }>;
	questions: DecisionQuestion[];
	prompt_cache_key?: string;
	prompt_cache_options?: { mode?: 'implicit' | 'explicit' | null; ttl?: '30m' };
	safety_identifier?: string;
}
export type DecisionAnswer = { name: string | null } & (
	{ type: 'predicate'; probability: number }
	| { type: 'choice'; choice: string | boolean; confidence: number; probabilities: Array<{ value: string | boolean; probability: number }> }
	| { type: 'score'; score: number; confidence: number; probabilities: Array<{ value: number; label: string; probability: number }> }
	| { type: 'refusal' }
);
export interface DecisionResult {
	model: string;
	answers: DecisionAnswer[];
	usage: {
		input_tokens: number; input_tokens_details: { cached_tokens: number; cache_write_tokens: number };
		output_tokens: number; output_tokens_details: { reasoning_tokens: number }; total_tokens: number;
	};
	cost_usd: number;
	credited_cost: number;
	usage_log_id: string;
}
const object = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value);
const integer = (value: unknown): value is number => Number.isSafeInteger(value) && (value as number) >= 0;
const finite = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value) && value >= 0;
const probability = (value: unknown): value is number => finite(value) && value <= 1;
const text = (value: unknown): value is string => typeof value === 'string' && Boolean(value.trim());
const bytes = (value: string) => new TextEncoder().encode(value).byteLength;
function fail(key: Parameters<typeof t>[0]): never { throw new Error(t(key)); }
const capabilities = (value: unknown): value is DecisionCapabilities['model_capabilities'] => object(value)
	&& typeof value.decisions === 'boolean' && object(value.feature_gates) && object(value.feature_gates.decisions)
	&& typeof value.feature_gates.decisions.available === 'boolean'
	&& ['native', 'none'].includes(String(value.feature_gates.decisions.mode))
	&& typeof value.feature_gates.decisions.pricing_available === 'boolean';

export function parseDecisionModels(value: unknown): DecisionModel[] {
	if (!Array.isArray(value)) fail('decisions.invalidResponse');
	const ids = new Set<number>();
	for (const model of value) {
		if (!object(model) || !integer(model.id) || !model.id || ids.has(model.id) || model.model_kind !== 'text'
			|| !text(model.model_name) || !text(model.display_name)) fail('decisions.invalidResponse');
		ids.add(model.id);
	}
	// The list is already access-filtered by Lumen. Do not infer support from model names.
	return (value as DecisionModel[]).filter((model) => model.capabilities?.decisions === true);
}
export function parseDecisionCapabilities(value: unknown, modelId: number): DecisionCapabilities {
	if (!object(value) || value.model_id !== modelId || value.model_kind !== 'text' || !capabilities(value.model_capabilities)) fail('decisions.invalidResponse');
	return value as unknown as DecisionCapabilities;
}
export function decisionReadiness(model: DecisionModel | undefined, verified: DecisionCapabilities | null): string | null {
	if (!model) return t('decisions.selectModel');
	if (!model.provider_api_key_configured) return t('decisions.providerKeyMissing');
	for (const caps of [model.capabilities, verified?.model_capabilities]) {
		if (!caps || caps.decisions !== true) return t(verified ? 'decisions.unavailable' : 'decisions.unverified');
		const gate = caps.feature_gates?.decisions;
		if (!gate || gate.available !== true || gate.mode !== 'native') return t('decisions.unavailable');
		if (gate.pricing_available !== true) return t('decisions.pricingMissing');
	}
	if (verified?.model_id !== model.id || verified?.model_kind !== 'text') return t('decisions.unverified');
	return null;
}

export function parseDecisionJson(source: string): Record<string, unknown> | Record<string, unknown>[] {
	let value: unknown;
	try { value = JSON.parse(source); } catch { return fail('decisions.invalidJson'); }
	if (!object(value) && !(Array.isArray(value) && value.every(object))) fail('decisions.invalidJson');
	if (bytes(JSON.stringify(value)) > MAX_DECISION_JSON_BYTES) fail('decisions.jsonLimit');
	let count = 0;
	const visit = (entry: unknown, depth: number): void => {
		if (++count > 10_000 || ((object(entry) || Array.isArray(entry)) && depth > 32)) fail('decisions.jsonLimit');
		if (object(entry) || Array.isArray(entry)) for (const child of Object.values(entry)) visit(child, depth + 1);
	};
	visit(value, 1);
	return value as Record<string, unknown> | Record<string, unknown>[];
}
export function validateDecisionImage(url: string): void {
	if (url.startsWith('data:')) {
		const match = /^data:(image\/(?:png|jpeg|webp|gif));base64,([A-Za-z0-9+/]+={0,2})$/.exec(url);
		if (!match || match[2].length % 4 !== 0) fail('decisions.invalidImage');
		const size = match[2].length / 4 * 3 - (match[2].endsWith('==') ? 2 : match[2].endsWith('=') ? 1 : 0);
		if (size > MAX_DECISION_IMAGE_BYTES) fail('decisions.imageLimit');
		return;
	}
	try {
		const parsed = new URL(url);
		if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password) fail('decisions.invalidImage');
	} catch { fail('decisions.invalidImage'); }
}
export function validateDecisionRequest(request: DecisionRequest): void {
	if (!text(request.model)) fail('decisions.invalidRequest');
	const parts = (content: DecisionPart[]) => {
		if (!Array.isArray(content) || !content.length) fail('decisions.invalidRequest');
		for (const part of content) {
			if (part.type === 'input_text') { if (!text(part.text)) fail('decisions.invalidRequest'); }
			else if (part.type === 'input_json') parseDecisionJson(JSON.stringify(part.data));
			else if (part.type === 'input_image') {
				validateDecisionImage(part.image_url);
				if (part.detail !== undefined && !['auto', 'low', 'high', 'original'].includes(part.detail)) fail('decisions.invalidImage');
			} else fail('decisions.invalidRequest');
		}
	};
	if (typeof request.input === 'string') { if (!text(request.input)) fail('decisions.invalidRequest'); }
	else {
		if (!Array.isArray(request.input) || !request.input.length) fail('decisions.invalidRequest');
		for (const message of request.input) {
			if (!['user', 'developer', 'system', 'assistant'].includes(message.role)) fail('decisions.invalidRequest');
			parts(message.content);
		}
	}
	if (!Array.isArray(request.questions) || request.questions.length < 1 || request.questions.length > 400) fail('decisions.questionLimit');
	const names = new Set<string>();
	for (const question of request.questions) {
		if (question.name !== undefined) {
			if (!text(question.name)) fail('decisions.invalidRequest');
			if (names.has(question.name)) fail('decisions.duplicateNames');
			names.add(question.name);
		}
		if (typeof question.instructions === 'string') { if (!text(question.instructions)) fail('decisions.invalidRequest'); }
		else parts(question.instructions);
		if (question.type === 'choice') {
			if (!Array.isArray(question.choices) || question.choices.length < 2 || question.choices.length > 255
				|| question.choices.some((entry) => !(text(entry.value) || typeof entry.value === 'boolean') || !text(entry.description))) fail('decisions.choiceLimit');
			if (new Set(question.choices.map((entry) => JSON.stringify(entry.value))).size !== question.choices.length) fail('decisions.duplicateChoices');
		} else if (question.type === 'score') {
			if (!Array.isArray(question.levels) || question.levels.length < 2 || question.levels.length > 10
				|| question.levels.some((entry) => !text(entry.label) || !text(entry.description))) fail('decisions.levelLimit');
		} else if (question.type !== 'predicate') fail('decisions.invalidRequest');
	}
	if (bytes(JSON.stringify(request)) > MAX_DECISION_REQUEST_BYTES) fail('decisions.requestLimit');
}

export function parseDecisionResult(value: unknown, request: DecisionRequest): DecisionResult {
	const invalid = () => fail('decisions.invalidResponse');
	if (!object(value) || value.model !== request.model || !Array.isArray(value.answers) || value.answers.length !== request.questions.length
		|| !object(value.usage) || !object(value.usage.input_tokens_details) || !object(value.usage.output_tokens_details)
		|| !integer(value.usage.input_tokens) || !integer(value.usage.output_tokens) || !integer(value.usage.total_tokens)
		|| !integer(value.usage.input_tokens_details.cached_tokens) || !integer(value.usage.input_tokens_details.cache_write_tokens)
		|| !integer(value.usage.output_tokens_details.reasoning_tokens) || !finite(value.cost_usd) || !finite(value.credited_cost)
		|| typeof value.usage_log_id !== 'string' || !/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(value.usage_log_id)) invalid();
	const result = value as unknown as DecisionResult;
	if (result.usage.total_tokens !== result.usage.input_tokens + result.usage.output_tokens
		|| result.usage.input_tokens_details.cached_tokens + result.usage.input_tokens_details.cache_write_tokens > result.usage.input_tokens
		|| result.usage.output_tokens_details.reasoning_tokens > result.usage.output_tokens) invalid();
	for (const [index, answer] of result.answers.entries()) {
		const question = request.questions[index];
		if (!object(answer) || answer.name !== (question.name ?? null)) invalid();
		if (answer.type === 'refusal') continue;
		if (answer.type !== question.type) invalid();
		if (answer.type === 'predicate') { if (!probability(answer.probability)) invalid(); }
		else if (answer.type === 'choice' && question.type === 'choice') {
			if (!probability(answer.confidence) || !question.choices.some((entry) => entry.value === answer.choice)
				|| !Array.isArray(answer.probabilities) || answer.probabilities.length !== question.choices.length) invalid();
			const seen = new Set<string>();
			for (const entry of answer.probabilities) {
				if (!object(entry) || !probability(entry.probability) || !question.choices.some((choice) => choice.value === entry.value)
					|| seen.has(JSON.stringify(entry.value))) invalid();
				seen.add(JSON.stringify(entry.value));
			}
		} else if (answer.type === 'score' && question.type === 'score') {
			if (!finite(answer.score) || answer.score > question.levels.length - 1 || !probability(answer.confidence) || !Array.isArray(answer.probabilities)
				|| answer.probabilities.length !== question.levels.length) invalid();
			const seen = new Set<number>();
			for (const entry of answer.probabilities) {
				if (!object(entry) || !integer(entry.value) || entry.value >= question.levels.length || seen.has(entry.value)
					|| entry.label !== question.levels[entry.value]?.label || !probability(entry.probability)) invalid();
				seen.add(entry.value);
			}
		} else invalid();
	}
	return result;
}
export const decisionStudioApi = {
	async models(scope: DecisionScope, signal?: AbortSignal): Promise<DecisionModel[]> {
		requireLumenCapability('lumen-chat_user', scope.token, scope.projectId);
		return parseDecisionModels(await api.get<unknown>('/api/v1/chat/models?model_kind=text', scope.token, scope.projectId, { refresh: true, signal, experience: scope.experience }));
	},
	async capabilities(id: number, scope: DecisionScope, signal?: AbortSignal): Promise<DecisionCapabilities> {
		requireLumenCapability('lumen-chat_user', scope.token, scope.projectId);
		return parseDecisionCapabilities(await api.get<unknown>(`/api/v1/chat/capabilities?model_id=${id}&model_kind=text`, scope.token, scope.projectId, { refresh: true, signal, experience: scope.experience }), id);
	},
	async decide(request: DecisionRequest, scope: DecisionScope, signal?: AbortSignal): Promise<DecisionResult> {
		requireLumenCapability('lumen-chat_user', scope.token, scope.projectId);
		validateDecisionRequest(request);
		const owner = sessionScopeKey(get(auth));
		const controller = new AbortController();
		const requestSignal = signal ? AbortSignal.any([signal, controller.signal]) : controller.signal;
		const invalidate = () => controller.abort(new ApiError(403, t('decisions.projectDenied')));
		const subscriptions = [
			auth.subscribe((value) => { if (!value.token || sessionScopeKey(value) !== owner) invalidate(); }),
			authReady.subscribe((ready) => { if (!ready) invalidate(); }),
			projectSwitching.subscribe((switching) => { if (switching) invalidate(); }),
			serviceCapabilities.subscribe((grants) => { if (!grants('lumen-chat_user')) invalidate(); })
		];
		try {
			requestSignal.throwIfAborted();
			const response = await fetchWithAuth('/api/v1/chat/decisions', {
				method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request), signal: requestSignal
			}, scope.token, scope.projectId, { replayOnUnauthorized: false, experience: scope.experience, beforeDispatch: () => {
				requestSignal.throwIfAborted();
				const current = get(auth);
				requireLumenCapability('lumen-chat_user', current.token ?? undefined, scope.projectId);
			} });
			requestSignal.throwIfAborted();
			if (!response.ok) {
				const body: unknown = await response.json().catch(() => null);
				requestSignal.throwIfAborted();
				throw new ApiError(response.status, object(body) && typeof body.detail === 'string' ? body.detail : t('decisions.requestFailed', { status: response.status }));
			}
			const body: unknown = await response.json();
			requestSignal.throwIfAborted();
			return parseDecisionResult(body, request);
		} finally {
			subscriptions.forEach((unsubscribe) => unsubscribe());
		}
	}
};
