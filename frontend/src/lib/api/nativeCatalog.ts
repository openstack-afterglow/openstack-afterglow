import type { ModelCapabilities } from './chatContracts';
import type { BillingBasis, ModelKind, TimeUnit } from '$lib/components/admin/chat/modelPricing';

export type ProviderFamily = 'native' | 'compatible';
export type PriceOrigin = 'manual' | 'native_catalog' | 'catalog' | null;
export interface NativeCatalogSummary {
	id: string;
	kind?: ModelKind;
	status: 'active' | 'preview' | 'deprecated';
	verified_at: string;
	source_urls: string[];
}
export interface NativeTokenPricing {
	input?: string | null;
	output?: string | null;
	cache_read?: string | null;
	cache_write?: string | null;
	cache_write_ttl?: string | null;
	cache_write_long?: string | null;
	cache_write_long_ttl?: string | null;
	long_context?: {
		threshold_tokens: number;
		input?: string | null;
		output?: string | null;
		cache_read?: string | null;
		cache_write?: string | null;
		cache_write_long?: string | null;
	} | null;
}
export interface NativeEmbeddingMetadata {
	default_dimensions: number | null;
	supports_dimensions: boolean;
	min_dimensions: number | null;
	max_dimensions: number | null;
	allowed_dimensions: number[] | null;
}
export type NativeMediaRateKey =
	| 'image_per_unit'
	| 'audio_per_character'
	| 'audio_per_second'
	| 'audio_per_minute'
	| `${'audio' | 'realtime'}_${'input' | 'output'}_per_${TimeUnit}`
	| `realtime_session_per_${TimeUnit}`;
export type NativeMediaTokenRates = {
	input_per_million?: string;
	output_per_million?: string;
	cache_read_per_million?: string;
};
export type NativeMediaPricing = Partial<Record<NativeMediaRateKey, string>> & {
	billing_basis?: BillingBasis;
	reservation_usd?: string;
	image_variants?: Record<string, string>;
	token_rates?: Partial<Record<'image' | 'audio', NativeMediaTokenRates>>;
};
export interface NativeCatalogEntry extends NativeCatalogSummary {
	aliases: string[];
	kind: ModelKind;
	display_name: string;
	context_window: number | null;
	max_output_tokens: number | null;
	input_modalities: string[];
	output_modalities: string[];
	capabilities: ModelCapabilities;
	token_pricing: NativeTokenPricing | null;
	media_pricing: NativeMediaPricing | null;
	embedding?: NativeEmbeddingMetadata | null;
	notes: string | null;
}
export interface NativeCatalog {
	schema_version: 1;
	catalog_version: string;
	providers: {
		provider_type: 'openai' | 'anthropic' | 'gemini' | 'perplexity';
		display_name: string;
		pricing_sources: string[];
		models: NativeCatalogEntry[];
	}[];
}

/** Clear every public stored rate slot, including hidden media and cache rates. */
export const FOLLOW_NATIVE_CATALOG_PRICES = Object.freeze({
	input_price_per_million: null,
	output_price_per_million: null,
	cache_read_price_per_million: null,
	cache_write_price_per_million: null,
	cache_write_1h_price_per_million: null,
	media_pricing: null
});

/** Catalog links never permit script, credential-bearing, or non-HTTPS navigation. */
export function catalogSourceUrl(value: string): string | undefined {
	try {
		const url = new URL(value);
		return url.protocol === 'https:' && !url.username && !url.password ? url.href : undefined;
	} catch { return undefined; }
}
