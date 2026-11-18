import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { tick } from 'svelte';
import { writable } from 'svelte/store';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/native-providers';
import { t as adminT } from '$lib/i18n/ns/admin-chat';
import { FOLLOW_NATIVE_CATALOG_PRICES, catalogSourceUrl, type NativeCatalog, type NativeCatalogEntry } from '$lib/api/nativeCatalog';

const calls = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), success: vi.fn(), error: vi.fn() }));
vi.mock('$lib/stores/auth', () => {
	return { auth: writable({ token: 'token', projectId: 'project', userId: 'owner', sessionId: 'session', roles: [], isSystemAdmin: true }), authReady: writable(true), projectSwitching: writable(false) };
});
vi.mock('$lib/api/client', () => ({ api: calls, ApiError: class extends Error { constructor(message: string, public status: number) { super(message); } } }));
vi.mock('$lib/stores/chatModels', () => ({ invalidateChatModels: vi.fn() }));
vi.mock('$lib/stores/toast', () => ({ toast: { success: calls.success, error: calls.error } }));
import { auth, authReady, projectSwitching } from '$lib/stores/auth';
import ChatConfiguration from '../ChatConfiguration.svelte';
import NativeCatalogPanel from '../NativeCatalogPanel.svelte';
import ModelCapabilityBadges from '$lib/components/chat/ModelCapabilityBadges.svelte';

const provider = { id: 1, name: 'Fixture OpenAI', provider_type: 'openai', provider_family: 'native', api_provider: 'openai', api_base: null, auth_mode: 'api_key', has_api_key: true, is_active: true, sort_order: 0 };
const entry: NativeCatalogEntry = {
	id: 'gpt-6-luna', display_name: 'GPT-6 Luna fixture', aliases: [], kind: 'text', status: 'active', context_window: null, max_output_tokens: null,
	input_modalities: ['text', 'image'], output_modalities: ['text'], capabilities: { decisions: true, tool_call: true },
	token_pricing: { input: '0.10', output: '0.50', cache_read: '0.01', cache_write: '0.125', cache_write_ttl: '30m', long_context: { threshold_tokens: 272000, input: '0.20' } },
	media_pricing: null, source_urls: ['https://developers.openai.com/api/docs/pricing'], verified_at: '2026-11-17', notes: null
};
const catalog: NativeCatalog = { schema_version: 1, catalog_version: '2026-11-17', providers: [{ provider_type: 'openai', display_name: 'OpenAI', pricing_sources: entry.source_urls, models: [entry] }] };
function model(overrides: Record<string, unknown> = {}) {
	return { id: 7, provider_id: 1, model_name: entry.id, display_name: 'Registered fixture', model_kind: 'text', api_provider: 'openai', is_active: false, sort_order: 0,
		provider_family: 'native', price_origin: 'manual', catalog_version: catalog.catalog_version,
		catalog_entry: { id: entry.id, status: entry.status, verified_at: entry.verified_at, source_urls: entry.source_urls },
		input_price_per_million: '1', output_price_per_million: '2', effective_input_price_per_million: '1', effective_output_price_per_million: '2',
		cache_read_price_per_million: '0.3', cache_write_price_per_million: '1.25', cache_write_1h_price_per_million: '2',
		media_pricing: { token_rates: { image: { input_per_million: '9' } }, future_slot: '4' }, effective_capabilities: { decisions: true, vision: true, feature_gates: { decisions: { available: true, mode: 'native', reason_code: null, pricing_available: true } } }, ...overrides };
}
function serve(rows: unknown[] = [model()], providers: unknown[] = [provider]) {
	calls.get.mockImplementation(async (path: string) => {
		if (path.endsWith('/native-catalog')) return catalog;
		if (path.endsWith('/providers')) return providers;
		if (path.endsWith('/models')) return rows;
		return [];
	});
}
async function openPricing() {
	await fireEvent.click(await screen.findByRole('button', { name: adminT('configuration.editPricing') }));
	return screen.getByRole('dialog', { name: adminT('configuration.editModelPricing') });
}
async function openCreation() {
	await screen.findByText(adminT('configuration.noModelsRegistered'));
	await fireEvent.click(screen.getByRole('button', { name: adminT('configuration.addModel') }));
	return screen.getByRole('dialog', { name: adminT('configuration.addModel') });
}
beforeEach(() => {
	vi.clearAllMocks(); initLocale('ko');
	auth.update(state => ({ ...state, token: 'token', projectId: 'project', userId: 'owner', sessionId: 'session', roles: [], isSystemAdmin: true }));
	authReady.set(true); projectSwitching.set(false);
	calls.post.mockResolvedValue({}); calls.patch.mockResolvedValue({}); serve();
});
afterEach(() => { cleanup(); initLocale('ko'); });

describe('native catalog registry', () => {
	it('loads bundled catalog with GET and exposes version, verification, official sources and Decisions', async () => {
		render(NativeCatalogPanel);
		await screen.findByText(t('catalog.version', { version: catalog.catalog_version }));
		await fireEvent.click(screen.getByRole('button', { name: `OpenAI · ${t('catalog.count', { filtered: 1, total: 1 })}` }));
		expect(screen.getByText(t('catalog.verified', { date: entry.verified_at }))).toBeTruthy();
		expect(screen.getByText(t('decisions.label'))).toBeTruthy();
		expect(screen.getAllByRole('link').every(link => link.getAttribute('href') === entry.source_urls[0] && link.getAttribute('rel') === 'noreferrer')).toBe(true);
		expect(calls.get).toHaveBeenCalledWith('/api/v1/chat/admin/models/native-catalog', 'token', 'project', expect.objectContaining({ cache: 'no-store', signal: expect.any(AbortSignal) }));
		expect(calls.post).not.toHaveBeenCalled(); expect(calls.patch).not.toHaveBeenCalled();
	});

	it.each([[], {}, { schema_version: 1, catalog_version: '', providers: [] }])('shows catalog failure instead of raw provenance placeholders for invalid response %j', async (response) => {
		calls.get.mockResolvedValue(response);
		render(NativeCatalogPanel);
		await screen.findByText(t('catalog.error'));
		expect(document.body.textContent).not.toMatch(/\{\w+\}/);
		expect(screen.queryByText(t('catalog.empty'))).toBeNull();
		expect(calls.patch).not.toHaveBeenCalled();
	});

	it('clears every stored price slot explicitly without storing native_catalog provenance', async () => {
		render(ChatConfiguration, { section: 'models' });
		const dialog = await openPricing();
		await fireEvent.click(within(dialog).getByRole('button', { name: t('price.follow') }));
		expect(calls.patch).toHaveBeenCalledTimes(1);
		expect(calls.patch).toHaveBeenCalledWith('/api/v1/chat/admin/models/7', { ...FOLLOW_NATIVE_CATALOG_PRICES }, 'token', 'project');
		expect(Object.keys(calls.patch.mock.calls[0][1])).toHaveLength(6);
		await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
	});

	it.each([
		{ kind: 'image', pricing: { billing_basis: 'unit', image_per_unit: '0.04' }, field: 'image_per_unit', rate: '0.04' },
		{ kind: 'stt', pricing: { billing_basis: 'duration', audio_input_per_minute: '0.006' }, field: 'audio_input_per_minute', rate: '0.006' }
	])('displays effective catalog $kind media prices while editor keeps stored rates unset', async ({ kind, pricing, field, rate }) => {
		serve([model({ model_kind: kind, media_pricing: null, effective_media_pricing: pricing, price_origin: 'native_catalog' })]);
		render(ChatConfiguration, { section: 'models' });
		await screen.findByText(adminT('configuration.mediaRatesConfigured'));
		const summary = screen.getByTestId('model-media-prices');
		expect(summary.textContent).toContain(rate);
		expect(summary.textContent).not.toContain(adminT('configuration.rateUnset'));
		const dialog = await openPricing();
		expect((dialog.querySelector(`#model-edit-${field}`) as HTMLInputElement).value).toBe('');
		expect(calls.patch).not.toHaveBeenCalled();
	});

	it('reports ready catalog-priced token images without creating manual rates', async () => {
		serve([model({
			model_name: 'gpt-image-2.6-sunburst', model_kind: 'image', price_origin: 'native_catalog', media_pricing: null,
			effective_media_pricing: { billing_basis: 'tokens', reservation_usd: '0.8', token_rates: { image: { input_per_million: '8', output_per_million: '30' } } },
			effective_capabilities: { feature_gates: { image_output: { available: true, mode: 'native', pricing_available: true } } }
		})]);
		render(ChatConfiguration, { section: 'models' });
		await screen.findByText(t('price.nativeCatalog'));
		expect(screen.queryByText(t('price.unpriced'))).toBeNull();
		expect(screen.getByTestId('model-media-prices').textContent).toContain('30');
		expect(calls.patch).not.toHaveBeenCalled();
	});

	it('treats an explicit null effective media price as unpriced rather than showing stored rates', async () => {
		serve([model({ model_kind: 'image', media_pricing: { image_per_unit: '0.04' }, effective_media_pricing: null })]);
		render(ChatConfiguration, { section: 'models' });
		await screen.findByText(adminT('configuration.mediaRatesUnset'));
		expect(screen.getByTestId('model-media-prices').textContent).toContain(adminT('configuration.rateUnset'));
	});

	it('never offers catalog-follow for compatible routes, even for an official-looking model name', async () => {
		serve([model({ provider_family: 'compatible' })], [{ ...provider, provider_family: 'compatible', api_base: 'https://compatible.example/custom/v1' }]);
		render(ChatConfiguration, { section: 'models' });
		await openPricing();
		expect(screen.queryByRole('button', { name: t('price.follow') })).toBeNull();
		expect(calls.patch).not.toHaveBeenCalled();
	});

	it('keeps unknown catalog-follow writes single-attempt', async () => {
		calls.patch.mockRejectedValue(new Error('lost response'));
		render(ChatConfiguration, { section: 'models' });
		const dialog = await openPricing();
		await fireEvent.click(within(dialog).getByRole('button', { name: t('price.follow') }));
		await waitFor(() => expect((within(dialog).getByRole('button', { name: t('price.follow') }) as HTMLButtonElement).disabled).toBe(true));
		expect(calls.patch).toHaveBeenCalledTimes(1);
	});

	it('discards catalog reads after synchronous owner A-B-A', async () => {
		const pending = Promise.withResolvers<NativeCatalog>(); calls.get.mockReturnValue(pending.promise);
		render(NativeCatalogPanel); await waitFor(() => expect(calls.get).toHaveBeenCalledTimes(1));
		auth.update(state => ({ ...state, userId: 'other' })); auth.update(state => ({ ...state, userId: 'owner' }));
		calls.get.mockResolvedValue({ ...catalog, catalog_version: 'fresh' }); await tick();
		pending.resolve(catalog);
		await screen.findByText(t('catalog.version', { version: 'fresh' }));
		expect(screen.queryByText(t('catalog.version', { version: catalog.catalog_version }))).toBeNull();
	});

	it.each(['owner', 'authority', 'readiness', 'switching'] as const)('drops follow completion after %s A-B-A without replay', async (change) => {
		const pending = Promise.withResolvers<unknown>(); calls.patch.mockReturnValue(pending.promise);
		render(ChatConfiguration, { section: 'models' }); const dialog = await openPricing();
		await fireEvent.click(within(dialog).getByRole('button', { name: t('price.follow') }));
		if (change === 'owner') { auth.update(state => ({ ...state, userId: 'other' })); auth.update(state => ({ ...state, userId: 'owner' })); }
		if (change === 'authority') { auth.update(state => ({ ...state, isSystemAdmin: false })); auth.update(state => ({ ...state, isSystemAdmin: true })); }
		if (change === 'readiness') { authReady.set(false); authReady.set(true); }
		if (change === 'switching') { projectSwitching.set(true); projectSwitching.set(false); }
		pending.resolve({}); await tick(); await tick();
		expect(calls.patch).toHaveBeenCalledTimes(1); expect(calls.success).not.toHaveBeenCalled();
		expect(screen.queryByRole('dialog')).toBeNull();
	});

	it('saves Decisions as capability without sending derived gates', async () => {
		serve([model({ capabilities: { decisions: true, vision: true, prompt_caching: true, structured_output: true, web_search: false } })]);
		render(ChatConfiguration, { section: 'models' });
		await fireEvent.click(await screen.findByRole('button', { name: adminT('configuration.editCapabilities') }));
		const checkbox = screen.getByRole('checkbox', { name: t('decisions.label') });
		expect((checkbox as HTMLInputElement).checked).toBe(true);
		await fireEvent.click(checkbox);
		await fireEvent.click(screen.getByRole('button', { name: adminT('configuration.saveCapabilities') }));
		expect(calls.patch.mock.calls[0][1].capabilities).toMatchObject({ decisions: false, vision: true, prompt_caching: true, structured_output: true, web_search: false });
		expect(calls.patch.mock.calls[0][1].capabilities).not.toHaveProperty('feature_gates');
	});

	it('activates the exact native discovered model with catalog prices, not copied stored rates', async () => {
		calls.get.mockImplementation(async (path: string) => {
			if (path.endsWith('/native-catalog')) return catalog;
			if (path.endsWith('/providers')) return [provider];
			if (path.endsWith('/available-models')) return { provider_id: 1, fetched_at: '', live_status: 'success', source: 'api', complete: true, error: null,
				models: [entry.id], candidates: [{ id: entry.id, model_kind: 'text', purpose: 'chat', provider_family: 'native', requires_manual_pricing: false,
					token_pricing: entry.token_pricing, media_pricing: null, capabilities: entry.capabilities, verified_at: entry.verified_at, catalog_version: catalog.catalog_version, catalog_entry: entry }] };
			return [];
		});
		render(ChatConfiguration, { section: 'models' }); const dialog = await openCreation();
		await fireEvent.click(within(dialog).getByRole('button', { name: adminT('configuration.loadModels') }));
		await fireEvent.click(await within(dialog).findByRole('checkbox', { name: entry.id }));
		await fireEvent.click(within(dialog).getByRole('button', { name: adminT('configuration.reviewSelectedModels') }));
		const activate = within(dialog).getByRole('button', { name: adminT('configuration.confirmPricingRegisterAndActivate') }) as HTMLButtonElement;
		expect(activate.disabled).toBe(false);
		await fireEvent.input(document.querySelector('#review-name-0')!, { target: { value: 'not-the-catalog-model' } });
		expect(activate.disabled).toBe(true);
		await fireEvent.input(document.querySelector('#review-name-0')!, { target: { value: entry.id } });
		await fireEvent.click(activate);
		expect(calls.post).toHaveBeenCalledWith('/api/v1/chat/admin/models', { provider_id: 1, model_name: entry.id, model_kind: 'text', is_active: true }, 'token', 'project');
	});
});

describe('compatible API registration', () => {
	it('offers only four native protocols, two subscriptions and two explicit compatible paths', async () => {
		render(ChatConfiguration, { section: 'providers' });
		const select = screen.getByRole('combobox', { name: adminT('configuration.connectionMethod') }) as HTMLSelectElement;
		expect([...select.options].map(option => option.value)).toEqual(['openai', 'anthropic', 'gemini', 'perplexity', 'chatgpt-subscription', 'claude-subscription', 'openai-compatible', 'anthropic-compatible']);
		await fireEvent.input(screen.getByRole('textbox', { name: adminT('configuration.name') }), { target: { value: 'Compatible fixture' } });
		await fireEvent.change(select, { target: { value: 'anthropic-compatible' } });
		await fireEvent.click(screen.getByRole('button', { name: adminT('configuration.addProvider') }));
		expect(calls.post).not.toHaveBeenCalled();
		expect(screen.getByRole('textbox', { name: t('compatible.baseUrl') }).getAttribute('aria-invalid')).toBe('true');
		await fireEvent.input(screen.getByRole('textbox', { name: t('compatible.baseUrl') }), { target: { value: 'https://compatible.example/proxy/claude/v1' } });
		await fireEvent.click(screen.getByRole('button', { name: adminT('configuration.addProvider') }));
		expect(calls.post).toHaveBeenCalledWith('/api/v1/chat/admin/providers', expect.objectContaining({ provider_type: 'anthropic', auth_mode: 'api_key', api_base: 'https://compatible.example/proxy/claude/v1' }), 'token', 'project');
	});

	it('requires manual input and output rates before compatible manual registration', async () => {
		serve([], [{ ...provider, provider_family: 'compatible', api_base: 'https://compatible.example/v1' }]);
		render(ChatConfiguration, { section: 'models' }); const dialog = await openCreation();
		await fireEvent.click(within(dialog).getByRole('button', { name: adminT('configuration.manualModelMethod') }));
		await fireEvent.input(within(dialog).getByPlaceholderText(adminT('configuration.modelNameEGGpt4o')), { target: { value: 'gpt-6-luna' } });
		await fireEvent.click(within(dialog).getByRole('button', { name: adminT('configuration.addModel') }));
		expect(calls.post).not.toHaveBeenCalled();
		expect(within(dialog).getByRole('textbox', { name: adminT('configuration.input') }).getAttribute('aria-invalid')).toBe('true');
		await fireEvent.input(within(dialog).getByRole('textbox', { name: adminT('configuration.input') }), { target: { value: '0' } });
		await fireEvent.input(within(dialog).getByRole('textbox', { name: adminT('configuration.output') }), { target: { value: '2.0001' } });
		await fireEvent.click(within(dialog).getByRole('button', { name: adminT('configuration.addModel') }));
		expect(calls.post).toHaveBeenCalledWith('/api/v1/chat/admin/models', expect.objectContaining({ input_price_per_million: '0', output_price_per_million: '2.0001' }), 'token', 'project');
	});

	it('requires manual rates for compatible inactive discovery registration too', async () => {
		calls.get.mockImplementation(async (path: string) => {
			if (path.endsWith('/native-catalog')) return catalog;
			if (path.endsWith('/providers')) return [{ ...provider, provider_family: 'compatible', api_base: 'https://compatible.example/v1' }];
			if (path.endsWith('/available-models')) return { provider_id: 1, fetched_at: '', live_status: 'success', source: 'api', complete: true, error: null,
				models: [entry.id], candidates: [{ id: entry.id, model_kind: 'text', purpose: 'chat', provider_family: 'compatible', requires_manual_pricing: true }] };
			return [];
		});
		render(ChatConfiguration, { section: 'models' }); const dialog = await openCreation();
		await fireEvent.click(within(dialog).getByRole('button', { name: adminT('configuration.loadModels') }));
		await fireEvent.click(await within(dialog).findByRole('checkbox', { name: entry.id }));
		await fireEvent.click(within(dialog).getByRole('button', { name: adminT('configuration.reviewSelectedModels') }));
		const inactive = within(dialog).getByRole('button', { name: adminT('configuration.saveAsInactive') }) as HTMLButtonElement;
		expect(inactive.disabled).toBe(true);
		await fireEvent.input(document.querySelector('#review-input-0')!, { target: { value: '1.00001' } });
		expect(inactive.disabled).toBe(true);
		await fireEvent.input(document.querySelector('#review-output-0')!, { target: { value: '0' } });
		expect(inactive.disabled).toBe(false);
		await fireEvent.click(inactive);
		expect(calls.post).toHaveBeenCalledWith('/api/v1/chat/admin/models', { provider_id: 1, model_name: entry.id, model_kind: 'text', input_price_per_million: '1.00001', output_price_per_million: '0', is_active: false }, 'token', 'project');
	});

	it('blocks compatible activation when only effective catalog-like prices exist', async () => {
		serve([model({ provider_family: 'compatible', input_price_per_million: null, output_price_per_million: null })], [{ ...provider, provider_family: 'compatible' }]);
		render(ChatConfiguration, { section: 'models' });
		await fireEvent.click(await screen.findByRole('button', { name: adminT('configuration.activate') }));
		expect(calls.patch).not.toHaveBeenCalled(); expect(calls.error).toHaveBeenCalledWith(t('compatible.requiredRates'));
	});
});

it.each(['ko', 'en', 'ja', 'zh-CN', 'bn', 'ms', 'nb', 'sw', 'vi'] as const)('provides native registry copy and Decisions badge in %s', (locale) => {
	initLocale(locale); render(ModelCapabilityBadges, { caps: { decisions: true } });
	expect(screen.getByText(t('decisions.label'))).toBeTruthy();
	expect(t('catalog.version', { version: 'fixture' })).toContain('fixture');
	expect(t('catalog.verified', { date: 'date' })).toContain('date');
	expect(t('compatible.help')).not.toMatch(/compatible\.help|\{\w+\}/);
});

it('rejects unsafe catalog navigation URLs', () => {
	for (const value of ['javascript:alert(1)', 'http://example.com', 'https://user:password@example.com', 'bad-url']) expect(catalogSourceUrl(value)).toBeUndefined();
	expect(catalogSourceUrl(entry.source_urls[0])).toBe(entry.source_urls[0]);
});
