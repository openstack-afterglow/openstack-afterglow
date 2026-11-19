import { grantLumen, setVerifiedLumenActor } from './lumenPermissionFixture';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type * as EmbeddingModule from '$lib/api/embeddingStudio';
import EmbeddingStudio from '../EmbeddingStudio.svelte';
import { t } from '$lib/i18n/ns/chat-studio';
import { intlLocale } from '$lib/i18n/runtime.svelte';
import { t as t2 } from '$lib/i18n/ns/chat-settings';
import { ApiError } from '$lib/api/errors';

const calls = vi.hoisted(() => ({ models: vi.fn(), capabilities: vi.fn(), embed: vi.fn() }));
vi.mock('$lib/api/embeddingStudio', async (original) => ({ ...await original<typeof EmbeddingModule>(), embeddingStudioApi: calls }));

const gate = { feature_gates: { embeddings: { available: true, mode: 'native' as const, reason_code: null, pricing_available: true } } };
const model = { id: 7, provider_id: 1, provider_type: 'openai', provider_sort_order: 0, sort_order: 0, model_name: 'text-embedding-3-small', display_name: 'Small embeddings', model_kind: 'embedding' as const, provider_api_key_configured: true, capabilities: gate };
const capability = (overrides: Partial<EmbeddingModule.EmbeddingCapabilities> = {}): EmbeddingModule.EmbeddingCapabilities => ({
	model_id: 7, model_kind: 'embedding', model_capabilities: gate, default_dimensions: 1536, supports_dimensions: true,
	min_dimensions: 1, max_dimensions: 1536, max_input_tokens: 8191, max_inputs: 16, ...overrides
});
const embedded: EmbeddingModule.EmbeddingResult = {
	model_id: 7, model: 'text-embedding-3-small', dimensions: 3,
	embeddings: [{ index: 0, embedding: [3, 4, 0] }, { index: 1, embedding: [0, 0, 2] }],
	usage: { prompt_tokens: 5, total_tokens: 5, estimated: true }, credited_cost: 0.00002
};
const user = (projectId: string) => ({ token: 'token', refreshToken: null, accessExpiresAt: null, userId: 'owner', username: 'tester', projectId, projectName: projectId, availableProjects: [], roles: [], isSystemAdmin: false, federated: false, domainId: 'domain-1', domainName: 'Domain', identityDomainId: 'domain-1', identityDomainName: 'Domain', isDomainManager: false });
const input = (number: number) => screen.getByLabelText(t('embeddingStudio.inputLabel', { number }));
const embedButton = () => screen.getByRole('button', { name: t('embeddingStudio.embed') });
const fixed4 = (value: number) => value.toLocaleString(intlLocale(), { minimumFractionDigits: 4, maximumFractionDigits: 4 });

async function fillTwoInputs() {
	await screen.findByText(t('embeddingStudio.ready'));
	await fireEvent.input(input(1), { target: { value: 'alpha' } });
	await fireEvent.click(screen.getByRole('button', { name: t('embeddingStudio.addInput') }));
	await fireEvent.input(input(2), { target: { value: 'beta' } });
}

beforeEach(() => {
	vi.clearAllMocks();
	setVerifiedLumenActor(user('project-1'));
	calls.models.mockResolvedValue([model]);
	calls.capabilities.mockImplementation(async (id: number) => capability({ model_id: id }));
	calls.embed.mockResolvedValue(embedded);
	vi.stubGlobal('URL', Object.assign(class extends URL {}, { createObjectURL: vi.fn(() => 'blob:embeddings'), revokeObjectURL: vi.fn() }));
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe('Embedding Studio', () => {
	it('embeds with the exact row from a different provider with the same model name', async () => {
		calls.models.mockResolvedValue([model, { ...model, id: 8, provider_id: 2, provider: 'Second OpenAI account' }]);
		calls.embed.mockResolvedValue({ ...embedded, model_id: 8, embeddings: [embedded.embeddings[0]] });
		render(EmbeddingStudio);
		await screen.findByText(t('embeddingStudio.ready'));
		await fireEvent.input(input(1), { target: { value: 'provider-specific vector' } });
		const select = screen.getByRole('combobox', { name: t('embeddingStudio.model') });
		await fireEvent.change(screen.getByRole('combobox', { name: t('modelPicker.providers') }), { target: { value: '2' } });
		expect(select).toHaveProperty('value', '');
		expect(embedButton()).toHaveProperty('disabled', true);
		await fireEvent.change(select, { target: { value: '8' } });
		await screen.findByText(t('embeddingStudio.ready'));
		await fireEvent.click(embedButton());
		expect(calls.capabilities).toHaveBeenLastCalledWith(8, expect.anything(), expect.any(AbortSignal));
		expect(calls.embed).toHaveBeenCalledWith({ model_id: 8, input: ['provider-specific vector'] }, expect.anything(), expect.any(AbortSignal));
	});

	it('uses published allowed dimensions as choices and sends only the explicit selection', async () => {
		calls.capabilities.mockResolvedValue(capability({ default_dimensions: 768, min_dimensions: 256, max_dimensions: 768, allowed_dimensions: [256, 768] }));
		render(EmbeddingStudio);
		await screen.findByText(t('embeddingStudio.ready'));
		const selector = screen.getByRole('combobox', { name: t('embeddingStudio.dimensions') });
		expect(Array.from((selector as HTMLSelectElement).options).map(option => option.value)).toEqual(['', '256', '768']);
		expect(screen.getByText(t('embeddingStudio.dimensionAllowedHelp', { values: '256, 768', default: 768 }))).toBeTruthy();
		await fireEvent.change(selector, { target: { value: '256' } });
		await fireEvent.input(input(1), { target: { value: 'catalog dimensions' } });
		await fireEvent.click(embedButton());
		await waitFor(() => expect(calls.embed).toHaveBeenCalledWith(
			{ model_id: 7, input: ['catalog dimensions'], dimensions: 256 }, expect.anything(), expect.any(AbortSignal)
		));
	});

	it('omits dimensions when the published choice selector stays at provider default', async () => {
		calls.capabilities.mockResolvedValue(capability({ default_dimensions: 768, min_dimensions: 256, max_dimensions: 768, allowed_dimensions: [256, 768] }));
		render(EmbeddingStudio);
		await screen.findByText(t('embeddingStudio.ready'));
		await fireEvent.input(input(1), { target: { value: 'default dimensions' } });
		await fireEvent.click(embedButton());
		await waitFor(() => expect(calls.embed).toHaveBeenCalledWith(
			{ model_id: 7, input: ['default dimensions'] }, expect.anything(), expect.any(AbortSignal)
		));
	});

	it('embeds every input and renders vectors, usage and the cosine matrix', async () => {
		render(EmbeddingStudio);
		await fillTwoInputs();
		await fireEvent.input(screen.getByLabelText(t('embeddingStudio.dimensions')), { target: { value: '3' } });
		await fireEvent.click(embedButton());

		await screen.findByRole('heading', { name: t('embeddingStudio.results') });
		expect(calls.embed).toHaveBeenCalledWith({ model_id: 7, input: ['alpha', 'beta'], dimensions: 3 }, expect.objectContaining({ token: 'token', projectId: 'project-1' }), expect.any(AbortSignal));
		expect(calls.capabilities).toHaveBeenCalledWith(7, expect.anything(), expect.any(AbortSignal));
		const norm = (value: number) => value.toLocaleString(intlLocale(), { maximumSignificantDigits: 8 });
		expect(screen.getByText(t('embeddingStudio.vectorStats', { length: 3, norm: norm(5) }))).toBeTruthy();
		expect(screen.getByText(t('embeddingStudio.vectorStats', { length: 3, norm: norm(2) }))).toBeTruthy();
		expect(screen.getByText('[3,4,0]')).toBeTruthy();
		expect(screen.getByText(t('embeddingStudio.estimated'))).toBeTruthy();
		// [3,4,0]·[0,0,2] = 0, so only the diagonal is 1.
		expect(screen.getAllByText(fixed4(1))).toHaveLength(2);
		expect(screen.getAllByText(fixed4(0))).toHaveLength(2);
		expect(screen.getByRole('link', { name: t('embeddingStudio.downloadJson') }).getAttribute('href')).toBe('blob:embeddings');
	});

	it('copies the exact response JSON', async () => {
		const writeText = vi.fn().mockResolvedValue(undefined);
		Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
		try {
			render(EmbeddingStudio);
			await fillTwoInputs();
			await fireEvent.click(embedButton());
			await fireEvent.click(await screen.findByRole('button', { name: t('embeddingStudio.copyJson') }));
			await screen.findByText(t('embeddingStudio.copied'));
			expect(JSON.parse(writeText.mock.calls[0][0])).toEqual(embedded);
		} finally {
			Reflect.deleteProperty(navigator, 'clipboard');
		}
	});

	it('omits the similarity matrix for a single input', async () => {
		calls.embed.mockResolvedValue({ ...embedded, embeddings: [embedded.embeddings[0]] });
		render(EmbeddingStudio);
		await screen.findByText(t('embeddingStudio.ready'));
		await fireEvent.input(input(1), { target: { value: 'alpha' } });
		await fireEvent.click(embedButton());
		await screen.findByRole('heading', { name: t('embeddingStudio.results') });
		expect(screen.queryByText(t('embeddingStudio.similarity'))).toBeNull();
		expect(calls.embed.mock.calls[0][0]).toEqual({ model_id: 7, input: ['alpha'] });
	});

	it('hides dimensions when the model cannot choose them and blocks out-of-range dimensions otherwise', async () => {
		calls.capabilities.mockResolvedValueOnce(capability({ supports_dimensions: false, min_dimensions: null, max_dimensions: null }));
		const view = render(EmbeddingStudio);
		await screen.findByText(t('embeddingStudio.ready'));
		expect(screen.queryByLabelText(t('embeddingStudio.dimensions'))).toBeNull();
		view.unmount();

		calls.capabilities.mockResolvedValueOnce(capability({ min_dimensions: 64, max_dimensions: 256 }));
		render(EmbeddingStudio);
		await screen.findByText(t('embeddingStudio.ready'));
		await fireEvent.input(input(1), { target: { value: 'alpha' } });
		await fireEvent.input(screen.getByLabelText(t('embeddingStudio.dimensions')), { target: { value: '512' } });
		expect(screen.getByText(t('embeddingStudio.dimensionInvalid'))).toBeTruthy();
		expect(embedButton().hasAttribute('disabled')).toBe(true);
		await fireEvent.input(screen.getByLabelText(t('embeddingStudio.dimensions')), { target: { value: '128' } });
		expect(embedButton().hasAttribute('disabled')).toBe(false);
	});

	it('bounds inputs by the model limit and requires every input to be non-empty', async () => {
		calls.capabilities.mockResolvedValue(capability({ max_inputs: 2 }));
		render(EmbeddingStudio);
		await fillTwoInputs();
		expect(screen.getByRole('button', { name: t('embeddingStudio.addInput') }).hasAttribute('disabled')).toBe(true);
		await fireEvent.input(input(2), { target: { value: '   ' } });
		expect(embedButton().hasAttribute('disabled')).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: t('embeddingStudio.removeInput', { number: 2 }) }));
		expect(screen.queryByLabelText(t('embeddingStudio.inputLabel', { number: 2 }))).toBeNull();
		expect(embedButton().hasAttribute('disabled')).toBe(false);
		expect(screen.getByRole('button', { name: t('embeddingStudio.removeInput', { number: 1 }) }).hasAttribute('disabled')).toBe(true);
	});

	it('aborts the in-flight request on cancel and ignores its late result', async () => {
		const pending = Promise.withResolvers<EmbeddingModule.EmbeddingResult>();
		let signal: AbortSignal | undefined;
		calls.embed.mockImplementation((_request, _scope, requestSignal: AbortSignal) => { signal = requestSignal; return pending.promise; });
		render(EmbeddingStudio);
		await fillTwoInputs();
		await fireEvent.click(embedButton());
		await fireEvent.click(await screen.findByRole('button', { name: t('embeddingStudio.cancel') }));
		expect(signal?.aborted).toBe(true);
		await screen.findByText(t('embeddingStudio.cancelled'));
		pending.resolve(embedded);
		await pending.promise;
		await Promise.resolve();
		expect(screen.queryByRole('heading', { name: t('embeddingStudio.results') })).toBeNull();
		expect(embedButton().hasAttribute('disabled')).toBe(false);
	});

	it('aborts and discards an in-flight request after a project switch', async () => {
		const pending = Promise.withResolvers<EmbeddingModule.EmbeddingResult>();
		let signal: AbortSignal | undefined;
		calls.embed.mockImplementation((_request, _scope, requestSignal: AbortSignal) => { signal = requestSignal; return pending.promise; });
		render(EmbeddingStudio);
		await fillTwoInputs();
		await fireEvent.click(embedButton());
		await waitFor(() => expect(calls.embed).toHaveBeenCalled());
		setVerifiedLumenActor(user('project-2'));
		expect(signal?.aborted).toBe(true);
		pending.resolve(embedded);
		await pending.promise;
		await waitFor(() => expect(calls.models).toHaveBeenCalledTimes(2));
		expect(screen.queryByRole('heading', { name: t('embeddingStudio.results') })).toBeNull();
		expect((input(1) as HTMLTextAreaElement).value).toBe('');
	});

	it('shows readiness blockers and service errors without dispatching', async () => {
		calls.models.mockResolvedValue([{ ...model, provider_api_key_configured: false }]);
		const view = render(EmbeddingStudio);
		await screen.findByText(t('embeddingStudio.providerKeyMissing'));
		expect(embedButton().hasAttribute('disabled')).toBe(true);
		view.unmount();

		calls.models.mockResolvedValue([model]);
		calls.embed.mockRejectedValue(new Error(t('embeddingStudio.invalidResponse')));
		render(EmbeddingStudio);
		await screen.findByText(t('embeddingStudio.ready'));
		await fireEvent.input(input(1), { target: { value: 'alpha' } });
		await fireEvent.click(embedButton());
		await screen.findByText(t('embeddingStudio.invalidResponse'));
		expect(screen.queryByRole('heading', { name: t('embeddingStudio.results') })).toBeNull();
	});

	it('does not query or embed without the Lumen chat leaf', async () => {
		grantLumen('lumen-images_user', 'lumen-audio_user');
		render(EmbeddingStudio);
		await Promise.resolve();
		expect(calls.models).not.toHaveBeenCalled();
		expect(embedButton().hasAttribute('disabled')).toBe(true);
		await fireEvent.click(embedButton());
		expect(calls.embed).not.toHaveBeenCalled();
	});
});

describe('Embedding Studio in the Personal domain', () => {
	const workIn = (kind: 'personal' | 'organization') => setVerifiedLumenActor({ ...user('project-1'), availableDomains: [{ id: 'domain-1', name: 'Domain', kind }] });

	it('shows the missing-pool notice and never runs, while models stay inspectable', async () => {
		workIn('personal');
		render(EmbeddingStudio);
		await waitFor(() => expect(calls.capabilities).toHaveBeenCalled());
		expect(screen.getByText(t2('dashboardChat.personalUnavailable'))).toBeTruthy();
		expect(screen.getByRole('button', { name: t2('dashboardChat.switchWorkspace') })).toBeTruthy();
		expect(screen.queryByText(t('embeddingStudio.ready'))).toBeNull();
		await fireEvent.input(input(1), { target: { value: 'personal input' } });
		expect(embedButton().hasAttribute('disabled')).toBe(true);
		await fireEvent.submit(embedButton().closest('form')!);
		expect(calls.embed).not.toHaveBeenCalled();
	});

	it('runs in an organization and maps an unfunded pool to a top-up request', async () => {
		workIn('organization');
		calls.embed.mockRejectedValue(new ApiError(429, 'domain_credit_insufficient'));
		render(EmbeddingStudio);
		await screen.findByText(t('embeddingStudio.ready'));
		expect(screen.queryByText(t2('dashboardChat.personalUnavailable'))).toBeNull();
		await fireEvent.input(input(1), { target: { value: 'organization input' } });
		await fireEvent.click(embedButton());
		expect(await screen.findByText(t2('dashboardChat.organizationCreditInsufficient'))).toBeTruthy();
	});
});
