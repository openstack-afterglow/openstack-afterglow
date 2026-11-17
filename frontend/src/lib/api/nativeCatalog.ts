import type { ModelCapabilities } from './chatContracts';
import type { MediaPricing, ModelKind } from '$lib/components/admin/chat/modelPricing';

export type ProviderFamily = 'native' | 'compatible';
export type PriceOrigin = 'manual' | 'native_catalog' | null;
export interface NativeCatalogSummary {
	id: string;
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
	media_pricing: MediaPricing | null;
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
