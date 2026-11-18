import { grantLumen, pendingLumen, refreshLumenAuth, setVerifiedLumenActor } from './lumenPermissionFixture';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type * as DecisionModule from '$lib/api/decisionStudio';
import { MAX_DECISION_IMAGE_BYTES, parseGeminiDecisionResult } from '$lib/api/decisionStudio';
import { api, ApiError } from '$lib/api/client';
import DecisionStudio from '../DecisionStudio.svelte';
import { t } from '$lib/i18n/ns/decision-studio';
import { projectSwitching } from '$lib/stores/auth';
import { tick } from 'svelte';

const calls = vi.hoisted(() => ({ models: vi.fn(), capabilities: vi.fn(), decide: vi.fn(), decideGemini: vi.fn() }));
vi.mock('$lib/api/decisionStudio', async (original) => ({ ...await original<typeof DecisionModule>(), decisionStudioApi: calls }));
const gate = { decisions: true, feature_gates: { decisions: { available: true, mode: 'native' as const, reason_code: null, pricing_available: true } } };
const model: DecisionModule.DecisionModel = { id: 9, provider_id: 1, provider_type: 'openai', provider_sort_order: 0, sort_order: 0, model_name: 'registered-luna', api_model_name: 'openai/gpt-6-luna', display_name: 'Luna decisions', model_kind: 'text', provider_api_key_configured: true, capabilities: gate };
const capability = (id = 9): DecisionModule.DecisionCapabilities => ({ model_id: id, model_kind: 'text', model_capabilities: gate });
const result = (request?: DecisionModule.DecisionRequest): DecisionModule.DecisionResult => ({
	model: request?.model ?? model.model_name,
	answers: request?.questions.map((question): DecisionModule.DecisionAnswer => {
		const name = question.name ?? null;
		if (question.type === 'choice') return { type: 'choice', name, choice: question.choices[0].value, confidence: 0.8, probabilities: question.choices.map((entry, index) => ({ value: entry.value, probability: index === 0 ? 0.8 : 0.2 })) };
		if (question.type === 'score') return { type: 'score', name, score: 0.8, confidence: 0.8, probabilities: question.levels.map((entry, index) => ({ value: index, label: entry.label, probability: index === 0 ? 0.2 : 0.8 })) };
		return { type: 'predicate', name, probability: 0.8 };
	}) ?? [{ type: 'predicate', name: null, probability: 0.8 }],
	usage: { input_tokens: 20, input_tokens_details: { cached_tokens: 5, cache_write_tokens: 2 }, output_tokens: 3, output_tokens_details: { reasoning_tokens: 1 }, total_tokens: 23 },
	cost_usd: 0.0000016, credited_cost: 0.000002, usage_log_id: '00000000-0000-4000-8000-000000000009'
});
const user = (projectId = 'project-1') => ({ token: 'token', refreshToken: null, accessExpiresAt: null, sessionId: 'session', userId: 'owner', username: 'tester', projectId, projectName: projectId, availableProjects: [], roles: [], isSystemAdmin: false, federated: false, domainId: 'domain-1', domainName: 'Domain', identityDomainId: 'domain-1', identityDomainName: 'Domain', isDomainManager: false });
const run = () => screen.getByRole('button', { name: t('decisions.run') });
const questionAt = (index = 0) => screen.getAllByTestId('decision-question')[index];
async function fillPredicate() {
	await screen.findByText(t('decisions.ready'));
	await fireEvent.input(screen.getByRole('textbox', { name: t('decisions.content') }), { target: { value: 'A damaged parcel arrived.' } });
	await fireEvent.input(within(questionAt()).getByRole('textbox', { name: t('decisions.instructions') }), { target: { value: 'Does it need a refund?' } });
}
async function chooseInput(type: string) {
	await fireEvent.change(screen.getByLabelText(t('decisions.inputType')), { target: { value: type } });
}
async function fillOptions(question: HTMLElement, type: 'choice' | 'score') {
	await fireEvent.change(within(question).getByLabelText(t('decisions.type')), { target: { value: type } });
	for (let index = 1; index <= 2; index++) {
		await fireEvent.input(within(question).getByRole('textbox', { name: `${t(type === 'choice' ? 'decisions.value' : 'decisions.label')} ${index}` }), { target: { value: index === 1 ? 'low' : 'high' } });
		await fireEvent.input(within(question).getByRole('textbox', { name: `${t('decisions.descriptionLabel')} ${index}` }), { target: { value: index === 1 ? 'Minor damage' : 'Major damage' } });
	}
}
class ControlledFileReader {
	static LOADING = 1;
	static readers: ControlledFileReader[] = [];
	readyState = 0;
	result: string | ArrayBuffer | null = null;
	onload: (() => void) | null = null;
	onerror: (() => void) | null = null;
	onabort: (() => void) | null = null;
	abort = vi.fn(() => { this.readyState = 2; this.onabort?.(); });
	readAsDataURL = vi.fn(() => { this.readyState = 1; ControlledFileReader.readers.push(this); });
	finish(value = 'data:image/png;base64,aGk=') { this.result = value; this.readyState = 2; this.onload?.(); }
}

beforeEach(() => {
	vi.clearAllMocks();
	setVerifiedLumenActor(user());
	calls.models.mockResolvedValue([model]);
	calls.capabilities.mockImplementation(async (id: number) => capability(id));
	calls.decide.mockImplementation(async (request: DecisionModule.DecisionRequest) => result(request));
	ControlledFileReader.readers = [];
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe('Decision Studio', () => {
	it('submits the registered model name, one predicate and scope, then shows probability, usage and cost', async () => {
		render(DecisionStudio); await fillPredicate();
		await fireEvent.input(within(questionAt()).getByLabelText(t('decisions.name')), { target: { value: 'refund' } });
		await fireEvent.click(run());
		await screen.findByTestId('decision-results');
		expect(calls.decide).toHaveBeenCalledTimes(1);
		expect(calls.decide).toHaveBeenCalledWith({ model: 'registered-luna', input: 'A damaged parcel arrived.', questions: [{ type: 'predicate', name: 'refund', instructions: 'Does it need a refund?' }] }, { token: 'token', projectId: 'project-1' }, expect.any(AbortSignal));
		expect(screen.getByRole('heading', { name: 'refund' })).toBeTruthy();
		expect(screen.getByText(new RegExp(`^${t('decisions.probability')}:`))).toBeTruthy();
		for (const key of ['inputTokens', 'cachedTokens', 'cacheWriteTokens', 'outputTokens', 'reasoningTokens', 'totalTokens', 'cost', 'creditedCost', 'usageLog'] as const) expect(screen.getByText(t(`decisions.${key}`), { selector: 'dt' })).toBeTruthy();
		expect(screen.getByText('00000000-0000-4000-8000-000000000009')).toBeTruthy();
	});
	it('builds choice and score questions with descriptions and renders their distributions', async () => {
		render(DecisionStudio); await fillPredicate();
		await fillOptions(questionAt(), 'choice');
		await fireEvent.click(screen.getByRole('button', { name: t('decisions.addQuestion') }));
		await fireEvent.input(within(questionAt(1)).getByRole('textbox', { name: t('decisions.instructions') }), { target: { value: 'Rate the damage.' } });
		await fillOptions(questionAt(1), 'score');
		await fireEvent.click(run());
		await screen.findByTestId('decision-results');
		const sent = calls.decide.mock.calls[0][0] as DecisionModule.DecisionRequest;
		expect(sent.questions).toEqual([
			{ type: 'choice', instructions: 'Does it need a refund?', choices: [{ value: 'low', description: 'Minor damage' }, { value: 'high', description: 'Major damage' }] },
			{ type: 'score', instructions: 'Rate the damage.', levels: [{ label: 'low', description: 'Minor damage' }, { label: 'high', description: 'Major damage' }] }
		]);
		expect(within(screen.getByTestId('decision-results')).getAllByText('low')).toHaveLength(2);
		expect(within(screen.getByTestId('decision-results')).getAllByText('high')).toHaveLength(2);
	});
	it('renders provider refusal without inventing probability or confidence', async () => {
		calls.decide.mockResolvedValue({ ...result(), answers: [{ type: 'refusal', name: null }] });
		render(DecisionStudio); await fillPredicate(); await fireEvent.click(run());
		await screen.findByText(t('decisions.refusal'));
		expect(screen.queryByText(`${t('decisions.probability')}:`)).toBeNull();
		expect(screen.queryByText(`${t('decisions.confidence')}:`)).toBeNull();
	});
	it('submits JSON objects and image URLs with the exact content-part keys', async () => {
		render(DecisionStudio); await fillPredicate(); await chooseInput('json');
		await fireEvent.input(screen.getByRole('textbox', { name: t('decisions.content') }), { target: { value: '{"ticket":"damaged"}' } });
		await fireEvent.click(run()); await screen.findByTestId('decision-results');
		expect(calls.decide.mock.calls[0][0].input).toEqual([{ role: 'user', content: [{ type: 'input_json', data: { ticket: 'damaged' } }] }]);
		await chooseInput('image');
		await fireEvent.input(screen.getByRole('textbox', { name: t('decisions.imageUrl') }), { target: { value: 'https://example.test/photo.png' } });
		await fireEvent.change(screen.getByLabelText(t('decisions.imageDetail')), { target: { value: 'original' } });
		await fireEvent.click(run()); await waitFor(() => expect(calls.decide).toHaveBeenCalledTimes(2));
		expect(calls.decide.mock.calls[1][0].input).toEqual([{ role: 'user', content: [{ type: 'input_image', image_url: 'https://example.test/photo.png', detail: 'original' }] }]);
	});
	it.each(['{', 'null', '[1]'])('blocks invalid JSON %s without sending', async (source) => {
		render(DecisionStudio); await fillPredicate(); await chooseInput('json');
		await fireEvent.input(screen.getByRole('textbox', { name: t('decisions.content') }), { target: { value: source } });
		await fireEvent.click(run());
		await screen.findByText(t('decisions.invalidJson'));
		expect(calls.decide).not.toHaveBeenCalled();
		expect(document.activeElement?.classList.contains('error-summary')).toBe(true);
	});
	it('blocks duplicate names and duplicate choice values', async () => {
		render(DecisionStudio); await fillPredicate();
		await fireEvent.input(within(questionAt()).getByLabelText(t('decisions.name')), { target: { value: 'same' } });
		await fireEvent.click(screen.getByRole('button', { name: t('decisions.addQuestion') }));
		await fireEvent.input(within(questionAt(1)).getByLabelText(t('decisions.name')), { target: { value: 'same' } });
		await fireEvent.input(within(questionAt(1)).getByRole('textbox', { name: t('decisions.instructions') }), { target: { value: 'Another question' } });
		await fireEvent.click(run()); await screen.findByText(t('decisions.duplicateNames'));
		expect(calls.decide).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: t('decisions.removeQuestion', { number: 2 }) }));
		await fillOptions(questionAt(), 'choice');
		await fireEvent.input(within(questionAt()).getByRole('textbox', { name: `${t('decisions.value')} 2` }), { target: { value: 'low' } });
		await fireEvent.click(run()); await screen.findByText(t('decisions.duplicateChoices'));
		expect(calls.decide).not.toHaveBeenCalled();
	});
	it('rejects oversized JSON and unsafe image URLs before dispatch', async () => {
		render(DecisionStudio); await fillPredicate(); await chooseInput('json');
		await fireEvent.input(screen.getByRole('textbox', { name: t('decisions.content') }), { target: { value: JSON.stringify({ text: 'x'.repeat(256 * 1024) }) } });
		await fireEvent.click(run()); await screen.findByText(t('decisions.jsonLimit'));
		await chooseInput('image');
		await fireEvent.input(screen.getByRole('textbox', { name: t('decisions.imageUrl') }), { target: { value: 'file:///private/photo.png' } });
		await fireEvent.click(run()); await screen.findByText(t('decisions.invalidImage'));
		expect(calls.decide).not.toHaveBeenCalled();
	});
	it('keeps two minimum options, limits score levels to ten, and retains stable question identities', async () => {
		render(DecisionStudio); await fillPredicate();
		await fillOptions(questionAt(), 'score');
		expect(within(questionAt()).getByRole('button', { name: t('decisions.removeLevel', { number: 1 }) }).hasAttribute('disabled')).toBe(true);
		for (let index = 0; index < 8; index++) await fireEvent.click(screen.getByRole('button', { name: t('decisions.addLevel') }));
		expect(screen.getByRole('button', { name: t('decisions.addLevel') }).hasAttribute('disabled')).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: t('decisions.addQuestion') }));
		await fireEvent.input(within(questionAt(1)).getByRole('textbox', { name: t('decisions.instructions') }), { target: { value: 'Keep this stable' } });
		await fireEvent.click(screen.getByRole('button', { name: t('decisions.removeQuestion', { number: 1 }) }));
		expect((within(questionAt()).getByRole('textbox', { name: t('decisions.instructions') }) as HTMLTextAreaElement).value).toBe('Keep this stable');
	});
	it('aborts cancel once and ignores its late result without automatic replay', async () => {
		const pending = Promise.withResolvers<DecisionModule.DecisionResult>(); calls.decide.mockReturnValue(pending.promise);
		render(DecisionStudio); await fillPredicate(); await fireEvent.click(run());
		const signal = calls.decide.mock.calls[0][2] as AbortSignal;
		await fireEvent.click(screen.getByRole('button', { name: t('decisions.cancel') }));
		expect(signal.aborted).toBe(true); await screen.findByText(t('decisions.cancelled'));
		pending.resolve(result()); await pending.promise; await Promise.resolve();
		expect(screen.queryByTestId('decision-results')).toBeNull(); expect(calls.decide).toHaveBeenCalledTimes(1);
	});
	it.each(['owner', 'denial', 'switching'] as const)('clears drafts and aborts on same-tick %s ABA', async (boundary) => {
		const pending = Promise.withResolvers<DecisionModule.DecisionResult>(); calls.decide.mockReturnValue(pending.promise);
		render(DecisionStudio); await fillPredicate(); await fireEvent.click(run());
		const signal = calls.decide.mock.calls[0][2] as AbortSignal;
		if (boundary === 'owner') { setVerifiedLumenActor(user('project-2')); setVerifiedLumenActor(user()); }
		if (boundary === 'denial') { grantLumen('lumen-images_user'); grantLumen('lumen-chat_user'); }
		if (boundary === 'switching') { projectSwitching.set(true); projectSwitching.set(false); }
		expect(signal.aborted).toBe(true);
		pending.resolve(result()); await pending.promise;
		await waitFor(() => expect(calls.models).toHaveBeenCalledTimes(2));
		await screen.findByText(t('decisions.ready'));
		expect(screen.queryByTestId('decision-results')).toBeNull();
		expect((screen.getByRole('textbox', { name: t('decisions.content') }) as HTMLTextAreaElement).value).toBe('');
		expect(calls.decide).toHaveBeenCalledTimes(1);
	});
	it.each(['loading', 'error'] as const)('masks accepted results during permission %s and restores same-owner drafts and results', async (state) => {
		render(DecisionStudio); await fillPredicate(); await fillOptions(questionAt(), 'choice');
		await fireEvent.input(within(questionAt()).getByLabelText(t('decisions.name')), { target: { value: 'refund' } });
		await fireEvent.click(run());
		const accepted = (await screen.findByTestId('decision-results')).textContent;
		await fireEvent.input(screen.getByRole('textbox', { name: t('decisions.content') }), { target: { value: 'Unsaved parcel draft.' } });
		await fireEvent.input(within(questionAt()).getByRole('textbox', { name: t('decisions.instructions') }), { target: { value: 'Unsaved follow-up question.' } });
		pendingLumen(state === 'error' ? 'Permission lookup unavailable' : '');
		await tick();
		expect(screen.queryByTestId('decision-results')).toBeNull();
		expect(run().hasAttribute('disabled')).toBe(true);
		expect(questionAt().hasAttribute('disabled')).toBe(true);
		grantLumen('lumen-chat_user');
		expect((await screen.findByTestId('decision-results')).textContent).toBe(accepted);
		expect((screen.getByRole('textbox', { name: t('decisions.content') }) as HTMLTextAreaElement).value).toBe('Unsaved parcel draft.');
		expect((within(questionAt()).getByRole('textbox', { name: t('decisions.instructions') }) as HTMLTextAreaElement).value).toBe('Unsaved follow-up question.');
		expect((within(questionAt()).getByLabelText(t('decisions.name')) as HTMLInputElement).value).toBe('refund');
		expect((within(questionAt()).getByRole('textbox', { name: `${t('decisions.value')} 1` }) as HTMLInputElement).value).toBe('low');
		expect(run().hasAttribute('disabled')).toBe(false);
		expect(calls.models).toHaveBeenCalledTimes(1); expect(calls.capabilities).toHaveBeenCalledTimes(1);
		expect(calls.decide).toHaveBeenCalledTimes(1);
	});
	it.each(['unverified', 'restored', 'same-tick'] as const)('ignores a late dispatch completed while permission is %s without clearing drafts', async (timing) => {
		const pending = Promise.withResolvers<DecisionModule.DecisionResult>(); calls.decide.mockReturnValue(pending.promise);
		render(DecisionStudio); await fillPredicate(); await fireEvent.click(run());
		const signal = calls.decide.mock.calls[0][2] as AbortSignal;
		pendingLumen();
		expect(signal.aborted).toBe(true);
		if (timing !== 'same-tick') await tick();
		if (timing !== 'unverified') grantLumen('lumen-chat_user');
		pending.resolve(result()); await pending.promise; await tick();
		expect(screen.queryByTestId('decision-results')).toBeNull();
		if (timing === 'unverified') grantLumen('lumen-chat_user');
		await screen.findByText(t('decisions.ready'));
		expect(screen.queryByTestId('decision-results')).toBeNull();
		expect((screen.getByRole('textbox', { name: t('decisions.content') }) as HTMLTextAreaElement).value).toBe('A damaged parcel arrived.');
		expect((within(questionAt()).getByRole('textbox', { name: t('decisions.instructions') }) as HTMLTextAreaElement).value).toBe('Does it need a refund?');
		expect(calls.models).toHaveBeenCalledTimes(1); expect(calls.capabilities).toHaveBeenCalledTimes(1);
		expect(calls.decide).toHaveBeenCalledTimes(1);
	});
	it('clears accepted results and drafts after confirmed permission denial, even when grants return', async () => {
		render(DecisionStudio); await fillPredicate(); await fireEvent.click(run());
		await screen.findByTestId('decision-results');
		grantLumen('lumen-images_user'); await tick();
		expect(screen.queryByTestId('decision-results')).toBeNull();
		grantLumen('lumen-chat_user'); await screen.findByText(t('decisions.ready'));
		expect(screen.queryByTestId('decision-results')).toBeNull();
		expect((screen.getByRole('textbox', { name: t('decisions.content') }) as HTMLTextAreaElement).value).toBe('');
		expect((within(questionAt()).getByRole('textbox', { name: t('decisions.instructions') }) as HTMLTextAreaElement).value).toBe('');
		expect(calls.decide).toHaveBeenCalledTimes(1);
	});
	it.each(['models', 'capabilities'] as const)('restarts pending %s reads after permission ABA and rejects old completion', async (stage) => {
		const oldModels = Promise.withResolvers<DecisionModule.DecisionModel[]>();
		const oldCapability = Promise.withResolvers<DecisionModule.DecisionCapabilities>();
		if (stage === 'models') calls.models.mockReturnValueOnce(oldModels.promise);
		else calls.capabilities.mockReturnValueOnce(oldCapability.promise);
		render(DecisionStudio);
		await waitFor(() => expect(calls[stage]).toHaveBeenCalledTimes(1));
		const signal = calls[stage].mock.calls[0][stage === 'models' ? 1 : 2] as AbortSignal;
		pendingLumen(); grantLumen('lumen-chat_user');
		expect(signal.aborted).toBe(true);
		await waitFor(() => expect(calls[stage]).toHaveBeenCalledTimes(2));
		await screen.findByText(t('decisions.ready'));
		if (stage === 'models') oldModels.resolve([{ ...model, display_name: 'Private stale model' }]);
		else oldCapability.resolve({ ...capability(), model_capabilities: { ...gate, decisions: false } });
		await (stage === 'models' ? oldModels.promise : oldCapability.promise); await tick();
		expect(screen.queryByRole('option', { name: 'Private stale model' })).toBeNull();
		expect(screen.getByText(t('decisions.ready'))).toBeTruthy();
		expect(run().hasAttribute('disabled')).toBe(false);
	});
	it('keeps same-owner drafts through verified token-only renewal and sends the fresh scope', async () => {
		render(DecisionStudio); await fillPredicate();
		refreshLumenAuth('fresh-token');
		await fireEvent.click(run()); await screen.findByTestId('decision-results');
		expect(calls.models).toHaveBeenCalledTimes(1);
		expect(calls.decide.mock.calls[0][1]).toEqual({ token: 'fresh-token', projectId: 'project-1' });
	});
	it('discards late model and capability reads after replacement', async () => {
		const oldModels = Promise.withResolvers<DecisionModule.DecisionModel[]>();
		calls.models.mockReturnValueOnce(oldModels.promise).mockResolvedValue([model, { ...model, id: 10, display_name: 'Other decisions' }]);
		const view = render(DecisionStudio);
		await waitFor(() => expect(calls.models).toHaveBeenCalledTimes(1));
		const oldSignal = calls.models.mock.calls[0][1] as AbortSignal;
		setVerifiedLumenActor(user('project-2')); expect(oldSignal.aborted).toBe(true);
		oldModels.resolve([{ ...model, display_name: 'Private stale model' }]);
		await screen.findByText(t('decisions.ready'));
		expect(screen.queryByRole('option', { name: 'Private stale model' })).toBeNull();
		view.unmount();
		calls.models.mockResolvedValue([model, { ...model, id: 10, display_name: 'Other decisions' }]);
		const oldCapability = Promise.withResolvers<DecisionModule.DecisionCapabilities>();
		calls.capabilities.mockReturnValueOnce(oldCapability.promise).mockImplementation(async (id: number) => capability(id));
		render(DecisionStudio);
		await waitFor(() => expect(screen.getByRole('option', { name: 'Other decisions' })).toBeTruthy());
		await fireEvent.change(screen.getByRole('combobox', { name: t('decisions.model') }), { target: { value: '10' } });
		oldCapability.resolve(capability(9)); await screen.findByText(t('decisions.ready'));
		expect((screen.getByRole('combobox', { name: t('decisions.model') }) as HTMLSelectElement).value).toBe('10');
	});
	it('does not query or send without chat authority, and shows unpriced models as unavailable', async () => {
		grantLumen('lumen-images_user');
		const view = render(DecisionStudio); await Promise.resolve();
		expect(calls.models).not.toHaveBeenCalled(); expect(run().hasAttribute('disabled')).toBe(true);
		view.unmount(); grantLumen('lumen-chat_user');
		calls.capabilities.mockResolvedValue({ ...capability(), model_capabilities: { ...gate, feature_gates: { decisions: { ...gate.feature_gates.decisions, pricing_available: false } } } });
		render(DecisionStudio); await screen.findByText(t('decisions.pricingMissing'));
		expect(run().hasAttribute('disabled')).toBe(true); expect(calls.decide).not.toHaveBeenCalled();
	});
	it('aborts an in-flight decision on unmount and ignores errors after teardown', async () => {
		const pending = Promise.withResolvers<DecisionModule.DecisionResult>(); calls.decide.mockReturnValue(pending.promise);
		const view = render(DecisionStudio); await fillPredicate(); await fireEvent.click(run());
		const signal = calls.decide.mock.calls[0][2] as AbortSignal;
		view.unmount(); expect(signal.aborted).toBe(true);
		pending.reject(new Error('late failure')); await pending.promise.catch(() => {});
		expect(screen.queryByText('late failure')).toBeNull();
	});
});

describe('Decision Studio local image ownership', () => {
	beforeEach(() => { vi.stubGlobal('FileReader', ControlledFileReader); });
	it('converts a bounded local image to a data URL and sends it once', async () => {
		render(DecisionStudio); await fillPredicate(); await chooseInput('file');
		await fireEvent.change(screen.getByLabelText(t('decisions.file'), { exact: false }), { target: { files: [new File(['hi'], 'photo.png', { type: 'image/png' })] } });
		expect(run().hasAttribute('disabled')).toBe(true);
		ControlledFileReader.readers[0].finish();
		await screen.findByText('photo.png');
		// jsdom does not populate the native file input's value from a synthetic FileList.
		await fireEvent.submit(screen.getByRole('form', { name: t('decisions.title') }));
		await screen.findByTestId('decision-results');
		expect(calls.decide.mock.calls[0][0].input).toEqual([{ role: 'user', content: [{ type: 'input_image', image_url: 'data:image/png;base64,aGk=', detail: 'auto' }] }]);
	});
	it.each(['oversize', 'wrong-type', 'empty'] as const)('rejects %s files before reading or sending', async (kind) => {
		render(DecisionStudio); await fillPredicate(); await chooseInput('file');
		const file = kind === 'oversize' ? new File([new Uint8Array(MAX_DECISION_IMAGE_BYTES + 1)], 'large.png', { type: 'image/png' })
			: kind === 'wrong-type' ? new File(['<svg/>'], 'unsafe.svg', { type: 'image/svg+xml' }) : new File([], 'empty.png', { type: 'image/png' });
		await fireEvent.change(screen.getByLabelText(t('decisions.file'), { exact: false }), { target: { files: [file] } });
		await screen.findByText(t('decisions.imageLimit'));
		expect(ControlledFileReader.readers).toHaveLength(0); expect(calls.decide).not.toHaveBeenCalled();
	});
	it('keeps the newest file when the older read finishes late', async () => {
		render(DecisionStudio); await fillPredicate(); await chooseInput('file');
		for (const name of ['old.png', 'new.png']) await fireEvent.change(screen.getByLabelText(t('decisions.file'), { exact: false }), { target: { files: [new File(['hi'], name, { type: 'image/png' })] } });
		expect(ControlledFileReader.readers[0].abort).toHaveBeenCalledOnce();
		ControlledFileReader.readers[1].finish('data:image/png;base64,bmV3');
		ControlledFileReader.readers[0].finish('data:image/png;base64,b2xk');
		await screen.findByText('new.png'); expect(screen.queryByText('old.png')).toBeNull();
		await fireEvent.submit(screen.getByRole('form', { name: t('decisions.title') }));
		await screen.findByTestId('decision-results');
		expect(calls.decide.mock.calls[0][0].input[0].content[0].image_url).toBe('data:image/png;base64,bmV3');
	});
	it.each(['input', 'owner', 'authority', 'model', 'unmount'] as const)('discards local file reads after %s replacement', async (boundary) => {
		calls.models.mockResolvedValue([model, { ...model, id: 10, display_name: 'Other decisions' }]);
		const view = render(DecisionStudio); await fillPredicate(); await chooseInput('file');
		await fireEvent.change(screen.getByLabelText(t('decisions.file'), { exact: false }), { target: { files: [new File(['hi'], 'private.png', { type: 'image/png' })] } });
		const old = ControlledFileReader.readers[0];
		if (boundary === 'input') { await chooseInput('text'); await chooseInput('file'); }
		if (boundary === 'owner') { setVerifiedLumenActor(user('project-2')); setVerifiedLumenActor(user()); }
		if (boundary === 'authority') { pendingLumen(); grantLumen('lumen-chat_user'); }
		if (boundary === 'model') await fireEvent.change(screen.getByRole('combobox', { name: t('decisions.model') }), { target: { value: '10' } });
		if (boundary === 'unmount') view.unmount();
		expect(old.abort).toHaveBeenCalledOnce(); old.finish(); await Promise.resolve();
		expect(screen.queryByText('private.png')).toBeNull(); expect(calls.decide).not.toHaveBeenCalled();
	});
});

const geminiModel: DecisionModule.DecisionModel = {
	...model, id: 19, provider_id: 14, provider_type: 'gemini', model_kind: 'decision',
	model_name: 'gemini/gemini-decision-1', display_name: 'Gemini Decision 1', effective_input_price_per_million: '0.10'
};
const geminiInput = () => screen.getByLabelText(t('decisions.text'));
const geminiKey = (index = 0) => within(questionAt(index)).getByRole('textbox', { name: t('gemini.questionKey') });
const fillInput = (element: HTMLElement, value: string) => fireEvent.input(element, { target: { value } });
async function fillGeminiQuestion(index: number, key: string, instructions: string, type = 'noul') {
	if (index) await fireEvent.click(screen.getByRole('button', { name: t('decisions.addQuestion') }));
	await fillInput(geminiKey(index), key);
	await fillInput(within(questionAt(index)).getByRole('textbox', { name: t('decisions.instructions') }), instructions);
	await fireEvent.change(within(questionAt(index)).getByLabelText(t('decisions.type')), { target: { value: type } });
}
async function selectGeminiModel(entry = geminiModel) {
	calls.models.mockResolvedValue([model, entry]);
	calls.capabilities.mockImplementation(async (id: number, _scope, _signal, kind) => ({ ...capability(id), model_kind: kind }));
	render(DecisionStudio); await fillPredicate();
	await fireEvent.change(screen.getByRole('combobox', { name: t('decisions.model') }), { target: { value: String(entry.id) } });
	await screen.findByText(t('decisions.ready'));
}

describe('Gemini Decision Studio', () => {
	it('shows Gemini only for Gemini decision models, with independent unchanged OpenAI drafts', async () => {
		await selectGeminiModel();
		expect(geminiInput()).toBeTruthy();
		expect(calls.capabilities).toHaveBeenLastCalledWith(19, expect.anything(), expect.any(AbortSignal), 'decision');
		expect(screen.queryByLabelText(t('decisions.inputType'))).toBeNull();
		await fillInput(geminiInput(), 'Gemini draft');
		await fireEvent.change(screen.getByRole('combobox', { name: t('decisions.model') }), { target: { value: '9' } });
		await screen.findByText(t('decisions.ready'));
		expect(screen.queryByLabelText(t('gemini.images'))).toBeNull();
		expect((screen.getByRole('textbox', { name: t('decisions.content') }) as HTMLTextAreaElement).value).toBe('A damaged parcel arrived.');
		await fireEvent.click(run());
		expect(calls.decide.mock.calls[0][0].questions[0].type).toBe('predicate');
		expect(calls.decideGemini).not.toHaveBeenCalled();
	});
	it('also uses the Gemini editor for a Gemini text model with the decisions capability', async () => {
		await selectGeminiModel({ ...geminiModel, model_kind: 'text' });
		expect(geminiInput()).toBeTruthy();
		expect(calls.capabilities).toHaveBeenLastCalledWith(19, expect.anything(), expect.any(AbortSignal), 'text');
	});
	it('requests decision-kind capabilities and explains a Lumen version rejection', async () => {
		const actual = await vi.importActual<typeof DecisionModule>('$lib/api/decisionStudio');
		const get = vi.spyOn(api, 'get').mockResolvedValueOnce(capability()).mockRejectedValueOnce(new ApiError(422, 'unsupported query kind')).mockResolvedValueOnce(capability());
		calls.models.mockResolvedValue([model, geminiModel]);
		calls.capabilities.mockImplementation(actual.decisionStudioApi.capabilities);
		render(DecisionStudio); await fillPredicate();
		await fireEvent.change(screen.getByRole('combobox', { name: t('decisions.model') }), { target: { value: '19' } });
		await screen.findByText(t('gemini.lumenUpdate'));
		expect(get).toHaveBeenLastCalledWith('/api/v1/chat/capabilities?model_id=19&model_kind=decision', 'token', 'project-1', expect.objectContaining({ signal: expect.any(AbortSignal) }));
		expect((run() as HTMLButtonElement).disabled).toBe(true);
		expect(calls.decideGemini).not.toHaveBeenCalled();
		await fireEvent.change(screen.getByRole('combobox', { name: t('decisions.model') }), { target: { value: '9' } });
		await screen.findByText(t('decisions.ready'));
		expect((run() as HTMLButtonElement).disabled).toBe(false);
	});
	it('blocks empty input, malformed question keys, duplicate keys and incomplete criteria', async () => {
		await selectGeminiModel();
		await fillGeminiQuestion(0, 'bad key', 'Is the mug cracked?');
		await fireEvent.click(run());
		expect((await screen.findByRole('alert')).textContent).toContain(t('gemini.emptyInput'));
		expect(document.activeElement).toBe(geminiInput());
		expect(geminiInput().getAttribute('aria-invalid')).toBe('true');
		await fillInput(geminiInput(), 'Cracked mug');
		expect(geminiInput().getAttribute('aria-invalid')).toBeNull();
		await fireEvent.click(run()); expect((await screen.findByRole('alert')).textContent).toContain(t('gemini.questionKeyHelp'));
		expect(document.activeElement).toBe(geminiKey());
		expect(geminiKey().getAttribute('aria-describedby')).toContain('decision-error-summary');
		await fillInput(geminiKey(), 'damage');
		await fillGeminiQuestion(1, 'damage', 'Which type?', 'choice');
		await fireEvent.click(run());
		const duplicate = await screen.findByRole('alert');
		expect(duplicate.textContent).toContain(t('decisions.duplicateNames'));
		expect(duplicate.textContent).toContain(t('gemini.questionField', { question: 2, field: t('gemini.questionKey') }));
		expect(document.activeElement).toBe(geminiKey(1));
		await fillInput(geminiKey(1), 'type');
		const choice = within(questionAt(1));
		const removeChoice = () => choice.getByRole('button', { name: t('decisions.removeChoice', { number: 1 }) }) as HTMLButtonElement;
		expect(removeChoice().disabled).toBe(true);
		await fireEvent.click(choice.getByRole('button', { name: t('decisions.addChoice') }));
		expect(choice.getByRole('textbox', { name: t('gemini.optionKey', { number: 3 }) })).toBeTruthy();
		await fireEvent.click(removeChoice());
		expect(removeChoice().disabled).toBe(true);
		expect(document.activeElement).toBe(choice.getByRole('textbox', { name: t('gemini.optionKey', { number: 1 }) }));
		await fireEvent.click(run()); expect((await screen.findByRole('alert')).textContent).toContain(t('gemini.choiceKey'));
		await fireEvent.change(choice.getByLabelText(t('decisions.type')), { target: { value: 'score' } });
		const removeLevel = () => choice.getByRole('button', { name: t('decisions.removeLevel', { number: 1 }) }) as HTMLButtonElement;
		expect(removeLevel().disabled).toBe(true);
		await fireEvent.click(choice.getByRole('button', { name: t('decisions.addLevel') }));
		expect(choice.getByRole('textbox', { name: t('gemini.levelDescription', { number: 3 }) })).toBeTruthy();
		await fireEvent.click(removeLevel());
		expect(removeLevel().disabled).toBe(true);
		const firstLevel = choice.getByRole('textbox', { name: t('gemini.levelDescription', { number: 1 }) });
		expect(document.activeElement).toBe(firstLevel);
		await fireEvent.click(run()); expect((await screen.findByRole('alert')).textContent).toContain(t('gemini.requiredText'));
		expect(document.activeElement).toBe(firstLevel);
		expect(firstLevel.getAttribute('aria-invalid')).toBe('true');
		expect(calls.decideGemini).not.toHaveBeenCalled();
	});
	it('posts mixed text, JSON and images; renders noul, choice, score and estimated usage cost', async () => {
		// Answer examples from https://aistudio.google.com/docs/decisions-api#question-types.
		const legend = {
			0: 'Cosmetic: appearance only, no lost functionality.',
			1: 'Workaround available: a task fails, but another way works.',
			2: 'Fully blocked: a task fails with no workaround.'
		};
		const providerResponse = {
			model: geminiModel.model_name,
			answers: {
				is_defect: { type: 'noul', noul: 0.03, confidence: 0.97 },
				department: { type: 'choice', choice: 'billing', probabilities: { billing: 0.99, shipping: 0.004, other: 0.003, technical: 0.002 }, confidence: 0.99 },
				severity: { type: 'score', score: 1.12, legend, probabilities: { 0: 0.03, 1: 0.83, 2: 0.15 }, confidence: 0.83 }
			},
			usage: { total_input_tokens: 100, input_tokens_by_modality: [{ modality: 'image', tokens: 70 }, { modality: 'text', tokens: 30 }], total_output_tokens: 0, total_tokens: 100 }
		};
		calls.decideGemini.mockImplementation(async (request: DecisionModule.PreparedGeminiDecision) => parseGeminiDecisionResult(providerResponse, request.questions, geminiModel.model_name));
		await selectGeminiModel();
		await fillInput(geminiInput(), 'Cracked mug');
		await fillInput(screen.getByLabelText(t('gemini.json')), '{"id":9007199254740993}');
		await fireEvent.change(screen.getByLabelText(t('gemini.images')), { target: { files: [new File(['mug'], 'mug.HEIC')] } });
		await fireEvent.change(screen.getByLabelText(t('gemini.imageResolution')), { target: { value: 'high' } });
		await fillGeminiQuestion(0, 'is_defect', 'Is the mug cracked?');
		await fillInput(screen.getByLabelText(t('gemini.yesDescription')), 'Visible crack');
		await fillGeminiQuestion(1, 'department', 'Which team?', 'choice');
		const choice = within(questionAt(1));
		for (const [index, key] of ['billing', 'shipping', 'other', 'technical'].entries()) {
			if (index >= 2) await fireEvent.click(choice.getByRole('button', { name: t('decisions.addChoice') }));
			await fillInput(choice.getByRole('textbox', { name: t('gemini.optionKey', { number: index + 1 }) }), key);
		}
		await fillGeminiQuestion(2, 'severity', 'How severe?', 'score');
		const score = within(questionAt(2));
		await fireEvent.click(score.getByRole('button', { name: t('decisions.addLevel') }));
		for (const [index, description] of Object.values(legend).entries()) {
			await fillInput(score.getByRole('textbox', { name: t('gemini.levelDescription', { number: index + 1 }) }), description);
		}
		await fireEvent.click(run());
		const results = await screen.findByTestId('decision-results');
		expect(calls.decideGemini).toHaveBeenCalledWith(expect.objectContaining({ body: expect.any(String) }), geminiModel.model_name, { token: 'token', projectId: 'project-1' }, expect.any(AbortSignal));
		const sent = calls.decideGemini.mock.calls[0][0] as DecisionModule.PreparedGeminiDecision;
		expect(JSON.parse(sent.body)).toEqual({
			model: 'lumen/14/19', input: [{ type: 'text', text: 'Cracked mug' }, { type: 'text', text: '{"id":9007199254740993}' },
				{ type: 'image', data: 'bXVn', mime_type: 'image/heic', resolution: 'high' }],
			questions: {
				is_defect: { type: 'noul', instructions: 'Is the mug cracked?', criteria: { true_description: 'Visible crack' } },
				department: { type: 'choice', instructions: 'Which team?', criteria: { billing: '', shipping: '', other: '', technical: '' } },
				severity: { type: 'score', instructions: 'How severe?', criteria: Object.values(legend) }
			}
		});
		expect(within(results).getByText('3%', { selector: 'strong' })).toBeTruthy();
		expect(within(results).getByText('97%', { exact: false })).toBeTruthy();
		expect(within(results).getByText('billing', { selector: 'strong' })).toBeTruthy();
		expect(within(results).getByText('1.12')).toBeTruthy();
		expect(within(results).getByText(t('gemini.legendLevel', { number: '1', description: legend[1] }))).toBeTruthy();
		expect(results.querySelectorAll('meter')).toHaveLength(7);
		expect(within(results).getByText('0.00001')).toBeTruthy();
		expect(within(results).getByText(t('gemini.imageTokens'))).toBeTruthy();
		expect(within(results).queryByText(t('decisions.cacheWriteTokens'))).toBeNull();
	});
	it('cancels a pending Gemini decision without replay or late results', async () => {
		const response = Promise.withResolvers<DecisionModule.GeminiDecisionResult>();
		calls.decideGemini.mockReturnValue(response.promise);
		await selectGeminiModel(); await fillInput(geminiInput(), 'Cracked mug'); await fillGeminiQuestion(0, 'damaged', 'Is it damaged?');
		await fireEvent.click(run());
		await waitFor(() => expect(calls.decideGemini).toHaveBeenCalledOnce());
		const requestSignal = calls.decideGemini.mock.calls[0][3] as AbortSignal;
		await fireEvent.click(screen.getByRole('button', { name: t('decisions.cancel') }));
		expect(requestSignal.aborted).toBe(true);
		response.resolve({ model: geminiModel.model_name, answers: {}, usage: { total_input_tokens: 0, input_tokens_by_modality: [], total_output_tokens: 0, total_tokens: 0 } });
		await response.promise; await tick();
		expect(screen.queryByTestId('decision-results')).toBeNull();
		expect(calls.decideGemini).toHaveBeenCalledOnce();
	});
	it.each([[422, 'decision_input_modality_unsupported', 'gemini.unsupportedModality'], [400, 'image_safety', 'gemini.safetyBlocked']] as const)(
		'localizes %s %s without displaying upstream text', async (status, code, key) => {
			calls.decideGemini.mockRejectedValue(new ApiError(status, 'private provider message', code));
			await selectGeminiModel(); await fillInput(geminiInput(), 'Cracked mug'); await fillGeminiQuestion(0, 'damaged', 'Is it damaged?');
			await fireEvent.click(run()); await screen.findByText(t(key));
			expect(screen.queryByText('private provider message')).toBeNull();
			expect(calls.decideGemini).toHaveBeenCalledOnce();
		}
	);
});
