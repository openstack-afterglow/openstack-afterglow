import { grantLumen, pendingLumen, setVerifiedLumenActor } from '../../components/chat/__tests__/lumenPermissionFixture';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
	decisionReadiness, decisionStudioApi, parseDecisionCapabilities, parseDecisionJson, parseDecisionModels, parseDecisionResult,
	validateDecisionImage, validateDecisionRequest, MAX_DECISION_IMAGE_BYTES, MAX_DECISION_REQUEST_BYTES,
	type DecisionCapabilities, type DecisionModel, type DecisionRequest, type DecisionResult
} from '../decisionStudio';
import { ApiError } from '../client';
import { t } from '$lib/i18n/ns/decision-studio';
import type * as ClientModule from '../client';
import { projectSwitching } from '$lib/stores/auth';

const calls = vi.hoisted(() => ({ get: vi.fn(), fetch: vi.fn() }));
vi.mock('../client', async (original) => ({ ...await original<typeof ClientModule>(), api: { get: calls.get }, fetchWithAuth: calls.fetch }));
const gate = { decisions: true, feature_gates: { decisions: { available: true, mode: 'native' as const, reason_code: null, pricing_available: true } } };
const model: DecisionModel = {
	id: 9, provider_id: 1, provider_type: 'openai', provider_sort_order: 0, sort_order: 0,
	model_name: 'registered-luna', api_model_name: 'openai/gpt-6-luna', display_name: 'Luna decisions', model_kind: 'text',
	provider_api_key_configured: true, capabilities: gate
};
const verified: DecisionCapabilities = { model_id: 9, model_kind: 'text', model_capabilities: gate };
const predicate = { type: 'predicate' as const, instructions: 'Is this urgent?', name: 'urgent' };
const choice = { type: 'choice' as const, instructions: 'Classify.', name: 'category', choices: [{ value: 'yes', description: 'Yes' }, { value: false, description: 'No' }] };
const score = { type: 'score' as const, instructions: 'Rate severity.', name: 'severity', levels: [{ label: 'low', description: 'Minor' }, { label: 'high', description: 'Major' }] };
const request: DecisionRequest = { model: model.model_name, input: 'Broken parcel', questions: [predicate, choice, score] };
const response = (): DecisionResult => ({
	model: model.model_name,
	answers: [
		{ type: 'predicate', name: 'urgent', probability: 0.8 },
		{ type: 'choice', name: 'category', choice: 'yes', confidence: 0.9, probabilities: [{ value: 'yes', probability: 0.9 }, { value: false, probability: 0.1 }] },
		{ type: 'score', name: 'severity', score: 0.7, confidence: 0.7, probabilities: [{ value: 0, label: 'low', probability: 0.3 }, { value: 1, label: 'high', probability: 0.7 }] }
	],
	usage: { input_tokens: 20, input_tokens_details: { cached_tokens: 5, cache_write_tokens: 2 }, output_tokens: 3, output_tokens_details: { reasoning_tokens: 1 }, total_tokens: 23 },
	cost_usd: 0.0000016, credited_cost: 0.000002, usage_log_id: '00000000-0000-4000-8000-000000000009'
});
const actor = (projectId = 'project-1') => ({ token: 'token', refreshToken: null, accessExpiresAt: null, sessionId: 'session', userId: 'owner', username: 'tester', projectId, projectName: projectId, availableProjects: [], roles: [], isSystemAdmin: false, federated: false, domainId: 'domain-1', domainName: 'Domain', identityDomainId: 'domain-1', identityDomainName: 'Domain', isDomainManager: false });
const scope = { token: 'token', projectId: 'project-1' };

beforeEach(() => { vi.clearAllMocks(); setVerifiedLumenActor(actor()); });
afterEach(() => { vi.restoreAllMocks(); });

describe('decision model admission', () => {
	it('filters on effective decisions capability, never the model name', () => {
		expect(parseDecisionModels([model, { ...model, id: 10, model_name: 'gpt-6-luna', capabilities: { ...gate, decisions: false } }])).toEqual([model]);
		expect(parseDecisionCapabilities(verified, 9)).toEqual(verified);
		expect(decisionReadiness(model, verified)).toBeNull();
	});
	it.each([
		['no model', undefined, verified, 'decisions.selectModel'],
		['no key', { ...model, provider_api_key_configured: false }, verified, 'decisions.providerKeyMissing'],
		['unverified', model, null, 'decisions.unverified'],
		['wrong model', model, { ...verified, model_id: 10 }, 'decisions.unverified'],
		['revoked capability', model, { ...verified, model_capabilities: { ...gate, decisions: false } }, 'decisions.unavailable'],
		['unpriced', model, { ...verified, model_capabilities: { ...gate, feature_gates: { decisions: { ...gate.feature_gates.decisions, pricing_available: false } } } }, 'decisions.pricingMissing'],
		['unavailable', { ...model, capabilities: { ...gate, feature_gates: { decisions: { ...gate.feature_gates.decisions, available: false } } } }, verified, 'decisions.unavailable']
	] as const)('blocks %s', (_name, entry, capabilities, key) => {
		expect(decisionReadiness(entry, capabilities)).toBe(t(key));
	});
	it('rejects malformed lists and cross-model capability envelopes', () => {
		for (const value of [{}, [model, model], [{ ...model, model_kind: 'embedding' }], [{ ...model, id: 0 }]]) expect(() => parseDecisionModels(value)).toThrow(t('decisions.invalidResponse'));
		for (const value of [{ ...verified, model_id: 10 }, { ...verified, model_kind: 'image' }, { ...verified, model_capabilities: {} }]) expect(() => parseDecisionCapabilities(value, 9)).toThrow(t('decisions.invalidResponse'));
	});
});

describe('decision input bounds', () => {
	it('accepts every question kind and text, JSON, HTTP image and inline image input', () => {
		expect(() => validateDecisionRequest(request)).not.toThrow();
		for (const part of [{ type: 'input_json' as const, data: { ticket: 'damaged' } }, { type: 'input_image' as const, image_url: 'https://example.test/image.png', detail: 'original' as const }, { type: 'input_image' as const, image_url: 'data:image/png;base64,aGk=' }]) {
			expect(() => validateDecisionRequest({ ...request, input: [{ role: 'user', content: [part] }] })).not.toThrow();
		}
		expect(parseDecisionJson('[{"ok":true}]')).toEqual([{ ok: true }]);
	});
	it.each(['{', 'null', '42', '"text"', '[1]', '[{},null]'])('rejects invalid JSON input %s', (source) => {
		expect(() => parseDecisionJson(source)).toThrow(t('decisions.invalidJson'));
	});
	it('enforces UTF-8 JSON size, container depth and value count', () => {
		expect(() => parseDecisionJson(JSON.stringify({ value: '한'.repeat(90_000) }))).toThrow(t('decisions.jsonLimit'));
		let nested: Record<string, unknown> = {};
		for (let index = 0; index < 31; index++) nested = { child: nested };
		expect(() => parseDecisionJson(JSON.stringify(nested))).not.toThrow();
		expect(() => parseDecisionJson(JSON.stringify({ child: nested }))).toThrow(t('decisions.jsonLimit'));
		expect(() => parseDecisionJson(JSON.stringify({ values: Array(10_000).fill(0) }))).toThrow(t('decisions.jsonLimit'));
	});
	it.each(['javascript:alert(1)', 'file:///tmp/image.png', 'https://user:secret@example.test/image.png', 'data:image/svg+xml;base64,PHN2Zz4=', 'data:image/png;base64,%%%=', 'data:image/png;base64,a'])('rejects unsafe or malformed image %s', (source) => {
		expect(() => validateDecisionImage(source)).toThrow(t('decisions.invalidImage'));
	});
	it('enforces decoded image bytes and total UTF-8 request bytes', () => {
		const exact = `data:image/png;base64,${'A'.repeat(Math.floor(MAX_DECISION_IMAGE_BYTES / 3) * 4)}AA==`;
		expect(() => validateDecisionImage(exact)).not.toThrow();
		expect(() => validateDecisionImage(exact.replace(/AA==$/, 'AAA='))).toThrow(t('decisions.imageLimit'));
		expect(() => validateDecisionRequest({ ...request, input: 'a'.repeat(MAX_DECISION_REQUEST_BYTES) })).toThrow(t('decisions.requestLimit'));
	});
	it('allows 1 and 400 questions, rejects 0, 401 and duplicate names', () => {
		for (const count of [1, 400]) expect(() => validateDecisionRequest({ ...request, questions: Array.from({ length: count }, (_, index) => ({ ...predicate, name: `q-${index}` })) })).not.toThrow();
		for (const count of [0, 401]) expect(() => validateDecisionRequest({ ...request, questions: Array.from({ length: count }, () => predicate) })).toThrow(t('decisions.questionLimit'));
		expect(() => validateDecisionRequest({ ...request, questions: [predicate, predicate] })).toThrow(t('decisions.duplicateNames'));
	});
	it('bounds choices at 2–255 with typed-unique values and descriptions', () => {
		const choices = Array.from({ length: 255 }, (_, index) => ({ value: String(index), description: 'Option' }));
		expect(() => validateDecisionRequest({ ...request, questions: [{ ...choice, choices }] })).not.toThrow();
		for (const invalid of [choices.slice(0, 1), [...choices, { value: '256', description: 'Extra' }], [{ value: '', description: 'Empty' }, { value: 'ok', description: 'OK' }]]) expect(() => validateDecisionRequest({ ...request, questions: [{ ...choice, choices: invalid }] })).toThrow(t('decisions.choiceLimit'));
		expect(() => validateDecisionRequest({ ...request, questions: [{ ...choice, choices: [choices[0], choices[0]] }] })).toThrow(t('decisions.duplicateChoices'));
		expect(() => validateDecisionRequest({ ...request, questions: [{ ...choice, choices: [{ value: true, description: 'Boolean' }, { value: 'true', description: 'String' }] }] })).not.toThrow();
	});
	it('bounds score levels at 2–10 with labels and descriptions', () => {
		const levels = Array.from({ length: 10 }, (_, index) => ({ label: String(index), description: 'Level' }));
		expect(() => validateDecisionRequest({ ...request, questions: [{ ...score, levels }] })).not.toThrow();
		for (const invalid of [levels.slice(0, 1), [...levels, { label: '11', description: 'Extra' }], [{ label: 'a', description: '' }, levels[0]]]) expect(() => validateDecisionRequest({ ...request, questions: [{ ...score, levels: invalid }] })).toThrow(t('decisions.levelLimit'));
	});
});

describe('decision response validation', () => {
	it('accepts predicate, choice, score and per-question refusal', () => {
		expect(parseDecisionResult(response(), request)).toEqual(response());
		const value = response(); value.answers[1] = { type: 'refusal', name: 'category' };
		expect(parseDecisionResult(value, request).answers[1]).toEqual({ type: 'refusal', name: 'category' });
	});
	it.each([
		['wrong model', (value: DecisionResult) => { value.model = 'upstream-alias'; }],
		['missing answer', (value: DecisionResult) => { value.answers.pop(); }],
		['wrong name', (value: DecisionResult) => { value.answers[0].name = 'another'; }],
		['wrong type', (value: DecisionResult) => { value.answers[0] = { type: 'score', name: 'urgent', score: 0, confidence: 1, probabilities: [] }; }],
		['infinite probability', (value: DecisionResult) => { value.answers[0] = { type: 'predicate', name: 'urgent', probability: Infinity }; }],
		['probability above one', (value: DecisionResult) => { value.answers[0] = { type: 'predicate', name: 'urgent', probability: 1.1 }; }],
		['negative cost', (value: DecisionResult) => { value.cost_usd = -1; }],
		['invalid event ID', (value: DecisionResult) => { value.usage_log_id = ''; }],
		['inconsistent usage', (value: DecisionResult) => { value.usage.total_tokens++; }],
		['excess cached input', (value: DecisionResult) => { value.usage.input_tokens_details.cached_tokens = 30; }],
		['excess reasoning', (value: DecisionResult) => { value.usage.output_tokens_details.reasoning_tokens = 30; }],
		['unlisted choice', (value: DecisionResult) => { if (value.answers[1].type === 'choice') value.answers[1].choice = 'unknown'; }],
		['duplicate probability', (value: DecisionResult) => { if (value.answers[1].type === 'choice') value.answers[1].probabilities[1] = value.answers[1].probabilities[0]; }],
		['out of range score', (value: DecisionResult) => { if (value.answers[2].type === 'score') value.answers[2].score = 2; }],
		['wrong level label', (value: DecisionResult) => { if (value.answers[2].type === 'score') value.answers[2].probabilities[0].label = 'wrong'; }]
	])('rejects %s', (_name, alter) => {
		const value = response(); alter(value);
		expect(() => parseDecisionResult(value, request)).toThrow(t('decisions.invalidResponse'));
	});
});

describe('decision transport', () => {
	it('reads text models and verifies exact-model capabilities', async () => {
		calls.get.mockResolvedValueOnce([model]).mockResolvedValueOnce(verified);
		await expect(decisionStudioApi.models(scope)).resolves.toEqual([model]);
		await expect(decisionStudioApi.capabilities(9, scope)).resolves.toEqual(verified);
		expect(calls.get.mock.calls.map(([path]) => path)).toEqual(['/api/v1/chat/models?model_kind=text', '/api/v1/chat/capabilities?model_id=9&model_kind=text']);
	});
	it('posts the registered model name once with cancellation and no 401 replay', async () => {
		const signal = new AbortController().signal;
		calls.fetch.mockResolvedValue(new Response(JSON.stringify(response()), { status: 200 }));
		await expect(decisionStudioApi.decide(request, scope, signal)).resolves.toEqual(response());
		expect(calls.fetch).toHaveBeenCalledTimes(1);
		const [path, init, token, project, options] = calls.fetch.mock.calls[0];
		expect(path).toBe('/api/v1/chat/decisions'); expect(init.method).toBe('POST'); expect(init.signal.aborted).toBe(false);
		expect(JSON.parse(init.body)).toEqual(request); expect(JSON.parse(init.body).model_id).toBeUndefined();
		expect(token).toBe(scope.token); expect(project).toBe(scope.projectId); expect(options.replayOnUnauthorized).toBe(false);
	});
	it('blocks stale scope before dispatch and never retries service errors', async () => {
		calls.fetch.mockImplementation(async (_path, _init, _token, _project, options) => {
			setVerifiedLumenActor(actor('project-2'));
			options.beforeDispatch();
			return new Response('{}');
		});
		await expect(decisionStudioApi.decide(request, scope)).rejects.toThrow(t('decisions.projectDenied'));
		setVerifiedLumenActor(actor());
		calls.fetch.mockResolvedValue(new Response(JSON.stringify({ detail: 'quota_denied' }), { status: 402 }));
		await expect(decisionStudioApi.decide(request, scope)).rejects.toBeInstanceOf(ApiError);
		expect(calls.fetch).toHaveBeenCalledTimes(2);
	});
	it.each(['owner', 'authority', 'switching'] as const)('fences same-tick %s ABA and discards a late response', async (boundary) => {
		const pending = Promise.withResolvers<Response>();
		calls.fetch.mockReturnValue(pending.promise);
		const operation = decisionStudioApi.decide(request, scope);
		const rejection = expect(operation).rejects.toThrow(t('decisions.projectDenied'));
		if (boundary === 'owner') { setVerifiedLumenActor(actor('project-2')); setVerifiedLumenActor(actor()); }
		if (boundary === 'authority') { pendingLumen(); grantLumen('lumen-chat_user'); }
		if (boundary === 'switching') { projectSwitching.set(true); projectSwitching.set(false); }
		expect(calls.fetch.mock.calls[0][1].signal.aborted).toBe(true);
		pending.resolve(new Response(JSON.stringify(response())));
		await rejection;
		expect(calls.fetch).toHaveBeenCalledTimes(1);
	});
	it('propagates external cancellation without repeating the provider call', async () => {
		const pending = Promise.withResolvers<Response>(), controller = new AbortController();
		calls.fetch.mockReturnValue(pending.promise);
		const operation = decisionStudioApi.decide(request, scope, controller.signal);
		const rejection = expect(operation).rejects.toMatchObject({ name: 'AbortError' });
		controller.abort();
		expect(calls.fetch.mock.calls[0][1].signal.aborted).toBe(true);
		pending.resolve(new Response(JSON.stringify(response())));
		await rejection;
		expect(calls.fetch).toHaveBeenCalledTimes(1);
	});
	it('rejects invalid input or an old project without sending a request', async () => {
		await expect(decisionStudioApi.decide({ ...request, questions: [] }, scope)).rejects.toThrow(t('decisions.questionLimit'));
		await expect(decisionStudioApi.decide(request, { ...scope, projectId: 'other' })).rejects.toBeInstanceOf(ApiError);
		expect(calls.fetch).not.toHaveBeenCalled();
	});
});
