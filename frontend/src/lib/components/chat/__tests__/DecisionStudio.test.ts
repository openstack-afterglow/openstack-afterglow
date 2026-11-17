import { grantLumen, pendingLumen, refreshLumenAuth, setVerifiedLumenActor } from './lumenPermissionFixture';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type * as DecisionModule from '$lib/api/decisionStudio';
import { MAX_DECISION_IMAGE_BYTES } from '$lib/api/decisionStudio';
import DecisionStudio from '../DecisionStudio.svelte';
import { t } from '$lib/i18n/ns/decision-studio';
import { projectSwitching } from '$lib/stores/auth';

const calls = vi.hoisted(() => ({ models: vi.fn(), capabilities: vi.fn(), decide: vi.fn() }));
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
	it.each(['owner', 'authority', 'switching'] as const)('clears drafts and aborts on same-tick %s ABA', async (boundary) => {
		const pending = Promise.withResolvers<DecisionModule.DecisionResult>(); calls.decide.mockReturnValue(pending.promise);
		render(DecisionStudio); await fillPredicate(); await fireEvent.click(run());
		const signal = calls.decide.mock.calls[0][2] as AbortSignal;
		if (boundary === 'owner') { setVerifiedLumenActor(user('project-2')); setVerifiedLumenActor(user()); }
		if (boundary === 'authority') { pendingLumen(); grantLumen('lumen-chat_user'); }
		if (boundary === 'switching') { projectSwitching.set(true); projectSwitching.set(false); }
		expect(signal.aborted).toBe(true);
		pending.resolve(result()); await pending.promise;
		await waitFor(() => expect(calls.models).toHaveBeenCalledTimes(2));
		await screen.findByText(t('decisions.ready'));
		expect(screen.queryByTestId('decision-results')).toBeNull();
		expect((screen.getByRole('textbox', { name: t('decisions.content') }) as HTMLTextAreaElement).value).toBe('');
		expect(calls.decide).toHaveBeenCalledTimes(1);
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
