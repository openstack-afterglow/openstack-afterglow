import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/admin-chat';
import { pricingDraft } from '../modelPricing';

const calls = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn() }));
vi.mock('$lib/stores/auth', async () => {
	const { writable } = await import('svelte/store');
	return { auth: writable({ token: 'token', projectId: 'project', userId: 'owner', sessionId: 'session', roles: [], isSystemAdmin: true }), authReady: writable(true), projectSwitching: writable(false) };
});
vi.mock('$lib/api/client', () => ({ api: calls, ApiError: class extends Error {} }));
vi.mock('$lib/stores/chatModels', () => ({ invalidateChatModels: vi.fn() }));
import ChatConfiguration from '../ChatConfiguration.svelte';
import ModelKindEditor from '../ModelKindEditor.svelte';
import ModelMediaPricingEditor from '../ModelMediaPricingEditor.svelte';

const provider = { id: 1, name: 'OpenAI fixture', provider_type: 'openai', api_provider: 'openai', auth_mode: 'api_key', has_api_key: true, is_active: true, sort_order: 0 };
const candidate = { id: 'text-embedding-3-small', model_kind: 'embedding', purpose: 'non_chat', input_token_limit: 8191 };
const geminiProvider = { ...provider, name: 'Gemini fixture', provider_type: 'gemini', api_provider: 'gemini', api_base: null };
const geminiCandidate = { id: 'gemini-decision-1', model_kind: 'decision', purpose: 'non_chat', input_token_limit: 262144, generation_methods: ['createDecision'] };
afterEach(() => { cleanup(); initLocale('ko'); });
beforeEach(() => {
	vi.clearAllMocks(); initLocale('ko');
	calls.get.mockImplementation(async (path: string) => {
		if (path.endsWith('/available-models')) return { provider_id: 1, source: 'live', live_status: 'success', complete: true, models: [candidate.id], candidates: [candidate] };
		if (path.endsWith('/providers')) return [provider];
		return [];
	});
	calls.post.mockResolvedValue({}); calls.patch.mockResolvedValue({});
});

describe('input-only model registry flow', () => {
	it.each([
		[provider, candidate, '0.02'],
		[geminiProvider, geminiCandidate, '0.10']
	])('preselects discovered $1.model_kind and submits only its input-token price', async (owner, found, rate) => {
		calls.get.mockImplementation(async (path: string) => {
			if (path.endsWith('/available-models')) return { provider_id: 1, source: 'live', live_status: 'success', complete: true, models: [found.id], candidates: [found] };
			if (path.endsWith('/providers')) return [owner];
			return [];
		});
		render(ChatConfiguration, { section: 'models' });
		await screen.findByText(t('configuration.noModelsRegistered'));
		await fireEvent.click(screen.getByRole('button', { name: t('configuration.addModel') }));
		await fireEvent.click(await screen.findByRole('button', { name: t('configuration.loadModels') }));
		await screen.findByText(found.id);
		const checkbox = screen.getAllByRole('checkbox').find((node) => node.getAttribute('aria-label')?.includes(found.id));
		expect(checkbox).toBeTruthy();
		await fireEvent.click(checkbox!);
		await fireEvent.click(screen.getByRole('button', { name: t('configuration.reviewSelectedModels') }));
		const kind = document.querySelector('#review-kind-0') as HTMLSelectElement;
		expect(kind.value).toBe(found.model_kind);
		expect([...kind.options].map((option) => option.value)).toContain(found.model_kind);
		expect(document.querySelector('#review-output-0')).toBeNull();
		expect(screen.queryByTestId('review-media-0-media-pricing')?.querySelector('select')).toBeNull();
		await fireEvent.input(document.querySelector('#review-input-0')!, { target: { value: rate } });
		await fireEvent.click(screen.getByRole('button', { name: t('configuration.saveAsInactive') }));
		await waitFor(() => expect(calls.post).toHaveBeenCalled());
		expect(calls.post.mock.calls[0][1]).toEqual({ provider_id: 1, model_name: found.id, model_kind: found.model_kind, input_price_per_million: rate, is_active: false });
	});

	it.each(['embedding', 'decision'] as const)('clears incompatible prices when switching existing rows to %s', async (kind) => {
		render(ModelKindEditor, { model: { id: 7, model_name: 'existing', display_name: null, model_kind: 'text', catalog_entry: { kind }, media_pricing: { token_rates: { image: { output_per_million: '30' } } } }, mediaSupported: true, decisionSupported: true, token: 'token', projectId: 'project', onclose: vi.fn(), onsaved: vi.fn() });
		await fireEvent.change(screen.getByLabelText(t('configuration.modelType')), { target: { value: kind } });
		await fireEvent.click(screen.getByRole('button', { name: t('pricing.saveKind') }));
		expect(calls.patch).toHaveBeenCalledWith('/api/v1/chat/admin/models/7', { model_kind: kind, is_active: false, media_pricing: null, output_price_per_million: null, cache_read_price_per_million: null, cache_write_price_per_million: null, cache_write_1h_price_per_million: null }, 'token', 'project');
	});

	it('hides the Decision kind editor option without a matching native catalog entry', () => {
		render(ModelKindEditor, { model: { id: 7, model_name: 'existing', display_name: null, model_kind: 'text' }, mediaSupported: true, decisionSupported: true, token: 'token', projectId: 'project', onclose: vi.fn(), onsaved: vi.fn() });
		expect(screen.queryByRole('option', { name: t('configuration.decision') })).toBeNull();
		expect(screen.getByRole('option', { name: t('configuration.embedding') })).toBeTruthy();
	});

	it.each(['embedding', 'decision'] as const)('hides stored media prices in %s editor', (kind) => {
		const draft = pricingDraft({ token_rates: { image: { output_per_million: '30' } }, image_per_unit: '0.04' });
		render(ModelMediaPricingEditor, { kind, draft, prefix: 'embedding-test' });
		expect(screen.queryAllByRole('textbox')).toHaveLength(0);
		expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
		expect(screen.queryAllByRole('combobox')).toHaveLength(0);
		expect(document.querySelector('#embedding-test-text-pricing')).toBeTruthy();
		expect(document.querySelector('#embedding-test-image-pricing')).toBeNull();
	});

	it('manual Gemini creation drops a previous output-token price', async () => {
		calls.get.mockImplementation(async (path: string) => path.endsWith('/providers') ? [geminiProvider] : []);
		render(ChatConfiguration, { section: 'models' });
		await screen.findByText(t('configuration.noModelsRegistered'));
		await fireEvent.click(screen.getByRole('button', { name: t('configuration.addModel') }));
		await fireEvent.click(screen.getByRole('button', { name: t('configuration.manualModelMethod') }));
		await fireEvent.input(screen.getByPlaceholderText(t('configuration.modelNameEGGpt4o')), { target: { value: geminiCandidate.id } });
		await fireEvent.input(document.querySelector('#model-create-output-price')!, { target: { value: '99' } });
		await fireEvent.change(screen.getByLabelText(t('configuration.modelType')), { target: { value: 'decision' } });
		expect(document.querySelector('#model-create-output-price')).toBeNull();
		expect(screen.queryByTestId('model-create-cache-prices')).toBeNull();
		await fireEvent.input(document.querySelector('#model-create-input-price')!, { target: { value: '0.10' } });
		await fireEvent.click(screen.getAllByRole('button', { name: t('configuration.addModel') }).at(-1)!);
		await waitFor(() => expect(calls.post).toHaveBeenCalledWith('/api/v1/chat/admin/models', {
			provider_id: 1, model_name: geminiCandidate.id, model_kind: 'decision', display_name: null, input_price_per_million: '0.10'
		}, 'token', 'project'));
	});

	it('disables manual Decision registration for an OpenAI provider', async () => {
		render(ChatConfiguration, { section: 'models' });
		await screen.findByText(t('configuration.noModelsRegistered'));
		await fireEvent.click(screen.getByRole('button', { name: t('configuration.addModel') }));
		await fireEvent.click(screen.getByRole('button', { name: t('configuration.manualModelMethod') }));
		const select = screen.getByRole('combobox', { name: t('configuration.modelType') }) as HTMLSelectElement;
		expect(Array.from(select.options).find(({ value }) => value === 'decision')?.disabled).toBe(true);
	});

	it.each(['ko', 'en', 'ja', 'zh-CN', 'bn', 'ms', 'nb', 'sw', 'vi'] as const)('interpolates billing kind in %s', (locale) => {
		initLocale(locale);
		render(ModelMediaPricingEditor, { kind: 'image', draft: pricingDraft(), prefix: 'pricing-test' });
		const label = t('pricing.billingBasis', { kind: t('configuration.image') });
		expect(screen.getByLabelText(label)).toBeTruthy();
		expect(document.body.textContent).not.toContain('{kind}');
	});
});
