import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { writable } from 'svelte/store';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/native-providers';
import { t as adminT } from '$lib/i18n/ns/admin-chat';
import { t as commonT } from '$lib/i18n/ns/common';
import type { NativeCatalog, NativeCatalogEntry, NativeMediaPricing, NativeMediaRateKey } from '$lib/api/nativeCatalog';
import ko from '$lib/i18n/messages/ko/native-providers.json';
import en from '$lib/i18n/messages/en/native-providers.json';
import ja from '$lib/i18n/messages/ja/native-providers.json';
import zh from '$lib/i18n/messages/zh-CN/native-providers.json';
import bn from '$lib/i18n/messages/bn/native-providers.json';
import ms from '$lib/i18n/messages/ms/native-providers.json';
import nb from '$lib/i18n/messages/nb/native-providers.json';
import sw from '$lib/i18n/messages/sw/native-providers.json';
import viCopy from '$lib/i18n/messages/vi/native-providers.json';

const mocks = vi.hoisted(() => ({ get: vi.fn(), desktop: true }));
vi.mock('$lib/api/client', () => ({ api: { get: mocks.get } }));
vi.mock('$lib/utils/tableBreakpoint', () => ({ tableDesktop: { get current() { return mocks.desktop; } } }));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token', projectId: 'project', userId: 'owner', sessionId: 'session', roles: [], isSystemAdmin: true }),
	authReady: writable(true), projectSwitching: writable(false)
}));
import NativeCatalogPanel from '../NativeCatalogPanel.svelte';
import NativeCatalogPricing from '../NativeCatalogPricing.svelte';

const entry: NativeCatalogEntry = {
	id: 'model-0', display_name: 'Model zero', aliases: [], kind: 'text', status: 'active', context_window: 1000000, max_output_tokens: 8192,
	input_modalities: ['text', 'image'], output_modalities: ['text'], capabilities: { reasoning: true },
	token_pricing: {
		input: '0.10', output: '0.50', cache_read: '0.01', cache_write: '0.125', cache_write_ttl: '30m', cache_write_long: '0.25', cache_write_long_ttl: '12h',
		long_context: { threshold_tokens: 272000, input: '0.20', output: '0.75', cache_read: null, cache_write: '0.250', cache_write_long: '0.500' }
	},
	media_pricing: null, source_urls: ['https://example.com/pricing'], verified_at: '2026-11-17', notes: null
};
function catalog(models: NativeCatalogEntry[] = [entry]): NativeCatalog {
	return { schema_version: 1, catalog_version: 'fixture', providers: [{ provider_type: 'openai', display_name: 'OpenAI', pricing_sources: entry.source_urls, models }] };
}
async function openProvider(name = 'OpenAI') {
	const button = await screen.findByRole('button', { name: new RegExp(`^${name} · `) });
	await fireEvent.click(button);
	return button;
}
function noRawJson(container: HTMLElement) {
	expect(container.querySelector('pre')).toBeNull();
	expect(container.textContent).not.toMatch(/token_pricing|media_pricing|threshold_tokens|input_per_million|billing_basis|default_dimensions/);
}
beforeEach(() => { vi.clearAllMocks(); initLocale('ko'); mocks.desktop = true; mocks.get.mockResolvedValue(catalog()); });
afterEach(() => { cleanup(); initLocale('ko'); });

describe('bounded native catalog', () => {
	it('keeps all source-sized provider groups collapsed and model contents unmounted', async () => {
		const providers = [
			['openai', 'OpenAI', 69], ['anthropic', 'Anthropic', 18], ['gemini', 'Gemini', 34], ['perplexity', 'Perplexity', 29]
		] as const;
		const data: NativeCatalog = { schema_version: 1, catalog_version: 'fixture', providers: providers.map(([provider_type, display_name, count]) => ({
			provider_type, display_name, pricing_sources: entry.source_urls,
			models: Array.from({ length: count }, (_, index) => ({ ...entry, id: `${provider_type}-${index}`, display_name: `${display_name} fixture ${index}` }))
		})) };
		mocks.get.mockResolvedValue(data);
		render(NativeCatalogPanel);
		expect(await screen.findByText(t('catalog.count', { filtered: 150, total: 150 }))).toHaveProperty('textContent', t('catalog.count', { filtered: 150, total: 150 }));
		for (const [, name, count] of providers) expect(screen.getByRole('button', { name: `${name} · ${t('catalog.count', { filtered: count, total: count })}` }).getAttribute('aria-expanded')).toBe('false');
		expect(screen.queryAllByTestId('catalog-model')).toHaveLength(0);
		expect(screen.queryByTestId('catalog-token-pricing')).toBeNull();
		await openProvider();
		expect(screen.getAllByTestId('catalog-model')).toHaveLength(5);
		expect(screen.queryByText('Anthropic fixture 0')).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: /^OpenAI · / }));
		expect(screen.queryAllByTestId('catalog-model')).toHaveLength(0);
	});

	it('mounts only each provider page and resets paging on size or filters', async () => {
		const models = Array.from({ length: 12 }, (_, index) => ({ ...entry, id: `model-${index}`, display_name: `Named fixture ${index}` }));
		mocks.get.mockResolvedValue(catalog(models));
		render(NativeCatalogPanel); await openProvider();
		expect(screen.getAllByTestId('catalog-model')).toHaveLength(5);
		expect(screen.queryByText('model-5')).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: commonT('pagination.next') }));
		expect(screen.getByText('model-5')).toBeTruthy(); expect(screen.queryByText('model-0')).toBeNull();
		await fireEvent.change(screen.getByLabelText(t('catalog.pageSize')), { target: { value: '10' } });
		expect(screen.getAllByTestId('catalog-model')).toHaveLength(10); expect(screen.getByText('model-0')).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: commonT('pagination.next') }));
		expect(screen.getAllByTestId('catalog-model')).toHaveLength(2);
		await fireEvent.input(screen.getByLabelText(t('catalog.filter')), { target: { value: 'MODEL-11' } });
		expect(screen.getAllByTestId('catalog-model')).toHaveLength(1); expect(screen.getByText('model-11')).toBeTruthy();
		expect(screen.getByRole('status').textContent).toBe(t('catalog.count', { filtered: 1, total: 12 }));
		expect(screen.getByRole('button', { name: commonT('pagination.previous') }).hasAttribute('disabled')).toBe(true);
	});

	it('matches ID and display name as case-insensitive plain text and combines kind filters', async () => {
		mocks.get.mockResolvedValue(catalog([
			{ ...entry, id: 'model[5]', display_name: 'A special name', kind: 'image' },
			{ ...entry, id: 'model5', display_name: 'Other entry', kind: 'text' }
		]));
		render(NativeCatalogPanel); await openProvider();
		const search = screen.getByLabelText(t('catalog.filter'));
		await fireEvent.input(search, { target: { value: 'MODEL[5]' } });
		expect(screen.getByText('model[5]')).toBeTruthy(); expect(screen.queryByText('model5')).toBeNull();
		await fireEvent.input(search, { target: { value: ' SPECIAL NAME ' } });
		expect(screen.getByText('model[5]')).toBeTruthy();
		await fireEvent.change(screen.getByLabelText(t('catalog.kind')), { target: { value: 'text' } });
		expect(screen.queryAllByTestId('catalog-model')).toHaveLength(0); expect(screen.getByText(t('catalog.noMatches'))).toBeTruthy();
		expect(screen.getByRole('status').textContent).toBe(t('catalog.count', { filtered: 0, total: 2 }));
	});

	it('keeps pagination independent between expanded providers', async () => {
		const data = catalog(Array.from({ length: 7 }, (_, index) => ({ ...entry, id: `openai-${index}` })));
		data.providers.push({ ...data.providers[0], provider_type: 'anthropic', display_name: 'Anthropic', models: Array.from({ length: 6 }, (_, index) => ({ ...entry, id: `anthropic-${index}` })) });
		mocks.get.mockResolvedValue(data); render(NativeCatalogPanel); await openProvider(); await openProvider('Anthropic');
		const openai = screen.getByRole('region', { name: /^OpenAI · / });
		await fireEvent.click(within(openai).getByRole('button', { name: commonT('pagination.next') }));
		expect(screen.getByText('openai-5')).toBeTruthy(); expect(screen.getByText('anthropic-0')).toBeTruthy(); expect(screen.queryByText('anthropic-5')).toBeNull();
	});
});

describe('semantic published pricing', () => {
	it.each([true, false])('renders exact base and long-context rates with TTLs; desktop=%s', (desktop) => {
		mocks.desktop = desktop;
		const view = render(NativeCatalogPricing, { tokens: entry.token_pricing, media: null });
		const prices = screen.getByTestId('catalog-token-pricing');
		expect(within(prices).getByText(t('pricing.default'))).toBeTruthy();
		expect(within(prices).getByText(t('pricing.longContext', { threshold: 272000 }))).toBeTruthy();
		for (const value of ['0.10', '0.50', '0.01', '0.125', '0.25', '0.20', '0.75', '0.250', '0.500', '—']) expect(within(prices).getByText(value)).toBeTruthy();
		expect(prices.textContent).toContain('TTL 30m'); expect(prices.textContent).toContain('TTL 12h');
		expect(prices.textContent).toContain(adminT('configuration.usd1mTokens'));
		if (desktop) {
			const rows = within(prices).getAllByRole('row');
			expect(within(rows[1]).getAllByRole('cell').map(cell => cell.textContent)).toEqual(['0.10', '0.50', '0.01', '0.125', '0.25']);
			expect(within(rows[2]).getAllByRole('cell').map(cell => cell.textContent)).toEqual(['0.20', '0.75', '—', '0.250', '0.500']);
		} else expect(view.container.querySelector('table')).toBeNull();
		noRawJson(view.container);
	});

	it.each([true, false])('renders media modality rates, variants, basis and reservation; desktop=%s', (desktop) => {
		mocks.desktop = desktop;
		const media: NativeMediaPricing = {
			billing_basis: 'tokens', reservation_usd: '1.50', image_per_unit: '0.04', image_variants: { '1024x1024:high': '0.167' },
			token_rates: { image: { input_per_million: '8', output_per_million: '32', cache_read_per_million: '2' }, audio: { input_per_million: '10', output_per_million: '20' } }
		};
		const view = render(NativeCatalogPricing, { tokens: null, media });
		const prices = screen.getByTestId('catalog-media-pricing');
		for (const value of ['0.04', '0.167', '8', '32', '2', '10', '20', '—']) {
			expect(within(prices).getByText((_, element) => element?.tagName === (desktop ? 'TD' : 'DD') && element.firstChild?.textContent?.trim() === value)).toBeTruthy();
		}
		expect(prices.textContent).toContain('1.50 USD'); expect(prices.textContent).toContain(t('media.variant', { variant: '1024x1024:high' }));
		expect(within(prices).getByText(adminT('pricing.tokens'))).toBeTruthy();
		for (const modality of [adminT('configuration.image'), adminT('pricing.audio')]) {
			for (const direction of [adminT('configuration.input'), adminT('configuration.output'), adminT('configuration.cacheRead')]) expect(within(prices).getByText(adminT('pricing.modalityDirection', { modality, direction }))).toBeTruthy();
		}
		if (!desktop) expect(view.container.querySelector('table')).toBeNull();
		noRawJson(view.container);
	});

	const durationFields = (['audio_input', 'audio_output', 'realtime_input', 'realtime_output', 'realtime_session'] as const).flatMap(prefix => (['second', 'minute', 'hour'] as const).map(unit => ({ key: `${prefix}_per_${unit}` as NativeMediaRateKey, unit })));
	it.each(durationFields)('labels $key with its published time unit without converting', ({ key, unit }) => {
		render(NativeCatalogPricing, { tokens: null, media: { billing_basis: 'duration', [key]: '0.123456' } });
		const table = screen.getByRole('table', { name: t('pricing.media') });
		expect(within(table).getByText('0.123456')).toBeTruthy();
		expect(within(table).getByText(t('media.usdPerTime', { unit: adminT(`pricing.${unit}`) }))).toBeTruthy();
		expect(table.textContent).not.toContain(key);
	});

	it.each([
		{ key: 'audio_per_character', basis: 'characters', label: () => adminT('configuration.speechGenerationCharacterRate'), unit: () => adminT('configuration.usdPerCharacter') },
		{ key: 'audio_per_minute', basis: 'duration', label: () => `${t('media.audioInput')} · ${t('media.audioLegacy')}`, unit: () => t('media.usdPerTime', { unit: adminT('pricing.minute') }) },
		{ key: 'audio_per_second', basis: 'duration', label: () => `${t('media.audioOutput')} · ${t('media.audioLegacy')}`, unit: () => t('media.usdPerTime', { unit: adminT('pricing.second') }) }
	] as const)('labels $key without exposing raw JSON keys', ({ key, basis, label, unit }) => {
		render(NativeCatalogPricing, { tokens: null, media: { billing_basis: basis, [key]: '0' } });
		expect(screen.getByRole('rowheader', { name: label() })).toBeTruthy(); expect(screen.getByText(unit())).toBeTruthy(); expect(screen.getByRole('cell', { name: '0' })).toBeTruthy();
	});

	it('never invents missing reservations or treats null as zero', () => {
		render(NativeCatalogPricing, { tokens: { input: '0', output: null }, media: { billing_basis: 'tokens', token_rates: { image: { input_per_million: '8' } } } });
		expect(screen.queryByText(adminT('pricing.reservationCap'))).toBeNull(); expect(screen.getAllByText('—').length).toBeGreaterThan(0); expect(screen.getByText('0')).toBeTruthy();
	});
});

describe('catalog metadata and localization', () => {
	it('shows preview and deprecated statuses as localized pills and complete embedding metadata', async () => {
		mocks.get.mockResolvedValue(catalog([
			{ ...entry, id: 'embedding-preview', kind: 'embedding', status: 'preview', embedding: { default_dimensions: 3072, supports_dimensions: true, min_dimensions: 256, max_dimensions: 3072, allowed_dimensions: [256, 1024, 3072] } },
			{ ...entry, id: 'embedding-deprecated', kind: 'embedding', status: 'deprecated', embedding: { default_dimensions: 1536, supports_dimensions: false, min_dimensions: 1536, max_dimensions: 1536, allowed_dimensions: null } }
		]));
		const view = render(NativeCatalogPanel); await openProvider();
		for (const status of ['preview', 'deprecated'] as const) expect(screen.getByText(t(`status.${status}`)).classList.contains('pill')).toBe(true);
		const metadata = screen.getAllByTestId('catalog-embedding');
		for (const key of ['embedding.default', 'embedding.adjustable', 'embedding.range', 'embedding.choices'] as const) expect(within(metadata[0]).getByText(t(key))).toBeTruthy();
		expect(within(metadata[0]).getByText('3072')).toBeTruthy(); expect(within(metadata[0]).getByText('256 – 3072')).toBeTruthy(); expect(within(metadata[0]).getByText('256, 1024, 3072')).toBeTruthy(); expect(within(metadata[0]).getByText(t('embedding.yes'))).toBeTruthy();
		expect(within(metadata[1]).getByText(t('embedding.no'))).toBeTruthy(); expect(within(metadata[1]).getByText('—')).toBeTruthy();
		noRawJson(view.container);
	});

	it.each([
		['ko', ko], ['en', en], ['ja', ja], ['zh-CN', zh], ['bn', bn], ['ms', ms], ['nb', nb], ['sw', sw], ['vi', viCopy]
	] as const)('renders native catalog labels and status text in %s with full locale-key parity', async (locale, copy) => {
		expect(Object.keys(copy).sort()).toEqual(Object.keys(ko).sort());
		for (const key of Object.keys(ko) as (keyof typeof ko)[]) {
			expect(copy[key].trim()).not.toBe('');
			expect(copy[key].match(/\{\w+\}/g) ?? []).toEqual(ko[key].match(/\{\w+\}/g) ?? []);
		}
		initLocale(locale);
		mocks.get.mockResolvedValue(catalog([{ ...entry, status: 'preview', embedding: { default_dimensions: 3072, supports_dimensions: true, min_dimensions: 256, max_dimensions: 3072, allowed_dimensions: null } }, { ...entry, id: 'old-model', status: 'deprecated' }]));
		render(NativeCatalogPanel); await openProvider();
		for (const key of ['catalog.filter', 'catalog.kind', 'catalog.pageSize', 'status.preview', 'status.deprecated', 'embedding.default', 'embedding.range'] as const) expect(screen.getByText(copy[key])).toBeTruthy();
		expect(screen.getAllByText(copy['pricing.longContext'].replace('{threshold}', '272000'))).toHaveLength(2);
	});
});
