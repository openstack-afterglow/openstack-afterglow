<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-chat';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import RichText from '$lib/i18n/RichText.svelte';
	import { onDestroy, tick, untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { toast } from '$lib/stores/toast';
	import { invalidateChatModels } from '$lib/stores/chatModels';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import ChatExtensionsManager from '$lib/components/chat/ChatExtensionsManager.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import FormModal from '$lib/components/ui/FormModal.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';
	import ModelCapabilityBadges from '$lib/components/chat/ModelCapabilityBadges.svelte';
	import type { ModelCapabilities } from '$lib/api/chatContracts';
	import ModelMediaPricingEditor from './ModelMediaPricingEditor.svelte';
	import { MODEL_LABELS as MEDIA_LABELS, TOKEN_FIELDS, hasMediaPrices, pricingDraft, pricingError, pricingPayload, pricingEquals, type ModelKind, type MediaPricing } from './modelPricing';

	let { section = 'providers' }: { section?: 'providers' | 'models' | 'tools' } = $props();

	interface Provider {
		id: number;
		name: string;
		provider_type: string;
		api_provider: string;
		sort_order: number;
		api_base: string | null;
		auth_mode?: 'api_key' | 'chatgpt_device' | 'anthropic_subscription';
		has_credentials?: boolean;
		auth_status?: 'disconnected' | 'configured' | 'reauth_required';
		auth_expires_at?: string | null;
		has_api_key: boolean;
		models_dev_provider_id: string | null;
		is_active: boolean;
		margin_multiplier: number;
		billing_capability?: 'openrouter_key' | 'deepseek_balance' | 'openai_admin_usage' | 'anthropic_admin_usage' | null;
		has_billing_admin_key?: boolean;
	}

	interface ProviderBillingBalance {
		currency: string;
		total: string;
		granted: string;
		purchased: string;
	}

	interface ProviderBillingPeriods {
		daily: string;
		weekly: string;
		monthly: string;
		total: string;
	}

	interface ProviderBillingLocalUsage {
		currency: 'USD';
		requests: ProviderBillingPeriods;
		tokens: ProviderBillingPeriods;
		raw_cost: ProviderBillingPeriods;
	}

	interface ProviderBillingOptionalPeriods {
		daily: string | null;
		weekly: string | null;
		monthly: string | null;
		total: string | null;
	}

	interface ProviderBillingProviderUsage {
		source: 'openai_admin_usage' | 'anthropic_admin_usage';
		currency: 'USD';
		cost: ProviderBillingOptionalPeriods | null;
		requests: ProviderBillingOptionalPeriods | null;
		tokens: ProviderBillingOptionalPeriods | null;
	}

	interface ProviderBilling {
		provider_id: number;
		provider_name: string;
		provider_type: string;
		capability: 'openrouter_key' | 'deepseek_balance' | 'openai_admin_usage' | 'anthropic_admin_usage' | null;
		status: 'available' | 'unavailable' | 'unsupported';
		reason: string | null;
		fetched_at: string;
		billing_url: string | null;
		usage_url: string | null;
		has_billing_admin_key: boolean;
		local_usage: ProviderBillingLocalUsage;
		provider_usage: ProviderBillingProviderUsage | null;
		is_available: boolean | null;
		is_free_tier: boolean | null;
		limit: string | null;
		remaining: string | null;
		usage_total: string | null;
		usage_daily: string | null;
		usage_weekly: string | null;
		usage_monthly: string | null;
		balances: ProviderBillingBalance[];
	}

	type ProviderCreditState =
		| { kind: 'account_balance'; balances: ProviderBillingBalance[]; isAvailable: boolean | null }
		| { kind: 'api_key_limit'; limit: string | null; remaining: string | null; isFreeTier: boolean | null }
		| { kind: 'unavailable'; message: string }
		| { kind: 'unsupported'; message: string };

	interface ProviderChoice {
		value: string;
		label: string;
		providerType: string;
		authMode: 'api_key' | 'chatgpt_device' | 'anthropic_subscription';
	}

	// Form selection values are UI-only. Provider type and authentication mode are sent explicitly.
	let PROVIDER_TYPES: ProviderChoice[] = $derived([
		{ value: 'openai', label: t('configuration.openaiApiAndOpenaiCompatibleApis'), providerType: 'openai', authMode: 'api_key' },
		{ value: 'anthropic', label: 'Claude API', providerType: 'anthropic', authMode: 'api_key' },
		{ value: 'chatgpt-subscription', label: t('configuration.chatgptSubscriptionExperimental'), providerType: 'chatgpt', authMode: 'chatgpt_device' },
		{ value: 'claude-subscription', label: t('configuration.claudeSubscriptionExperimental'), providerType: 'anthropic', authMode: 'anthropic_subscription' },
		{ value: 'gemini', label: 'Google Gemini (AI Studio)', providerType: 'gemini', authMode: 'api_key' },
		{ value: 'vertex_ai', label: 'Google Vertex AI (GCP)', providerType: 'vertex_ai', authMode: 'api_key' },
		{ value: 'azure', label: 'Azure OpenAI', providerType: 'azure', authMode: 'api_key' },
		{ value: 'bedrock', label: 'AWS Bedrock', providerType: 'bedrock', authMode: 'api_key' },
		{ value: 'ollama', label: t('configuration.ollamaLocal'), providerType: 'ollama', authMode: 'api_key' },
		{ value: 'mistral', label: 'Mistral', providerType: 'mistral', authMode: 'api_key' },
		{ value: 'cohere', label: 'Cohere', providerType: 'cohere', authMode: 'api_key' },
		{ value: 'groq', label: 'Groq', providerType: 'groq', authMode: 'api_key' },
		{ value: 'deepseek', label: 'DeepSeek', providerType: 'deepseek', authMode: 'api_key' },
		{ value: 'together_ai', label: 'Together AI', providerType: 'together_ai', authMode: 'api_key' },
		{ value: 'openrouter', label: 'OpenRouter', providerType: 'openrouter', authMode: 'api_key' },
		{ value: 'perplexity', label: 'Perplexity (Agent API · Router · Sonar)', providerType: 'perplexity', authMode: 'api_key' },
		{ value: 'xai', label: 'xAI (Grok)', providerType: 'xai', authMode: 'api_key' }
	]);
	function mediaPriceSummary(model: Model): string {
		const pricing = model.media_pricing;
		const rates = Object.entries(pricing ?? {}).filter(([key, value]) => key !== 'token_rates' && key !== 'image_variants' && typeof value === 'string')
			.map(([key, value]) => `${key}: ${displayPrice(String(value))}`);
		const variants = Object.entries(pricing?.image_variants ?? {}).map(([name, price]) => t('configuration.usdImageAlternate', { v0: name, v1: displayPrice(price) }));
		const tokens = Object.entries(pricing?.token_rates ?? {}).flatMap(([modality, values]) => Object.entries(values).map(([key, value]) => `${modality === 'image' ? t('configuration.image') : modality === 'audio' ? t('pricing.audio') : modality} ${TOKEN_FIELDS.find((field) => field.key === key)?.label ?? key}: ${displayPrice(String(value))} ${t('configuration.usd1mTokens')}`));
		return [...rates, ...variants, ...tokens, ...(!hasMediaPrices(pricing) ? [t('configuration.rateUnset')] : [])].join(' · ');
	}
	function mediaReadiness(model: Model): string {
		const feature = model.model_kind === 'image' ? 'image_output' : model.model_kind === 'stt' ? 'audio_input' : 'audio_output';
		const gate = model.effective_capabilities?.feature_gates?.[feature];
		return gate?.reason_code === 'route_unavailable'
			? t('configuration.noExecutionPathCannotRun')
			: t('configuration.executionUnverifiedCheckExecutionPath', { v0: gate?.reason_code ? ` (${gate.reason_code})` : '' });
	}
	function mediaCapability(model: Model): string {
		const kind = model.model_kind ?? 'text';
		const features = kind === 'image' ? ['image_output'] : kind === 'stt' ? ['audio_input'] : kind === 'realtime' ? ['audio_input', 'audio_output'] : ['audio_output'];
		const names: Record<string, string> = { image_output: t('configuration.imageOutput'), audio_input: t('configuration.audioInput'), audio_output: t('configuration.audioOutput') };
		const priced = features.every((feature) => model.effective_capabilities?.feature_gates?.[feature]?.pricing_available === true);
		return `${features.map((feature) => names[feature]).join('·')} · ${priced ? t('configuration.rateShownForThisCapability') : t('configuration.rateUnverifiedForThisCapability')}`;
	}




	interface Model {
		id: number;
		provider_id: number;
		sort_order: number;
		model_name: string;
		api_model_name?: string;
		api_provider: string;
		display_name: string | null;
		is_active: boolean;
		model_kind?: ModelKind;
		media_pricing?: MediaPricing | null;
		is_title_model?: boolean;
		input_price_per_million: string | null;
		output_price_per_million: string | null;
		effective_input_price_per_million: string | null;
		effective_output_price_per_million: string | null;
		effective_price_source: 'manual' | 'models.dev' | 'litellm' | 'partial' | 'unpriced' | `perplexity_agent_api_${string}` | null;
		// Prompt-cache prices are manual-only (no catalog fallback). Absent/null means the
		// component is billed at 0 USD until an administrator sets it. Optional because an
		// older Lumen may not return them yet.
		cache_read_price_per_million?: string | null;
		cache_write_price_per_million?: string | null;
		cache_write_1h_price_per_million?: string | null;
		models_dev_model_id: string | null;
		price_source: 'manual' | 'models.dev' | null;
		capabilities?: ModelCapabilities | null;
		effective_capabilities?: ModelCapabilities | null;
		capability_source?: string | null;
		effective_capability_source?: string | null;
	}

	type CachePriceKey =
		| 'cache_read_price_per_million'
		| 'cache_write_price_per_million'
		| 'cache_write_1h_price_per_million';
	type CachePriceInputs = Record<CachePriceKey, string>;
	type CachePriceErrors = Partial<Record<CachePriceKey, string>>;
	type CachePriceValues = Record<CachePriceKey, string | null>;

	// Cache prices are optional and independent of each other and of text input/output rates.
	let CACHE_PRICE_FIELDS: { key: CachePriceKey; label: string; slug: string }[] = $derived([
		{ key: 'cache_read_price_per_million', label: t('configuration.cacheRead'), slug: 'read' },
		{ key: 'cache_write_price_per_million', label: t('configuration.cacheWriteFiveMinutes'), slug: 'write-5m' },
		{ key: 'cache_write_1h_price_per_million', label: t('configuration.cacheWriteOneHour'), slug: 'write-1h' }
	]);
	// Plain non-negative decimal; rejects exponent, hex, sign, Infinity/NaN. Lumen owns precision.
	const CACHE_PRICE_PATTERN = /^\d+(?:\.\d+)?$/;
	let CACHE_PRICE_ERROR = $derived(t('configuration.enterANumberGreaterThanOrEqualTo0'));

	function emptyCachePriceInputs(): CachePriceInputs {
		return {
			cache_read_price_per_million: '',
			cache_write_price_per_million: '',
			cache_write_1h_price_per_million: ''
		};
	}

	// Any all-zero decimal, including Python Decimal's scientific zero ("0E-10") that Lumen
	// serializes for a stored 0. Requires a zero digit so "", "." or "E5" never match.
	const ZERO_DECIMAL_PATTERN = /^[+-]?(?:0+(?:\.0*)?|\.0+)(?:E[+-]?\d+)?$/i;

	/** Only zero is emitted in scientific form, so a zero-only rule suffices; never float-converted. */
	function normalizeDecimalString(price: string): string {
		if (ZERO_DECIMAL_PATTERN.test(price.trim())) return '0';
		return formatPricePerMillion(price);
	}

	function cachePriceInputsFrom(model: Model): CachePriceInputs {
		// Strip storage trailing zeros ("0.3000000000" → "0.3", "0E-10" → "0") for readability; same decimal value.
		const prefill = (price: string | null | undefined) =>
			price === null || price === undefined || price === '' ? '' : normalizeDecimalString(price);
		return {
			cache_read_price_per_million: prefill(model.cache_read_price_per_million),
			cache_write_price_per_million: prefill(model.cache_write_price_per_million),
			cache_write_1h_price_per_million: prefill(model.cache_write_1h_price_per_million)
		};
	}

	function cachePriceError(raw: string): string | undefined {
		const value = raw.trim();
		if (!value || CACHE_PRICE_PATTERN.test(value)) return undefined;
		return CACHE_PRICE_ERROR;
	}

	/** Blank → null (unset / clear). The trimmed string is forwarded as-is, never float round-tripped. */
	function parseCachePrices(inputs: CachePriceInputs): { values: CachePriceValues; errors: CachePriceErrors } {
		const values = {} as CachePriceValues;
		const errors: CachePriceErrors = {};
		for (const { key } of CACHE_PRICE_FIELDS) {
			const message = cachePriceError(inputs[key]);
			if (message) errors[key] = message;
			values[key] = inputs[key].trim() || null;
		}
		return { values, errors };
	}

	/**
	 * Edit form: only keys whose trimmed input differs from the prefill. A value sets it, a blank
	 * clears a previously set price with null. Untouched keys are neither validated nor sent.
	 */
	function changedCachePrices(
		inputs: CachePriceInputs,
		baseline: CachePriceInputs
	): { values: Partial<CachePriceValues>; errors: CachePriceErrors } {
		const values: Partial<CachePriceValues> = {};
		const errors: CachePriceErrors = {};
		for (const { key } of CACHE_PRICE_FIELDS) {
			const value = inputs[key].trim();
			if (value === baseline[key]) continue;
			const message = cachePriceError(value);
			if (message) errors[key] = message;
			values[key] = value || null;
		}
		return { values, errors };
	}

	/** Once a field shows an error, re-check it while the admin corrects it. */
	function recheckCachePrice(errors: CachePriceErrors, key: CachePriceKey, raw: string): CachePriceErrors {
		if (!errors[key]) return errors;
		const next = { ...errors };
		const message = cachePriceError(raw);
		if (message) next[key] = message;
		else delete next[key];
		return next;
	}

	function presentCachePrices(values: CachePriceValues): Partial<CachePriceValues> {
		return Object.fromEntries(Object.entries(values).filter(([, value]) => value !== null));
	}

	function formatCachePrice(price: string | null | undefined): string {
		if (price === null || price === undefined || price === '') return t('configuration.unset');
		return displayPrice(price);
	}

	function cachePriceState(model: Model): 'none' | 'partial' | 'all' {
		const set = CACHE_PRICE_FIELDS.filter(({ key }) => model[key] !== null && model[key] !== undefined && model[key] !== '').length;
		if (set === 0) return 'none';
		return set === CACHE_PRICE_FIELDS.length ? 'all' : 'partial';
	}

	// A Lumen that predates cache pricing omits the keys entirely; null means an admin cleared the price.
	function cachePricingSupported(model: Model): boolean {
		return CACHE_PRICE_FIELDS.some(({ key }) => key in model);
	}

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	let providers = $state<Provider[]>([]);
	let models = $state<Model[]>([]);
	// An empty list cannot tell the Lumen version apart, so the create form keeps its cache inputs then.
	const cachePricingAvailable = $derived(models.length === 0 || models.some(cachePricingSupported));
	let loading = $state(true);
	let loadGeneration = 0;
	let error = $state('');
	let billingByProvider = $state<Record<number, ProviderBilling>>({});
	let billingLoading = $state(false);
	let billingError = $state('');
	let billingRequestGeneration = 0;
	let billingKeyModalOpen = $state(false);
	let billingKeyProvider = $state<Provider | null>(null);
	let billingAdminKey = $state('');
	let billingKeyBusy = $state(false);

	let pName = $state('');
	let pType = $state('openai');
	let pApiBase = $state('');
	let pApiKey = $state('');
	let addingProvider = $state(false);
	let pApiProvider = $state('openai');
	let pSortOrder = $state('0');
	let providerCreateAttempted = $state(false);
	let providerCreateError = $state('');
	let editingProvider = $state<Provider | null>(null);
	let editProviderName = $state('');
	let editApiProvider = $state('');
	let editProviderOrder = $state('0');
	let providerEditAttempted = $state(false);
	let providerSaving = $state(false);
	let providerEditError = $state('');
	const ORDER_HELP = $derived(t('pricing.orderHelp'));
	const QUALIFIER_HELP = $derived(t('pricing.qualifierHelp'));
	function orderError(value: string): string | undefined {
		return /^\d+$/.test(value.trim()) && Number(value.trim()) <= 2147483647
			? undefined : t('pricing.orderError');
	}
	function qualifierError(value: string): string | undefined {
		return /^[a-z][a-z0-9_-]{0,39}$/.test(value.trim())
			? undefined : t('pricing.qualifierError');
	}
	function metadataSaveError(e: unknown): string {
		return e instanceof ApiError ? t('pricing.saveStatusError', { status: e.status }) : t('pricing.saveError');
	}
	const selectedProviderChoice = $derived(PROVIDER_TYPES.find((choice) => choice.value === pType) ?? PROVIDER_TYPES[0]!);
	const isSubscriptionChoice = $derived(selectedProviderChoice.authMode !== 'api_key');

	interface DeviceAuthAttempt {
		attempt_id: string;
		status: 'pending' | 'connected' | 'cancelled' | 'expired' | 'error';
		verification_uri?: string;
		user_code?: string;
		expires_at: string;
		interval_seconds: number;
	}

	let authModalOpen = $state(false);
	let authProvider = $state<Provider | null>(null);
	let deviceAttempt = $state<DeviceAuthAttempt | null>(null);
	let authError = $state('');
	let authBusy = $state(false);
	let authCancelling = $state(false);
	let claudeToken = $state('');
	let claudeExpiry = $state('');
	let authSessionGeneration = $state(0);
	let authPollTimer = $state<ReturnType<typeof setTimeout> | null>(null);
	let authScopeToken = $state<string | undefined>();
	let authScopeProjectId = $state<string | undefined>();

	let mProviderId = $state<number | ''>('');
	let mName = $state('');
	let mDisplay = $state('');
	let mKind = $state<ModelKind>('text');
	let mInputPrice = $state('');
	let mOutputPrice = $state('');
	let mPricing = $state(pricingDraft());
	let mCachePrices = $state<CachePriceInputs>(emptyCachePriceInputs());
	let mCacheErrors = $state<CachePriceErrors>({});
	let addingModel = $state(false);

	let editingPrice = $state<Model | null>(null);
	let editInputPrice = $state('');
	let editOutputPrice = $state('');
	let editCachePrices = $state<CachePriceInputs>(emptyCachePriceInputs());
	let editCacheErrors = $state<CachePriceErrors>({});
	let editPricing = $state(pricingDraft());
	let priceSaving = $state(false);
	let priceScopeToken: string | undefined;
	let priceScopeProjectId: string | undefined;
	let editingCapabilities = $state<Model | null>(null);
	let capVision = $state(false);
	let capReasoning = $state(false);
	let capToolCall = $state(false);
	let capAttachment = $state(false);
	let capContextLimit = $state('');
	let capSuggestedInputLimit = $state<number | null>(null);
	let capSaving = $state(false);
	let capError = $state('');
	let draggedModelId = $state<number | null>(null);
	let modelDropTarget = $state<{ id: number; edge: 'before' | 'after' } | null>(null);
	let modelDragAllowedId: number | null = null;
	let modelOrderGeneration = 0;
	let modelOrderStatus = $state('');
	let modelOrderSaving = $state(false);
	let modelOrderSaveError = $state('');

	interface ModelsDevProvider { id: string; name: string; model_count: number }
	interface ModelsDevModel {
		id: string; name: string; last_updated: string | null;
		input_price_per_million: string | null; output_price_per_million: string | null;
		price_available: boolean; unsupported_price_fields: string[];
	}
	let modelsDevOpen = $state(false);
	let modelsDevProvider = $state<Provider | null>(null);
	let modelsDevProviders = $state<ModelsDevProvider[]>([]);
	let selectedModelsDevProviderId = $state('');
	let modelsDevProviderSearch = $state('');
	let modelsDevModels = $state<ModelsDevModel[]>([]);
	let modelsDevSelections = $state<Record<number, string>>({});
	let modelsDevLoading = $state(false);
	let modelsDevError = $state('');
	let modelsDevImporting = $state(false);
	function filterModelsDevProviders(query: string): ModelsDevProvider[] {
		const normalizedQuery = query.trim().toLocaleLowerCase();
		if (!normalizedQuery) return modelsDevProviders;
		return modelsDevProviders.filter((provider) =>
			`${provider.name} ${provider.id}`.toLocaleLowerCase().includes(normalizedQuery)
		);
	}

	const filteredModelsDevProviders = $derived.by(() => filterModelsDevProviders(modelsDevProviderSearch));

	// 등록된 모델 일괄 선택/삭제
	let selectedModelIds = $state<Record<number, boolean>>({});
	let deletingBulk = $state(false);
	let registeredProviderId = $state('');
	let registeredKind = $state<ModelKind | ''>('');
	const visibleModels = $derived(models.filter((model) => (registeredProviderId === '' || model.provider_id === Number(registeredProviderId)) && (registeredKind === '' || (model.model_kind ?? 'text') === registeredKind)));
	const selectedVisibleIds = $derived(visibleModels.filter((model) => selectedModelIds[model.id]).map((model) => model.id));
	const selectedCount = $derived(selectedVisibleIds.length);
	const allModelsSelected = $derived(visibleModels.length > 0 && selectedCount === visibleModels.length);
	const modelOrderBusy = $derived(loading || modelOrderSaving || deletingBulk);
	function changeRegisteredProvider() {
		selectedModelIds = {};
		resetModelDrag();
	}

	// Discovery is advisory: only administrator-entered price pairs can authorize activation.
	interface DiscoveryCandidate {
		id: string;
		display_name?: string | null;
		purpose?: 'chat' | 'non_chat' | 'unknown';
		model_kind?: ModelKind | null;
		generation_methods?: string[];
		input_token_limit?: number | null;
		output_token_limit?: number | null;
	}
	interface DiscoveryResult {
		provider_id: number;
		fetched_at: string;
		live_status: 'success' | 'empty' | 'unsupported' | 'error';
		complete: boolean;
		error: { code: string; message: string; retryable: boolean } | null;
		candidates: DiscoveryCandidate[];
		models: string[];
		source: 'api' | 'litellm' | 'none';
	}
	interface RegistrationEntry {
		name: string;
		displayName: string;
		kind: ModelKind | '';
		inputPrice: string;
		outputPrice: string;
		inputTokenLimit: number | null;
		outputTokenLimit: number | null;
		purpose: 'chat' | 'non_chat' | 'unknown';
	}
	interface RegistrationReview {
		providerId: number;
		providerName: string;
		entries: RegistrationEntry[];
		token: string | undefined;
		projectId: string | undefined;
	}
	let discoverId = $state<number | null>(null);
	let discovery = $state<DiscoveryResult | null>(null);
	let discoveryError = $state('');
	let availFilter = $state('');
	let availKind = $state<ModelKind | 'unknown' | ''>('');
	let selectedAvail = $state<Record<string, boolean>>({});
	let discovering = $state(false);
	let registeringBulk = $state(false);
	let registrationReview = $state<RegistrationReview | null>(null);
	let registrationOutcomes = $state<Record<string, 'success' | 'failed'>>({});
	let registrationMode = $state<'inactive' | 'active' | null>(null);
	let discoveryGeneration = 0;
	let registrationGeneration = 0;
	let discoveryScopeToken: string | undefined;
	let discoveryScopeProjectId: string | undefined;
	let destroyed = false;

	function resetDiscovery() {
		++discoveryGeneration;
		++registrationGeneration;
		discoverId = null;
		discovery = null;
		discoveryError = '';
		availFilter = '';
		availKind = '';
		selectedAvail = {};
		discovering = false;
		registeringBulk = false;
		registrationReview = null;
		registrationOutcomes = {};
		registrationMode = null;
	}

	function discoveryIsCurrent(generation: number, providerId: number, requestToken: string | undefined, requestProjectId: string | undefined) {
		return !destroyed && generation === discoveryGeneration && discoverId === providerId && mProviderId === providerId && token === requestToken && projectId === requestProjectId;
	}

	function registrationIsCurrent(generation: number, review: RegistrationReview) {
		return !destroyed && generation === registrationGeneration && discoverId === review.providerId && mProviderId === review.providerId && token === review.token && projectId === review.projectId;
	}

	function cleanShortModelName(name: string): string {
		if (!name) return '';
		let s = name.trim();
		for (const prefix of ['perplexity/', 'gemini/']) {
			while (s.startsWith(prefix)) {
				const rest = s.slice(prefix.length);
				if (!rest) break;
				s = rest;
			}
		}
		return s;
	}

	function publicModelName(model: Model): string {
		const raw = model.api_model_name || model.model_name;
		if (
			raw.startsWith('perplexity/perplexity/') ||
			raw.startsWith('gemini/gemini/') ||
			raw.startsWith('gemini/gemini-') ||
			(providerType(model.provider_id) === 'gemini' && raw.startsWith('gemini/'))
		) {
			return cleanShortModelName(raw);
		}
		return raw;
	}

	function displayModelTitle(model: Model): string {
		if (
			model.display_name &&
			model.display_name !== model.model_name &&
			!model.display_name.startsWith('perplexity/perplexity/') &&
			!model.display_name.startsWith('gemini/gemini-') &&
			!(providerType(model.provider_id) === 'gemini' && model.display_name.startsWith('gemini/'))
		) {
			return cleanShortModelName(model.display_name);
		}
		return cleanShortModelName(publicModelName(model));
	}

	function registeredNames(providerId: number): Set<string> {
		return new Set(
			models
				.filter((m) => m.provider_id === providerId)
				.flatMap((m) => [m.model_name, publicModelName(m), cleanShortModelName(m.model_name)])
		);
	}

	const filteredAvailable = $derived.by(() => {
		if (discoverId === null || !discovery || discovery.live_status === 'error') return [];
		const reg = registeredNames(discoverId);
		const filter = availFilter.toLocaleLowerCase();
		const candidates = discovery.candidates;
		return candidates.filter((candidate) =>
			!reg.has(candidate.id) && registrationOutcomes[candidate.id] !== 'success' && (availKind === '' || (candidate.model_kind ?? (candidate.purpose === 'chat' ? 'text' : 'unknown')) === availKind) && `${candidate.id} ${candidate.display_name ?? ''}`.toLocaleLowerCase().includes(filter)
		);
	});

	function reviewPriceError(entry: RegistrationEntry): string | undefined {
		if (!entry.kind) return t('pricing.kindRequired');
		if (entry.kind !== 'text' && !mediaProviderSupported(registrationReview?.providerId ?? '')) return t('pricing.directProviderRequired');
		const input = entry.inputPrice.trim();
		const output = entry.outputPrice.trim();
		if (!input && !output) return undefined;
		if ([input, output].some((value) => value && !CACHE_PRICE_PATTERN.test(value))) return t('pricing.reviewRateError');
		return undefined;
	}

	function reviewCanActivate(review: RegistrationReview): boolean {
		return review.entries.filter((entry) => registrationOutcomes[entry.name] !== 'success')
			.every((entry) => entry.kind === 'text' && entry.inputPrice.trim() !== '' && entry.outputPrice.trim() !== '' && !reviewPriceError(entry));
	}

	function formatBillingAmount(value: string | null): string {
		if (value === null) return '—';
		return Number(value).toLocaleString(intlLocale(), { maximumFractionDigits: 6 });
	}

	function billingFailureLabel(reason: string | null): string {
		if (reason === 'credential_not_configured') return t('configuration.noApiKeyConfigured');
		if (reason === 'credential_unavailable') return t('configuration.couldNotDecryptTheSavedApiKey');
		if (reason === 'admin_credential_not_configured') return t('configuration.setAnAdminKeyForOrganizationUsageLookup');
		if (reason === 'admin_credential_unavailable') return t('configuration.couldNotDecryptTheSavedAdminKeySetThe');
		if (reason === 'admin_credential_rejected') return t('configuration.theProviderRejectedTheAdminKeyCheckItsOrganization');
		if (reason === 'provider_authorization_failed') return t('configuration.theProviderDeniedBillingLookupForThisApiKey');
		if (reason === 'provider_request_failed') return t('configuration.theProviderUsageApiRequestFailed');
		return t('configuration.couldNotConnectToTheProviderUsageApi');
	}

	function unsupportedCreditLabel(providerType: string): string {
		const normalized = providerType.toLowerCase();
		if (normalized === 'openai') {
			return t('configuration.theOfficialOpenaiApiProvidesOnlyOrganizationCostsAnd');
		}
		if (normalized === 'anthropic') {
			return t('configuration.theOfficialAnthropicApiProvidesOnlyOrganizationCostsAnd');
		}
		if (normalized === 'gemini') {
			return t('configuration.geminiPrepaidBalancesAndTransactionsAreAvailableOnlyIn');
		}
		if (normalized === 'perplexity') {
			return t('configuration.thePerplexityEnterpriseComputerAnalyticsApiProvidesComputerProduct');
		}
		return t('configuration.thisProviderHasNoOfficialEndpointForLookingUp');
	}

	function providerCreditState(billing: ProviderBilling): ProviderCreditState {
		if (billing.capability === 'deepseek_balance') {
			if (billing.status !== 'available') {
				return { kind: 'unavailable', message: billingFailureLabel(billing.reason) };
			}
			return { kind: 'account_balance', balances: billing.balances, isAvailable: billing.is_available };
		}
		if (billing.capability === 'openrouter_key') {
			if (billing.status !== 'available') {
				return { kind: 'unavailable', message: billingFailureLabel(billing.reason) };
			}
			return {
				kind: 'api_key_limit',
				limit: billing.limit,
				remaining: billing.remaining,
				isFreeTier: billing.is_free_tier
			};
		}
		return { kind: 'unsupported', message: unsupportedCreditLabel(billing.provider_type) };
	}

	function availableBillingLabel(capability: ProviderBilling['capability']): string {
		if (capability === 'openai_admin_usage' || capability === 'anthropic_admin_usage') return t('configuration.organizationUsageIntegration');
		if (capability === 'deepseek_balance') return t('configuration.accountBalanceIntegration');
		if (capability === 'openrouter_key') return t('configuration.apiKeyLimitIntegration');
		return t('configuration.providerLookupIntegration');
	}

	function safeExternalUrl(value: string | null): string | undefined {
		if (!value) return undefined;
		try {
			const parsed = new URL(value);
			return parsed.protocol === 'https:' ? parsed.toString() : undefined;
		} catch {
			return undefined;
		}
	}

	function supportsBillingAdminKey(provider: Provider): boolean {
		if (providerAuthMode(provider) !== 'api_key' || !['openai', 'anthropic'].includes(provider.provider_type)) return false;
		if (!provider.api_base) return true;
		try {
			const host = new URL(provider.api_base).hostname.toLowerCase();
			return provider.provider_type === 'openai' ? host === 'api.openai.com' : host === 'api.anthropic.com';
		} catch {
			return false;
		}
	}

	async function loadProviderBilling({ fresh = false }: { fresh?: boolean } = {}) {
		if (!token) return;
		const generation = ++billingRequestGeneration;
		const requestToken = token;
		const requestProjectId = projectId;
		billingLoading = true;
		billingError = '';
		try {
			const snapshots = fresh
				? await api.get<ProviderBilling[]>(
					'/api/v1/chat/admin/providers/billing',
					requestToken,
					requestProjectId,
					{ refresh: true }
				)
				: await api.get<ProviderBilling[]>('/api/v1/chat/admin/providers/billing', requestToken, requestProjectId);
			if (generation !== billingRequestGeneration || requestToken !== token || requestProjectId !== projectId) return;
			billingByProvider = Object.fromEntries(snapshots.map((snapshot) => [snapshot.provider_id, snapshot]));
		} catch (caught) {
			if (generation !== billingRequestGeneration || requestToken !== token || requestProjectId !== projectId) return;
			billingByProvider = {};
			billingError = caught instanceof ApiError
				? t('configuration.billingStatusLookupFailed', { v0: caught.status })
				: t('configuration.couldNotRetrieveBillingStatus');
		} finally {
			if (generation === billingRequestGeneration && requestToken === token && requestProjectId === projectId) {
				billingLoading = false;
			}
		}
	}

	async function load({ freshBilling = false }: { freshBilling?: boolean } = {}) {
		if (!token) return;
		const generation = ++loadGeneration;
		resetModelDrag();
		const requestToken = token;
		const requestProjectId = projectId;
		++billingRequestGeneration;
		billingByProvider = {};
		billingLoading = false;
		loading = true;
		try {
			const [ps, ms] = await Promise.all([
				api.get<Provider[]>('/api/v1/chat/admin/providers', requestToken, requestProjectId),
				api.get<Model[]>('/api/v1/chat/admin/models', requestToken, requestProjectId)
			]);
			if (generation !== loadGeneration || requestToken !== token || requestProjectId !== projectId || destroyed) return;
			providers = [...ps].sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || a.id - b.id);
			if (mProviderId === '' && ps.length === 1) mProviderId = ps[0].id;
			const providerRanks = new Map(ps.map((provider) => [provider.id, provider.sort_order ?? 0]));
			models = [...ms].sort((a, b) =>
				(providerRanks.get(a.provider_id) ?? 0) - (providerRanks.get(b.provider_id) ?? 0)
				|| a.provider_id - b.provider_id || (a.sort_order ?? 0) - (b.sort_order ?? 0) || a.id - b.id);
			if (registeredProviderId && !ps.some((provider) => provider.id === Number(registeredProviderId))) registeredProviderId = '';
			selectedModelIds = Object.fromEntries(visibleModels.filter((model) => selectedModelIds[model.id]).map((model) => [model.id, true]));
			void loadProviderBilling({ fresh: freshBilling });
			error = '';
		} catch (e) {
			if (generation !== loadGeneration || requestToken !== token || requestProjectId !== projectId || destroyed) return;
			error = e instanceof ApiError ? t('configuration.lookupFailedAlternate', { v0: e.status }) : t('configuration.serverError');
		} finally {
			if (generation === loadGeneration && requestToken === token && requestProjectId === projectId && !destroyed) loading = false;
		}
	}

	async function addProvider() {
		providerCreateAttempted = true;
		if (addingProvider || !pName.trim() || qualifierError(pApiProvider) || orderError(pSortOrder)) return;
		providerCreateError = '';
		const choice = selectedProviderChoice;
		const requestToken = token, requestProjectId = projectId;
		addingProvider = true;
		try {
			const body: Record<string, unknown> = {
				name: pName.trim(),
				api_provider: pApiProvider.trim(),
				sort_order: Number(pSortOrder.trim()),
				provider_type: choice.providerType,
				auth_mode: choice.authMode
			};
			if (choice.authMode === 'api_key') {
				body.api_base = pApiBase.trim() || null;
				body.api_key = pApiKey.trim() || null;
			}
			const created = await api.post<Provider>(
				'/api/v1/chat/admin/providers',
				body,
				requestToken,
				requestProjectId
			);
			if (requestToken !== token || requestProjectId !== projectId || destroyed) return;
			invalidateChatModels();
			pName = '';
			pType = 'openai';
			pApiBase = '';
			pApiKey = '';
			pApiProvider = 'openai';
			pSortOrder = '0';
			providerCreateAttempted = false;
			await load();
			toast.success(t('configuration.providerAdded'));
			if (choice.authMode !== 'api_key') openSubscriptionAuth(created);
		} catch (e) {
			if (requestToken === token && requestProjectId === projectId && !destroyed) providerCreateError = metadataSaveError(e);
		} finally {
			addingProvider = false;
		}
	}

	function openProviderEditor(provider: Provider) {
		editingProvider = provider;
		editProviderName = provider.name;
		editApiProvider = provider.api_provider;
		editProviderOrder = String(provider.sort_order ?? 0);
		providerEditAttempted = false;
		providerEditError = '';
	}

	async function saveProviderMetadata() {
		providerEditAttempted = true;
		if (!editingProvider || providerSaving || !editProviderName.trim() || qualifierError(editApiProvider) || orderError(editProviderOrder)) return;
		const requestToken = token, requestProjectId = projectId;
		providerSaving = true;
		providerEditError = '';
		try {
			await api.patch(`/api/v1/chat/admin/providers/${editingProvider.id}`, {
				name: editProviderName.trim(), api_provider: editApiProvider.trim(), sort_order: Number(editProviderOrder.trim())
			}, requestToken, requestProjectId);
			if (requestToken !== token || requestProjectId !== projectId || destroyed) return;
			invalidateChatModels();
			editingProvider = null;
			await load();
			toast.success(t('pricing.providerSaved'));
		} catch (e) {
			if (requestToken === token && requestProjectId === projectId && !destroyed) providerEditError = metadataSaveError(e);
		} finally {
			providerSaving = false;
		}
	}

	function resetModelDrag() {
		if (draggedModelId !== null && !modelOrderSaving) modelOrderStatus = '';
		draggedModelId = null;
		modelDragAllowedId = null;
		modelDropTarget = null;
	}

	function modelSiblings(model: Model) {
		return visibleModels.filter((row) => row.provider_id === model.provider_id);
	}
	function handleModelPointerDown(event: PointerEvent | MouseEvent, model: Model) {
		const target = event.target instanceof Element ? event.target : null;
		if (event.button === 0 && !target?.closest('button, input, select, textarea, a, [contenteditable="true"]')) {
			modelDragAllowedId = model.id;
		} else {
			modelDragAllowedId = null;
		}
	}


	function startModelDrag(event: DragEvent, model: Model) {
		const target = event.target instanceof Element ? event.target : null;
		if (
			modelOrderBusy ||
			modelDragAllowedId !== model.id ||
			modelSiblings(model).length < 2 ||
			!event.dataTransfer ||
			Boolean(target?.closest('button, input, select, textarea, a, [contenteditable="true"]'))
		) {
			event.preventDefault();
			return;
		}
		modelDragAllowedId = null;
		event.dataTransfer.setData('text/plain', String(model.id));
		draggedModelId = model.id;
		modelDropTarget = null;
		modelOrderStatus = t('pricing.modelDragging', { name: displayModelTitle(model) });
	}

	function modelDropEdge(event: DragEvent): 'before' | 'after' {
		const targetElement = (event.currentTarget ?? event.target) as HTMLElement | null;
		const rect = targetElement?.getBoundingClientRect?.();
		if (!rect || rect.height <= 0) {
			return typeof event.clientY === 'number' && event.clientY < 0 ? 'before' : 'after';
		}
		return event.clientY < rect.top + rect.height / 2 ? 'before' : 'after';
	}

	function allowModelDrop(event: DragEvent, target: Model) {
		const source = models.find((row) => row.id === draggedModelId);
		if (modelOrderBusy || !source || source.id === target.id || source.provider_id !== target.provider_id) {
			modelDropTarget = null;
			return;
		}
		event.preventDefault();
		if (event.dataTransfer) event.dataTransfer.dropEffect = 'move';
		modelDropTarget = { id: target.id, edge: modelDropEdge(event) };
	}

	function dropModel(event: DragEvent, target: Model) {
		const source = models.find((row) => row.id === draggedModelId);
		const edge = modelDropTarget?.id === target.id ? modelDropTarget.edge : modelDropEdge(event);
		resetModelDrag();
		if (modelOrderBusy || !source || source.provider_id !== target.provider_id) return;
		event.preventDefault();
		void reorderModel(source, target, edge);
	}

	function moveModel(model: Model, direction: 'up' | 'down') {
		const siblings = modelSiblings(model);
		const index = siblings.findIndex((row) => row.id === model.id);
		const target = siblings[index + (direction === 'up' ? -1 : 1)];
		if (target) void reorderModel(model, target, direction === 'up' ? 'before' : 'after', direction);
	}

	async function reorderModel(source: Model, target: Model, edge: 'before' | 'after', focusMove?: 'up' | 'down') {
		if (!token || modelOrderBusy || source.id === target.id || source.provider_id !== target.provider_id) return;
		const siblings = modelSiblings(source);
		if (!siblings.some((row) => row.id === source.id) || !siblings.some((row) => row.id === target.id)) return;
		const visibleIds = new Set(siblings.map((row) => row.id));
		const reordered = siblings.filter((row) => row.id !== source.id).map((row) => row.id);
		reordered.splice(reordered.indexOf(target.id) + (edge === 'after' ? 1 : 0), 0, source.id);
		const expectedIds = models.filter((row) => row.provider_id === source.provider_id).map((row) => row.id);
		// Permute only visible slots: kind-filtered models keep their place in the provider catalog.
		let visibleIndex = 0;
		const orderedIds = expectedIds.map((id) => visibleIds.has(id) ? reordered[visibleIndex++] : id);
		if (orderedIds.every((id, index) => id === expectedIds[index])) return;
		const previousModels = models;
		const byId = new Map(models.map((row) => [row.id, row]));
		const orderedModels = orderedIds.map((id, sort_order) => ({ ...byId.get(id)!, sort_order }));
		let providerIndex = 0;
		models = models.map((row) => row.provider_id === source.provider_id ? orderedModels[providerIndex++] : row);
		const requestToken = token, requestProjectId = projectId;
		const generation = ++modelOrderGeneration;
		const current = () => generation === modelOrderGeneration && requestToken === token && requestProjectId === projectId && !destroyed;
		modelOrderSaving = true;
		modelOrderSaveError = '';
		modelOrderStatus = t('pricing.modelOrderSaving');
		resetModelDrag();
		try {
			await api.post('/api/v1/chat/admin/models/reorder', {
				provider_id: source.provider_id, expected_model_ids: expectedIds, model_ids: orderedIds
			}, requestToken, requestProjectId);
			if (!current()) return;
			invalidateChatModels();
			await load();
			if (!current()) return;
			modelOrderStatus = t('pricing.modelOrderSaved');
			toast.success(t('pricing.modelOrderSaved'));
		} catch (caught) {
			if (!current()) return;
			models = previousModels;
			modelOrderSaveError = caught instanceof ApiError && caught.status === 409
				? t('pricing.modelOrderConflict')
				: t('pricing.modelOrderSaveFailed', { status: caught instanceof ApiError ? ` (${caught.status})` : '' });
			modelOrderStatus = t('pricing.modelOrderFailed');
			await load();
		} finally {
			if (current()) {
				modelOrderSaving = false;
				if (focusMove) {
					await tick();
					if (current()) document.querySelector<HTMLButtonElement>(`[data-model-id="${source.id}"] [data-model-move="${focusMove}"] button:not(:disabled), [data-model-id="${source.id}"] [data-model-move] button:not(:disabled)`)?.focus();
				}
			}
		}
	}

	async function deleteProvider(id: number) {
		if (!(await confirmDialog(t('configuration.deleteThisProviderItsAssociatedModelsWillAlsoBe')))) return;
		try {
			await api.delete(`/api/v1/chat/admin/providers/${id}`, token, projectId);
			invalidateChatModels();
			await load();
		} catch {
			toast.error(t('configuration.deleteFailed'));
		}
	}

	async function toggleProvider(p: Provider) {
		try {
			await api.patch(`/api/v1/chat/admin/providers/${p.id}`, { is_active: !p.is_active }, token, projectId);
			await load();
		} catch {
			toast.error(t('configuration.changeFailed'));
		}
	}

	async function updateKey(p: Provider) {
		const key = prompt(t('configuration.enterANewApiKeyForLeaveBlankTo', { v0: p.name }));
		if (key === null) return;
		try {
			await api.patch(`/api/v1/chat/admin/providers/${p.id}`, { api_key: key.trim() || null }, token, projectId);
			await load({ freshBilling: true });
			toast.success(t('configuration.apiKeyUpdated'));
		} catch {
			toast.error(t('configuration.updateFailed'));
		}
	}

	function openBillingKeyModal(provider: Provider) {
		billingKeyProvider = provider;
		billingAdminKey = '';
		billingKeyModalOpen = true;
	}

	function closeBillingKeyModal() {
		billingKeyModalOpen = false;
		billingKeyProvider = null;
		billingAdminKey = '';
	}

	async function saveBillingAdminKey() {
		if (!billingKeyProvider) return;
		const provider = billingKeyProvider;
		billingKeyBusy = true;
		try {
			await api.patch(
				`/api/v1/chat/admin/providers/${provider.id}`,
				{ billing_admin_key: billingAdminKey.trim() || null },
				token,
				projectId
			);
			closeBillingKeyModal();
			await load({ freshBilling: true });
			toast.success(t('configuration.organizationUsageAdminKeyUpdated'));
		} catch (caught) {
			toast.error(caught instanceof ApiError ? caught.message : t('configuration.adminKeyUpdateFailed'));
		} finally {
			billingKeyBusy = false;
		}
	}

	function subscriptionStatusLabel(provider: Provider): string {
		if (provider.auth_status === 'configured' && provider.has_credentials) return t('configuration.authenticationConfigured');
		if (provider.auth_status === 'reauth_required') return t('configuration.reconnectRequired');
		return t('configuration.authenticationNotConnected');
	}

	function subscriptionStatusTone(provider: Provider): 'success' | 'warning' | 'neutral' {
		if (provider.auth_status === 'configured' && provider.has_credentials) return 'success';
		if (provider.auth_status === 'reauth_required') return 'warning';
		return 'neutral';
	}

	function providerAuthMode(provider: Provider): 'api_key' | 'chatgpt_device' | 'anthropic_subscription' {
		return provider.auth_mode ?? 'api_key';
	}

	function isSubscriptionProviderId(providerId: number | ''): boolean {
		if (!providerId) return false;
		const provider = providers.find((candidate) => candidate.id === providerId);
		return provider ? providerAuthMode(provider) !== 'api_key' : false;
	}

	function mediaProviderSupported(providerId: number | ''): boolean {
		const provider = providers.find((candidate) => candidate.id === providerId);
		if (!provider || providerAuthMode(provider) !== 'api_key') return false;
		const officialBases: Record<string, string[]> = {
			openai: ['https://api.openai.com', 'https://api.openai.com/v1'],
			gemini: ['https://generativelanguage.googleapis.com', 'https://generativelanguage.googleapis.com/v1beta']
		};
		const allowed = officialBases[provider.provider_type];
		return !!allowed && (provider.api_base === null || allowed.includes(provider.api_base.replace(/\/+$/, '')));
	}

	function clearProviderSecrets() {
		pApiBase = '';
		pApiKey = '';
	}

	function handleProviderChoiceChange() {
		clearProviderSecrets();
	}

	function subscriptionErrorMessage(error: unknown): string {
		if (!(error instanceof ApiError)) return t('configuration.subscriptionAuthenticationRequestFailedTryAgain');
		if (error.status === 409) return t('configuration.completeOrCancelTheCurrentChatExecutionOrAnother');
		if (error.status === 429) return t('configuration.authenticationRequestsAreRateLimitedCheckAgainManuallyIn');
		if (error.status === 503) return t('configuration.couldNotConnectToTheSubscriptionAuthenticationProviderOr');
		try {
			const detail = JSON.parse(error.message) as { message?: unknown };
			if (typeof detail.message === 'string') return detail.message;
		} catch {
			// The shared API client can also provide an already-safe plain message.
		}
		return error.message || t('configuration.subscriptionAuthenticationRequestFailed');
	}

	function stopAuthPolling() {
		if (authPollTimer !== null) {
			clearTimeout(authPollTimer);
			authPollTimer = null;
		}
	}

	function invalidateAuthSession() {
		stopAuthPolling();
		authSessionGeneration += 1;
		authScopeToken = token;
		authScopeProjectId = projectId;
		authBusy = false;
		authCancelling = false;
	}

	function openSubscriptionAuth(provider: Provider) {
		invalidateAuthSession();
		authProvider = provider;
		deviceAttempt = null;
		authError = '';
		claudeToken = '';
		claudeExpiry = '';
		authModalOpen = true;
	}

	function scheduleDevicePoll(attempt: DeviceAuthAttempt, generation: number) {
		stopAuthPolling();
		const remainingMs = new Date(attempt.expires_at).getTime() - Date.now();
		if (remainingMs <= 0) {
			deviceAttempt = { ...attempt, status: 'expired' };
			return;
		}
		const delayMs = Math.min(remainingMs, Math.max(1, attempt.interval_seconds) * 1000);
		authPollTimer = setTimeout(() => void pollDeviceAuth(attempt.attempt_id, generation), delayMs);
	}

	async function startDeviceAuth() {
		if (!authProvider || providerAuthMode(authProvider) !== 'chatgpt_device' || authBusy) return;
		invalidateAuthSession();
		const generation = authSessionGeneration;
		const providerId = authProvider.id;
		authBusy = true;
		authError = '';
		deviceAttempt = null;
		try {
			const attempt = await api.post<DeviceAuthAttempt>(
				`/api/v1/chat/admin/providers/${providerId}/auth/device`,
				{},
				token,
				projectId
			);
			if (generation !== authSessionGeneration || authProvider?.id !== providerId || !authModalOpen) return;
			deviceAttempt = attempt;
			scheduleDevicePoll(attempt, generation);
		} catch (e) {
			if (generation === authSessionGeneration) authError = subscriptionErrorMessage(e);
		} finally {
			if (generation === authSessionGeneration) authBusy = false;
		}
	}

	async function pollDeviceAuth(attemptId: string, generation: number) {
		if (
			authBusy ||
			generation !== authSessionGeneration ||
			!authProvider ||
			!authModalOpen ||
			deviceAttempt?.attempt_id !== attemptId
		) return;
		const providerId = authProvider.id;
		authBusy = true;
		authPollTimer = null;
		try {
			const status = await api.post<DeviceAuthAttempt>(
				`/api/v1/chat/admin/providers/${providerId}/auth/device/${encodeURIComponent(attemptId)}/poll`,
				{},
				token,
				projectId
			);
			if (

				generation !== authSessionGeneration ||
				authProvider?.id !== providerId ||
				deviceAttempt?.attempt_id !== attemptId ||
				!authModalOpen
			) return;
			deviceAttempt = { ...deviceAttempt, ...status };
			authError = '';
			if (status.status === 'pending') {
				scheduleDevicePoll(deviceAttempt, generation);
			} else if (status.status === 'connected') {
				await load();
				toast.success(t('configuration.chatgptSubscriptionConnected'));
			}
		} catch (e) {
			if (generation === authSessionGeneration) {
				stopAuthPolling();
				authError = subscriptionErrorMessage(e);
			}
		} finally {
			if (generation === authSessionGeneration) authBusy = false;
		}
	}
	function pollCurrentDeviceAuth() {
		if (!deviceAttempt) return;
		void pollDeviceAuth(deviceAttempt.attempt_id, authSessionGeneration);
	}

	async function cancelDeviceAuth() {
		if (!authProvider || !deviceAttempt || deviceAttempt.status !== 'pending') return;
		const providerId = authProvider.id;
		const attemptId = deviceAttempt.attempt_id;
		invalidateAuthSession();
		authBusy = true;
		authCancelling = true;
		authError = '';
		try {
			await api.delete(
				`/api/v1/chat/admin/providers/${providerId}/auth/device/${encodeURIComponent(attemptId)}`,
				token,
				projectId
			);
			if (authProvider?.id === providerId && deviceAttempt?.attempt_id === attemptId) {
				deviceAttempt = { ...deviceAttempt, status: 'cancelled' };
			}
		} catch (e) {
			authError = t('configuration.theAuthenticationRequestOnTheServerMayRemainActive', { v0: subscriptionErrorMessage(e) });
		} finally {
			authBusy = false;
			authCancelling = false;
		}
	}

	function closeSubscriptionAuth() {
		const providerId = authProvider?.id;
		const attemptId = deviceAttempt?.status === 'pending' ? deviceAttempt.attempt_id : null;
		invalidateAuthSession();
		authModalOpen = false;
		authProvider = null;
		deviceAttempt = null;
		authError = '';
		claudeToken = '';
		claudeExpiry = '';
		if (providerId && attemptId) {
			void api
				.delete(
					`/api/v1/chat/admin/providers/${providerId}/auth/device/${encodeURIComponent(attemptId)}`,
					token,
					projectId
				)
				.catch(() => toast.error(t('configuration.couldNotConfirmAuthenticationCancellationCheckTheServersExpiration')));
		}
	}

	async function saveClaudeSubscription() {
		if (!authProvider || providerAuthMode(authProvider) !== 'anthropic_subscription' || authBusy) return;
		if (!claudeToken.trim()) {
			authError = t('configuration.enterAClaudeSetupToken');
			return;
		}
		const generation = authSessionGeneration;
		const providerId = authProvider.id;
		authBusy = true;
		authError = '';
		try {
			const updated = await api.put<Provider>(
				`/api/v1/chat/admin/providers/${providerId}/auth/token`,
				{
					token: claudeToken.trim(),
					expires_at: claudeExpiry ? new Date(claudeExpiry).toISOString() : null
				},
				token,
				projectId
			);
			if (generation !== authSessionGeneration || authProvider?.id !== providerId || !authModalOpen) return;
			authProvider = updated;
			claudeToken = '';
			await load();
			toast.success(t('configuration.claudeSubscriptionTokenRegistered'));
		} catch (e) {
			if (generation === authSessionGeneration) authError = subscriptionErrorMessage(e);
		} finally {
			if (generation === authSessionGeneration) authBusy = false;
		}
	}

	async function disconnectSubscription(provider: Provider) {
		if (!(await confirmDialog(t('configuration.disconnectTheSubscriptionForRegisteredModelsWillBeKept', { v0: provider.name })))) return;
		try {
			await api.delete(`/api/v1/chat/admin/providers/${provider.id}/auth`, token, projectId);
			await load();
			toast.success(t('configuration.subscriptionDisconnected'));
		} catch (e) {
			toast.error(subscriptionErrorMessage(e));
		}
	}

	function isAllowedVerificationUri(value: string | undefined): boolean {
		if (!value) return false;
		try {
			const url = new URL(value);
			return url.protocol === 'https:' && (url.hostname === 'openai.com' || url.hostname.endsWith('.openai.com') || url.hostname === 'chatgpt.com' || url.hostname.endsWith('.chatgpt.com'));
		} catch {
			return false;
		}
	}

	async function copyDeviceCode() {
		if (!deviceAttempt?.user_code) return;
		try {
			await navigator.clipboard.writeText(deviceAttempt.user_code);
			toast.success(t('configuration.authenticationCodeCopied'));
		} catch {
			toast.error(t('configuration.couldNotCopyAuthenticationCode'));
		}
	}

	async function addModel() {
		if (addingModel || !mProviderId || !mName.trim()) { toast.error(t('configuration.enterAProviderAndModelName')); return; }
		if (mKind !== 'text' && !mediaProviderSupported(mProviderId)) { toast.error(t('pricing.mediaProviderRequired')); return; }
		if (!cachePricingAvailable) { mCachePrices = emptyCachePriceInputs(); mCacheErrors = {}; }
		const cache = parseCachePrices(mCachePrices);
		mCacheErrors = cache.errors;
		const prices = pricePayload(mInputPrice, mOutputPrice);
		const message = pricingError(mKind, mPricing);
		if (message) toast.error(message);
		if (Object.keys(cache.errors).length || message) return;
		const pricing = pricingPayload(mPricing);
		const requestToken = token, requestProjectId = projectId, providerId = mProviderId;
		const body = {
			provider_id: providerId, model_name: mName.trim(), display_name: mDisplay.trim() || null,
			...(mKind !== 'text' ? { model_kind: mKind } : {}),
			...(mKind === 'text' ? prices : Object.fromEntries(Object.entries(prices).filter(([, value]) => value !== null))), ...presentCachePrices(cache.values),
			...(pricing ? { media_pricing: pricing } : {})
		};
		addingModel = true;
		try {
			await api.post('/api/v1/chat/admin/models', body, requestToken, requestProjectId);
			invalidateChatModels();
			if (destroyed || token !== requestToken || projectId !== requestProjectId || mProviderId !== providerId) return;
			mName = ''; mDisplay = ''; mInputPrice = ''; mOutputPrice = '';
			mCachePrices = emptyCachePriceInputs(); mCacheErrors = {}; mPricing = pricingDraft();
			await load();
			if (!destroyed && token === requestToken && projectId === requestProjectId) toast.success(t('configuration.modelAdded'));
		} catch (e) {
			if (!destroyed && token === requestToken && projectId === requestProjectId && mProviderId === providerId) toast.error(e instanceof ApiError ? e.message : t('configuration.addFailed'));
		} finally {
			addingModel = false;
		}
	}

	function formatPricePerMillion(price: string | number | null | undefined): string {
		if (price === null || price === undefined) return t('configuration.pricingUnverified');
		return String(price).replace(/(\.\d*?[1-9])0+$/, '$1').replace(/\.0+$/, '');
	}

	function formatNumber(value: number): string {
		return value.toLocaleString(intlLocale());
	}

	/** Display-only formatting: never use localized rates in request drafts or payloads. */
	function displayPrice(price: string | number | null | undefined): string {
		if (price === null || price === undefined) return t('configuration.pricingUnverified');
		const raw = normalizeDecimalString(String(price));
		const locale = intlLocale();
		if (/^(?:\d+(?:\.\d+)?|\.\d+)[eE][+-]?\d+$/.test(raw)) {
			const value = Number(raw);
			return Number.isFinite(value) && value !== 0 ? value.toLocaleString(locale, { maximumSignificantDigits: 21 }) : raw;
		}
		if (!/^(?:\d+(?:\.\d+)?|\.\d+)$/.test(raw)) return raw;
		const [integer, fraction] = raw.split('.');
		const grouped = BigInt(integer || '0').toLocaleString(locale);
		const decimal = new Intl.NumberFormat(locale).formatToParts(1.1).find((part) => part.type === 'decimal')?.value ?? '.';
		return fraction ? `${grouped}${decimal}${fraction}` : grouped;
	}

	function pricePayload(input: string, output: string): { input_price_per_million: string | null; output_price_per_million: string | null } {
		return { input_price_per_million: input.trim() || null, output_price_per_million: output.trim() || null };
	}

	function openPriceEditor(model: Model) {
		editingPrice = model;
		priceScopeToken = token; priceScopeProjectId = projectId;
		editInputPrice = model.input_price_per_million ?? '';
		editOutputPrice = model.output_price_per_million ?? '';
		editCachePrices = cachePriceInputsFrom(model);
		editCacheErrors = {};
		editPricing = pricingDraft(model.media_pricing);
	}

	async function savePrice() {
		if (!editingPrice || priceSaving || destroyed || token !== priceScopeToken || projectId !== priceScopeProjectId) return;
		const model = editingPrice, requestToken = token, requestProjectId = projectId;
		const message = pricingError(model.model_kind ?? 'text', editPricing);
		if (message) { toast.error(message); return; }
		const cache = cachePricingSupported(model) ? changedCachePrices(editCachePrices, cachePriceInputsFrom(model)) : { values: {}, errors: {} };
		editCacheErrors = cache.errors;
		// Untouched text prices stay absent so a media/cache edit does not invalidate models.dev metadata.
		const prices = Object.fromEntries(
			Object.entries(pricePayload(editInputPrice, editOutputPrice)).filter(([key, value]) => value !== (model[key as keyof Model] ?? null))
		);
		if (Object.keys(cache.errors).length) return;
		const pricing = pricingPayload(editPricing, model.media_pricing);
		const body = { ...prices, ...cache.values, ...(!pricingEquals(pricing ?? {}, model.media_pricing ?? {}) ? { media_pricing: pricing } : {}) };
		if (!Object.keys(body).length) { editingPrice = null; return; }
		priceSaving = true;
		try {
			await api.patch(`/api/v1/chat/admin/models/${model.id}`, body, requestToken, requestProjectId);
			invalidateChatModels();
			if (destroyed || editingPrice !== model || token !== requestToken || projectId !== requestProjectId) return;
			editingPrice = null;
			await load();
			if (!destroyed && token === requestToken && projectId === requestProjectId) toast.success(t('configuration.modelPricingSaved'));
		} catch (e) {
			if (!destroyed && editingPrice === model && token === requestToken && projectId === requestProjectId) toast.error(e instanceof ApiError ? e.message : t('configuration.couldNotSavePricing'));
		} finally {
			priceSaving = false;
		}
	}

	function capabilityState(model: Model): 'override' | 'metadata' | 'unknown' {
		if (model.capability_source === 'override') return 'override';
		const caps = model.effective_capabilities ?? model.capabilities;
		if ((model.effective_capability_source || model.capability_source) && (caps?.vision || caps?.reasoning || caps?.tool_call || caps?.attachment || caps?.context_limit)) {
			return 'metadata';
		}
		return 'unknown';
	}

	function capabilityStatus(model: Model): string {
		const state = capabilityState(model);
		if (state === 'override') return t('configuration.adminCapabilitySettingsExecutionUnverified');
		if (state === 'metadata') return t('configuration.capabilityMetadataExecutionUnverified');
		return t('configuration.advancedCapabilitiesUnverified');
	}

	function openCapabilityEditor(model: Model) {
		editingCapabilities = model;
		const caps = model.capabilities ?? model.effective_capabilities;
		capVision = caps?.vision ?? false;
		capReasoning = caps?.reasoning ?? false;
		capToolCall = caps?.tool_call ?? false;
		capAttachment = caps?.attachment ?? false;
		capSuggestedInputLimit = !model.capabilities && !model.effective_capabilities?.context_limit && discoverId === model.provider_id
			? discovery?.candidates?.find((candidate) => candidate.id === model.model_name)?.input_token_limit ?? null
			: null;
		capContextLimit = model.capabilities
			? model.capabilities.context_limit == null ? '' : String(model.capabilities.context_limit)
			: model.effective_capabilities?.context_limit
				? String(model.effective_capabilities.context_limit)
				: capSuggestedInputLimit != null ? String(capSuggestedInputLimit) : '';
		capError = '';
	}

	function contextLimitError(raw: string): string | undefined {
		const value = raw.trim();
		if (!value) return undefined;
		const parsed = Number(value);
		return /^\d+$/.test(value) && Number.isSafeInteger(parsed) && parsed > 0
			? undefined : t('configuration.enterAContextLimitAsAnIntegerGreaterThan');
	}

	async function saveCapabilities() {
		if (!editingCapabilities || capSaving) return;
		const value = capContextLimit.trim();
		if (contextLimitError(value)) return;
		const contextLimit = value ? Number(value) : null;
		const model = editingCapabilities;
		capSaving = true;
		capError = '';
		try {
			await api.patch(`/api/v1/chat/admin/models/${model.id}`, {
				capabilities: {
					vision: capVision,
					reasoning: capReasoning,
					tool_call: capToolCall,
					attachment: capAttachment,
					modalities: model.capabilities?.modalities ?? null,
					reasoning_options: model.capabilities?.reasoning_options ?? [],
					context_limit: contextLimit
				}
			}, token, projectId);
			invalidateChatModels();
			editingCapabilities = null;
			await load();
			toast.success(t('configuration.modelCapabilitiesSavedVerifyExecutionSupportSeparately'));
		} catch (e) {
			capError = e instanceof ApiError ? e.message : t('configuration.couldNotSaveCapabilitiesTryAgain');
		} finally {
			capSaving = false;
		}
	}

	async function fetchModelsDevProviders(provider: Provider) {
		const query = new URLSearchParams({
			local_provider_id: String(provider.id)
		});
		const result = await api.get<{ providers: ModelsDevProvider[]; preferred_provider_ids?: string[] }>(
			`/api/v1/chat/admin/models/pricing/models-dev/providers?${query}`,
			token,
			projectId
		);
		modelsDevProviders = result.providers;
		modelsDevProviderSearch = '';
		selectedModelsDevProviderId = result.providers.some(
			(candidate) => candidate.id === provider.models_dev_provider_id
		)
			? provider.models_dev_provider_id!
			: result.preferred_provider_ids?.[0] ?? '';
	}

	async function openModelsDev(provider: Provider) {
		modelsDevOpen = true;
		modelsDevProvider = provider;
		modelsDevError = '';
		modelsDevModels = [];
		modelsDevSelections = {};
		modelsDevLoading = true;
		try {
			await fetchModelsDevProviders(provider);
			await loadModelsDevProvider();
		} catch (e) {
			modelsDevError = e instanceof ApiError ? e.message : t('configuration.couldNotLoadTheModelsDevPriceList');
		} finally {
			modelsDevLoading = false;
		}
	}


	function updateModelsDevProviderSearch(event: Event) {
		modelsDevProviderSearch = (event.currentTarget as HTMLInputElement).value;
		const candidates = filterModelsDevProviders(modelsDevProviderSearch);
		if (candidates.some((candidate) => candidate.id === selectedModelsDevProviderId)) return;
		selectedModelsDevProviderId = candidates[0]?.id ?? '';
		modelsDevModels = [];
		modelsDevSelections = {};
		if (selectedModelsDevProviderId) {
			void loadModelsDevProvider();
		} else {
			modelsDevLoading = false;
		}
	}

	async function loadModelsDevProvider() {
		const providerId = selectedModelsDevProviderId;
		if (!providerId) {
			modelsDevLoading = false;
			modelsDevModels = [];
			modelsDevSelections = {};
			return;
		}
		modelsDevLoading = true;
		try {
			const result = await api.get<{ models: ModelsDevModel[] }>(
				`/api/v1/chat/admin/models/pricing/models-dev/providers/${encodeURIComponent(providerId)}`,
				token,
				projectId
			);
			if (providerId !== selectedModelsDevProviderId) return;
			modelsDevModels = result.models;
			modelsDevSelections = Object.fromEntries(
				models
					.filter((model) => model.provider_id === modelsDevProvider?.id && (model.model_kind ?? 'text') === 'text' && model.price_source !== 'manual')
					.flatMap((model) => {
						const exact = result.models.find((external) => external.price_available && external.id === model.model_name);
						return exact ? [[model.id, exact.id]] : [];
					})
			);
		} catch (e) {
			if (providerId === selectedModelsDevProviderId) {
				modelsDevError = e instanceof ApiError ? e.message : t('configuration.couldNotLoadTheModelsDevModelList');
			}
		} finally {
			if (providerId === selectedModelsDevProviderId) modelsDevLoading = false;
		}
	}

	async function importModelsDevPrices() {
		if (!modelsDevProvider) return;
		const selections = Object.entries(modelsDevSelections)
			.filter(([localModelId, externalId]) => externalId && models.some((model) => model.id === Number(localModelId) && (model.model_kind ?? 'text') === 'text'))
			.map(([localModelId, modelsDevModelId]) => ({ local_model_id: Number(localModelId), models_dev_model_id: modelsDevModelId }));
		if (selections.length === 0) {
			toast.error(t('configuration.selectModelsToApplyPricesTo'));
			return;
		}
		modelsDevImporting = true;
		try {
			await api.post('/api/v1/chat/admin/models/pricing/models-dev/import', {
				local_provider_id: modelsDevProvider.id,
				models_dev_provider_id: selectedModelsDevProviderId,
				selections
			}, token, projectId);
			invalidateChatModels();
			modelsDevOpen = false;
			await load();
			toast.success(t('configuration.modelsDevSuggestedPricesApplied'));
		} catch (e) {
			modelsDevError = e instanceof ApiError ? e.message : t('configuration.priceImportFailed');
		} finally {
			modelsDevImporting = false;
		}
	}

	async function discover(providerId: number) {
		if (discoverId === providerId) {
			resetDiscovery();
			return;
		}
		resetDiscovery();
		discoverId = providerId;
		await retryDiscovery();
	}

	async function retryDiscovery() {
		const providerId = discoverId;
		if (providerId === null || mProviderId !== providerId || registeringBulk) return;
		const generation = ++discoveryGeneration;
		const requestToken = token;
		const requestProjectId = projectId;
		discovering = true;
		discoveryError = '';
		discovery = null;
		selectedAvail = {};
		registrationReview = null;
		registrationOutcomes = {};
		try {
			const result = await api.get<DiscoveryResult>(
				`/api/v1/chat/admin/providers/${providerId}/available-models`,
				requestToken,
				requestProjectId
			);
			if (!discoveryIsCurrent(generation, providerId, requestToken, requestProjectId)) return;
			if (result.provider_id !== undefined && result.provider_id !== providerId) {
				discoveryError = t('configuration.receivedDiscoveryResultsForADifferentProviderFetchAgain');
				return;
			}
			discovery = result.live_status === 'error'
				? { ...result, source: 'none', models: [], candidates: [], complete: false }
				: result;
		} catch {
			if (discoveryIsCurrent(generation, providerId, requestToken, requestProjectId)) {
				discoveryError = t('configuration.modelLookupFailedCheckTheConnectionAndApiKey');
			}
		} finally {
			if (discoveryIsCurrent(generation, providerId, requestToken, requestProjectId)) discovering = false;
		}
	}

	function reviewSelected() {
		if (discoverId === null || !discovery || discovery.live_status === 'error' || registeringBulk) return;
		const registered = registeredNames(discoverId);
		const candidates = discovery.candidates
			.filter((candidate) => selectedAvail[candidate.id] && !registered.has(candidate.id) && registrationOutcomes[candidate.id] !== 'success');
		if (candidates.length === 0) {
			toast.error(t('pricing.registrationRequired'));
			return;
		}
		registrationOutcomes = {};
		registrationMode = null;
		registrationReview = {
			providerId: discoverId,
			providerName: providerName(discoverId),
			entries: candidates.map((candidate) => ({
				name: candidate.id,
				displayName: candidate.display_name ?? '',
				kind: candidate.model_kind ?? (candidate.purpose === 'chat' ? 'text' : ''),
				inputPrice: '',
				outputPrice: '',
				inputTokenLimit: candidate.input_token_limit ?? null,
				outputTokenLimit: candidate.output_token_limit ?? null,
				purpose: candidate.purpose ?? 'unknown'
			})),
			token,
			projectId
		};
	}

	async function registerSelected(activate: boolean) {
		if (!registrationReview || registeringBulk || (registrationMode && registrationMode !== (activate ? 'active' : 'inactive'))) return;
		const review: RegistrationReview = {
			...registrationReview,
			entries: registrationReview.entries.map((entry) => ({ ...entry }))
		};
		const pending = review.entries.filter((entry) => registrationOutcomes[entry.name] !== 'success');
		if (pending.some((entry) => reviewPriceError(entry)) || (activate && !reviewCanActivate(review))) {
			toast.error(t('configuration.toActivateEnterBothExactInputAndOutputRates'));
			return;
		}
		const generation = ++registrationGeneration;
		if (!registrationIsCurrent(generation, review)) return;
		registrationMode = activate ? 'active' : 'inactive';
		registeringBulk = true;
		let ok = 0;
		const failed: string[] = [];
		try {
			for (const entry of pending) {
				if (!registrationIsCurrent(generation, review)) break;
				const inputPrice = entry.inputPrice.trim();
				const outputPrice = entry.outputPrice.trim();
				try {
					await api.post(
						'/api/v1/chat/admin/models',
						{
							provider_id: review.providerId,
							model_name: entry.name,
							model_kind: entry.kind,
							...(entry.displayName.trim() ? { display_name: entry.displayName.trim() } : {}),
							...(inputPrice ? { input_price_per_million: inputPrice } : {}),
							...(outputPrice ? { output_price_per_million: outputPrice } : {}),
							is_active: activate
						},
						review.token,
						review.projectId
					);
					ok++;
					invalidateChatModels();
					if (registrationIsCurrent(generation, review)) registrationOutcomes = { ...registrationOutcomes, [entry.name]: 'success' };
				} catch {
					failed.push(entry.name);
					if (registrationIsCurrent(generation, review)) registrationOutcomes = { ...registrationOutcomes, [entry.name]: 'failed' };
				}
			}
			if (!registrationIsCurrent(generation, review)) return;
			if (ok > 0) await load();
			if (!registrationIsCurrent(generation, review)) return;
			if (ok > 0) toast.success(t('configuration.modelsAlternate', { v0: formatNumber(ok), v1: activate ? t('configuration.registeredAndActivated') : t('configuration.savedAsInactive') }));
			if (failed.length > 0) toast.error(t('configuration.modelsFailedToRegisterYouCanRetryOnlyThe', { v0: formatNumber(failed.length) }));
			selectedAvail = Object.fromEntries(failed.map((name) => [name, true]));
			if (failed.length === 0) registrationReview = null;
		} finally {
			if (registrationIsCurrent(generation, review)) registeringBulk = false;
		}
	}

	function toggleAllFiltered(checked: boolean) {
		const next = { ...selectedAvail };
		for (const candidate of filteredAvailable) {
			next[candidate.id] = checked;
		}
		selectedAvail = next;
	}

	async function deleteModel(id: number) {
		if (!(await confirmDialog(t('configuration.deleteThisModel')))) return;
		try {
			await api.delete(`/api/v1/chat/admin/models/${id}`, token, projectId);
			invalidateChatModels();
			await load();
		} catch {
			toast.error(t('configuration.deleteFailed'));
		}
	}

	function toggleAllModels(checked: boolean) {
		const next: Record<number, boolean> = {};
		if (checked) for (const m of visibleModels) next[m.id] = true;
		selectedModelIds = next;
	}

	async function deleteSelectedModels() {
		const ids = [...selectedVisibleIds];
		const requestToken = token, requestProjectId = projectId;
		if (ids.length === 0) return;
		if (!(await confirmDialog(t('configuration.deleteTheSelectedModels', { v0: formatNumber(ids.length) })))) return;
		if (requestToken !== token || requestProjectId !== projectId || destroyed) return;
		const visibleIds = new Set(selectedVisibleIds);
		const confirmedIds = ids.filter((id) => visibleIds.has(id));
		if (confirmedIds.length === 0) return;
		deletingBulk = true;
		let ok = 0;
		const failed: string[] = [];
		try {
			for (const id of confirmedIds) {
				if (requestToken !== token || requestProjectId !== projectId || destroyed) return;
				try {
					await api.delete(`/api/v1/chat/admin/models/${id}`, requestToken, requestProjectId);
					ok++;
					invalidateChatModels();
				} catch {
					failed.push(String(id));
				}
			}
			if (requestToken !== token || requestProjectId !== projectId || destroyed) return;
			selectedModelIds = {};
			await load();
			if (ok > 0) toast.success(t('configuration.modelsDeleted', { v0: formatNumber(ok) }));
			if (failed.length > 0) toast.error(t('configuration.modelsFailedToDelete', { v0: formatNumber(failed.length) }));
		} finally {
			deletingBulk = false;
		}
	}

	async function toggleModel(m: Model) {
		if ((m.model_kind ?? 'text') === 'text' && !m.is_active && (m.effective_input_price_per_million == null || m.effective_output_price_per_million == null)) {
			toast.error(t('configuration.inputAndOutputRatesAreUnverifiedEditPricingOr'));
			return;
		}
		try {
			await api.patch(`/api/v1/chat/admin/models/${m.id}`, { is_active: !m.is_active }, token, projectId);
			invalidateChatModels();
			await load();
		} catch {
			toast.error(t('configuration.changeFailed'));
		}
	}

	function providerName(id: number): string {
		return providers.find((provider) => provider.id === id)?.name ?? String(id);
	}

	function providerType(id: number): string {
		return providers.find((provider) => provider.id === id)?.provider_type ?? 'unknown';
	}

	// 제목 요약 모델 지정/해제 — 최대 1개만 지정(백엔드가 단일 보장). 요약 호출은 시스템 부담.
	async function setTitleModel(m: Model) {
		try {
			const target = m.is_title_model ? null : m.id;
			await api.put('/api/v1/chat/admin/title-model', { model_id: target }, token, projectId);
			invalidateChatModels();
			models = models.map((x) => ({ ...x, is_title_model: x.id === target }));
			toast.success(target ? t('configuration.titleGenerationModelAssigned') : t('configuration.titleGenerationModelUnassigned'));
		} catch (e) {
			toast.error(e instanceof ApiError ? e.message : t('configuration.couldNotSetTheTitleGenerationModel'));
		}
	}

	$effect(() => {
		if (token) untrack(() => void load());
	});

	const unsubscribeAuthScope = auth.subscribe((state) => {
		const nextToken = state.token ?? undefined;
		const nextProjectId = state.projectId ?? undefined;
		if (discoveryScopeToken !== nextToken || discoveryScopeProjectId !== nextProjectId) {
			discoveryScopeToken = nextToken;
			discoveryScopeProjectId = nextProjectId;
			resetDiscovery();
			selectedModelIds = {};
			registeredProviderId = '';
			registeredKind = '';
			editingPrice = null;
			editingProvider = null;
			++modelOrderGeneration;
			modelOrderSaving = false;
			modelOrderSaveError = '';
			modelOrderStatus = '';
			resetModelDrag();
		}
		if (
			authModalOpen &&
			(authScopeToken !== nextToken || authScopeProjectId !== nextProjectId)
		) {
			invalidateAuthSession();
			authModalOpen = false;
			authProvider = null;
			deviceAttempt = null;
			authError = '';
			claudeToken = '';
			claudeExpiry = '';
		}
	});

	onDestroy(() => {
		destroyed = true;
		++loadGeneration;
		resetDiscovery();
		unsubscribeAuthScope();
		invalidateAuthSession();
	});

	const inputCls =
		'w-full rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-base)] px-3 py-2 text-sm text-[var(--color-ink-1)] focus:outline-none focus:border-[var(--color-accent)]';
	const cardCls = 'rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-raised)]';
	const rowActionCls = 'text-[var(--color-ink-2)] hover:text-[var(--color-ink-0)] transition-colors';
</script>

<div class="max-w-4xl p-4 md:p-8">
	<PageHeader
		breadcrumb={section === 'models' ? t('configuration.aiChatModelSettings') : section === 'tools' ? t('configuration.aiChatToolSettings') : t('configuration.aiChatSettings')}
		title={section === 'models' ? t('configuration.modelSettings') : section === 'tools' ? t('configuration.toolSettings') : t('configuration.chatSettings')}
		subtitle={section === 'models'
			? t('configuration.manageProviderModelsPricingAndTheConversationTitleModel')
			: section === 'tools'
				? t('configuration.manageMcpServersSkillsAndCustomHttpTools')
				: t('configuration.manageLlmProvidersAndConnectionsApiKeysAreStored')}
	/>

	{#if error}
		<div
			class="mb-4 rounded-lg border border-[var(--color-state-danger)]/40 bg-[var(--color-state-danger)]/10 px-4 py-3 text-sm text-[var(--color-state-danger)]"
		>
			{error}
		</div>
	{/if}

	{#if section === 'providers'}
	<!-- 프로바이더 -->
	<section class="mb-8">
		<h3 class="mb-3 text-sm font-semibold text-[var(--color-ink-1)]">{t('configuration.llmProviders')}</h3>
		<div class="{cardCls} mb-4 p-5">
			<div class="grid grid-cols-1 gap-3 md:grid-cols-2">
				<Field label={t('configuration.name')} for="provider-name" required error={providerCreateAttempted && !pName.trim() ? t('pricing.nameRequired') : undefined}>
					<TextInput id="provider-name" placeholder={t('configuration.eGOpenaiProd')} bind:value={pName} required ariaInvalid={providerCreateAttempted && !pName.trim()} />
				</Field>
				<Field label={t('configuration.connectionMethod')} for="provider-type" required>
					<SelectInput id="provider-type" bind:value={pType} onchange={handleProviderChoiceChange}>
						{#each PROVIDER_TYPES as pt (pt.value)}
							<option value={pt.value}>{pt.label}</option>
						{/each}
					</SelectInput>
				</Field>
				<Field label={t('pricing.apiProviderLabel')} for="provider-api-provider" required help={QUALIFIER_HELP} error={pApiProvider || providerCreateAttempted ? qualifierError(pApiProvider) : undefined}>
					<TextInput id="provider-api-provider" bind:value={pApiProvider} required maxlength={40} ariaInvalid={Boolean(qualifierError(pApiProvider))} />
				</Field>
				<Field label={t('pricing.providerOrder')} for="provider-sort-order" required help={ORDER_HELP} error={pSortOrder || providerCreateAttempted ? orderError(pSortOrder) : undefined}>
					<TextInput id="provider-sort-order" inputmode="numeric" bind:value={pSortOrder} required ariaInvalid={Boolean(orderError(pSortOrder))} />
				</Field>
				{#if !isSubscriptionChoice}
					<Field label={t('configuration.apiBaseUrl')} for="provider-api-base" help={t('configuration.enterOnlyForOpenaiCompatibleOrCustomEndpoints')}>
						<TextInput id="provider-api-base" type="url" placeholder="https://api.example.com/v1" bind:value={pApiBase} />
					</Field>
					<Field label={t('configuration.apiKey')} for="provider-api-key">
						<TextInput id="provider-api-key" type="password" placeholder={t('configuration.apiKey')} bind:value={pApiKey} />
					</Field>
				{/if}
			</div>
			{#if isSubscriptionChoice}
				{#snippet rich2markup1(text: string)}<a class="underline" href={selectedProviderChoice.authMode === 'chatgpt_device' ? 'https://help.openai.com/en/articles/11369540-codex-in-chatgpt' : 'https://support.anthropic.com/en/articles/11145838-using-claude-code-with-your-pro-or-max-plan'} target="_blank" rel="noreferrer">{text}</a>{/snippet}
				<Alert tone="warning" title={t('configuration.experimentalSharedByAllUsers')} class="mt-4">
					<RichText segments={t.rich('configuration.sharedSubscriptionPolicy')} tags={{ markup1: rich2markup1 }} />
				</Alert>
			{:else if selectedProviderChoice.providerType === 'perplexity'}
				{#snippet rich4markup1(text: string)}<code>{text}</code>{/snippet}
				{#snippet rich4markup2(text: string)}<code>{text}</code>{/snippet}
				<Alert tone="info" title={t('configuration.perplexityApiBaseUrl')} class="mt-4">
					<RichText segments={t.rich('configuration.perplexityApiBaseGuidance')} tags={{ markup1: rich4markup1, markup2: rich4markup2 }} />
				</Alert>
			{:else}
				<p class="mt-2 text-xs text-[var(--color-ink-3)]">
					{t('configuration.theTypeIsTheInternalLitellmRelayFormatConnect')}
				</p>
			{/if}
			{#if providerCreateError}<Alert tone="danger" class="mt-3">{providerCreateError}</Alert>{/if}
			<div class="mt-3 flex justify-end">
				<Button onclick={addProvider} disabled={addingProvider} ariaBusy={addingProvider}>
					{#if addingProvider}<ActivityIndicator size="xs" tone="ink" />{/if}{addingProvider ? t('configuration.adding') : t('configuration.addProvider')}
				</Button>
			</div>
		</div>

		{#if loading}
			<div class="{cardCls} h-20 motion-skeleton" role="status" aria-busy="true" aria-label={t('configuration.loadingProviders')}><span class="sr-only">{t('configuration.loadingProviders')}</span></div>
		{:else if providers.length === 0}
			<EmptyState headline={t('configuration.noProvidersRegistered')} class="py-4 [&_.motion-enter]:animate-none" />
		{:else}
			<div class="mb-3 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
				<div>
					<h4 class="text-sm font-semibold text-[var(--color-ink-1)]">{t('configuration.usageAndCreditStatus')}</h4>
					<p class="mt-1 text-xs text-[var(--color-ink-2)]">{t('configuration.theLumenLedgerIsShownSeparatelyFromOfficialProvider')}</p>
				</div>
				<Button variant="outline" size="sm" disabled={billingLoading} ariaBusy={billingLoading} onclick={() => void loadProviderBilling({ fresh: true })}>
					{#if billingLoading}<ActivityIndicator size="xs" tone="ink" />{/if}{billingLoading ? t('configuration.fetching') : t('configuration.refreshAll')}
				</Button>
			</div>
			{#if billingError}
				<Alert tone="warning" title={t('configuration.couldNotLoadBillingStatus')} class="mb-3">{t('configuration.billingFailureSettingsAvailable', { v0: billingError })}</Alert>
			{/if}
			<div class="space-y-2">
				{#each providers as p (p.id)}
					{@const billing = billingByProvider[p.id]}
					<div class="{cardCls} px-4 py-3" data-provider-id={p.id}>
						<div class="flex flex-col items-start justify-between gap-3 sm:flex-row sm:items-center">
							<div class="min-w-0">
								<div class="flex flex-wrap items-center gap-2">
									<span class="truncate text-sm font-medium text-[var(--color-ink-1)]">{p.name}</span>
									<Pill tone={p.is_active ? 'success' : 'neutral'} size="xs">{p.is_active ? t('configuration.active') : t('configuration.inactive')}</Pill>
									{#if providerAuthMode(p) === 'api_key'}
										<Pill tone={p.has_api_key ? 'accent' : 'warning'} size="xs">{p.has_api_key ? t('configuration.keyConfigured') : t('configuration.noKey')}</Pill>
									{#if supportsBillingAdminKey(p)}
										<Pill tone={p.has_billing_admin_key ? 'info' : 'neutral'} size="xs">{p.has_billing_admin_key ? t('configuration.usageKeyConfigured') : t('configuration.noUsageKey')}</Pill>
									{/if}
									{:else}
										<Pill tone="warning" size="xs">{t('configuration.experimental')}</Pill>
										<Pill tone="info" size="xs">{t('configuration.sharedByAllUsers')}</Pill>
										<Pill tone={subscriptionStatusTone(p)} size="xs">{subscriptionStatusLabel(p)}</Pill>
									{/if}
									<Pill tone="neutral" size="xs">{t('pricing.connection', { type: p.provider_type })}</Pill>
								</div>
								<p class="mt-1 break-all text-xs text-[var(--color-ink-2)]"><RichText segments={t.rich('pricing.providerMetadata', { provider: p.api_provider, order: formatNumber(p.sort_order ?? 0) })} /></p>
								{#if p.api_base}
									<div class="mt-1 truncate text-xs text-[var(--color-ink-3)]">{p.api_base}</div>
								{:else if providerAuthMode(p) !== 'api_key' && p.auth_expires_at}
									<div class="mt-1 text-xs text-[var(--color-ink-3)]">{t('configuration.credentialExpiry', { v0: new Date(p.auth_expires_at).toLocaleString(intlLocale()) })}</div>
								{/if}
							</div>
							<div class="flex flex-wrap items-center gap-x-3 gap-y-2 text-xs sm:justify-end">
								<Button variant="outline" size="sm" onclick={() => openProviderEditor(p)}>{t('pricing.editDisplay')}</Button>
								{#if providerAuthMode(p) === 'api_key'}
									<button class={rowActionCls} onclick={() => updateKey(p)}>{t('configuration.changeKey')}</button>
									{#if supportsBillingAdminKey(p)}
										<button class={rowActionCls} onclick={() => openBillingKeyModal(p)}>{p.has_billing_admin_key ? t('configuration.changeUsageKey') : t('configuration.setUsageKey')}</button>
									{/if}
								{:else}
									<button class={rowActionCls} onclick={() => openSubscriptionAuth(p)}>
										{providerAuthMode(p) === 'chatgpt_device'
											? p.has_credentials ? t('configuration.reconnectAlternate') : t('configuration.connect')
											: p.has_credentials ? t('configuration.replaceToken') : t('configuration.registerToken')}
									</button>
									{#if p.auth_status !== 'disconnected'}
										<button class={rowActionCls} onclick={() => disconnectSubscription(p)}>{t('configuration.disconnect')}</button>
									{/if}
								{/if}
								<button class={rowActionCls} onclick={() => toggleProvider(p)}>{p.is_active ? t('configuration.deactivate') : t('configuration.activate')}</button>
								<button class="text-[var(--color-state-danger)] transition-opacity hover:opacity-80" onclick={() => deleteProvider(p.id)}>{t('configuration.delete')}</button>
							</div>
						</div>

						<div class="mt-3 border-t border-[var(--color-line)] pt-3">
							<div class="flex flex-wrap items-center gap-2">
								<span class="text-xs font-semibold text-[var(--color-ink-1)]">{t('configuration.usageBillingStatus')}</span>
								{#if billing?.status === 'available'}
									<Pill tone="success" size="xs">{availableBillingLabel(billing.capability)}</Pill>
								{:else if billing?.status === 'unavailable'}
									<Pill tone="warning" size="xs">{t('configuration.providerLookupFailed')}</Pill>
								{:else if billing?.status === 'unsupported'}
									<Pill tone="neutral" size="xs">{t('configuration.checkOfficialConsole')}</Pill>
								{/if}
							</div>

							{#if billingLoading && !billing}
								<ActivityIndicator size="xs" label={t('configuration.fetchingUsageAndBillingStatus')} class="mt-2 text-xs text-ink-2" />
							{:else if !billing}
								<p class="mt-2 text-xs text-[var(--color-ink-2)]">{t('configuration.noBillingStatusToDisplayUseRefreshAllTo')}</p>
							{:else}
								{@const billingUrl = safeExternalUrl(billing.billing_url)}
								{@const usageUrl = safeExternalUrl(billing.usage_url)}
								{@const credit = providerCreditState(billing)}
								<div class="mt-3 rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-base)] p-3">
									<div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
										<div class="min-w-0">
											<div class="flex flex-wrap items-center gap-2">
												<span class="text-xs font-semibold text-[var(--color-ink-1)]">{t('configuration.accountCredits')}</span>
												{#if credit.kind === 'account_balance'}
													<Pill tone={credit.isAvailable ? 'success' : 'warning'} size="xs">{t('configuration.officialAccountBalance')}</Pill>
												{:else if credit.kind === 'api_key_limit'}
													<Pill tone="info" size="xs">{t('configuration.apiKeyLimit')}</Pill>
												{:else if credit.kind === 'unavailable'}
													<Pill tone="warning" size="xs">{t('configuration.lookupFailed')}</Pill>
												{:else}
													<Pill tone="neutral" size="xs">{t('configuration.officialApiLookupUnsupported')}</Pill>
												{/if}
											</div>
											{#if credit.kind === 'unavailable' || credit.kind === 'unsupported'}
												<p class="mt-2 text-xs leading-relaxed text-[var(--color-ink-2)]">{t('configuration.balanceNotEstimated', { v0: credit.message })}</p>
											{:else if credit.kind === 'api_key_limit'}
												<p class="mt-2 text-xs leading-relaxed text-[var(--color-ink-2)]">{t('configuration.theSpendingLimitOpenrouterReportsForTheCurrentApi')}</p>
											{/if}
										</div>
										{#if billingUrl}
											<Button variant="outline" size="sm" href={billingUrl} target="_blank">{t('configuration.addCreditsBilling')}</Button>
										{/if}
									</div>

									{#if credit.kind === 'account_balance'}
										{#if credit.balances.length === 0}
											<p class="mt-3 text-xs text-[var(--color-ink-2)]">{t('configuration.theProviderReturnedNoBalanceEntries')}</p>
										{:else}
											{#each credit.balances as balance (balance.currency)}
												<div class="mt-3">
													<div class="mb-2 flex items-center justify-between gap-2">
														<span class="text-xs font-medium text-[var(--color-ink-2)]">DeepSeek {balance.currency}</span>
														<Pill tone={credit.isAvailable ? 'success' : 'warning'} size="xs">{credit.isAvailable ? t('configuration.available') : t('configuration.insufficientBalance')}</Pill>
													</div>
													<div class="grid grid-cols-1 gap-2 sm:grid-cols-3">
														<div class="rounded-lg bg-[var(--color-surface-sunken)] p-3"><div class="text-xs text-[var(--color-ink-2)]">{t('configuration.currentAccountBalance')}</div><div class="mt-1 font-medium tabular-nums text-[var(--color-ink-1)]">{formatBillingAmount(balance.total)} {balance.currency}</div></div>
														<div class="rounded-lg bg-[var(--color-surface-sunken)] p-3"><div class="text-xs text-[var(--color-ink-2)]">{t('configuration.purchasedCredits')}</div><div class="mt-1 font-medium tabular-nums text-[var(--color-ink-1)]">{formatBillingAmount(balance.purchased)} {balance.currency}</div></div>
														<div class="rounded-lg bg-[var(--color-surface-sunken)] p-3"><div class="text-xs text-[var(--color-ink-2)]">{t('configuration.grantedCredits')}</div><div class="mt-1 font-medium tabular-nums text-[var(--color-ink-1)]">{formatBillingAmount(balance.granted)} {balance.currency}</div></div>
													</div>
												</div>
											{/each}
										{/if}
									{:else if credit.kind === 'api_key_limit'}
										<div class="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
											<div class="rounded-lg bg-[var(--color-surface-sunken)] p-3"><div class="text-xs text-[var(--color-ink-2)]">{t('configuration.remainingApiKeyAllowance')}</div><div class="mt-1 font-medium tabular-nums text-[var(--color-ink-1)]">{credit.remaining === null ? t('configuration.unlimited') : `$${formatBillingAmount(credit.remaining)}`}</div></div>
											<div class="rounded-lg bg-[var(--color-surface-sunken)] p-3"><div class="text-xs text-[var(--color-ink-2)]">{t('configuration.apiKeySpendingLimit')}</div><div class="mt-1 font-medium tabular-nums text-[var(--color-ink-1)]">{credit.limit === null ? t('configuration.unlimited') : `$${formatBillingAmount(credit.limit)}`}</div></div>
										</div>
										<p class="mt-2 text-xs text-[var(--color-ink-2)]">{credit.isFreeTier ? t('configuration.freeTierKey') : t('configuration.paidCreditKey')}</p>
									{/if}
								</div>

								<div class="mt-3 grid grid-cols-2 gap-2 lg:grid-cols-4">
									<div class="rounded-lg bg-[var(--color-surface-sunken)] p-3">
										<div class="text-xs text-[var(--color-ink-2)]">{t('configuration.lumenSpendThisMonth')}</div>
										<div class="mt-1 font-medium tabular-nums text-[var(--color-ink-1)]">${formatBillingAmount(billing.local_usage.raw_cost.monthly)}</div>
									</div>
									<div class="rounded-lg bg-[var(--color-surface-sunken)] p-3">
										<div class="text-xs text-[var(--color-ink-2)]">{t('configuration.totalLumenSpend')}</div>
										<div class="mt-1 font-medium tabular-nums text-[var(--color-ink-1)]">${formatBillingAmount(billing.local_usage.raw_cost.total)}</div>
									</div>
									<div class="rounded-lg bg-[var(--color-surface-sunken)] p-3">
										<div class="text-xs text-[var(--color-ink-2)]">{t('configuration.requestsThisMonth')}</div>
										<div class="mt-1 font-medium tabular-nums text-[var(--color-ink-1)]">{t('configuration.requestCount', { v0: Number(billing.local_usage.requests.monthly) })}</div>
									</div>
									<div class="rounded-lg bg-[var(--color-surface-sunken)] p-3">
										<div class="text-xs text-[var(--color-ink-2)]">{t('configuration.tokensThisMonth')}</div>
										<div class="mt-1 font-medium tabular-nums text-[var(--color-ink-1)]">{formatBillingAmount(billing.local_usage.tokens.monthly)}</div>
									</div>
								</div>
								<p class="mt-2 text-xs tabular-nums text-[var(--color-ink-2)]">{t('configuration.lumenLedgerDailyWeekly', { v0: formatBillingAmount(billing.local_usage.raw_cost.daily), v1: formatBillingAmount(billing.local_usage.raw_cost.weekly) })}</p>

								{#if billing.status === 'unavailable' && credit.kind !== 'unavailable'}
									<Alert tone="warning" title={t('configuration.providerUsageLookupFailed')} class="mt-3">{billingFailureLabel(billing.reason)}</Alert>
								{:else if (billing.capability === 'openai_admin_usage' || billing.capability === 'anthropic_admin_usage') && billing.provider_usage}
									{@const providerUsage = billing.provider_usage}
									<div class="mt-3">
										<div class="mb-2 text-xs font-semibold text-[var(--color-ink-2)]">{t('configuration.organizationUsage', { v0: billing.capability === 'openai_admin_usage' ? 'OpenAI' : 'Anthropic' })}</div>
										<div class="grid grid-cols-2 gap-2 lg:grid-cols-4">
											<div class="rounded-lg bg-[var(--color-surface-sunken)] p-3"><div class="text-xs text-[var(--color-ink-2)]">{t('configuration.officialCostThisMonth')}</div><div class="mt-1 font-medium tabular-nums text-[var(--color-ink-1)]">${formatBillingAmount(providerUsage.cost?.monthly ?? null)}</div></div>
											<div class="rounded-lg bg-[var(--color-surface-sunken)] p-3"><div class="text-xs text-[var(--color-ink-2)]">{t('configuration.officialCostThisWeek')}</div><div class="mt-1 font-medium tabular-nums text-[var(--color-ink-1)]">${formatBillingAmount(providerUsage.cost?.weekly ?? null)}</div></div>
											<div class="rounded-lg bg-[var(--color-surface-sunken)] p-3"><div class="text-xs text-[var(--color-ink-2)]">{t('configuration.officialRequestsThisMonth')}</div><div class="mt-1 font-medium tabular-nums text-[var(--color-ink-1)]">{providerUsage.requests ? t('configuration.officialRequestCount', { value: formatBillingAmount(providerUsage.requests.monthly), count: Number(providerUsage.requests.monthly) }) : formatBillingAmount(null)}</div></div>
											<div class="rounded-lg bg-[var(--color-surface-sunken)] p-3"><div class="text-xs text-[var(--color-ink-2)]">{t('configuration.officialTokensThisMonth')}</div><div class="mt-1 font-medium tabular-nums text-[var(--color-ink-1)]">{formatBillingAmount(providerUsage.tokens?.monthly ?? null)}</div></div>
										</div>
										<p class="mt-2 text-xs tabular-nums text-[var(--color-ink-2)]">{t('configuration.officialOrganizationDaily', { v0: formatBillingAmount(providerUsage.cost?.daily ?? null), v1: formatBillingAmount(providerUsage.tokens?.daily ?? null) })}</p>
										{#if billing.reason === 'partial_provider_data'}
											<Alert tone="warning" title={t('configuration.onlySomeOfficialReportsAvailable')} class="mt-3">{t('configuration.oneCostOrUsageReportCouldNotBeRetrieved')}</Alert>
										{/if}
									</div>
								{:else if billing.capability === 'openrouter_key' && billing.status === 'available'}
									<div class="mt-3">
										<div class="mb-2 text-xs font-semibold text-[var(--color-ink-2)]">{t('configuration.openrouterProviderUsage')}</div>
										<div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
											<div class="rounded-lg bg-[var(--color-surface-sunken)] p-3"><div class="text-xs text-[var(--color-ink-2)]">{t('configuration.providerSpendThisMonth')}</div><div class="mt-1 font-medium tabular-nums text-[var(--color-ink-1)]">${formatBillingAmount(billing.usage_monthly)}</div></div>
											<div class="rounded-lg bg-[var(--color-surface-sunken)] p-3"><div class="text-xs text-[var(--color-ink-2)]">{t('configuration.totalProviderSpend')}</div><div class="mt-1 font-medium tabular-nums text-[var(--color-ink-1)]">${formatBillingAmount(billing.usage_total)}</div></div>
										</div>
										<p class="mt-2 text-xs text-[var(--color-ink-2)]">{t('configuration.providerDailyWeekly', { v0: formatBillingAmount(billing.usage_daily), v1: formatBillingAmount(billing.usage_weekly) })}</p>
									</div>
								{/if}

								{#if usageUrl && usageUrl !== billingUrl}
									<div class="mt-3 flex flex-wrap gap-2">
										<Button variant="ghost" size="sm" href={usageUrl} target="_blank">{t('configuration.providerUsage')}</Button>
									</div>
								{/if}
							{/if}
						</div>
					</div>
				{/each}
			</div>
		{/if}
	</section>
	{/if}

	{#if section === 'providers'}
		<FormModal open={editingProvider !== null} title={t('pricing.providerDisplay')} onClose={() => { if (!providerSaving) editingProvider = null; }} onSubmit={saveProviderMetadata} submitLabel={t('configuration.save')} submitting={providerSaving}>
			<div class="space-y-4">
				<p class="text-sm text-[var(--color-ink-2)]">{t('pricing.connectionMethod')}<Pill tone="neutral">{editingProvider?.provider_type}</Pill></p>
				<p class="text-xs text-[var(--color-ink-2)]">{t('pricing.metadataScope')}</p>
				<Alert tone="warning" title={t('pricing.qualifierWarningTitle')}>{t('pricing.qualifierWarning')}</Alert>
				<Field label={t('pricing.displayName')} for="provider-edit-name" required error={providerEditAttempted && !editProviderName.trim() ? t('pricing.nameRequired') : undefined}>
					<TextInput id="provider-edit-name" bind:value={editProviderName} required disabled={providerSaving} ariaInvalid={providerEditAttempted && !editProviderName.trim()} />
				</Field>
				<Field label={t('pricing.apiProviderLabel')} for="provider-edit-api-provider" required help={QUALIFIER_HELP} error={editApiProvider || providerEditAttempted ? qualifierError(editApiProvider) : undefined}>
					<TextInput id="provider-edit-api-provider" bind:value={editApiProvider} required maxlength={40} disabled={providerSaving} ariaInvalid={Boolean(qualifierError(editApiProvider))} />
				</Field>
				<Field label={t('pricing.providerOrder')} for="provider-edit-sort-order" required help={ORDER_HELP} error={editProviderOrder || providerEditAttempted ? orderError(editProviderOrder) : undefined}>
					<TextInput id="provider-edit-sort-order" inputmode="numeric" bind:value={editProviderOrder} required disabled={providerSaving} ariaInvalid={Boolean(orderError(editProviderOrder))} />
				</Field>
				{#if providerEditError}<Alert tone="danger">{providerEditError}</Alert>{/if}
			</div>
			{#snippet actions()}
				<Button variant="secondary" disabled={providerSaving} onclick={() => (editingProvider = null)}>{t('configuration.cancel')}</Button>
				<Button onclick={saveProviderMetadata} disabled={providerSaving} ariaBusy={providerSaving}>{#if providerSaving}<ActivityIndicator size="xs" tone="ink" />{/if}{providerSaving ? t('configuration.saving') : t('configuration.save')}</Button>
			{/snippet}
		</FormModal>

		<FormModal
			bind:open={billingKeyModalOpen}
			title={t('configuration.organizationUsageAdminKey')}
			onClose={closeBillingKeyModal}
			onSubmit={saveBillingAdminKey}
			submitLabel={billingKeyProvider?.has_billing_admin_key ? t('configuration.changeKey') : t('configuration.setKey')}
			submitting={billingKeyBusy}
		>
			<div class="space-y-4">
				<p class="text-sm text-[var(--color-ink-2)]">
					{t('configuration.billingAdminOrganizationReport', { v0: billingKeyProvider?.name ?? '', v1: billingKeyProvider?.provider_type === 'anthropic' ? 'Anthropic Admin API' : 'OpenAI Admin API' })}
				</p>
				<Alert tone="info" title={t('configuration.storedSeparatelyFromTheInferenceKey')}>
					{t('configuration.thisKeyIsUsedOnlyToRetrieveOrganizationUsage')}
				</Alert>
				<Field
					label={billingKeyProvider?.provider_type === 'anthropic' ? t('configuration.anthropicAdminApiKey') : t('configuration.openaiAdminApiKey')}
					for="provider-billing-admin-key"
					help={billingKeyProvider?.has_billing_admin_key ? t('configuration.enterANewKeyToReplaceTheExistingOne') : t('configuration.enterASeparateKeyWithOrganizationAdminPermissions')}
				>
					<TextInput id="provider-billing-admin-key" type="password" placeholder={billingKeyProvider?.has_billing_admin_key ? t('configuration.newKeyOrLeaveBlankToRemove') : t('configuration.adminApiKey')} bind:value={billingAdminKey} />
				</Field>
			</div>
			{#snippet actions()}
				<Button variant="secondary" disabled={billingKeyBusy} onclick={closeBillingKeyModal}>{t('configuration.cancel')}</Button>
				<Button onclick={saveBillingAdminKey} disabled={billingKeyBusy} ariaBusy={billingKeyBusy}>{#if billingKeyBusy}<ActivityIndicator size="xs" tone="ink" />{/if}{billingKeyBusy ? t('configuration.saving') : billingKeyProvider?.has_billing_admin_key ? t('configuration.changeKey') : t('configuration.setKey')}</Button>
			{/snippet}
		</FormModal>

		<Modal bind:open={authModalOpen} onClose={closeSubscriptionAuth} ariaLabel={t('configuration.subscriptionAuthentication')}>
			<div class="max-h-[calc(100vh-2rem)] w-[min(36rem,calc(100vw-2rem))] overflow-y-auto rounded-xl border border-[var(--color-line)] bg-[var(--color-surface-raised)] p-4 shadow-[var(--shadow-restraint)] sm:p-5">
				<div class="flex items-start justify-between gap-3">
					<div>
						<h3 class="text-base font-semibold text-[var(--color-ink-1)]">
							{authProvider && providerAuthMode(authProvider) === 'chatgpt_device' ? t('configuration.connectChatgptSubscription') : t('configuration.registerClaudeSubscriptionToken')}
						</h3>
						<p class="mt-1 text-sm text-[var(--color-ink-3)]">{authProvider?.name}</p>
					</div>
					<Button variant="ghost" size="sm" onclick={closeSubscriptionAuth}>{t('configuration.close')}</Button>
				</div>

				<Alert tone="warning" title={t('configuration.experimentalSharedByAllUsers')} class="mt-4">
					{t('configuration.thisConnectionIsSharedByAllAfterglowUsersUse')}
				</Alert>

				{#if authError}
					<Alert tone="danger" title={t('configuration.cannotContinueAuthentication')} class="mt-3">{authError}</Alert>
				{/if}

				{#if authProvider && providerAuthMode(authProvider) === 'chatgpt_device'}
					<div class="mt-5 space-y-4">
						{#if !deviceAttempt}
							<p class="text-sm leading-6 text-[var(--color-ink-2)]">
								{t('configuration.startingTheConnectionDisplaysAnOpenaiAuthenticationPageAnd')}
							</p>
							<div class="flex flex-wrap justify-end gap-2">
								<Button onclick={startDeviceAuth} disabled={authBusy} ariaBusy={authBusy}>{#if authBusy}<ActivityIndicator size="xs" tone="ink" />{/if}{authBusy ? t('configuration.starting') : t('configuration.connectChatgpt')}</Button>
							</div>
						{:else}
							<div class="rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-sunken)] p-4">
								<div class="flex flex-wrap items-center justify-between gap-2">
									<Pill
										tone={deviceAttempt.status === 'connected'
											? 'success'
											: deviceAttempt.status === 'pending'
												? 'info'
												: 'warning'}
										dot
									>
										{#if deviceAttempt.status === 'pending'}
											<ActivityIndicator variant="dots" size="xs" label={t('configuration.awaitingAuthentication')} />
										{:else}
											{deviceAttempt.status === 'connected' ? t('configuration.connected') : deviceAttempt.status === 'expired' ? t('configuration.authenticationExpired') : deviceAttempt.status === 'cancelled' ? t('configuration.authenticationCanceled') : t('configuration.authenticationError')}
										{/if}
									</Pill>
									<span class="text-xs text-[var(--color-ink-3)]">{t('configuration.deviceCredentialExpiry', { v0: new Date(deviceAttempt.expires_at).toLocaleString(intlLocale()) })}</span>
								</div>
								{#if deviceAttempt.user_code}
									<div class="mt-4">
										<p class="text-xs text-[var(--color-ink-3)]">{t('configuration.oneTimeAuthenticationCode')}</p>
										<div class="mt-1 flex flex-wrap items-center gap-2">
											<code class="rounded bg-[var(--color-surface-base)] px-3 py-2 font-mono text-lg tracking-widest text-[var(--color-ink-0)]">{deviceAttempt.user_code}</code>
											<Button variant="secondary" size="sm" onclick={copyDeviceCode}>{t('configuration.copyCode')}</Button>
										</div>
									</div>
								{/if}
								{#if deviceAttempt.verification_uri && isAllowedVerificationUri(deviceAttempt.verification_uri)}
									<Button class="mt-4" href={deviceAttempt.verification_uri}>{t('configuration.openOpenaiAuthenticationPage')}</Button>
								{:else if deviceAttempt.verification_uri}
									<Alert tone="danger" class="mt-4">{t('configuration.theAuthenticationUrlWasNotOpenedBecauseItIs')}</Alert>
								{/if}
							</div>
							<div class="flex flex-wrap justify-end gap-2">
								{#if deviceAttempt.status === 'pending'}
									<Button variant="secondary" onclick={pollCurrentDeviceAuth} disabled={authBusy} ariaBusy={authBusy && !authCancelling}>
										{#if authBusy && !authCancelling}<ActivityIndicator size="xs" tone="ink" />{/if}{authBusy && !authCancelling ? t('configuration.checking') : t('configuration.checkNow')}
									</Button>
									<Button variant="danger-outline" onclick={cancelDeviceAuth} disabled={authBusy} ariaBusy={authCancelling}>{#if authCancelling}<ActivityIndicator size="xs" tone="ink" />{/if}{authCancelling ? t('configuration.cancelling') : t('configuration.cancelAuthentication')}</Button>
								{:else if deviceAttempt.status !== 'connected'}
									<Button onclick={startDeviceAuth} disabled={authBusy} ariaBusy={authBusy}>{#if authBusy}<ActivityIndicator size="xs" tone="ink" />{/if}{authBusy ? t('configuration.starting') : t('configuration.reconnect')}</Button>
								{/if}
							</div>
						{/if}
					</div>
				{:else if authProvider}
					<div class="mt-5 space-y-4">
						<p class="text-sm leading-6 text-[var(--color-ink-2)]">
							{#snippet rich65markup1(text: string)}<code class="font-mono">{text}</code>{/snippet}<RichText segments={t.rich('configuration.claudeSetupTokenGuidance')} tags={{ markup1: rich65markup1 }} />
						</p>
						<Field label={t('configuration.claudeSetupToken')} for="claude-subscription-token" required>
							<TextInput
								id="claude-subscription-token"
								type="password"
								placeholder="setup-token"
								bind:value={claudeToken}
								required
							/>
						</Field>
						<Field label={t('configuration.expirationTime')} for="claude-subscription-expiry" help={t('configuration.enterOnlyIfTheProviderSpecifiedAnExpirationTime')}>
							<input id="claude-subscription-expiry" class={inputCls} type="datetime-local" bind:value={claudeExpiry} />
						</Field>
						<div class="flex flex-wrap justify-end gap-2">
							<Button variant="secondary" href="https://support.anthropic.com/en/articles/11145838-using-claude-code-with-your-pro-or-max-plan">{t('configuration.officialGuidance')}</Button>
							<Button onclick={saveClaudeSubscription} disabled={authBusy || !claudeToken.trim()} ariaBusy={authBusy}>
								{#if authBusy}<ActivityIndicator size="xs" tone="ink" />{/if}{authBusy ? t('configuration.saving') : authProvider.has_credentials ? t('configuration.replaceToken') : t('configuration.registerSubscriptionToken')}
							</Button>
						</div>
					</div>
				{/if}
			</div>
		</Modal>
	{/if}

	{#if section === 'models'}
	<!-- 모델 -->
	<section>
		<h3 class="mb-1 text-sm font-semibold text-[var(--color-ink-1)]">{t('configuration.models')}</h3>
		<p class="mb-3 text-xs text-[var(--color-ink-3)]">
			{t('configuration.apiModelIdsAreUsedForExternalOpenaiAnd')}
		</p>
		<div class="{cardCls} mb-4 p-5">
			<div class="flex flex-col gap-3 sm:flex-row sm:items-center">
				<select class={inputCls} aria-label={t('configuration.discoveryProvider')} bind:value={mProviderId} onchange={resetDiscovery}>
					<option value="">{t('configuration.selectProvider')}</option>
					{#each providers as p (p.id)}
						<option value={p.id}>{p.name}</option>
					{/each}
				</select>
				<div class="flex shrink-0 gap-2">
					<Button
						variant="secondary"
						onclick={() => {
							if (!mProviderId) return toast.error(t('configuration.selectAProvider'));
							void discover(mProviderId);
						}}
						disabled={!mProviderId || discovering}
						ariaBusy={discovering}
					>
						{#if discovering}<ActivityIndicator size="xs" tone="ink" />{/if}{discovering ? t('configuration.fetching') : t('configuration.loadModels')}
					</Button>
					<Button
						variant="secondary"
						onclick={() => {
							const provider = providers.find((p) => p.id === mProviderId);
							if (provider) void openModelsDev(provider);
						}}
						disabled={!mProviderId}
					>
						{t('configuration.modelsDevPricing')}
					</Button>
				</div>
			</div>
			<p class="mt-2 text-xs text-[var(--color-ink-2)]">{t('pricing.discoveryGuidance')}</p>
			{#if discoverId === mProviderId && discoverId !== null}
				<div class="mt-4 border-t border-[var(--color-line)] pt-4" data-testid="model-discovery">
					<div class="mb-3 flex flex-wrap items-center justify-between gap-2">
						<p class="text-sm font-semibold text-[var(--color-ink-1)]">{t('configuration.discoveredCandidates', { v0: providerName(discoverId) })}</p>
						<div class="flex gap-2">
							<Button variant="secondary" size="sm" onclick={retryDiscovery} disabled={discovering || registeringBulk} ariaBusy={discovering}>{#if discovering}<ActivityIndicator size="xs" tone="ink" />{/if}{discovering ? t('configuration.fetching') : t('configuration.fetchAgain')}</Button>
							<Button variant="ghost" size="sm" onclick={resetDiscovery}>{t('configuration.closeDiscovery')}</Button>
						</div>
					</div>
					{#if discovering}
						<ActivityIndicator label={t('configuration.loadingModelList')} class="text-sm text-ink-2" />
					{:else if discoveryError}
						<Alert tone="warning">{discoveryError}</Alert>
					{:else if discovery}
						<p class="mb-3 text-xs text-[var(--color-ink-2)]" data-testid="discovery-provenance">
							{t('configuration.discoveryProvenance', { v0: discovery.source === 'api' ? t('configuration.providerApi') : discovery.source === 'litellm' ? t('configuration.litellmStaticList') : t('configuration.noListProvided'), v1: discovery.live_status === 'success' ? t('configuration.responseReceived') : discovery.live_status === 'empty' ? t('configuration.successfulEmptyResult') : discovery.live_status === 'unsupported' ? t('configuration.unsupported') : discovery.live_status === 'error' ? t('configuration.failed') : t('configuration.statusUnknown'), v2: discovery.complete === true ? t('configuration.complete') : discovery.complete === false ? t('configuration.incomplete') : t('configuration.unknown') })}
							{#if discovery.fetched_at} {t('configuration.discoveryFetchedAt', { v0: new Date(discovery.fetched_at).toLocaleString(intlLocale()) })}{/if}
							{t('configuration.discoveryModelCounts', { v0: formatNumber(discovery.models.length), v1: formatNumber(filteredAvailable.length) })}
						</p>
						{#if discovery.error}
							<Alert tone="warning" class="mb-3">{discovery.error.message} {discovery.error.retryable ? t('configuration.youCanFetchAgain') : t('configuration.checkTheConnectionSettings')}</Alert>
						{/if}
						{#if discovery.live_status === 'error' && !discovery.error}
							<Alert tone="warning" class="mb-3">{t('configuration.liveModelLookupFailedCheckTheConnectionAndFetch')}</Alert>
						{/if}
						{#if discovery.live_status === 'empty' && discovery.models.length === 0}
							<Alert tone="info">{t('configuration.theLookupSucceededButReturnedNoModelsAddThem')}</Alert>
						{:else if discovery.live_status === 'unsupported' && discovery.models.length === 0}
							<Alert tone="info">{t('configuration.thisProviderDoesNotSupportModelLookupYouCan')}</Alert>
						{:else if discovery.models.length === 0 && !discovery.error && discovery.live_status !== 'error'}
							<Alert tone="info">{t('configuration.noCandidatesProvidedCheckTheLookupStatusOrAdd')}</Alert>
						{/if}
						{#if discovery.models.length > 0 && discovery.live_status !== 'error'}
							<Alert tone="info" class="mb-3">{t('configuration.discoveryCandidatesDoNotVerifyPricingOrExecutionSupport')}</Alert>
							{#if isSubscriptionProviderId(mProviderId)}
								<Alert tone="info" class="mb-3">{t('configuration.theseAreSubscriptionCatalogCandidatesAvailabilityUnderYourCurrent')}</Alert>
							{/if}
							<div class="mb-3 flex flex-wrap gap-3 text-xs">
								<Button variant="ghost" size="xs" onclick={() => toggleAllFiltered(true)}>{t('configuration.selectAll')}</Button>
								<Button variant="ghost" size="xs" onclick={() => toggleAllFiltered(false)}>{t('configuration.clearSelection')}</Button>
							</div>
							<div class="mb-3">
								<Field label={t('configuration.filterCandidateModels')} for="discovery-candidate-filter">
									<TextInput id="discovery-candidate-filter" type="search" placeholder={t('configuration.searchModelIdOrDisplayName')} bind:value={availFilter} oninput={() => (selectedAvail = {})} disabled={registeringBulk} />
								</Field>
								<Field label={t('pricing.candidateKindFilter')} for="discovery-kind-filter">
									<SelectInput id="discovery-kind-filter" value={availKind} disabled={registeringBulk} onchange={(event) => { availKind = (event.target as HTMLSelectElement).value as typeof availKind; selectedAvail = {}; }}>
										<option value="">{t('pricing.allKinds')}</option>
										{#each Object.entries(MEDIA_LABELS) as [kind, label]}<option value={kind}>{label}</option>{/each}
										<option value="unknown">{t('pricing.unknownKind')}</option>
									</SelectInput>
								</Field>
							</div>
							<div class="max-h-64 space-y-1 overflow-y-auto rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-base)] p-2">
								{#each filteredAvailable as candidate (candidate.id)}
									<label class="flex items-start gap-2 rounded-md px-2 py-2 text-sm text-[var(--color-ink-1)] hover:bg-[var(--color-surface-selected)]">
										<input class="mt-1" type="checkbox" aria-label={candidate.id} disabled={registeringBulk} bind:checked={selectedAvail[candidate.id]} />
										<span class="min-w-0 break-all"><span class="block font-mono">{candidate.id}</span>
											{#if candidate.display_name}<span class="block text-xs text-[var(--color-ink-2)]">{candidate.display_name}</span>{/if}
											<span class="block text-xs text-[var(--color-ink-2)]">{t('pricing.candidateReadiness', { kind: candidate.model_kind ? MEDIA_LABELS[candidate.model_kind] : candidate.purpose === 'chat' ? t('pricing.textCandidate') : t('pricing.unknownKind') })}</span>
										</span>
									</label>
								{:else}
									<EmptyState headline={t('configuration.noUnregisteredModelsMatchTheFilters')} class="py-4 [&_.motion-enter]:animate-none" />
								{/each}
							</div>
							<div class="mt-3 flex justify-end">
								<Button onclick={reviewSelected} disabled={registeringBulk}>{t('configuration.reviewSelectedModels')}</Button>
							</div>
						{/if}
					{/if}
				</div>
			{/if}
		</div>
		<div class="{cardCls} mb-4 p-5">
			<div class="grid grid-cols-1 gap-3 md:grid-cols-3">
				<select class={inputCls} aria-label={t('configuration.providerForManualRegistration')} bind:value={mProviderId} onchange={resetDiscovery}>
					<option value="">{t('configuration.selectProvider')}</option>
					{#each providers as p (p.id)}
						<option value={p.id}>{p.name}</option>
					{/each}
				</select>
				<select class={inputCls} aria-label={t('configuration.modelType')} value={mKind} onchange={(event) => (mKind = event.currentTarget.value as ModelKind)}>
					{#each Object.entries(MEDIA_LABELS) as [kind, label]}
						<option value={kind}>{label}</option>
					{/each}
				</select>
				<input class={inputCls} placeholder={t('configuration.modelNameEGGpt4o')} bind:value={mName} />
				<input class={inputCls} placeholder={t('configuration.displayNameOptional')} bind:value={mDisplay} />
			</div>
			<p class="mt-3 text-sm font-semibold text-[var(--color-ink-1)]">{t('pricing.textTokenRates')}</p>
			<div class="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
				<input class={inputCls} inputmode="decimal" placeholder={t('configuration.inputPriceUsd1mTokens')} bind:value={mInputPrice} />
				<input class={inputCls} inputmode="decimal" placeholder={t('configuration.outputPriceUsd1mTokens')} bind:value={mOutputPrice} />
			</div>
			{#if mKind !== 'text' && mProviderId && !mediaProviderSupported(mProviderId)}
				<Alert tone="warning" class="mt-3">{t('configuration.mediaModelsCanOnlyBeRegisteredWithDirectlyConnected')}</Alert>
			{/if}
			<ModelMediaPricingEditor kind={mKind} bind:draft={mPricing} prefix="model-create" disabled={addingModel} />
			{#if cachePricingAvailable}
			<div class="mt-4 border-t border-[var(--color-line)] pt-4" role="group" aria-labelledby="model-create-cache-heading" data-testid="model-create-cache-prices">
				<p id="model-create-cache-heading" class="text-xs font-semibold text-[var(--color-ink-1)]">{t('configuration.promptCacheRatesOptional')}</p>
				<p class="mt-1 text-xs leading-relaxed text-[var(--color-ink-2)]">
					{mKind === 'text' ? t('configuration.eachRateIsSavedSeparatelyFromInputAndOutput') : t('pricing.mediaCacheCreateHelp')}
				</p>
				<div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
					{#each CACHE_PRICE_FIELDS as field (field.key)}
						<Field label={field.label} for="model-create-cache-{field.slug}" help={t('configuration.usd1mTokens')} error={mCacheErrors[field.key]}>
							<TextInput
								id="model-create-cache-{field.slug}"
								inputmode="decimal"
								placeholder={t('configuration.eG03')}
								bind:value={mCachePrices[field.key]}
								ariaInvalid={Boolean(mCacheErrors[field.key])}
								oninput={(event) => (mCacheErrors = recheckCachePrice(mCacheErrors, field.key, (event.currentTarget as HTMLInputElement).value))}
							/>
						</Field>
					{/each}
				</div>
			</div>
			{/if}
			<div class="mt-3 flex justify-end">
				<Button onclick={addModel} disabled={addingModel || providers.length === 0 || (mKind !== 'text' && !!mProviderId && !mediaProviderSupported(mProviderId))} ariaBusy={addingModel}>
					{#if addingModel}<ActivityIndicator size="xs" tone="ink" />{/if}{addingModel ? t('configuration.adding') : t('configuration.addModel')}
				</Button>
			</div>
		</div>

		<div class="mb-3">
			<Field label={t('pricing.registeredProviderFilter')} for="registered-model-provider" help={t('pricing.registeredProviderHelp')}>
				<SelectInput id="registered-model-provider" bind:value={registeredProviderId} onchange={changeRegisteredProvider} disabled={deletingBulk || modelOrderSaving}>
					<option value="">{t('pricing.allProviders')}</option>
					{#each providers as provider (provider.id)}<option value={String(provider.id)}>{provider.name}</option>{/each}
				</SelectInput>
			</Field>
			<Field label={t('pricing.registeredKindFilter')} for="registered-model-kind">
				<SelectInput id="registered-model-kind" value={registeredKind} disabled={deletingBulk || modelOrderSaving} onchange={(event) => { registeredKind = (event.target as HTMLSelectElement).value as typeof registeredKind; selectedModelIds = {}; resetModelDrag(); }}>
					<option value="">{t('pricing.allKinds')}</option>
					{#each Object.entries(MEDIA_LABELS) as [kind, label]}<option value={kind}>{label}</option>{/each}
				</SelectInput>
			</Field>
			<p class="mt-2 text-xs text-[var(--color-ink-2)]">{t('pricing.registeredCount', { visible: formatNumber(visibleModels.length), total: formatNumber(models.length) })}</p>
			<p id="model-reorder-help" class="mt-1 text-xs text-[var(--color-ink-2)]">{t('pricing.modelReorderHelp')}</p>
			<p role="status" aria-live="polite" class="mt-1 text-xs text-[var(--color-ink-2)]">{modelOrderStatus}</p>
			{#if modelOrderSaveError}<Alert tone="danger" class="mt-2">{modelOrderSaveError}</Alert>{/if}
		</div>
		{#if loading}
			<div class="{cardCls} h-20 motion-skeleton" role="status" aria-busy="true" aria-label={t('configuration.loadingModels')}><span class="sr-only">{t('configuration.loadingModels')}</span></div>
		{:else if visibleModels.length === 0}
			<EmptyState headline={registeredProviderId ? t('pricing.providerEmpty') : t('configuration.noModelsRegistered')} class="py-4 [&_.motion-enter]:animate-none" />
		{:else}
			<div class="mb-2 flex items-center justify-between gap-3 px-1">
				<label class="flex cursor-pointer items-center gap-2 text-xs text-[var(--color-ink-2)]">
					<input
						type="checkbox"
						checked={allModelsSelected}
						disabled={deletingBulk || modelOrderSaving}
						onchange={(e) => toggleAllModels(e.currentTarget.checked)}
					/>
					{t('configuration.selectAllWithCount', { v0: selectedCount > 0 ? ` (${formatNumber(selectedCount)})` : '' })}
				</label>
				{#if selectedCount > 0}
					<Button variant="danger-outline" size="sm" onclick={deleteSelectedModels} disabled={deletingBulk || modelOrderSaving} ariaBusy={deletingBulk}>
						{#if deletingBulk}<ActivityIndicator size="xs" tone="ink" />{/if}{deletingBulk ? t('configuration.deleting') : t('configuration.deleteSelected', { v0: formatNumber(selectedCount) })}
					</Button>
				{/if}
			</div>
			<ul class="space-y-2" aria-label={t('pricing.registeredModelOrder')} aria-busy={modelOrderSaving}>
				{#each visibleModels as m (m.id)}
					{@const siblings = modelSiblings(m)}
					{@const siblingIndex = siblings.findIndex((row) => row.id === m.id)}
					<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
					<li
						class="{cardCls} model-card flex flex-col items-stretch gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
						data-model-id={m.id}
						draggable={!modelOrderBusy && siblings.length > 1}
						data-dragging={draggedModelId === m.id}
						data-drop-edge={modelDropTarget?.id === m.id ? modelDropTarget.edge : undefined}
						aria-describedby="model-reorder-help"
						ondragstart={(event) => startModelDrag(event, m)}
						onpointerdown={(event) => handleModelPointerDown(event, m)}
						onmousedown={(event) => handleModelPointerDown(event, m)}
						ondragover={(event) => allowModelDrop(event, m)}
						ondragleave={(event) => { if (!(event.relatedTarget instanceof Node) || !event.currentTarget.contains(event.relatedTarget)) modelDropTarget = null; }}
						ondrop={(event) => dropModel(event, m)}
						ondragend={resetModelDrag}
					>
						<div class="flex min-w-0 items-start gap-3">
							<div class="flex shrink-0 flex-col items-center text-[var(--color-ink-3)]" role="group" aria-label={t('pricing.moveModelOrder', { name: displayModelTitle(m) })}>
								<svg class="mb-1 h-5 w-5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="9" cy="5" r="1.5" /><circle cx="15" cy="5" r="1.5" /><circle cx="9" cy="12" r="1.5" /><circle cx="15" cy="12" r="1.5" /><circle cx="9" cy="19" r="1.5" /><circle cx="15" cy="19" r="1.5" /></svg>
								<span data-model-move="up"><Button variant="ghost" size="xs" class="!h-11 !w-11 !p-0" ariaLabel={t('pricing.moveModelUp', { name: displayModelTitle(m) })} title={t('pricing.moveUp')} disabled={modelOrderBusy || siblingIndex === 0} onclick={() => moveModel(m, 'up')}><svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="m6 12 6-6 6 6M12 6v12" /></svg></Button></span>
								<span data-model-move="down"><Button variant="ghost" size="xs" class="!h-11 !w-11 !p-0" ariaLabel={t('pricing.moveModelDown', { name: displayModelTitle(m) })} title={t('pricing.moveDown')} disabled={modelOrderBusy || siblingIndex === siblings.length - 1} onclick={() => moveModel(m, 'down')}><svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="m6 12 6 6 6-6M12 6v12" /></svg></Button></span>
							</div>
							<input class="mt-0.5 shrink-0" type="checkbox" disabled={deletingBulk || modelOrderSaving} bind:checked={selectedModelIds[m.id]} aria-label={t('configuration.selectModel', { v0: m.display_name || publicModelName(m) })} />
							<div class="min-w-0 flex-1">
							<div class="flex flex-wrap items-center gap-2">
								<span class="truncate text-sm font-medium text-[var(--color-ink-1)]">{displayModelTitle(m)}</span>
							<Pill tone={m.is_active ? 'success' : 'neutral'} size="xs">{(m.model_kind ?? 'text') === 'text' ? (m.is_active ? t('configuration.activeSaved') : t('configuration.inactiveSaved')) : (m.is_active ? t('configuration.adminEnabledExecutionSeparate') : t('configuration.adminDisabledSaved'))}</Pill>
							<Pill tone="neutral" size="xs">{MEDIA_LABELS[m.model_kind ?? 'text']}</Pill>
								{#if m.is_title_model}
									<span class="rounded bg-[var(--color-accent)]/15 px-1.5 py-0.5 text-xs text-[var(--color-accent)]">
										{t('configuration.titleGeneration')}
									</span>
								{/if}
							{#if (m.model_kind ?? 'text') === 'text'}
								<Pill tone={m.price_source === 'manual' ? 'success' : m.price_source === 'models.dev' ? 'accent' : 'neutral'} size="xs">
									{m.price_source === 'manual' ? t('configuration.manual') : m.price_source === 'models.dev' ? 'models.dev' : m.effective_price_source?.startsWith('perplexity_agent_api_') ? t('configuration.officialPerplexityPricing') : m.effective_price_source === 'litellm' ? t('configuration.litellmDefaults') : t('configuration.pricingSourceUnknown')}
								</Pill>
								<Pill tone={m.effective_input_price_per_million != null && m.effective_output_price_per_million != null ? 'accent' : 'warning'} size="xs">
									{m.effective_input_price_per_million != null && m.effective_output_price_per_million != null ? t('configuration.defaultTextRatesShown') : t('configuration.pricingUnverified')}
								</Pill>
								<Pill tone={capabilityState(m) === 'unknown' ? 'neutral' : 'accent'} size="xs">{capabilityStatus(m)}</Pill>
								<ModelCapabilityBadges caps={m.capabilities || m.effective_capabilities} size="xs" />
							{:else}
								<Pill tone={hasMediaPrices(m.media_pricing) ? 'accent' : 'warning'} size="xs">{hasMediaPrices(m.media_pricing) ? t('configuration.mediaRatesConfigured') : t('configuration.mediaRatesUnset')}</Pill>
								<Pill tone="warning" size="xs">{mediaReadiness(m)}</Pill>
							{/if}
							</div>
							<div class="mt-0.5 text-xs text-[var(--color-ink-3)]">
								<div class="break-all"><RichText segments={t.rich('pricing.apiIdentity', { id: publicModelName(m), provider: m.api_provider })} /></div>
								{#if m.model_name !== publicModelName(m)}
									<div class="mt-0.5 break-all">{#snippet rich103markup1(text: string)}<code class="font-mono">{text}</code>{/snippet}<RichText segments={t.rich('configuration.internalRoutingIdentifier', { v0: m.model_name })} tags={{ markup1: rich103markup1 }} /></div>
								{/if}
								<div class="mt-0.5">{providerName(m.provider_id)}</div>
								<div class="mt-0.5">{t('pricing.displayOrder', { order: formatNumber(m.sort_order ?? 0) })}</div>
							</div>
							<div class="mt-1 text-xs text-[var(--color-ink-2)]">
								{t((m.model_kind ?? 'text') === 'text' ? 'configuration.inputOutputPriceSummary' : 'pricing.mediaTextSummary', (m.model_kind ?? 'text') === 'text' ? { v0: displayPrice(m.effective_input_price_per_million), v1: displayPrice(m.effective_output_price_per_million) } : { input: displayPrice(m.effective_input_price_per_million ?? m.input_price_per_million), output: displayPrice(m.effective_output_price_per_million ?? m.output_price_per_million) })}
							</div>
							{#if !cachePricingSupported(m)}
								<div class="mt-0.5 text-xs text-[var(--color-ink-2)]" data-testid="model-cache-prices">
									{t('configuration.cacheRatesUnsupportedThisLumenVersionDoesNotAccept')}
								</div>
							{:else if cachePriceState(m) === 'none'}
								<div class="mt-0.5 text-xs text-[var(--color-ink-2)]" data-testid="model-cache-prices">
									{(m.model_kind ?? 'text') === 'text' ? t('configuration.cacheRatesUnsetCacheTokensAreBilledAt0') : t('pricing.mediaCacheUnset')}
								</div>
							{:else}
								<div class="mt-0.5 text-xs tabular-nums text-[var(--color-ink-2)]" data-testid="model-cache-prices">
									{t('configuration.cachePriceSummary', { v0: formatCachePrice(m.cache_read_price_per_million), v1: formatCachePrice(m.cache_write_price_per_million), v2: formatCachePrice(m.cache_write_1h_price_per_million), v3: cachePriceState(m) === 'partial' ? (m.model_kind ?? 'text') === 'text' ? t('configuration.unsetRatesAreBilledAt0Usd') : t('pricing.mediaCachePartial') : '' })}
								</div>
							{/if}
							{#if (m.model_kind ?? 'text') !== 'text' || m.media_pricing?.token_rates}
								<div class="mt-1 break-words text-xs text-[var(--color-ink-2)]" data-testid="model-media-prices">{mediaPriceSummary(m)}</div>
								{#if (m.model_kind ?? 'text') !== 'text'}<div class="mt-0.5 text-xs text-[var(--color-ink-2)]">{t('configuration.mediaCapabilityExecutionWarning', { v0: mediaCapability(m) })}</div>{/if}
							{/if}
						</div>
						</div>
						<div class="flex flex-wrap items-center justify-end gap-x-3 gap-y-2 border-t border-[var(--color-line)] pt-3 text-xs sm:shrink-0 sm:border-t-0 sm:pt-0">
							{#if (m.model_kind ?? 'text') === 'text'}
								<button class={rowActionCls} disabled={modelOrderSaving} onclick={() => setTitleModel(m)}>
									{m.is_title_model ? t('configuration.unassignTitleModel') : t('configuration.assignTitleModel')}
								</button>
							{/if}
							<button class={rowActionCls} disabled={modelOrderSaving} onclick={() => openPriceEditor(m)}>{t('configuration.editPricing')}</button>
							{#if (m.model_kind ?? 'text') === 'text'}<Button variant="ghost" size="xs" disabled={modelOrderSaving} onclick={() => openCapabilityEditor(m)}>{t('configuration.editCapabilities')}</Button>{/if}
							<button class={rowActionCls} disabled={modelOrderSaving} onclick={() => toggleModel(m)}>{m.is_active ? t('configuration.deactivate') : t('configuration.activate')}</button>
							<button class="text-[var(--color-state-danger)] transition-opacity hover:opacity-80" disabled={modelOrderSaving} onclick={() => deleteModel(m.id)}>{t('configuration.delete')}</button>
						</div>
					</li>
				{/each}
			</ul>
		{/if}
	</section>
	{/if}

	{#if section === 'models'}
	<Modal open={registrationReview !== null} onClose={() => { if (!registeringBulk) registrationReview = null; }} dismissible={!registeringBulk} ariaLabel={t('configuration.reviewModelRegistration')}>
		<div class="max-h-[calc(100vh-2rem)] w-[min(32rem,calc(100vw-2rem))] overflow-y-auto rounded-xl border border-[var(--color-line)] bg-[var(--color-surface-raised)] p-5 shadow-[var(--shadow-restraint)]" data-testid="model-registration-review">
			<h3 class="text-base font-semibold text-[var(--color-ink-1)]">{t('configuration.reviewModelRegistration')}</h3>
			{#if registrationReview}
				<p class="mt-2 text-sm text-[var(--color-ink-2)]">{t('configuration.registrationReviewProviderCount', { v0: registrationReview.providerName, v1: formatNumber(registrationReview.entries.length) })}</p>
				<Alert tone="warning" class="mt-3">{t('pricing.registrationGuidance')}</Alert>
				<div class="mt-4 max-h-[min(50vh,28rem)] space-y-3 overflow-y-auto">
					{#each registrationReview.entries as entry, index (entry.name)}
						<div class="rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-base)] p-3" data-testid="registration-entry">
							<p class="break-all font-mono text-sm text-[var(--color-ink-1)]">{entry.name}</p>
							<p class="mt-1 text-xs text-[var(--color-ink-2)]">
								{t('configuration.registrationReportedLimits', { v0: entry.purpose === 'unknown' ? t('pricing.candidateReadiness', { kind: t('pricing.unknownPurpose') }) : entry.purpose === 'non_chat' ? t('pricing.candidateReadiness', { kind: t('pricing.nonChatPurpose') }) : t('configuration.reviewChatCandidate'), v1: entry.inputTokenLimit == null ? t('configuration.unknown') : formatNumber(entry.inputTokenLimit), v2: entry.outputTokenLimit == null ? t('configuration.unknown') : formatNumber(entry.outputTokenLimit) })}
							</p>
							{#if registrationOutcomes[entry.name] === 'success'}
								<Pill tone="success" size="sm">{t('configuration.registeredNoRepeatRequest')}</Pill>
							{:else}
								{#if registrationOutcomes[entry.name] === 'failed'}<Pill tone="warning" size="sm">{t('configuration.registrationFailedRetryThisModelOnly')}</Pill>{/if}
								<div class="mt-3 grid gap-3 sm:grid-cols-2">
									<div class="sm:col-span-2">
										<Field label={t('configuration.reviewDisplayName', { v0: entry.name })} for="review-display-{index}">
											<TextInput id="review-display-{index}" placeholder={t('configuration.optional')} bind:value={entry.displayName} disabled={registeringBulk} />
										</Field>
									</div>
									<Field label={t('pricing.reviewKind', { name: entry.name })} for="review-kind-{index}" error={reviewPriceError(entry)}>
										<SelectInput id="review-kind-{index}" bind:value={entry.kind} disabled={registeringBulk}>
											<option value="">{t('pricing.selectKind')}</option>
											{#each Object.entries(MEDIA_LABELS) as [kind, label]}<option value={kind}>{label}</option>{/each}
										</SelectInput>
									</Field>
									<Field label={t('configuration.reviewInputPrice', { v0: entry.name })} for="review-input-{index}" help={t('configuration.usd1mTokens')} error={reviewPriceError(entry)}>
										<TextInput id="review-input-{index}" inputmode="decimal" placeholder={t('configuration.eG2')} bind:value={entry.inputPrice} disabled={registeringBulk} ariaInvalid={Boolean(reviewPriceError(entry))} />
									</Field>
									<Field label={t('configuration.reviewOutputPrice', { v0: entry.name })} for="review-output-{index}" help={t('configuration.usd1mTokens')} error={reviewPriceError(entry)}>
										<TextInput id="review-output-{index}" inputmode="decimal" placeholder={t('configuration.eG8')} bind:value={entry.outputPrice} disabled={registeringBulk} ariaInvalid={Boolean(reviewPriceError(entry))} />
									</Field>
								</div>
							{/if}
						</div>
					{/each}
				</div>
				<div class="mt-5 flex flex-wrap justify-end gap-2">
					<Button variant="secondary" onclick={() => (registrationReview = null)} disabled={registeringBulk}>{t('configuration.cancel')}</Button>
					<Button onclick={() => registerSelected(false)} disabled={registeringBulk || registrationMode === 'active' || registrationReview.entries.some((entry) => registrationOutcomes[entry.name] !== 'success' && Boolean(reviewPriceError(entry)))} ariaBusy={registeringBulk && registrationMode === 'inactive'}>{#if registeringBulk && registrationMode === 'inactive'}<ActivityIndicator size="xs" tone="ink" />{/if}{registeringBulk && registrationMode === 'inactive' ? t('configuration.registering') : t('configuration.saveAsInactive')}</Button>
					<Button variant="accent" onclick={() => registerSelected(true)} disabled={registeringBulk || registrationMode === 'inactive' || !reviewCanActivate(registrationReview)} ariaBusy={registeringBulk && registrationMode === 'active'}>{#if registeringBulk && registrationMode === 'active'}<ActivityIndicator size="xs" tone="ink" />{/if}{registeringBulk && registrationMode === 'active' ? t('configuration.registeringAndActivating') : t('configuration.confirmPricingRegisterAndActivate')}</Button>
				</div>
			{/if}
		</div>
	</Modal>

	<Modal open={editingPrice !== null} onClose={() => { if (!priceSaving) editingPrice = null; }} dismissible={!priceSaving} ariaLabel={t('configuration.editModelPricing')}>
		<div class="max-h-[calc(100vh-2rem)] w-[min(32rem,calc(100vw-2rem))] overflow-y-auto rounded-xl border border-[var(--color-line)] bg-[var(--color-surface-raised)] p-5 shadow-[var(--shadow-restraint)]">
			<h3 class="text-base font-semibold text-[var(--color-ink-1)]">{t('configuration.editModelPricing')}</h3>
			<p class="mt-1 text-sm text-[var(--color-ink-2)]">{MEDIA_LABELS[editingPrice?.model_kind ?? 'text']} · {editingPrice ? displayModelTitle(editingPrice) : ''}</p>
			{#if editingPrice}
			<p class="mt-3 text-sm font-semibold text-[var(--color-ink-1)]">{t('pricing.textTokenRates')}</p>
				<p class="mt-1 text-sm text-[var(--color-ink-2)]">{t('pricing.independentTextEditHelp')}</p>
			<div class="mt-4 grid gap-3 sm:grid-cols-2">
				<Field label={t('configuration.input')} for="model-edit-input-price">
					<TextInput id="model-edit-input-price" inputmode="decimal" placeholder={t('configuration.usd1mTokens')} bind:value={editInputPrice} disabled={priceSaving} />
				</Field>
				<Field label={t('configuration.output')} for="model-edit-output-price">
					<TextInput id="model-edit-output-price" inputmode="decimal" placeholder={t('configuration.usd1mTokens')} bind:value={editOutputPrice} disabled={priceSaving} />
				</Field>
			</div>
			{#if editingPrice && cachePricingSupported(editingPrice)}
			<div class="mt-4 border-t border-[var(--color-line)] pt-4" role="group" aria-labelledby="model-edit-cache-heading">
				<p id="model-edit-cache-heading" class="text-sm font-semibold text-[var(--color-ink-1)]">{t('configuration.promptCacheRatesOptional')}</p>
				<p class="mt-1 text-xs leading-relaxed text-[var(--color-ink-2)]">
					{(editingPrice.model_kind ?? 'text') === 'text' ? t('configuration.eachRateIsSavedIndependentlyInputAndOutputPrices') : t('pricing.mediaCacheEditHelp')}
				</p>
				<div class="mt-3 grid gap-3 sm:grid-cols-3">
					{#each CACHE_PRICE_FIELDS as field (field.key)}
						<Field label={field.label} for="model-edit-cache-{field.slug}" help={t('configuration.usd1mTokens')} error={editCacheErrors[field.key]}>
							<TextInput
								id="model-edit-cache-{field.slug}"
								inputmode="decimal"
								placeholder={t('configuration.eG03')}
								bind:value={editCachePrices[field.key]}
								disabled={priceSaving}
								ariaInvalid={Boolean(editCacheErrors[field.key])}
								oninput={(event) => (editCacheErrors = recheckCachePrice(editCacheErrors, field.key, (event.currentTarget as HTMLInputElement).value))}
							/>
						</Field>
					{/each}
				</div>
			</div>
			{/if}
			<ModelMediaPricingEditor kind={editingPrice.model_kind ?? 'text'} bind:draft={editPricing} prefix="model-edit" disabled={priceSaving} />
			{/if}
			<div class="mt-5 flex justify-end gap-2">
				<Button variant="secondary" disabled={priceSaving} onclick={() => (editingPrice = null)}>{t('configuration.cancel')}</Button>
				<Button onclick={savePrice} disabled={priceSaving} ariaBusy={priceSaving}>{#if priceSaving}<ActivityIndicator size="xs" tone="ink" />{/if}{priceSaving ? t('configuration.saving') : t('configuration.save')}</Button>
			</div>
		</div>
	</Modal>

	<Modal open={editingCapabilities !== null} onClose={() => { if (!capSaving) editingCapabilities = null; }} dismissible={!capSaving} ariaLabel={t('configuration.editModelCapabilities')}>
		<div class="max-h-[calc(100vh-2rem)] w-[min(32rem,calc(100vw-2rem))] overflow-y-auto rounded-xl border border-[var(--color-line)] bg-[var(--color-surface-raised)] p-5 shadow-[var(--shadow-restraint)]">
			<h3 class="text-base font-semibold text-[var(--color-ink-1)]">{t('configuration.editModelCapabilities')}</h3>
			{#if editingCapabilities}
				<p class="mt-2 break-all font-mono text-sm text-[var(--color-ink-1)]">{editingCapabilities.model_name}</p>
				<Alert tone="warning" class="mt-3">{t('configuration.capabilitySourceGuidance', { v0: editingCapabilities.effective_capability_source ?? t('configuration.unknown') })}</Alert>
				{#if capSuggestedInputLimit !== null}
					<p class="mt-3 text-sm text-[var(--color-ink-2)]">{t('configuration.candidateContextLimitGuidance', { v0: formatNumber(capSuggestedInputLimit) })}</p>
				{/if}
				<div class="mt-4 grid gap-3 sm:grid-cols-2">
					<label class="flex items-center gap-2 text-sm text-[var(--color-ink-1)]"><input type="checkbox" bind:checked={capVision} disabled={capSaving} />{t('configuration.imageInputVision')}</label>
					<label class="flex items-center gap-2 text-sm text-[var(--color-ink-1)]"><input type="checkbox" bind:checked={capReasoning} disabled={capSaving} />{t('configuration.reasoning')}</label>
					<label class="flex items-center gap-2 text-sm text-[var(--color-ink-1)]"><input type="checkbox" bind:checked={capToolCall} disabled={capSaving} />{t('configuration.toolCalls')}</label>
					<label class="flex items-center gap-2 text-sm text-[var(--color-ink-1)]"><input type="checkbox" bind:checked={capAttachment} disabled={capSaving} />{t('configuration.fileAttachments')}</label>
				</div>
				<div class="mt-4">
					<Field label={t('configuration.contextLimit')} for="model-capability-context" help={t('configuration.totalContextTokensLeaveBlankIfUnknown')} error={contextLimitError(capContextLimit)}>
						<TextInput id="model-capability-context" inputmode="numeric" placeholder={t('configuration.eG128000')} bind:value={capContextLimit} disabled={capSaving} ariaInvalid={Boolean(contextLimitError(capContextLimit))} />
					</Field>
				</div>
				{#if capError}<Alert tone="warning" class="mt-3">{capError}</Alert>{/if}
				<div class="mt-5 flex justify-end gap-2">
					<Button variant="secondary" onclick={() => (editingCapabilities = null)} disabled={capSaving}>{t('configuration.cancel')}</Button>
					<Button onclick={saveCapabilities} disabled={capSaving || Boolean(contextLimitError(capContextLimit))} ariaBusy={capSaving}>{#if capSaving}<ActivityIndicator size="xs" tone="ink" />{/if}{capSaving ? t('configuration.saving') : t('configuration.saveCapabilities')}</Button>
				</div>
			{/if}
		</div>
	</Modal>

	<Modal bind:open={modelsDevOpen} ariaLabel={t('configuration.modelsDevSuggestedPricing')}>
		<div class="max-h-[calc(100vh-2rem)] w-[min(48rem,calc(100vw-2rem))] overflow-y-auto rounded-xl border border-[var(--color-line)] bg-[var(--color-surface-raised)] p-5 shadow-[var(--shadow-restraint)]">
			<h3 class="text-base font-semibold text-[var(--color-ink-1)]">{t('configuration.modelsDevSuggestedPricing')}</h3>
			<p class="mt-1 text-sm text-[var(--color-ink-2)]">
				{#snippet rich140markup1(text: string)}<a class="underline" href="https://models.dev" target="_blank" rel="noreferrer">{text}</a>{/snippet}{#snippet rich140markup2(text: string)}<strong class="font-medium text-[var(--color-ink-1)]">{text}</strong>{/snippet}<RichText segments={t.rich('configuration.modelsDevPriceImportGuidance')} tags={{ markup1: rich140markup1, markup2: rich140markup2 }} />
			</p>
			{#if modelsDevError}<Alert tone="warning" class="mt-3">{modelsDevError}</Alert>{/if}
			<div class="mt-4 space-y-3">
				<div>
					<label class="mb-1 block text-sm text-[var(--color-ink-2)]" for="models-dev-provider-search">{t('configuration.searchPricingProviders')}</label>
					<TextInput
						id="models-dev-provider-search"
						type="search"
						placeholder={t('configuration.searchByNameOrId')}
						value={modelsDevProviderSearch}
						oninput={updateModelsDevProviderSearch}
					/>
				</div>
				<div aria-live="polite">
					<label class="mb-1 block text-sm text-[var(--color-ink-2)]" for="models-dev-provider">{t('configuration.pricingProvider')}</label>
					{#if modelsDevLoading && modelsDevProviders.length === 0}
						<ActivityIndicator label={t('configuration.loadingPricingProviders')} />
					{:else if filteredModelsDevProviders.length > 0}
						<select id="models-dev-provider" class={inputCls} bind:value={selectedModelsDevProviderId} onchange={loadModelsDevProvider}>
							<option value="" disabled>{t('configuration.selectPricingProvider')}</option>
							{#each filteredModelsDevProviders as provider (provider.id)}<option value={provider.id}>{provider.name} ({formatNumber(provider.model_count)})</option>{/each}
						</select>
					{:else if modelsDevProviders.length > 0}
						<EmptyState headline={t('configuration.noPricingProvidersMatchYourSearch')} class="py-4 [&_.motion-enter]:animate-none" />
					{:else}
						<EmptyState headline={t('configuration.noModelsDevPriceListMatchesARegisteredProvider')} class="py-4 [&_.motion-enter]:animate-none" />
					{/if}
				</div>
				<p class="text-xs text-[var(--color-ink-3)]">{t('configuration.onlyPriceListsMatchingRegisteredProvidersAreShown')}</p>
			</div>
			{#if modelsDevLoading}
				<ActivityIndicator label={t('configuration.loadingPriceList')} class="mt-4 text-sm text-ink-2" />
			{:else}
				<div class="mt-4 space-y-2">
					{#each models.filter((model) => model.provider_id === modelsDevProvider?.id && (model.model_kind ?? 'text') === 'text') as model (model.id)}
						<div class="rounded-lg border border-[var(--color-line)] p-3">
							<div class="flex items-center gap-2">
								<input
									type="checkbox"
									checked={Boolean(modelsDevSelections[model.id])}
									disabled={model.price_source === 'manual'}
									onchange={(event) => {
										modelsDevSelections = {
											...modelsDevSelections,
											[model.id]: event.currentTarget.checked
												? (modelsDevModels.find((external) => external.price_available && external.id === model.model_name)?.id ?? '')
												: ''
										};
									}}
								/>
								<span class="min-w-0 flex-1 truncate text-sm text-[var(--color-ink-1)]">
									{model.model_name}{model.price_source === 'manual' ? t('configuration.manualPricesPreserved') : ''}
								</span>
								<select class={inputCls} disabled={model.price_source === 'manual'} bind:value={modelsDevSelections[model.id]}>
									<option value="">{t('configuration.selectModelsFromPriceList')}</option>
									{#each modelsDevModels.filter((external) => external.price_available) as external (external.id)}
										<option value={external.id}>{external.id} · ${displayPrice(external.input_price_per_million)}/${displayPrice(external.output_price_per_million)} / 1M</option>
									{/each}
								</select>
							</div>
							{#if modelsDevSelections[model.id]}
								{@const selected = modelsDevModels.find((external) => external.id === modelsDevSelections[model.id])}
								{#if selected && selected.unsupported_price_fields.length > 0}
									<Alert tone="warning" class="mt-2">{t('configuration.modelsDevExcludedPrices', { v0: selected.unsupported_price_fields.join(', ') })}</Alert>
								{/if}
							{/if}
						</div>
					{/each}
				</div>
			{/if}
			<div class="mt-5 flex justify-end gap-2">
				<Button variant="secondary" onclick={() => (modelsDevOpen = false)}>{t('configuration.cancel')}</Button>
				<Button onclick={importModelsDevPrices} disabled={modelsDevImporting || modelsDevLoading || !selectedModelsDevProviderId} ariaBusy={modelsDevImporting}>
					{#if modelsDevImporting}<ActivityIndicator size="xs" tone="ink" />{/if}{modelsDevImporting ? t('configuration.applying') : t('configuration.applySelectedPrices')}
				</Button>
			</div>
		</div>
	</Modal>
	{/if}


	{#if section === 'tools'}
		<div class="mt-2">
			<ChatExtensionsManager base="/api/v1/chat/admin" />
		</div>
	{/if}
</div>

<style>
	.model-card { position: relative; }
	.model-card[draggable='true'] { cursor: grab; }
	.model-card[data-dragging='true'] { opacity: 0.45; }
	.model-card[data-drop-edge] { border-color: var(--color-accent); }
	.model-card[data-drop-edge]::before {
		content: '';
		position: absolute;
		left: 0;
		right: 0;
		height: 2px;
		background: var(--color-accent);
	}
	.model-card[data-drop-edge='before']::before { top: -6px; }
	.model-card[data-drop-edge='after']::before { bottom: -6px; }
</style>
