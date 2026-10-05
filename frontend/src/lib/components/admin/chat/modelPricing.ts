import { t } from '$lib/i18n/ns/admin-chat';
export type ModelKind = 'text' | 'image' | 'tts' | 'stt' | 'realtime';
export type BillingBasis = 'unit' | 'duration' | 'characters' | 'tokens' | 'session';
export type TimeUnit = 'second' | 'minute' | 'hour';
export type MediaPricing = Record<string, unknown> & {
	billing_basis?: BillingBasis;
	reservation_usd?: string;
	image_variants?: Record<string, string>;
	token_rates?: Record<string, Record<string, unknown>>;
};
export const MODEL_LABELS: Record<ModelKind, string> = {
	get text() { return t('configuration.text'); },
	get image() { return t('configuration.image'); },
	get tts() { return t('configuration.speechGenerationTts'); },
	get stt() { return t('configuration.speechRecognitionStt'); },
	get realtime() { return t('configuration.realtimeAudio'); }
};
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
	return kind === 'text' ? 'tokens' : draft.basis || (kind === 'image' ? 'unit' : 'duration');
}
export function pricingError(kind: ModelKind, draft: PricingDraft): string | undefined {
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
export function pricingPayload(draft: PricingDraft, baseline?: MediaPricing | null): MediaPricing | null {
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
