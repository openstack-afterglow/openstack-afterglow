import { t } from '$lib/i18n/ns/admin-chat';
export type ModelKind = 'text' | 'image' | 'tts' | 'stt' | 'realtime' | 'embedding' | 'decision';
export type BillingBasis = 'unit' | 'duration' | 'characters' | 'tokens' | 'session';
export type TimeUnit = 'second' | 'minute' | 'hour';
export type MediaPricing = Record<string, unknown> & {
	billing_basis?: BillingBasis;
	reservation_usd?: string;
	image_variants?: Record<string, string>;
	token_rates?: Record<string, Record<string, unknown>>;
	override_mode?: 'leaf' | 'replace';
};
export const MODEL_LABELS: Record<ModelKind, string> = {
	get text() { return t('configuration.text'); },
	get image() { return t('configuration.image'); },
	get tts() { return t('configuration.speechGenerationTts'); },
	get stt() { return t('configuration.speechRecognitionStt'); },
	get realtime() { return t('configuration.realtimeAudio'); },
	get embedding() { return t('configuration.embedding'); },
	get decision() { return t('configuration.decision'); }
};
/** Lumen may add kinds this build cannot price; unknown values must never reach labels or request payloads. */
export function knownModelKind(value: unknown): ModelKind | null {
	return typeof value === 'string' && Object.hasOwn(MODEL_LABELS, value) ? value as ModelKind : null;
}
export function modelKindLabel(value: unknown): string {
	const kind = knownModelKind(value);
	return kind ? MODEL_LABELS[kind] : t('pricing.unknownKind');
}
export function inputTokenOnly(kind: ModelKind | '' | undefined): boolean {
	return kind === 'embedding' || kind === 'decision';
}
export const TOKEN_FIELDS = [
	{ key: 'input_per_million', get label() { return t('configuration.input'); } },
	{ key: 'cache_read_per_million', get label() { return t('pricing.cacheInput'); } },
	{ key: 'output_per_million', get label() { return t('configuration.output'); } }
] as const;
export const RATE_KEYS = [
	'image_per_unit', 'audio_per_character', 'audio_per_second', 'audio_per_minute',
	...['audio', 'realtime'].flatMap((prefix) => ['input', 'output'].flatMap((direction) => ['second', 'minute', 'hour'].map((unit) => `${prefix}_${direction}_per_${unit}`))),
	...['second', 'minute', 'hour'].map((unit) => `realtime_session_per_${unit}`),
	'reservation_usd'
];
export function hasMediaPrices(pricing?: MediaPricing | null): boolean {
	return !!pricing && (RATE_KEYS.some((key) => key !== 'reservation_usd' && pricing[key] !== null && pricing[key] !== undefined && pricing[key] !== '') || Object.keys(pricing.image_variants ?? {}).length > 0 || ['image', 'audio'].some((modality) => TOKEN_FIELDS.some(({ key }) => pricing.token_rates?.[modality]?.[key] !== null && pricing.token_rates?.[modality]?.[key] !== undefined && pricing.token_rates?.[modality]?.[key] !== '')));
}
export interface PricingDraft {
	basis: string;
	rates: Record<string, string>;
	tokens: Record<'image' | 'audio', Record<string, string>>;
	variants: { id: number; name: string; price: string }[];
	inputUnit: TimeUnit;
	outputUnit: TimeUnit;
	sessionUnit: TimeUnit;
}
export function pricingDraft(pricing?: MediaPricing | null): PricingDraft {
	const unit = (direction: string): TimeUnit => ['hour', 'minute', 'second'].find((u) =>
		['audio', 'realtime'].some((prefix) => pricing?.[`${prefix}_${direction}_per_${u}`] != null)) as TimeUnit ?? 'minute';
	return {
		basis: pricing?.billing_basis ?? '',
		rates: Object.fromEntries(RATE_KEYS.map((key) => [key, pricing?.[key] == null ? '' : String(pricing[key])])),
		tokens: Object.fromEntries(['image', 'audio'].map((modality) => [modality, Object.fromEntries(TOKEN_FIELDS.map(({ key }) => [key, pricing?.token_rates?.[modality]?.[key] == null ? '' : String(pricing.token_rates[modality][key])]))])) as PricingDraft['tokens'],
		variants: Object.entries(pricing?.image_variants ?? {}).map(([name, price], id) => ({ id, name, price: String(price) })),
		inputUnit: unit('input'), outputUnit: unit('output'), sessionUnit: unit('session')
	};
}
const DECIMAL = /^(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?$/;
const ZERO = /^(?:0+(?:\.0*)?|\.0+)(?:[eE][+-]?\d+)?$/;
export function effectiveBasis(kind: ModelKind, draft: PricingDraft): string {
	return kind === 'text' || inputTokenOnly(kind) ? 'tokens' : draft.basis || (kind === 'image' ? 'unit' : 'duration');
}
export function pricingError(kind: ModelKind, draft: PricingDraft): string | undefined {
	if (inputTokenOnly(kind)) return;
	for (const value of [...Object.values(draft.rates), ...Object.values(draft.tokens.image), ...Object.values(draft.tokens.audio)]) {
		if (value.trim() && !DECIMAL.test(value.trim())) return t('pricing.decimalError');
	}
	if (kind !== 'text' && effectiveBasis(kind, draft) === 'tokens' && (!draft.rates.reservation_usd.trim() || ZERO.test(draft.rates.reservation_usd.trim()))) return t('pricing.reservationError');
	if (draft.variants.length > 500) return t('pricing.variantLimit');
	const names = new Set<string>();
	for (const row of draft.variants) {
		const name = row.name.trim(), price = row.price.trim();
		if (!/^[1-9][0-9]*x[1-9][0-9]*:[A-Za-z][A-Za-z0-9_-]*$/.test(name) || !DECIMAL.test(price) || names.has(name)) return t('pricing.variantError');
		names.add(name);
	}
}
/** Merge only edited leaves: hidden units, other billing bases and unknown server keys survive. */
export function pricingPayload(kind: ModelKind, draft: PricingDraft, baseline?: MediaPricing | null): MediaPricing | null {
	// Input-only models never send hidden media drafts.
	if (inputTokenOnly(kind)) return null;
	const before = pricingDraft(baseline);
	const result: MediaPricing = JSON.parse(JSON.stringify(baseline ?? {}));
	if (draft.basis !== before.basis) {
		if (draft.basis) result.billing_basis = draft.basis as BillingBasis;
		else delete result.billing_basis;
	}
	for (const key of RATE_KEYS) {
		const value = draft.rates[key].trim();
		if (value === before.rates[key]) continue;
		if (value) result[key] = value;
		else delete result[key];
	}
	let tokensChanged = false;
	for (const modality of ['image', 'audio'] as const) {
		let modalityChanged = false;
		for (const { key } of TOKEN_FIELDS) {
			const value = draft.tokens[modality][key].trim();
			if (value === before.tokens[modality][key]) continue;
			modalityChanged = true;
			tokensChanged = true;
			result.token_rates ??= {};
			result.token_rates[modality] ??= {};
			if (value) result.token_rates[modality][key] = value;
			else delete result.token_rates[modality][key];
		}
		if (modalityChanged && result.token_rates?.[modality] && !Object.keys(result.token_rates[modality]).length) delete result.token_rates[modality];
	}
	if (tokensChanged && result.token_rates && !Object.keys(result.token_rates).length) delete result.token_rates;
	const variants = Object.fromEntries(draft.variants.map((row) => [row.name.trim(), row.price.trim()]));
	if (!pricingEquals(variants, baseline?.image_variants ?? {})) {
		if (Object.keys(variants).length) result.image_variants = variants;
		else delete result.image_variants;
	}
	return Object.keys(result).length ? result : null;
}
export function pricingEquals(a: unknown, b: unknown): boolean {
	if (a === b) return true;
	if (!a || !b || typeof a !== 'object' || typeof b !== 'object') return false;
	const left = a as Record<string, unknown>, right = b as Record<string, unknown>;
	return Object.keys(left).length === Object.keys(right).length && Object.keys(left).every((key) => Object.hasOwn(right, key) && pricingEquals(left[key], right[key]));
}

export const IMAGE_TEXT_FIELDS = [
	{ key: 'input_price_per_million', get label() { return t('configuration.input'); } },
	{ key: 'cache_read_price_per_million', get label() { return t('pricing.cacheInput'); } }
] as const;
type ImageTextKey = (typeof IMAGE_TEXT_FIELDS)[number]['key'];
type TokenKey = (typeof TOKEN_FIELDS)[number]['key'];
type ImageTextPrices = Partial<Record<ImageTextKey, string | null>>;
type ImageRateKey = 'image_per_unit' | 'reservation_usd';

/** Null is inherited; an empty manual draft can be typed before blur restores inheritance. */
export interface ImagePriceLeaf {
	manual: string | null;
	official: string | null;
}

interface ImageVariantDraft {
	id: number;
	name: string;
	rate: ImagePriceLeaf;
}

export interface ImagePricingDraft {
	stored: MediaPricing | null;
	storedText: ImageTextPrices;
	legacy: boolean;
	convert: boolean;
	basis: ImagePriceLeaf;
	text: Record<ImageTextKey, ImagePriceLeaf>;
	rates: Record<ImageRateKey, ImagePriceLeaf>;
	tokens: Record<'image' | 'audio', Record<TokenKey, ImagePriceLeaf>>;
	variants: ImageVariantDraft[];
}

function priceLeaf(manual: unknown, official?: unknown): ImagePriceLeaf {
	return { manual: manual == null ? null : String(manual), official: official == null ? null : String(official) };
}

export function imagePricingDraft(
	stored?: MediaPricing | null,
	storedText?: ImageTextPrices | null,
	official?: MediaPricing | null,
	officialText?: ImageTextPrices | null
): ImagePricingDraft {
	function tokenLeaves(modality: 'image' | 'audio'): Record<TokenKey, ImagePriceLeaf> {
		return {
			input_per_million: priceLeaf(stored?.token_rates?.[modality]?.input_per_million, official?.token_rates?.[modality]?.input_per_million),
			cache_read_per_million: priceLeaf(stored?.token_rates?.[modality]?.cache_read_per_million, official?.token_rates?.[modality]?.cache_read_per_million),
			output_per_million: priceLeaf(stored?.token_rates?.[modality]?.output_per_million, official?.token_rates?.[modality]?.output_per_million)
		};
	}
	const variantNames = new Set([...Object.keys(stored?.image_variants ?? {}), ...Object.keys(official?.image_variants ?? {})]);
	return {
		stored: stored ?? null,
		storedText: storedText ?? {},
		legacy: stored != null && stored.override_mode !== 'leaf',
		convert: false,
		basis: priceLeaf(stored?.billing_basis, official?.billing_basis ?? (hasMediaPrices(official) ? 'unit' : null)),
		text: {
			input_price_per_million: priceLeaf(storedText?.input_price_per_million, officialText?.input_price_per_million),
			cache_read_price_per_million: priceLeaf(storedText?.cache_read_price_per_million, officialText?.cache_read_price_per_million)
		},
		rates: {
			image_per_unit: priceLeaf(stored?.image_per_unit, official?.image_per_unit),
			reservation_usd: priceLeaf(stored?.reservation_usd, official?.reservation_usd)
		},
		tokens: { image: tokenLeaves('image'), audio: tokenLeaves('audio') },
		variants: [...variantNames].map((name, id) => ({ id, name, rate: priceLeaf(stored?.image_variants?.[name], official?.image_variants?.[name]) }))
	};
}

export const imageFollowsMedia = (draft: ImagePricingDraft, useCatalog: boolean) => useCatalog && (!draft.legacy || draft.convert);
export const manualImagePrice = (field: ImagePriceLeaf) => field.manual?.trim() || null;
export const visibleImagePrice = (field: ImagePriceLeaf, follows: boolean) => field.manual ?? (follows ? field.official : null) ?? '';
const effectiveImagePrice = (field: ImagePriceLeaf, follows: boolean) => manualImagePrice(field) ?? (follows ? field.official : null);
export const imageBasis = (draft: ImagePricingDraft, useCatalog: boolean) => effectiveImagePrice(draft.basis, imageFollowsMedia(draft, useCatalog)) ?? 'unit';
export const imageVariants = (draft: ImagePricingDraft, follows: boolean) =>
	draft.variants.filter((row) => row.rate.official === null || follows || row.rate.manual !== null);

/** Lumen derives a bounded hold only for direct OpenAI image token billing. */
export function imageReservationDerived(providerType?: string | null): boolean {
	return providerType === 'openai';
}

export function imagePricingError(draft: ImagePricingDraft, useCatalog: boolean, providerType?: string | null): string | undefined {
	const follows = imageFollowsMedia(draft, useCatalog);
	const leaves = [...Object.values(draft.text), ...Object.values(draft.rates), ...Object.values(draft.tokens.image), ...Object.values(draft.tokens.audio)];
	if (leaves.some(({ manual }) => manual?.trim() && !DECIMAL.test(manual.trim()))) return t('pricing.decimalError');
	for (const rates of Object.values(draft.tokens)) {
		if (effectiveImagePrice(rates.cache_read_per_million, follows) !== null && effectiveImagePrice(rates.input_per_million, follows) === null) return t('pricing.cacheRequiresInput');
	}
	const reservation = effectiveImagePrice(draft.rates.reservation_usd, follows);
	if (imageBasis(draft, useCatalog) === 'tokens') {
		if (reservation === null ? !imageReservationDerived(providerType) : ZERO.test(reservation)) return t('pricing.reservationError');
	} else if (follows && draft.rates.reservation_usd.official !== null) {
		return t('pricing.imageUnitCatalogReservation');
	}
	const variants = imageVariants(draft, follows);
	if (variants.length > 500) return t('pricing.variantLimit');
	const names = new Set<string>();
	for (const { name, rate } of variants) {
		const key = name.trim(), value = effectiveImagePrice(rate, follows);
		if (!/^(auto|[1-9][0-9]*x[1-9][0-9]*):[A-Za-z0-9][A-Za-z0-9_-]*$/.test(key) || value === null || !DECIMAL.test(value) || names.has(key)) return t('pricing.variantError');
		names.add(key);
	}
}

/**
 * Client gate for obviously incomplete drafts only. Variant support is model-specific,
 * so activation readiness comes from Lumen's `image_pricing_readiness`.
 */
export function imagePricingReady(draft: ImagePricingDraft, useCatalog: boolean): boolean {
	const follows = imageFollowsMedia(draft, useCatalog);
	if (imageBasis(draft, useCatalog) === 'tokens') {
		return effectiveImagePrice(draft.text.input_price_per_million, useCatalog) !== null && effectiveImagePrice(draft.tokens.image.output_per_million, follows) !== null;
	}
	return imageVariants(draft, follows).some(({ rate }) => {
		const price = effectiveImagePrice(rate, follows);
		return price !== null && DECIMAL.test(price) && !ZERO.test(price);
	});
}

/** Lumen's server-side image readiness for saved pricing; credentials are not considered. */
export interface ImagePricingReadiness {
	ready: boolean;
	reason: string | null;
	executable_variants: string[];
	unsupported_variants: string[];
	supported_variants: string[];
}

export function imageReadinessMessage(readiness: ImagePricingReadiness | null | undefined): string | null {
	if (!readiness || readiness.ready) return null;
	switch (readiness.reason) {
		case 'pricing_unavailable': return t('pricing.imageReadinessPricing');
		case 'unsupported_image_variants': return t('pricing.imageReadinessVariants');
		case 'route_unavailable': return t('pricing.imageReadinessRoute');
		default: return t('pricing.imageReadinessUnknown');
	}
}

/** Compare against stored leaves, not rendered catalog suggestions. */
export function imagePricingPayload(draft: ImagePricingDraft, useCatalog: boolean): Record<string, unknown> {
	const body: Record<string, unknown> = {};
	const stored = draft.stored;
	for (const { key } of IMAGE_TEXT_FIELDS) {
		const value = manualImagePrice(draft.text[key]);
		if (value !== (draft.storedText[key] ?? null)) body[key] = value;
	}
	const patch: Record<string, unknown> = {};
	function change(key: string, value: string | null, previous: unknown, changes: Record<string, unknown>) {
		if (value !== (previous == null ? null : String(previous))) changes[key] = value;
	}
	change('billing_basis', manualImagePrice(draft.basis), stored?.billing_basis, patch);
	change('image_per_unit', manualImagePrice(draft.rates.image_per_unit), stored?.image_per_unit, patch);
	// Lumen rejects a reservation on unit billing. The draft keeps it while
	// switching, but saving unit billing clears any stored reservation.
	const reservation = imageBasis(draft, useCatalog) === 'tokens' ? manualImagePrice(draft.rates.reservation_usd) : null;
	change('reservation_usd', reservation, stored?.reservation_usd, patch);
	const tokens: Record<string, Record<string, unknown>> = {};
	for (const modality of ['image', 'audio'] as const) {
		const rates: Record<string, unknown> = {};
		for (const { key } of TOKEN_FIELDS) change(key, manualImagePrice(draft.tokens[modality][key]), stored?.token_rates?.[modality]?.[key], rates);
		if (Object.keys(rates).length) tokens[modality] = rates;
	}
	if (Object.keys(tokens).length) patch.token_rates = tokens;
	const variants = new Map(imageVariants(draft, imageFollowsMedia(draft, useCatalog)).map(({ name, rate }) => [name.trim(), manualImagePrice(rate)]));
	const variantPatch: Record<string, unknown> = {};
	for (const name of new Set([...Object.keys(stored?.image_variants ?? {}), ...variants.keys()])) {
		change(name, variants.get(name) ?? null, stored?.image_variants?.[name], variantPatch);
	}
	if (Object.keys(variantPatch).length) patch.image_variants = variantPatch;
	if (!Object.keys(patch).length && !draft.convert) return body;

	if (!draft.legacy || draft.convert) {
		// Lumen overlays leaf patches on any catalog entry for the model name. When this
		// form is not following that catalog, pin the basis it displays.
		if (!imageFollowsMedia(draft, useCatalog) && manualImagePrice(draft.basis) === null && stored?.billing_basis == null) {
			patch.billing_basis = imageBasis(draft, useCatalog);
		}
		body.media_pricing = { override_mode: 'leaf', ...patch };
	} else {
		// Never convert legacy replacement rows implicitly or drop unknown fields.
		const replaced = applyImagePriceChanges(stored ?? {}, patch);
		body.media_pricing = Object.keys(replaced).length ? replaced : null;
	}
	return body;
}

function applyImagePriceChanges(previous: Record<string, unknown>, patch: Record<string, unknown>): Record<string, unknown> {
	const result = { ...previous };
	for (const [key, value] of Object.entries(patch)) {
		if (value === null) delete result[key];
		else if (typeof value === 'object') {
			const merged = applyImagePriceChanges((previous[key] ?? {}) as Record<string, unknown>, value as Record<string, unknown>);
			if (Object.keys(merged).length) result[key] = merged;
			else delete result[key];
		} else result[key] = value;
	}
	return result;
}
