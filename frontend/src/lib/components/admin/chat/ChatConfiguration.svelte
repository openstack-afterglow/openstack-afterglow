<script lang="ts">
	import { onDestroy } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { toast } from '$lib/stores/toast';
	import { invalidateChatModels } from '$lib/stores/chatModels';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Button from '$lib/components/ui/Button.svelte';
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

	let { section = 'providers' }: { section?: 'providers' | 'models' | 'tools' } = $props();

	interface Provider {
		id: number;
		name: string;
		provider_type: string;
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
	const PROVIDER_TYPES: ProviderChoice[] = [
		{ value: 'openai', label: 'OpenAI API (및 OpenAI 호환 API)', providerType: 'openai', authMode: 'api_key' },
		{ value: 'anthropic', label: 'Claude API', providerType: 'anthropic', authMode: 'api_key' },
		{ value: 'chatgpt-subscription', label: 'ChatGPT 구독 (실험)', providerType: 'chatgpt', authMode: 'chatgpt_device' },
		{ value: 'claude-subscription', label: 'Claude 구독 (실험)', providerType: 'anthropic', authMode: 'anthropic_subscription' },
		{ value: 'gemini', label: 'Google Gemini (AI Studio)', providerType: 'gemini', authMode: 'api_key' },
		{ value: 'vertex_ai', label: 'Google Vertex AI (GCP)', providerType: 'vertex_ai', authMode: 'api_key' },
		{ value: 'azure', label: 'Azure OpenAI', providerType: 'azure', authMode: 'api_key' },
		{ value: 'bedrock', label: 'AWS Bedrock', providerType: 'bedrock', authMode: 'api_key' },
		{ value: 'ollama', label: 'Ollama (로컬)', providerType: 'ollama', authMode: 'api_key' },
		{ value: 'mistral', label: 'Mistral', providerType: 'mistral', authMode: 'api_key' },
		{ value: 'cohere', label: 'Cohere', providerType: 'cohere', authMode: 'api_key' },
		{ value: 'groq', label: 'Groq', providerType: 'groq', authMode: 'api_key' },
		{ value: 'deepseek', label: 'DeepSeek', providerType: 'deepseek', authMode: 'api_key' },
		{ value: 'together_ai', label: 'Together AI', providerType: 'together_ai', authMode: 'api_key' },
		{ value: 'openrouter', label: 'OpenRouter', providerType: 'openrouter', authMode: 'api_key' },
		{ value: 'perplexity', label: 'Perplexity (Agent API · Router · Sonar)', providerType: 'perplexity', authMode: 'api_key' },
		{ value: 'xai', label: 'xAI (Grok)', providerType: 'xai', authMode: 'api_key' }
	];
	interface Model {
		id: number;
		provider_id: number;
		model_name: string;
		api_model_name?: string;
		api_provider?: string;
		display_name: string | null;
		is_active: boolean;
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

	// Cache prices are optional and independent of each other and of the input/output pair rule.
	const CACHE_PRICE_FIELDS: { key: CachePriceKey; label: string; slug: string }[] = [
		{ key: 'cache_read_price_per_million', label: '캐시 읽기', slug: 'read' },
		{ key: 'cache_write_price_per_million', label: '캐시 쓰기 5분', slug: 'write-5m' },
		{ key: 'cache_write_1h_price_per_million', label: '캐시 쓰기 1시간', slug: 'write-1h' }
	];
	// Plain non-negative decimal; rejects exponent, hex, sign, Infinity/NaN. Lumen owns precision.
	const CACHE_PRICE_PATTERN = /^\d+(?:\.\d+)?$/;
	const CACHE_PRICE_ERROR = '0 이상의 숫자로 입력하세요 (예: 0.3)';

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
		if (price === null || price === undefined || price === '') return '미설정';
		return normalizeDecimalString(price);
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
	let claudeToken = $state('');
	let claudeExpiry = $state('');
	let authSessionGeneration = $state(0);
	let authPollTimer = $state<ReturnType<typeof setTimeout> | null>(null);
	let authScopeToken = $state<string | undefined>();
	let authScopeProjectId = $state<string | undefined>();

	let mProviderId = $state<number | ''>('');
	let mName = $state('');
	let mDisplay = $state('');
	let mInputPrice = $state('');
	let mOutputPrice = $state('');
	let mCachePrices = $state<CachePriceInputs>(emptyCachePriceInputs());
	let mCacheErrors = $state<CachePriceErrors>({});
	let addingModel = $state(false);

	let editingPrice = $state<Model | null>(null);
	let editInputPrice = $state('');
	let editOutputPrice = $state('');
	let editCachePrices = $state<CachePriceInputs>(emptyCachePriceInputs());
	let editCacheErrors = $state<CachePriceErrors>({});
	let editingCapabilities = $state<Model | null>(null);
	let capVision = $state(false);
	let capReasoning = $state(false);
	let capToolCall = $state(false);
	let capAttachment = $state(false);
	let capContextLimit = $state('');
	let capSuggestedInputLimit = $state<number | null>(null);
	let capSaving = $state(false);
	let capError = $state('');

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
	const selectedCount = $derived(Object.values(selectedModelIds).filter(Boolean).length);
	const allModelsSelected = $derived(models.length > 0 && selectedCount === models.length);

	// Discovery is advisory: only administrator-entered price pairs can authorize activation.
	interface DiscoveryCandidate {
		id: string;
		display_name?: string | null;
		purpose?: 'chat' | 'non_chat' | 'unknown';
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
			(model.api_provider === 'gemini' && raw.startsWith('gemini/'))
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
			!(model.api_provider === 'gemini' && model.display_name.startsWith('gemini/'))
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
			!reg.has(candidate.id) && registrationOutcomes[candidate.id] !== 'success' && `${candidate.id} ${candidate.display_name ?? ''}`.toLocaleLowerCase().includes(filter)
		);
	});

	function reviewPriceError(entry: RegistrationEntry): string | undefined {
		const input = entry.inputPrice.trim();
		const output = entry.outputPrice.trim();
		if (!input && !output) return undefined;
		if (!CACHE_PRICE_PATTERN.test(input) || !CACHE_PRICE_PATTERN.test(output)) return '입력·출력 단가를 모두 0 이상의 숫자로 입력하세요.';
		return undefined;
	}

	function reviewCanActivate(review: RegistrationReview): boolean {
		return review.entries.filter((entry) => registrationOutcomes[entry.name] !== 'success')
			.every((entry) => entry.inputPrice.trim() !== '' && entry.outputPrice.trim() !== '' && !reviewPriceError(entry));
	}

	function formatBillingAmount(value: string | null): string {
		if (value === null) return '—';
		return Number(value).toLocaleString('en-US', { maximumFractionDigits: 6 });
	}

	function billingFailureLabel(reason: string | null): string {
		if (reason === 'credential_not_configured') return 'API 키가 설정되지 않았습니다.';
		if (reason === 'credential_unavailable') return '저장된 API 키를 복호화할 수 없습니다.';
		if (reason === 'admin_credential_not_configured') return '조직 사용량 조회용 관리자 키를 설정하세요.';
		if (reason === 'admin_credential_unavailable') return '저장된 관리자 키를 복호화할 수 없습니다. 키를 다시 설정하세요.';
		if (reason === 'admin_credential_rejected') return '프로바이더가 관리자 키를 거부했습니다. 키의 조직 권한을 확인하세요.';
		if (reason === 'provider_authorization_failed') return '프로바이더가 이 API 키의 결제 조회를 거부했습니다.';
		if (reason === 'provider_request_failed') return '프로바이더 사용량 API 요청이 실패했습니다.';
		return '프로바이더 사용량 API에 연결할 수 없습니다.';
	}

	function unsupportedCreditLabel(providerType: string): string {
		const normalized = providerType.toLowerCase();
		if (normalized === 'openai') {
			return 'OpenAI 공식 API는 조직 비용과 사용량만 제공하며, 현재 선불 잔액과 충전액은 결제 콘솔에서 확인해야 합니다.';
		}
		if (normalized === 'anthropic') {
			return 'Anthropic 공식 API는 조직 비용과 사용량만 제공하며, 현재 크레딧 잔액과 충전액은 결제 콘솔에서 확인해야 합니다.';
		}
		if (normalized === 'gemini') {
			return 'Gemini 선불 잔액과 거래 내역은 공식 Google AI Studio 결제 화면에서만 확인할 수 있습니다.';
		}
		if (normalized === 'perplexity') {
			return 'Perplexity Enterprise Computer Analytics API는 Computer 제품 분석용이며 Sonar/API Platform 크레딧 조회 API가 아닙니다.';
		}
		return '이 프로바이더는 저장된 API 키로 현재 계정 잔액이나 충전액을 조회하는 공식 endpoint를 제공하지 않습니다.';
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
		if (capability === 'openai_admin_usage' || capability === 'anthropic_admin_usage') return '조직 사용량 연동';
		if (capability === 'deepseek_balance') return '계정 잔액 연동';
		if (capability === 'openrouter_key') return 'API 키 한도 연동';
		return '공급자 조회 연동';
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
				? `결제 상태 조회 실패 (${caught.status})`
				: '결제 상태를 조회할 수 없습니다.';
		} finally {
			if (generation === billingRequestGeneration && requestToken === token && requestProjectId === projectId) {
				billingLoading = false;
			}
		}
	}

	async function load({ freshBilling = false }: { freshBilling?: boolean } = {}) {
		if (!token) return;
		const generation = ++loadGeneration;
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
			providers = ps;
			if (mProviderId === '' && ps.length === 1) mProviderId = ps[0].id;
			models = ms;
			void loadProviderBilling({ fresh: freshBilling });
			error = '';
		} catch (e) {
			if (generation !== loadGeneration || requestToken !== token || requestProjectId !== projectId || destroyed) return;
			error = e instanceof ApiError ? `조회 실패 (${e.status})` : '서버 오류';
		} finally {
			if (generation === loadGeneration && requestToken === token && requestProjectId === projectId && !destroyed) loading = false;
		}
	}

	async function addProvider() {
		if (!pName.trim()) {
			toast.error('프로바이더 이름을 입력하세요');
			return;
		}
		const choice = selectedProviderChoice;
		addingProvider = true;
		try {
			const body: Record<string, unknown> = {
				name: pName.trim(),
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
				token,
				projectId
			);
			pName = '';
			pType = 'openai';
			pApiBase = '';
			pApiKey = '';
			await load();
			toast.success('프로바이더가 추가되었습니다');
			if (choice.authMode !== 'api_key') openSubscriptionAuth(created);
		} catch (e) {
			toast.error(e instanceof ApiError ? e.message : '추가 실패');
		} finally {
			addingProvider = false;
		}
	}

	async function deleteProvider(id: number) {
		if (!(await confirmDialog('프로바이더를 삭제하시겠습니까? 연결된 모델도 함께 삭제됩니다.'))) return;
		try {
			await api.delete(`/api/v1/chat/admin/providers/${id}`, token, projectId);
			invalidateChatModels();
			await load();
		} catch {
			toast.error('삭제 실패');
		}
	}

	async function toggleProvider(p: Provider) {
		try {
			await api.patch(`/api/v1/chat/admin/providers/${p.id}`, { is_active: !p.is_active }, token, projectId);
			await load();
		} catch {
			toast.error('변경 실패');
		}
	}

	async function updateKey(p: Provider) {
		const key = prompt(`${p.name} 의 새 API 키를 입력하세요 (비우면 제거)`);
		if (key === null) return;
		try {
			await api.patch(`/api/v1/chat/admin/providers/${p.id}`, { api_key: key.trim() || null }, token, projectId);
			await load({ freshBilling: true });
			toast.success('API 키가 갱신되었습니다');
		} catch {
			toast.error('갱신 실패');
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
			toast.success('조직 사용량 관리자 키가 갱신되었습니다');
		} catch (caught) {
			toast.error(caught instanceof ApiError ? caught.message : '관리자 키 갱신 실패');
		} finally {
			billingKeyBusy = false;
		}
	}

	function subscriptionStatusLabel(provider: Provider): string {
		if (provider.auth_status === 'configured' && provider.has_credentials) return '인증 설정됨';
		if (provider.auth_status === 'reauth_required') return '재연결 필요';
		return '인증 미연결';
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

	function clearProviderSecrets() {
		pApiBase = '';
		pApiKey = '';
	}

	function handleProviderChoiceChange() {
		clearProviderSecrets();
	}

	function subscriptionErrorMessage(error: unknown): string {
		if (!(error instanceof ApiError)) return '구독 인증 요청에 실패했습니다. 다시 시도하세요.';
		if (error.status === 409) return '진행 중인 채팅 실행 또는 다른 관리자의 인증을 완료하거나 취소한 뒤 다시 시도하세요.';
		if (error.status === 429) return '인증 요청이 제한되었습니다. 잠시 후 수동으로 다시 확인하세요.';
		if (error.status === 503) return '구독 인증 공급자 또는 저장소에 연결할 수 없습니다. 상태를 확인한 뒤 다시 시도하세요.';
		try {
			const detail = JSON.parse(error.message) as { message?: unknown };
			if (typeof detail.message === 'string') return detail.message;
		} catch {
			// The shared API client can also provide an already-safe plain message.
		}
		return error.message || '구독 인증 요청에 실패했습니다.';
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
				toast.success('ChatGPT 구독이 연결되었습니다');
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
			authError = `${subscriptionErrorMessage(e)} 서버의 인증 요청은 만료될 때까지 유지될 수 있습니다.`;
		} finally {
			authBusy = false;
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
				.catch(() => toast.error('인증 취소를 확인하지 못했습니다. 서버 만료 상태를 확인하세요.'));
		}
	}

	async function saveClaudeSubscription() {
		if (!authProvider || providerAuthMode(authProvider) !== 'anthropic_subscription' || authBusy) return;
		if (!claudeToken.trim()) {
			authError = 'Claude setup-token을 입력하세요.';
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
			toast.success('Claude 구독 토큰이 등록되었습니다');
		} catch (e) {
			if (generation === authSessionGeneration) authError = subscriptionErrorMessage(e);
		} finally {
			if (generation === authSessionGeneration) authBusy = false;
		}
	}

	async function disconnectSubscription(provider: Provider) {
		if (!(await confirmDialog(`“${provider.name}”의 구독 연결을 해제하시겠습니까? 등록된 모델은 유지됩니다.`))) return;
		try {
			await api.delete(`/api/v1/chat/admin/providers/${provider.id}/auth`, token, projectId);
			await load();
			toast.success('구독 연결이 해제되었습니다');
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
			toast.success('인증 코드를 복사했습니다');
		} catch {
			toast.error('인증 코드를 복사하지 못했습니다');
		}
	}

	async function addModel() {
		if (!mProviderId || !mName.trim()) {
			toast.error('프로바이더와 모델명을 입력하세요');
			return;
		}
		if (!cachePricingAvailable) {
			// Hidden cache inputs (an older Lumen) must neither send stale values nor block the create.
			mCachePrices = emptyCachePriceInputs();
			mCacheErrors = {};
		}
		const cache = parseCachePrices(mCachePrices);
		mCacheErrors = cache.errors;
		const prices = pricePayload(mInputPrice, mOutputPrice);
		if (prices === undefined || Object.keys(cache.errors).length > 0) return;
		addingModel = true;
		try {
			await api.post(
				'/api/v1/chat/admin/models',
				{
					provider_id: mProviderId,
					model_name: mName.trim(),
					display_name: mDisplay.trim() || null,
					...prices,
					// Blank cache prices are omitted on create; the model starts with no cache rate.
					...presentCachePrices(cache.values)
				},
				token,
				projectId
			);
			invalidateChatModels();
			mName = '';
			mDisplay = '';
			mInputPrice = '';
			mOutputPrice = '';
			mCachePrices = emptyCachePriceInputs();
			mCacheErrors = {};
			await load();
			toast.success('모델이 추가되었습니다');
		} catch (e) {
			toast.error(e instanceof ApiError ? e.message : '추가 실패');
		} finally {
			addingModel = false;
		}
	}

	function formatPricePerMillion(price: string | number | null | undefined): string {
		if (price === null || price === undefined) return '가격 미확인';
		return String(price).replace(/(\.\d*?[1-9])0+$/, '$1').replace(/\.0+$/, '');
	}

	function pricePayload(input: string, output: string): { input_price_per_million: string | null; output_price_per_million: string | null } | undefined {
		const normalizedInput = input.trim() || null;
		const normalizedOutput = output.trim() || null;
		if ((normalizedInput === null) !== (normalizedOutput === null)) {
			toast.error('입력·출력 가격은 함께 입력하거나 함께 비워야 합니다');
			return undefined;
		}
		return { input_price_per_million: normalizedInput, output_price_per_million: normalizedOutput };
	}

	function openPriceEditor(model: Model) {
		editingPrice = model;
		editInputPrice = model.input_price_per_million ?? '';
		editOutputPrice = model.output_price_per_million ?? '';
		editCachePrices = cachePriceInputsFrom(model);
		editCacheErrors = {};
	}

	async function savePrice() {
		if (!editingPrice) return;
		const cache = changedCachePrices(editCachePrices, cachePriceInputsFrom(editingPrice));
		editCacheErrors = cache.errors;
		// Send only what changed. Lumen marks a model manual (clearing its models.dev metadata and
		// blocking later imports) whenever an input/output key is present, so an untouched pair stays
		// absent. When either side changed, both are sent to satisfy Lumen's pair rule.
		const pairChanged =
			editInputPrice.trim() !== (editingPrice.input_price_per_million ?? '') ||
			editOutputPrice.trim() !== (editingPrice.output_price_per_million ?? '');
		const prices = pairChanged ? pricePayload(editInputPrice, editOutputPrice) : {};
		if (prices === undefined || Object.keys(cache.errors).length > 0) return;
		const body = { ...prices, ...cache.values };
		if (Object.keys(body).length === 0) {
			editingPrice = null;
			return;
		}
		try {
			await api.patch(`/api/v1/chat/admin/models/${editingPrice.id}`, body, token, projectId);
			invalidateChatModels();
			editingPrice = null;
			await load();
			toast.success('모델 가격을 저장했습니다');
		} catch (e) {
			toast.error(e instanceof ApiError ? e.message : '가격 저장 실패');
		}
	}

	function capabilityStatus(model: Model): string {
		if (model.capability_source === 'override') return '관리자 기능 설정 · 실행 미검증';
		const caps = model.effective_capabilities ?? model.capabilities;
		if ((model.effective_capability_source || model.capability_source) && (caps?.vision || caps?.reasoning || caps?.tool_call || caps?.attachment || caps?.context_limit)) {
			return '기능 메타데이터 · 실행 미검증';
		}
		return '고급 기능 미확인';
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
			? undefined : '컨텍스트 한도는 1 이상의 정수로 입력하세요.';
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
			toast.success('모델 기능 설정을 저장했습니다. 실행 지원은 별도로 확인하세요.');
		} catch (e) {
			capError = e instanceof ApiError ? e.message : '기능 저장에 실패했습니다. 다시 시도하세요.';
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
			modelsDevError = e instanceof ApiError ? e.message : 'models.dev 가격표를 불러오지 못했습니다';
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
					.filter((model) => model.provider_id === modelsDevProvider?.id && model.price_source !== 'manual')
					.flatMap((model) => {
						const exact = result.models.find((external) => external.price_available && external.id === model.model_name);
						return exact ? [[model.id, exact.id]] : [];
					})
			);
		} catch (e) {
			if (providerId === selectedModelsDevProviderId) {
				modelsDevError = e instanceof ApiError ? e.message : 'models.dev 모델 목록을 불러오지 못했습니다';
			}
		} finally {
			if (providerId === selectedModelsDevProviderId) modelsDevLoading = false;
		}
	}

	async function importModelsDevPrices() {
		if (!modelsDevProvider) return;
		const selections = Object.entries(modelsDevSelections)
			.filter(([, externalId]) => externalId)
			.map(([localModelId, modelsDevModelId]) => ({ local_model_id: Number(localModelId), models_dev_model_id: modelsDevModelId }));
		if (selections.length === 0) {
			toast.error('가격을 적용할 모델을 선택하세요');
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
			toast.success('models.dev 추천 가격을 적용했습니다');
		} catch (e) {
			modelsDevError = e instanceof ApiError ? e.message : '가격 import 실패';
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
				discoveryError = '다른 프로바이더의 조회 결과를 받았습니다. 다시 조회하세요.';
				return;
			}
			discovery = result.live_status === 'error'
				? { ...result, source: 'none', models: [], candidates: [], complete: false }
				: result;
		} catch {
			if (discoveryIsCurrent(generation, providerId, requestToken, requestProjectId)) {
				discoveryError = '모델 조회에 실패했습니다. 연결과 API 키를 확인한 뒤 다시 조회하세요.';
			}
		} finally {
			if (discoveryIsCurrent(generation, providerId, requestToken, requestProjectId)) discovering = false;
		}
	}

	function reviewSelected() {
		if (discoverId === null || !discovery || discovery.live_status === 'error' || registeringBulk) return;
		const registered = registeredNames(discoverId);
		const candidates = discovery.candidates
			.filter((candidate) => selectedAvail[candidate.id] && candidate.purpose !== 'non_chat' && !registered.has(candidate.id) && registrationOutcomes[candidate.id] !== 'success');
		if (candidates.length === 0) {
			toast.error('등록할 채팅 후보 모델을 선택하세요');
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
			toast.error('활성화하려면 각 모델의 정확한 입력·출력 단가를 함께 입력하세요');
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
							...(entry.displayName.trim() ? { display_name: entry.displayName.trim() } : {}),
							...(inputPrice && outputPrice ? { input_price_per_million: inputPrice, output_price_per_million: outputPrice } : {}),
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
			if (ok > 0) toast.success(`${ok}개 모델을 ${activate ? '등록·활성화' : '비활성 상태로 저장'}했습니다`);
			if (failed.length > 0) toast.error(`${failed.length}개 등록 실패. 실패한 후보만 재시도할 수 있습니다.`);
			selectedAvail = Object.fromEntries(failed.map((name) => [name, true]));
			if (failed.length === 0) registrationReview = null;
		} finally {
			if (registrationIsCurrent(generation, review)) registeringBulk = false;
		}
	}

	function toggleAllFiltered(checked: boolean) {
		const next = { ...selectedAvail };
		for (const candidate of filteredAvailable) {
			if (candidate.purpose !== 'non_chat') next[candidate.id] = checked;
		}
		selectedAvail = next;
	}

	async function deleteModel(id: number) {
		if (!(await confirmDialog('모델을 삭제하시겠습니까?'))) return;
		try {
			await api.delete(`/api/v1/chat/admin/models/${id}`, token, projectId);
			invalidateChatModels();
			await load();
		} catch {
			toast.error('삭제 실패');
		}
	}

	function toggleAllModels(checked: boolean) {
		const next: Record<number, boolean> = {};
		if (checked) for (const m of models) next[m.id] = true;
		selectedModelIds = next;
	}

	async function deleteSelectedModels() {
		const ids = Object.keys(selectedModelIds)
			.filter((k) => selectedModelIds[Number(k)])
			.map(Number);
		if (ids.length === 0) return;
		if (!(await confirmDialog(`선택한 ${ids.length}개 모델을 삭제하시겠습니까?`))) return;
		deletingBulk = true;
		let ok = 0;
		const failed: string[] = [];
		try {
			for (const id of ids) {
				try {
					await api.delete(`/api/v1/chat/admin/models/${id}`, token, projectId);
					ok++;
					invalidateChatModels();
				} catch {
					failed.push(String(id));
				}
			}
			selectedModelIds = {};
			await load();
			if (ok > 0) toast.success(`${ok}개 모델을 삭제했습니다`);
			if (failed.length > 0) toast.error(`${failed.length}개 삭제 실패`);
		} finally {
			deletingBulk = false;
		}
	}

	async function toggleModel(m: Model) {
		if (!m.is_active && (m.effective_input_price_per_million == null || m.effective_output_price_per_million == null)) {
			toast.error('입력·출력 단가가 미확인입니다. 가격 수정 또는 models.dev 가격 적용 후 활성화하세요.');
			return;
		}
		try {
			await api.patch(`/api/v1/chat/admin/models/${m.id}`, { is_active: !m.is_active }, token, projectId);
			invalidateChatModels();
			await load();
		} catch {
			toast.error('변경 실패');
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
			toast.success(target ? '제목 요약 모델로 지정했습니다' : '제목 요약 모델을 해제했습니다');
		} catch (e) {
			toast.error(e instanceof ApiError ? e.message : '제목 요약 모델 설정 실패');
		}
	}

	$effect(() => {
		if (token) void load();
	});


	const unsubscribeAuthScope = auth.subscribe((state) => {
		const nextToken = state.token ?? undefined;
		const nextProjectId = state.projectId ?? undefined;
		if (discoveryScopeToken !== nextToken || discoveryScopeProjectId !== nextProjectId) {
			discoveryScopeToken = nextToken;
			discoveryScopeProjectId = nextProjectId;
			resetDiscovery();
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
		breadcrumb={section === 'models' ? 'AI 채팅 / 모델 설정' : section === 'tools' ? 'AI 채팅 / 도구 설정' : 'AI 채팅 / 설정'}
		title={section === 'models' ? '모델 설정' : section === 'tools' ? '도구 설정' : '채팅 설정'}
		subtitle={section === 'models'
			? '프로바이더 모델, 가격, 제목 요약 모델을 관리합니다.'
			: section === 'tools'
				? 'MCP 서버, 스킬, 커스텀 HTTP 도구를 관리합니다.'
				: 'LLM 프로바이더와 연결 정보를 관리합니다. API 키는 암호화되어 저장됩니다.'}
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
		<h3 class="mb-3 text-sm font-semibold text-[var(--color-ink-1)]">LLM 프로바이더</h3>
		<div class="{cardCls} mb-4 p-5">
			<div class="grid grid-cols-1 gap-3 md:grid-cols-2">
				<Field label="이름" for="provider-name" required>
					<TextInput id="provider-name" placeholder="예: openai-prod" bind:value={pName} required />
				</Field>
				<Field label="연결 방식" for="provider-type" required>
					<SelectInput id="provider-type" bind:value={pType} onchange={handleProviderChoiceChange}>
						{#each PROVIDER_TYPES as pt (pt.value)}
							<option value={pt.value}>{pt.label}</option>
						{/each}
					</SelectInput>
				</Field>
				{#if !isSubscriptionChoice}
					<Field label="API Base" for="provider-api-base" help="OpenAI 호환 또는 커스텀 엔드포인트에서만 입력합니다.">
						<TextInput id="provider-api-base" type="url" placeholder="https://api.example.com/v1" bind:value={pApiBase} />
					</Field>
					<Field label="API 키" for="provider-api-key">
						<TextInput id="provider-api-key" type="password" placeholder="API 키" bind:value={pApiKey} />
					</Field>
				{/if}
			</div>
			{#if isSubscriptionChoice}
				<Alert tone="warning" title="실험 기능 · 전체 사용자 공용" class="mt-4">
					이 개인 구독 연결은 이 Afterglow의 모든 사용자 요청에 공용으로 사용됩니다. 공급자 이용 약관과 조직 정책을 확인하고 전용 계정을 사용하세요.
					<a class="underline" href={selectedProviderChoice.authMode === 'chatgpt_device' ? 'https://help.openai.com/en/articles/11369540-codex-in-chatgpt' : 'https://support.anthropic.com/en/articles/11145838-using-claude-code-with-your-pro-or-max-plan'} target="_blank" rel="noreferrer">공식 안내</a>
				</Alert>
			{:else if selectedProviderChoice.providerType === 'perplexity'}
				<Alert tone="info" title="Perplexity API Base" class="mt-4">
					Agent API는 <code>https://api.perplexity.ai/v1</code>, Router는
					<code>https://api.perplexity.ai/router</code>를 입력하세요. 비워 두면 기존 Sonar API 호환 경로를 사용합니다.
				</Alert>
			{:else}
				<p class="mt-2 text-xs text-[var(--color-ink-3)]">
					타입은 내부 LiteLLM 중계 형식입니다. OpenAI 호환 엔드포인트(vLLM·LM Studio 등)는 OpenAI API + API Base로 연결하세요.
				</p>
			{/if}
			<div class="mt-3 flex justify-end">
				<Button onclick={addProvider} disabled={addingProvider}>
					{addingProvider ? '추가 중…' : '+ 프로바이더 추가'}
				</Button>
			</div>
		</div>

		{#if loading}
			<div class="{cardCls} h-20 animate-pulse"></div>
		{:else if providers.length === 0}
			<p class="px-1 text-sm text-[var(--color-ink-3)]">등록된 프로바이더가 없습니다.</p>
		{:else}
			<div class="mb-3 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
				<div>
					<h4 class="text-sm font-semibold text-[var(--color-ink-1)]">사용량과 크레딧 상태</h4>
					<p class="mt-1 text-xs text-[var(--color-ink-2)]">Lumen 원장과 프로바이더 공식 조직 사용량·잔액을 분리해 표시합니다.</p>
				</div>
				<Button variant="outline" size="sm" disabled={billingLoading} onclick={() => void loadProviderBilling({ fresh: true })}>
					{billingLoading ? '조회 중…' : '전체 새로고침'}
				</Button>
			</div>
			{#if billingError}
				<Alert tone="warning" title="결제 상태를 불러오지 못했습니다" class="mb-3">{billingError} 프로바이더 설정과 키 관리 기능은 계속 사용할 수 있습니다.</Alert>
			{/if}
			<div class="space-y-2">
				{#each providers as p (p.id)}
					{@const billing = billingByProvider[p.id]}
					<div class="{cardCls} px-4 py-3" data-provider-id={p.id}>
						<div class="flex flex-col items-start justify-between gap-3 sm:flex-row sm:items-center">
							<div class="min-w-0">
								<div class="flex flex-wrap items-center gap-2">
									<span class="truncate text-sm font-medium text-[var(--color-ink-1)]">{p.name}</span>
									<Pill tone={p.is_active ? 'success' : 'neutral'} size="xs">{p.is_active ? '활성' : '비활성'}</Pill>
									{#if providerAuthMode(p) === 'api_key'}
										<Pill tone={p.has_api_key ? 'accent' : 'warning'} size="xs">{p.has_api_key ? '키 설정됨' : '키 없음'}</Pill>
									{#if supportsBillingAdminKey(p)}
										<Pill tone={p.has_billing_admin_key ? 'info' : 'neutral'} size="xs">{p.has_billing_admin_key ? '사용량 키 설정됨' : '사용량 키 없음'}</Pill>
									{/if}
									{:else}
										<Pill tone="warning" size="xs">실험</Pill>
										<Pill tone="info" size="xs">전체 공용</Pill>
										<Pill tone={subscriptionStatusTone(p)} size="xs">{subscriptionStatusLabel(p)}</Pill>
									{/if}
									<Pill tone="neutral" size="xs">{p.provider_type}</Pill>
								</div>
								{#if p.api_base}
									<div class="mt-1 truncate text-xs text-[var(--color-ink-3)]">{p.api_base}</div>
								{:else if providerAuthMode(p) !== 'api_key' && p.auth_expires_at}
									<div class="mt-1 text-xs text-[var(--color-ink-3)]">만료 {new Date(p.auth_expires_at).toLocaleString()}</div>
								{/if}
							</div>
							<div class="flex flex-wrap items-center gap-x-3 gap-y-2 text-xs sm:justify-end">
								{#if providerAuthMode(p) === 'api_key'}
									<button class={rowActionCls} onclick={() => updateKey(p)}>키 변경</button>
									{#if supportsBillingAdminKey(p)}
										<button class={rowActionCls} onclick={() => openBillingKeyModal(p)}>{p.has_billing_admin_key ? '사용량 키 변경' : '사용량 키 설정'}</button>
									{/if}
								{:else}
									<button class={rowActionCls} onclick={() => openSubscriptionAuth(p)}>
										{providerAuthMode(p) === 'chatgpt_device'
											? p.has_credentials ? '재연결' : '연결'
											: p.has_credentials ? '토큰 교체' : '토큰 등록'}
									</button>
									{#if p.auth_status !== 'disconnected'}
										<button class={rowActionCls} onclick={() => disconnectSubscription(p)}>연결 해제</button>
									{/if}
								{/if}
								<button class={rowActionCls} onclick={() => toggleProvider(p)}>{p.is_active ? '비활성화' : '활성화'}</button>
								<button class="text-[var(--color-state-danger)] transition-opacity hover:opacity-80" onclick={() => deleteProvider(p.id)}>삭제</button>
							</div>
						</div>

						<div class="mt-3 border-t border-[var(--color-line)] pt-3">
							<div class="flex flex-wrap items-center gap-2">
								<span class="text-xs font-semibold text-[var(--color-ink-1)]">사용량 · 결제 상태</span>
								{#if billing?.status === 'available'}
									<Pill tone="success" size="xs">{availableBillingLabel(billing.capability)}</Pill>
								{:else if billing?.status === 'unavailable'}
									<Pill tone="warning" size="xs">공급자 조회 실패</Pill>
								{:else if billing?.status === 'unsupported'}
									<Pill tone="neutral" size="xs">공식 콘솔 확인</Pill>
								{/if}
							</div>

							{#if billingLoading && !billing}
								<p class="mt-2 text-xs text-[var(--color-ink-2)]">사용량과 결제 상태를 조회하는 중…</p>
							{:else if !billing}
								<p class="mt-2 text-xs text-[var(--color-ink-2)]">표시할 결제 상태가 없습니다. 전체 새로고침으로 다시 조회할 수 있습니다.</p>
							{:else}
								{@const billingUrl = safeExternalUrl(billing.billing_url)}
								{@const usageUrl = safeExternalUrl(billing.usage_url)}
								{@const credit = providerCreditState(billing)}
								<div class="mt-3 rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-base)] p-3">
									<div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
										<div class="min-w-0">
											<div class="flex flex-wrap items-center gap-2">
												<span class="text-xs font-semibold text-[var(--color-ink-1)]">계정 크레딧</span>
												{#if credit.kind === 'account_balance'}
													<Pill tone={credit.isAvailable ? 'success' : 'warning'} size="xs">공식 계정 잔액</Pill>
												{:else if credit.kind === 'api_key_limit'}
													<Pill tone="info" size="xs">API 키 한도</Pill>
												{:else if credit.kind === 'unavailable'}
													<Pill tone="warning" size="xs">조회 실패</Pill>
												{:else}
													<Pill tone="neutral" size="xs">공식 API 조회 미지원</Pill>
												{/if}
											</div>
											{#if credit.kind === 'unavailable' || credit.kind === 'unsupported'}
												<p class="mt-2 text-xs leading-relaxed text-[var(--color-ink-2)]">{credit.message} 잔액은 사용량에서 추정하지 않습니다.</p>
											{:else if credit.kind === 'api_key_limit'}
												<p class="mt-2 text-xs leading-relaxed text-[var(--color-ink-2)]">OpenRouter가 현재 API 키에 보고한 지출 한도입니다. 계정 전체 선불 잔액이 아닙니다.</p>
											{/if}
										</div>
										{#if billingUrl}
											<Button variant="outline" size="sm" href={billingUrl} target="_blank">크레딧 충전·결제 ↗</Button>
										{/if}
									</div>

									{#if credit.kind === 'account_balance'}
										{#if credit.balances.length === 0}
											<p class="mt-3 text-xs text-[var(--color-ink-2)]">프로바이더가 반환한 잔액 항목이 없습니다.</p>
										{:else}
											{#each credit.balances as balance (balance.currency)}
												<div class="mt-3">
													<div class="mb-2 flex items-center justify-between gap-2">
														<span class="text-xs font-medium text-[var(--color-ink-2)]">DeepSeek {balance.currency}</span>
														<Pill tone={credit.isAvailable ? 'success' : 'warning'} size="xs">{credit.isAvailable ? '사용 가능' : '잔액 부족'}</Pill>
													</div>
													<div class="grid grid-cols-1 gap-2 sm:grid-cols-3">
														<div class="rounded-lg bg-[var(--color-surface-sunken)] p-3"><div class="text-xs text-[var(--color-ink-2)]">현재 계정 잔액</div><div class="mt-1 font-medium tabular-nums text-[var(--color-ink-1)]">{formatBillingAmount(balance.total)} {balance.currency}</div></div>
														<div class="rounded-lg bg-[var(--color-surface-sunken)] p-3"><div class="text-xs text-[var(--color-ink-2)]">구매 충전액</div><div class="mt-1 font-medium tabular-nums text-[var(--color-ink-1)]">{formatBillingAmount(balance.purchased)} {balance.currency}</div></div>
														<div class="rounded-lg bg-[var(--color-surface-sunken)] p-3"><div class="text-xs text-[var(--color-ink-2)]">지급 크레딧</div><div class="mt-1 font-medium tabular-nums text-[var(--color-ink-1)]">{formatBillingAmount(balance.granted)} {balance.currency}</div></div>
													</div>
												</div>
											{/each}
										{/if}
									{:else if credit.kind === 'api_key_limit'}
										<div class="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
											<div class="rounded-lg bg-[var(--color-surface-sunken)] p-3"><div class="text-xs text-[var(--color-ink-2)]">API 키 남은 한도</div><div class="mt-1 font-medium tabular-nums text-[var(--color-ink-1)]">{credit.remaining === null ? '제한 없음' : `$${formatBillingAmount(credit.remaining)}`}</div></div>
											<div class="rounded-lg bg-[var(--color-surface-sunken)] p-3"><div class="text-xs text-[var(--color-ink-2)]">API 키 지출 한도</div><div class="mt-1 font-medium tabular-nums text-[var(--color-ink-1)]">{credit.limit === null ? '제한 없음' : `$${formatBillingAmount(credit.limit)}`}</div></div>
										</div>
										<p class="mt-2 text-xs text-[var(--color-ink-2)]">{credit.isFreeTier ? '무료 티어 키' : '유료 크레딧 키'}</p>
									{/if}
								</div>

								<div class="mt-3 grid grid-cols-2 gap-2 lg:grid-cols-4">
									<div class="rounded-lg bg-[var(--color-surface-sunken)] p-3">
										<div class="text-xs text-[var(--color-ink-2)]">이번 달 Lumen 사용</div>
										<div class="mt-1 font-medium tabular-nums text-[var(--color-ink-1)]">${formatBillingAmount(billing.local_usage.raw_cost.monthly)}</div>
									</div>
									<div class="rounded-lg bg-[var(--color-surface-sunken)] p-3">
										<div class="text-xs text-[var(--color-ink-2)]">누적 Lumen 사용</div>
										<div class="mt-1 font-medium tabular-nums text-[var(--color-ink-1)]">${formatBillingAmount(billing.local_usage.raw_cost.total)}</div>
									</div>
									<div class="rounded-lg bg-[var(--color-surface-sunken)] p-3">
										<div class="text-xs text-[var(--color-ink-2)]">이번 달 요청</div>
										<div class="mt-1 font-medium tabular-nums text-[var(--color-ink-1)]">{formatBillingAmount(billing.local_usage.requests.monthly)}회</div>
									</div>
									<div class="rounded-lg bg-[var(--color-surface-sunken)] p-3">
										<div class="text-xs text-[var(--color-ink-2)]">이번 달 토큰</div>
										<div class="mt-1 font-medium tabular-nums text-[var(--color-ink-1)]">{formatBillingAmount(billing.local_usage.tokens.monthly)}</div>
									</div>
								</div>
								<p class="mt-2 text-xs tabular-nums text-[var(--color-ink-2)]">Lumen 원장 기준 · 오늘 ${formatBillingAmount(billing.local_usage.raw_cost.daily)} · 이번 주 ${formatBillingAmount(billing.local_usage.raw_cost.weekly)}</p>

								{#if billing.status === 'unavailable' && credit.kind !== 'unavailable'}
									<Alert tone="warning" title="프로바이더 사용량 조회 실패" class="mt-3">{billingFailureLabel(billing.reason)}</Alert>
								{:else if (billing.capability === 'openai_admin_usage' || billing.capability === 'anthropic_admin_usage') && billing.provider_usage}
									{@const providerUsage = billing.provider_usage}
									<div class="mt-3">
										<div class="mb-2 text-xs font-semibold text-[var(--color-ink-2)]">{billing.capability === 'openai_admin_usage' ? 'OpenAI' : 'Anthropic'} 조직 사용량</div>
										<div class="grid grid-cols-2 gap-2 lg:grid-cols-4">
											<div class="rounded-lg bg-[var(--color-surface-sunken)] p-3"><div class="text-xs text-[var(--color-ink-2)]">이번 달 공식 비용</div><div class="mt-1 font-medium tabular-nums text-[var(--color-ink-1)]">${formatBillingAmount(providerUsage.cost?.monthly ?? null)}</div></div>
											<div class="rounded-lg bg-[var(--color-surface-sunken)] p-3"><div class="text-xs text-[var(--color-ink-2)]">이번 주 공식 비용</div><div class="mt-1 font-medium tabular-nums text-[var(--color-ink-1)]">${formatBillingAmount(providerUsage.cost?.weekly ?? null)}</div></div>
											<div class="rounded-lg bg-[var(--color-surface-sunken)] p-3"><div class="text-xs text-[var(--color-ink-2)]">이번 달 공식 요청</div><div class="mt-1 font-medium tabular-nums text-[var(--color-ink-1)]">{formatBillingAmount(providerUsage.requests?.monthly ?? null)}{providerUsage.requests ? '회' : ''}</div></div>
											<div class="rounded-lg bg-[var(--color-surface-sunken)] p-3"><div class="text-xs text-[var(--color-ink-2)]">이번 달 공식 토큰</div><div class="mt-1 font-medium tabular-nums text-[var(--color-ink-1)]">{formatBillingAmount(providerUsage.tokens?.monthly ?? null)}</div></div>
										</div>
										<p class="mt-2 text-xs tabular-nums text-[var(--color-ink-2)]">공식 조직 보고서 기준 · 오늘 비용 ${formatBillingAmount(providerUsage.cost?.daily ?? null)} · 오늘 토큰 {formatBillingAmount(providerUsage.tokens?.daily ?? null)}</p>
										{#if billing.reason === 'partial_provider_data'}
											<Alert tone="warning" title="일부 공식 보고서만 표시" class="mt-3">비용 또는 사용량 보고서 하나를 가져오지 못했습니다. 표시된 값만 최신 공식 응답입니다.</Alert>
										{/if}
									</div>
								{:else if billing.capability === 'openrouter_key' && billing.status === 'available'}
									<div class="mt-3">
										<div class="mb-2 text-xs font-semibold text-[var(--color-ink-2)]">OpenRouter 공급자 사용량</div>
										<div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
											<div class="rounded-lg bg-[var(--color-surface-sunken)] p-3"><div class="text-xs text-[var(--color-ink-2)]">이번 달 공급자 사용</div><div class="mt-1 font-medium tabular-nums text-[var(--color-ink-1)]">${formatBillingAmount(billing.usage_monthly)}</div></div>
											<div class="rounded-lg bg-[var(--color-surface-sunken)] p-3"><div class="text-xs text-[var(--color-ink-2)]">누적 공급자 사용</div><div class="mt-1 font-medium tabular-nums text-[var(--color-ink-1)]">${formatBillingAmount(billing.usage_total)}</div></div>
										</div>
										<p class="mt-2 text-xs text-[var(--color-ink-2)]">오늘 ${formatBillingAmount(billing.usage_daily)} · 이번 주 ${formatBillingAmount(billing.usage_weekly)}</p>
									</div>
								{/if}

								{#if usageUrl && usageUrl !== billingUrl}
									<div class="mt-3 flex flex-wrap gap-2">
										<Button variant="ghost" size="sm" href={usageUrl} target="_blank">프로바이더 사용량 ↗</Button>
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
		<FormModal
			bind:open={billingKeyModalOpen}
			title="조직 사용량 관리자 키"
			onClose={closeBillingKeyModal}
			onSubmit={saveBillingAdminKey}
			submitLabel={billingKeyProvider?.has_billing_admin_key ? '키 변경' : '키 설정'}
			submitting={billingKeyBusy}
		>
			<div class="space-y-4">
				<p class="text-sm text-[var(--color-ink-2)]">
					{billingKeyProvider?.name}의 {billingKeyProvider?.provider_type === 'anthropic' ? 'Anthropic Admin API' : 'OpenAI Admin API'} 조직 보고서를 조회합니다.
				</p>
				<Alert tone="info" title="Inference 키와 별도 보관">
					이 키는 모델 호출에 사용하지 않으며 조직 사용량·비용 보고서 조회에만 사용합니다. 저장된 키 값은 다시 표시되지 않습니다.
				</Alert>
				<Field
					label={billingKeyProvider?.provider_type === 'anthropic' ? 'Anthropic Admin API 키' : 'OpenAI Admin API 키'}
					for="provider-billing-admin-key"
					help={billingKeyProvider?.has_billing_admin_key ? '새 키를 입력하면 교체됩니다. 비워 저장하면 기존 키를 제거합니다.' : '조직 관리자 권한이 있는 별도 키를 입력하세요.'}
				>
					<TextInput id="provider-billing-admin-key" type="password" placeholder={billingKeyProvider?.has_billing_admin_key ? '새 키 또는 제거하려면 비움' : '관리자 API 키'} bind:value={billingAdminKey} />
				</Field>
			</div>
		</FormModal>

		<Modal bind:open={authModalOpen} onClose={closeSubscriptionAuth} ariaLabel="구독 인증">
			<div class="max-h-[calc(100vh-2rem)] w-[min(36rem,calc(100vw-2rem))] overflow-y-auto rounded-xl border border-[var(--color-line)] bg-[var(--color-surface-raised)] p-4 shadow-[var(--shadow-restraint)] sm:p-5">
				<div class="flex items-start justify-between gap-3">
					<div>
						<h3 class="text-base font-semibold text-[var(--color-ink-1)]">
							{authProvider && providerAuthMode(authProvider) === 'chatgpt_device' ? 'ChatGPT 구독 연결' : 'Claude 구독 토큰 등록'}
						</h3>
						<p class="mt-1 text-sm text-[var(--color-ink-3)]">{authProvider?.name}</p>
					</div>
					<Button variant="ghost" size="sm" onclick={closeSubscriptionAuth}>닫기</Button>
				</div>

				<Alert tone="warning" title="실험 기능 · 전체 사용자 공용" class="mt-4">
					이 연결은 Afterglow의 모든 사용자에게 공유됩니다. 개인 정보가 없는 전용 구독 계정과 공급자 정책을 확인하세요.
				</Alert>

				{#if authError}
					<Alert tone="danger" title="인증을 계속할 수 없습니다" class="mt-3">{authError}</Alert>
				{/if}

				{#if authProvider && providerAuthMode(authProvider) === 'chatgpt_device'}
					<div class="mt-5 space-y-4">
						{#if !deviceAttempt}
							<p class="text-sm leading-6 text-[var(--color-ink-2)]">
								연결을 시작하면 OpenAI 인증 페이지와 일회용 코드가 표시됩니다. 관리자 브라우저에서 코드를 승인하세요.
							</p>
							<div class="flex flex-wrap justify-end gap-2">
								<Button onclick={startDeviceAuth} disabled={authBusy}>{authBusy ? '시작 중…' : 'ChatGPT 연결'}</Button>
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
										{deviceAttempt.status === 'pending'
											? '인증 대기 중'
											: deviceAttempt.status === 'connected'
												? '연결 완료'
												: deviceAttempt.status === 'expired'
													? '인증 만료'
													: deviceAttempt.status === 'cancelled'
														? '인증 취소됨'
														: '인증 오류'}
									</Pill>
									<span class="text-xs text-[var(--color-ink-3)]">만료 {new Date(deviceAttempt.expires_at).toLocaleString()}</span>
								</div>
								{#if deviceAttempt.user_code}
									<div class="mt-4">
										<p class="text-xs text-[var(--color-ink-3)]">일회용 인증 코드</p>
										<div class="mt-1 flex flex-wrap items-center gap-2">
											<code class="rounded bg-[var(--color-surface-base)] px-3 py-2 font-mono text-lg tracking-widest text-[var(--color-ink-0)]">{deviceAttempt.user_code}</code>
											<Button variant="secondary" size="sm" onclick={copyDeviceCode}>코드 복사</Button>
										</div>
									</div>
								{/if}
								{#if deviceAttempt.verification_uri && isAllowedVerificationUri(deviceAttempt.verification_uri)}
									<Button class="mt-4" href={deviceAttempt.verification_uri}>OpenAI 인증 페이지 열기</Button>
								{:else if deviceAttempt.verification_uri}
									<Alert tone="danger" class="mt-4">OpenAI 공식 도메인이 아닌 인증 주소는 열지 않았습니다.</Alert>
								{/if}
							</div>
							<div class="flex flex-wrap justify-end gap-2">
								{#if deviceAttempt.status === 'pending'}
									<Button variant="secondary" onclick={pollCurrentDeviceAuth} disabled={authBusy}>
										{authBusy ? '확인 중…' : '지금 확인'}
									</Button>
									<Button variant="danger-outline" onclick={cancelDeviceAuth} disabled={authBusy}>인증 취소</Button>
								{:else if deviceAttempt.status !== 'connected'}
									<Button onclick={startDeviceAuth} disabled={authBusy}>다시 연결</Button>
								{/if}
							</div>
						{/if}
					</div>
				{:else if authProvider}
					<div class="mt-5 space-y-4">
						<p class="text-sm leading-6 text-[var(--color-ink-2)]">
							Claude에서 <code class="font-mono">claude setup-token</code>을 실행해 발급한 setup-token을 등록하세요. 토큰은 저장 후 다시 표시되지 않습니다.
						</p>
						<Field label="Claude setup-token" for="claude-subscription-token" required>
							<TextInput
								id="claude-subscription-token"
								type="password"
								placeholder="setup-token"
								bind:value={claudeToken}
								required
							/>
						</Field>
						<Field label="만료 시각" for="claude-subscription-expiry" help="공급자가 만료 시각을 안내한 경우에만 입력합니다.">
							<input id="claude-subscription-expiry" class={inputCls} type="datetime-local" bind:value={claudeExpiry} />
						</Field>
						<div class="flex flex-wrap justify-end gap-2">
							<Button variant="secondary" href="https://support.anthropic.com/en/articles/11145838-using-claude-code-with-your-pro-or-max-plan">공식 안내</Button>
							<Button onclick={saveClaudeSubscription} disabled={authBusy || !claudeToken.trim()}>
								{authBusy ? '저장 중…' : authProvider.has_credentials ? '토큰 교체' : '구독 토큰 등록'}
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
		<h3 class="mb-1 text-sm font-semibold text-[var(--color-ink-1)]">모델</h3>
		<p class="mb-3 text-xs text-[var(--color-ink-3)]">
			API 모델 ID는 외부 OpenAI·Anthropic 호환 요청에 사용합니다. 내부 라우팅 ID는 Lumen 전송 전용이며 다를 수 있습니다.
			'제목요약 지정'한 모델은 새 대화 제목을 자동 생성합니다. 이 호출 비용은 사용자 크레딧이 아닌 시스템에서 부담합니다.
		</p>
		<div class="{cardCls} mb-4 p-5">
			<div class="flex flex-col gap-3 sm:flex-row sm:items-center">
				<select class={inputCls} aria-label="조회 프로바이더" bind:value={mProviderId} onchange={resetDiscovery}>
					<option value="">프로바이더 선택</option>
					{#each providers as p (p.id)}
						<option value={p.id}>{p.name}</option>
					{/each}
				</select>
				<div class="flex shrink-0 gap-2">
					<Button
						variant="secondary"
						onclick={() => {
							if (!mProviderId) return toast.error('프로바이더를 선택하세요');
							void discover(mProviderId);
						}}
						disabled={!mProviderId}
					>
						모델 불러오기
					</Button>
					<Button
						variant="secondary"
						onclick={() => {
							const provider = providers.find((p) => p.id === mProviderId);
							if (provider) void openModelsDev(provider);
						}}
						disabled={!mProviderId}
					>
						models.dev 가격
					</Button>
				</div>
			</div>
			{#if discoverId === mProviderId && discoverId !== null}
				<div class="mt-4 border-t border-[var(--color-line)] pt-4" data-testid="model-discovery">
					<div class="mb-3 flex flex-wrap items-center justify-between gap-2">
						<p class="text-sm font-semibold text-[var(--color-ink-1)]">조회 후보 · {providerName(discoverId)}</p>
						<div class="flex gap-2">
							<Button variant="secondary" size="sm" onclick={retryDiscovery} disabled={discovering || registeringBulk}>다시 조회</Button>
							<Button variant="ghost" size="sm" onclick={resetDiscovery}>조회 닫기</Button>
						</div>
					</div>
					{#if discovering}
						<p class="text-sm text-[var(--color-ink-2)]">모델 목록을 불러오는 중…</p>
					{:else if discoveryError}
						<Alert tone="warning">{discoveryError}</Alert>
					{:else if discovery}
						<p class="mb-3 text-xs text-[var(--color-ink-2)]" data-testid="discovery-provenance">
							출처: {discovery.source === 'api' ? '프로바이더 API' : discovery.source === 'litellm' ? 'LiteLLM 정적 목록' : '제공된 목록 없음'}
							· 실시간 조회: {discovery.live_status === 'success' ? '응답' : discovery.live_status === 'empty' ? '정상 빈 결과' : discovery.live_status === 'unsupported' ? '미지원' : discovery.live_status === 'error' ? '실패' : '상태 미확인'}
							· 완전성: {discovery.complete === true ? '전체' : discovery.complete === false ? '불완전' : '미확인'}
							{#if discovery.fetched_at} · 조회 시각: {discovery.fetched_at}{/if}
							· 전체 {discovery.models.length}개 · 미등록 {filteredAvailable.length}개
						</p>
						{#if discovery.error}
							<Alert tone="warning" class="mb-3">{discovery.error.message} {discovery.error.retryable ? '다시 조회할 수 있습니다.' : '연결 설정을 확인하세요.'}</Alert>
						{/if}
						{#if discovery.live_status === 'error' && !discovery.error}
							<Alert tone="warning" class="mb-3">실시간 모델 조회에 실패했습니다. 연결을 확인하고 다시 조회하세요.</Alert>
						{/if}
						{#if discovery.live_status === 'empty' && discovery.models.length === 0}
							<Alert tone="info">정상적으로 조회했지만 반환된 모델이 없습니다. 필요하면 직접 추가하세요.</Alert>
						{:else if discovery.live_status === 'unsupported' && discovery.models.length === 0}
							<Alert tone="info">이 프로바이더는 모델 조회를 지원하지 않습니다. 직접 추가할 수 있습니다.</Alert>
						{:else if discovery.models.length === 0 && !discovery.error && discovery.live_status !== 'error'}
							<Alert tone="info">제공된 후보가 없습니다. 조회 상태를 확인하거나 직접 추가하세요.</Alert>
						{/if}
						{#if discovery.models.length > 0 && discovery.live_status !== 'error'}
							<Alert tone="info" class="mb-3">조회 후보는 가격이나 실행 가능성의 증거가 아닙니다. 정확한 입력·출력 및 캐시 단가와 기능을 확인한 뒤 활성화하세요.</Alert>
							{#if isSubscriptionProviderId(mProviderId)}
								<Alert tone="info" class="mb-3">구독 카탈로그 후보입니다. 현재 구독 등급에서 실제 사용할 수 있는 모델인지는 보장되지 않습니다.</Alert>
							{/if}
							<div class="mb-3 flex flex-wrap gap-3 text-xs">
								<Button variant="ghost" size="xs" onclick={() => toggleAllFiltered(true)}>전체 선택</Button>
								<Button variant="ghost" size="xs" onclick={() => toggleAllFiltered(false)}>선택 해제</Button>
							</div>
							<div class="mb-3">
								<Field label="후보 모델 필터" for="discovery-candidate-filter">
									<TextInput id="discovery-candidate-filter" type="search" placeholder="모델 ID 또는 표시 이름 검색" bind:value={availFilter} />
								</Field>
							</div>
							<div class="max-h-64 space-y-1 overflow-y-auto rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-base)] p-2">
								{#each filteredAvailable as candidate (candidate.id)}
									<label class="flex items-start gap-2 rounded-md px-2 py-2 text-sm text-[var(--color-ink-1)] hover:bg-[var(--color-surface-selected)]">
										<input class="mt-1" type="checkbox" aria-label={candidate.id} disabled={candidate.purpose === 'non_chat' || registeringBulk} bind:checked={selectedAvail[candidate.id]} />
										<span class="min-w-0 break-all"><span class="block font-mono">{candidate.id}</span>
											{#if candidate.display_name}<span class="block text-xs text-[var(--color-ink-2)]">{candidate.display_name}</span>{/if}
											<span class="block text-xs text-[var(--color-ink-2)]">{candidate.purpose === 'non_chat' ? '채팅 외 용도 · 자동 등록 불가' : candidate.purpose === 'chat' ? '채팅 후보 · 실행 미검증' : '용도 미확인 · 검토 필요'}</span>
										</span>
									</label>
								{:else}
									<p class="px-2 py-1 text-sm text-[var(--color-ink-2)]">필터에 맞는 미등록 모델이 없습니다.</p>
								{/each}
							</div>
							<div class="mt-3 flex justify-end">
								<Button onclick={reviewSelected} disabled={registeringBulk}>선택 모델 검토</Button>
							</div>
						{/if}
					{/if}
				</div>
			{/if}
		</div>
		<div class="{cardCls} mb-4 p-5">
			<div class="grid grid-cols-1 gap-3 md:grid-cols-5">
				<select class={inputCls} aria-label="수동 등록 프로바이더" bind:value={mProviderId} onchange={resetDiscovery}>
					<option value="">프로바이더 선택</option>
					{#each providers as p (p.id)}
						<option value={p.id}>{p.name}</option>
					{/each}
				</select>
				<input class={inputCls} placeholder="모델명 (예: gpt-4o)" bind:value={mName} />
				<input class={inputCls} placeholder="표시 이름 (선택)" bind:value={mDisplay} />
				<input class={inputCls} inputmode="decimal" placeholder="입력 가격 (USD / 1M tokens)" bind:value={mInputPrice} />
				<input class={inputCls} inputmode="decimal" placeholder="출력 가격 (USD / 1M tokens)" bind:value={mOutputPrice} />
			</div>
			{#if cachePricingAvailable}
			<div class="mt-4 border-t border-[var(--color-line)] pt-4" role="group" aria-labelledby="model-create-cache-heading" data-testid="model-create-cache-prices">
				<p id="model-create-cache-heading" class="text-xs font-semibold text-[var(--color-ink-1)]">프롬프트 캐시 단가 (선택)</p>
				<p class="mt-1 text-xs leading-relaxed text-[var(--color-ink-2)]">
					입력·출력 가격과 별도로 항목마다 저장합니다. 비워 둔 항목의 캐시 토큰은 단가를 설정할 때까지 0 USD로 청구하며 LiteLLM·models.dev 기본 단가로 대체하지 않습니다.
				</p>
				<div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
					{#each CACHE_PRICE_FIELDS as field (field.key)}
						<Field label={field.label} for="model-create-cache-{field.slug}" help="USD / 1M tokens" error={mCacheErrors[field.key]}>
							<TextInput
								id="model-create-cache-{field.slug}"
								inputmode="decimal"
								placeholder="예: 0.3"
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
				<Button onclick={addModel} disabled={addingModel || providers.length === 0}>
					{addingModel ? '추가 중…' : '+ 모델 추가'}
				</Button>
			</div>
		</div>

		{#if loading}
			<div class="{cardCls} h-20 animate-pulse"></div>
		{:else if models.length === 0}
			<p class="px-1 text-sm text-[var(--color-ink-3)]">등록된 모델이 없습니다.</p>
		{:else}
			<div class="mb-2 flex items-center justify-between gap-3 px-1">
				<label class="flex cursor-pointer items-center gap-2 text-xs text-[var(--color-ink-2)]">
					<input
						type="checkbox"
						checked={allModelsSelected}
						onchange={(e) => toggleAllModels(e.currentTarget.checked)}
					/>
					전체 선택{selectedCount > 0 ? ` (${selectedCount})` : ''}
				</label>
				{#if selectedCount > 0}
					<Button variant="danger-outline" size="sm" onclick={deleteSelectedModels} disabled={deletingBulk}>
						{deletingBulk ? '삭제 중…' : `선택 삭제 (${selectedCount})`}
					</Button>
				{/if}
			</div>
			<div class="space-y-2">
				{#each models as m (m.id)}
					<div class="{cardCls} flex flex-col items-stretch gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
						<div class="flex min-w-0 items-start gap-3">
							<input class="mt-0.5 shrink-0" type="checkbox" bind:checked={selectedModelIds[m.id]} aria-label="{m.display_name || publicModelName(m)} 선택" />
							<div class="min-w-0 flex-1">
							<div class="flex flex-wrap items-center gap-2">
								<span class="truncate text-sm font-medium text-[var(--color-ink-1)]">{displayModelTitle(m)}</span>
								<Pill tone={m.is_active ? 'success' : 'neutral'} size="xs">{m.is_active ? '활성 · 저장됨' : '비활성 · 저장됨'}</Pill>
								{#if m.is_title_model}
									<span class="rounded bg-[var(--color-accent)]/15 px-1.5 py-0.5 text-xs text-[var(--color-accent)]">
										제목 요약
									</span>
								{/if}
								<Pill tone={m.price_source === 'manual' ? 'success' : m.price_source === 'models.dev' ? 'accent' : 'neutral'} size="xs">
									{m.price_source === 'manual' ? '수동' : m.price_source === 'models.dev' ? 'models.dev' : m.effective_price_source?.startsWith('perplexity_agent_api_') ? 'Perplexity 공식 가격' : m.effective_price_source === 'litellm' ? 'LiteLLM 기본값' : '가격 출처 미확인'}
								</Pill>
								<Pill tone={m.effective_input_price_per_million != null && m.effective_output_price_per_million != null ? 'accent' : 'warning'} size="xs">
									{m.effective_input_price_per_million != null && m.effective_output_price_per_million != null ? '기본 텍스트 단가 표시됨' : '가격 미확인'}
								</Pill>
								<Pill tone={capabilityStatus(m) === '고급 기능 미확인' ? 'neutral' : 'accent'} size="xs">{capabilityStatus(m)}</Pill>
								<ModelCapabilityBadges caps={m.capabilities || m.effective_capabilities} size="xs" />
							</div>
							<div class="mt-0.5 text-xs text-[var(--color-ink-3)]">
								<div class="break-all">API ID: <code class="font-mono">{publicModelName(m)}</code> · provider: <code class="font-mono">{m.api_provider || providerType(m.provider_id)}</code></div>
								{#if m.model_name !== publicModelName(m)}
									<div class="mt-0.5 break-all">내부 라우팅 ID: <code class="font-mono">{m.model_name}</code></div>
								{/if}
								<div class="mt-0.5">{providerName(m.provider_id)}</div>
							</div>
							<div class="mt-1 text-xs text-[var(--color-ink-2)]">
								입력 {formatPricePerMillion(m.effective_input_price_per_million)} · 출력 {formatPricePerMillion(m.effective_output_price_per_million)} USD / 1M tokens
							</div>
							{#if !cachePricingSupported(m)}
								<div class="mt-0.5 text-xs text-[var(--color-ink-2)]" data-testid="model-cache-prices">
									캐시 단가 미지원 · 이 Lumen 버전은 캐시 단가를 받지 않습니다
								</div>
							{:else if cachePriceState(m) === 'none'}
								<div class="mt-0.5 text-xs text-[var(--color-ink-2)]" data-testid="model-cache-prices">
									캐시 단가 미설정 · 캐시 토큰은 단가를 설정할 때까지 0 USD로 청구됩니다
								</div>
							{:else}
								<div class="mt-0.5 text-xs tabular-nums text-[var(--color-ink-2)]" data-testid="model-cache-prices">
									캐시 읽기 {formatCachePrice(m.cache_read_price_per_million)} · 캐시 쓰기 5분 {formatCachePrice(m.cache_write_price_per_million)} · 캐시 쓰기 1시간 {formatCachePrice(m.cache_write_1h_price_per_million)} USD / 1M tokens{cachePriceState(m) === 'partial' ? ' · 미설정 항목은 0 USD로 청구' : ''}
								</div>
							{/if}
						</div>
						</div>
						<div class="flex flex-wrap items-center justify-end gap-x-3 gap-y-2 border-t border-[var(--color-line)] pt-3 text-xs sm:shrink-0 sm:border-t-0 sm:pt-0">
							<button class={rowActionCls} onclick={() => setTitleModel(m)}>
								{m.is_title_model ? '제목요약 해제' : '제목요약 지정'}
							</button>
							<button class={rowActionCls} onclick={() => openPriceEditor(m)}>가격 수정</button>
							<Button variant="ghost" size="xs" onclick={() => openCapabilityEditor(m)}>기능 수정</Button>
							<button class={rowActionCls} onclick={() => toggleModel(m)}>{m.is_active ? '비활성화' : '활성화'}</button>
							<button class="text-[var(--color-state-danger)] transition-opacity hover:opacity-80" onclick={() => deleteModel(m.id)}>삭제</button>
						</div>
					</div>
				{/each}
			</div>
		{/if}
	</section>
	{/if}

	{#if section === 'models'}
	<Modal open={registrationReview !== null} onClose={() => { if (!registeringBulk) registrationReview = null; }} dismissible={!registeringBulk} ariaLabel="선택 모델 등록 검토">
		<div class="max-h-[calc(100vh-2rem)] w-[min(32rem,calc(100vw-2rem))] overflow-y-auto rounded-xl border border-[var(--color-line)] bg-[var(--color-surface-raised)] p-5 shadow-[var(--shadow-restraint)]" data-testid="model-registration-review">
			<h3 class="text-base font-semibold text-[var(--color-ink-1)]">선택 모델 등록 검토</h3>
			{#if registrationReview}
				<p class="mt-2 text-sm text-[var(--color-ink-2)]">프로바이더: {registrationReview.providerName} · {registrationReview.entries.length}개 후보</p>
				<Alert tone="warning" class="mt-3">조회 결과는 가격·기능·실행 가능성을 검증하지 않습니다. 비활성 저장 후 가격 수정 또는 models.dev 가격에서 정확한 단가를 지정할 수 있습니다. 활성화는 관리자 입력 단가가 모두 있을 때만 가능하며, 캐시 단가와 기능은 별도 확인이 필요합니다.</Alert>
				<div class="mt-4 max-h-[min(50vh,28rem)] space-y-3 overflow-y-auto">
					{#each registrationReview.entries as entry, index (entry.name)}
						<div class="rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-base)] p-3" data-testid="registration-entry">
							<p class="break-all font-mono text-sm text-[var(--color-ink-1)]">{entry.name}</p>
							<p class="mt-1 text-xs text-[var(--color-ink-2)]">
								{entry.purpose === 'unknown' ? '용도 미확인 · 채팅 실행 미검증' : '채팅 후보 · 실행 미검증'}
								· 제공된 입력 한도 {entry.inputTokenLimit ?? '미확인'} · 출력 한도 {entry.outputTokenLimit ?? '미확인'} tokens (참고용, 기능 설정에 반영하지 않음)
							</p>
							{#if registrationOutcomes[entry.name] === 'success'}
								<Pill tone="success" size="sm">등록됨 · 재요청하지 않음</Pill>
							{:else}
								{#if registrationOutcomes[entry.name] === 'failed'}<Pill tone="warning" size="sm">등록 실패 · 이 모델만 재시도</Pill>{/if}
								<div class="mt-3 grid gap-3 sm:grid-cols-2">
									<div class="sm:col-span-2">
										<Field label="표시 이름 · {entry.name}" for="review-display-{index}">
											<TextInput id="review-display-{index}" placeholder="선택 사항" bind:value={entry.displayName} disabled={registeringBulk} />
										</Field>
									</div>
									<Field label="입력 단가 · {entry.name}" for="review-input-{index}" help="USD / 1M tokens" error={reviewPriceError(entry)}>
										<TextInput id="review-input-{index}" inputmode="decimal" placeholder="예: 2" bind:value={entry.inputPrice} disabled={registeringBulk} ariaInvalid={Boolean(reviewPriceError(entry))} />
									</Field>
									<Field label="출력 단가 · {entry.name}" for="review-output-{index}" help="USD / 1M tokens" error={reviewPriceError(entry)}>
										<TextInput id="review-output-{index}" inputmode="decimal" placeholder="예: 8" bind:value={entry.outputPrice} disabled={registeringBulk} ariaInvalid={Boolean(reviewPriceError(entry))} />
									</Field>
								</div>
							{/if}
						</div>
					{/each}
				</div>
				<div class="mt-5 flex flex-wrap justify-end gap-2">
					<Button variant="secondary" onclick={() => (registrationReview = null)} disabled={registeringBulk}>취소</Button>
					<Button onclick={() => registerSelected(false)} disabled={registeringBulk || registrationMode === 'active' || registrationReview.entries.some((entry) => registrationOutcomes[entry.name] !== 'success' && Boolean(reviewPriceError(entry)))}>{registeringBulk ? '등록 중…' : '비활성으로 저장'}</Button>
					<Button variant="accent" onclick={() => registerSelected(true)} disabled={registeringBulk || registrationMode === 'inactive' || !reviewCanActivate(registrationReview)}>가격 확인 후 등록·활성화</Button>
				</div>
			{/if}
		</div>
	</Modal>

	<Modal open={editingPrice !== null} onClose={() => (editingPrice = null)} ariaLabel="모델 가격 수정">
		<div class="max-h-[calc(100vh-2rem)] w-[min(32rem,calc(100vw-2rem))] overflow-y-auto rounded-xl border border-[var(--color-line)] bg-[var(--color-surface-raised)] p-5 shadow-[var(--shadow-restraint)]">
			<h3 class="text-base font-semibold text-[var(--color-ink-1)]">모델 가격 수정</h3>
			<p class="mt-1 text-sm text-[var(--color-ink-2)]">입력·출력 가격은 함께 저장하거나 모두 비우면 수동 단가가 해제됩니다. 대체 단가가 없으면 가격 미확인으로 표시됩니다.</p>
			<div class="mt-4 grid gap-3 sm:grid-cols-2">
				<Field label="입력" for="model-edit-input-price">
					<TextInput id="model-edit-input-price" inputmode="decimal" placeholder="USD / 1M tokens" bind:value={editInputPrice} />
				</Field>
				<Field label="출력" for="model-edit-output-price">
					<TextInput id="model-edit-output-price" inputmode="decimal" placeholder="USD / 1M tokens" bind:value={editOutputPrice} />
				</Field>
			</div>
			{#if editingPrice && cachePricingSupported(editingPrice)}
			<div class="mt-4 border-t border-[var(--color-line)] pt-4" role="group" aria-labelledby="model-edit-cache-heading">
				<p id="model-edit-cache-heading" class="text-sm font-semibold text-[var(--color-ink-1)]">프롬프트 캐시 단가 (선택)</p>
				<p class="mt-1 text-xs leading-relaxed text-[var(--color-ink-2)]">
					항목마다 따로 저장하며 입력·출력 가격과 함께 입력할 필요가 없습니다. 비우고 저장하면 해당 단가를 지우고, 그 캐시 토큰은 다시 설정할 때까지 0 USD로 청구됩니다. LiteLLM·models.dev 기본 단가로 대체하지 않습니다.
				</p>
				<div class="mt-3 grid gap-3 sm:grid-cols-3">
					{#each CACHE_PRICE_FIELDS as field (field.key)}
						<Field label={field.label} for="model-edit-cache-{field.slug}" help="USD / 1M tokens" error={editCacheErrors[field.key]}>
							<TextInput
								id="model-edit-cache-{field.slug}"
								inputmode="decimal"
								placeholder="예: 0.3"
								bind:value={editCachePrices[field.key]}
								ariaInvalid={Boolean(editCacheErrors[field.key])}
								oninput={(event) => (editCacheErrors = recheckCachePrice(editCacheErrors, field.key, (event.currentTarget as HTMLInputElement).value))}
							/>
						</Field>
					{/each}
				</div>
			</div>
			{/if}
			<div class="mt-5 flex justify-end gap-2">
				<Button variant="secondary" onclick={() => (editingPrice = null)}>취소</Button>
				<Button onclick={savePrice}>저장</Button>
			</div>
		</div>
	</Modal>

	<Modal open={editingCapabilities !== null} onClose={() => { if (!capSaving) editingCapabilities = null; }} dismissible={!capSaving} ariaLabel="모델 기능 수정">
		<div class="max-h-[calc(100vh-2rem)] w-[min(32rem,calc(100vw-2rem))] overflow-y-auto rounded-xl border border-[var(--color-line)] bg-[var(--color-surface-raised)] p-5 shadow-[var(--shadow-restraint)]">
			<h3 class="text-base font-semibold text-[var(--color-ink-1)]">모델 기능 수정</h3>
			{#if editingCapabilities}
				<p class="mt-2 break-all font-mono text-sm text-[var(--color-ink-1)]">{editingCapabilities.model_name}</p>
				<Alert tone="warning" class="mt-3">현재 기능 출처: {editingCapabilities.effective_capability_source ?? '미확인'}. 표시된 카탈로그 정보는 실행 검증이 아닙니다. 저장하면 선택한 기능을 관리자 수동 설정으로 지정합니다. 웹 검색·컴팩션은 이 설정으로 켤 수 없습니다.</Alert>
				{#if capSuggestedInputLimit !== null}
					<p class="mt-3 text-sm text-[var(--color-ink-2)]">조회 후보의 입력 한도 {capSuggestedInputLimit} tokens를 컨텍스트 한도 초안으로 채웠습니다. 입력 한도와 전체 컨텍스트 한도는 다를 수 있으므로 확인 후 저장하세요.</p>
				{/if}
				<div class="mt-4 grid gap-3 sm:grid-cols-2">
					<label class="flex items-center gap-2 text-sm text-[var(--color-ink-1)]"><input type="checkbox" bind:checked={capVision} disabled={capSaving} />이미지 입력 (Vision)</label>
					<label class="flex items-center gap-2 text-sm text-[var(--color-ink-1)]"><input type="checkbox" bind:checked={capReasoning} disabled={capSaving} />추론 (Reasoning)</label>
					<label class="flex items-center gap-2 text-sm text-[var(--color-ink-1)]"><input type="checkbox" bind:checked={capToolCall} disabled={capSaving} />도구 호출 (Tools)</label>
					<label class="flex items-center gap-2 text-sm text-[var(--color-ink-1)]"><input type="checkbox" bind:checked={capAttachment} disabled={capSaving} />파일 첨부 (Files)</label>
				</div>
				<div class="mt-4">
					<Field label="컨텍스트 한도" for="model-capability-context" help="전체 컨텍스트 tokens · 미확인이면 비워두세요" error={contextLimitError(capContextLimit)}>
						<TextInput id="model-capability-context" inputmode="numeric" placeholder="예: 128000" bind:value={capContextLimit} disabled={capSaving} ariaInvalid={Boolean(contextLimitError(capContextLimit))} />
					</Field>
				</div>
				{#if capError}<Alert tone="warning" class="mt-3">{capError}</Alert>{/if}
				<div class="mt-5 flex justify-end gap-2">
					<Button variant="secondary" onclick={() => (editingCapabilities = null)} disabled={capSaving}>취소</Button>
					<Button onclick={saveCapabilities} disabled={capSaving || Boolean(contextLimitError(capContextLimit))}>{capSaving ? '저장 중…' : '기능 설정 저장'}</Button>
				</div>
			{/if}
		</div>
	</Modal>

	<Modal bind:open={modelsDevOpen} ariaLabel="models.dev 추천 가격">
		<div class="max-h-[calc(100vh-2rem)] w-[min(48rem,calc(100vw-2rem))] overflow-y-auto rounded-xl border border-[var(--color-line)] bg-[var(--color-surface-raised)] p-5 shadow-[var(--shadow-restraint)]">
			<h3 class="text-base font-semibold text-[var(--color-ink-1)]">models.dev 추천 가격</h3>
			<p class="mt-1 text-sm text-[var(--color-ink-2)]">
				<a class="underline" href="https://models.dev" target="_blank" rel="noreferrer">models.dev</a>의 기본 input/output 단가만 적용합니다. 수동 확정 가격은 덮어쓰지 않습니다.
				캐시 단가는 가져오지 않으므로 각 모델의 <strong class="font-medium text-[var(--color-ink-1)]">가격 수정</strong>에서 직접 설정하세요.
			</p>
			{#if modelsDevError}<Alert tone="warning" class="mt-3">{modelsDevError}</Alert>{/if}
			<div class="mt-4 space-y-3">
				<div>
					<label class="mb-1 block text-sm text-[var(--color-ink-2)]" for="models-dev-provider-search">가격표 프로바이더 검색</label>
					<TextInput
						id="models-dev-provider-search"
						type="search"
						placeholder="이름 또는 ID로 검색"
						value={modelsDevProviderSearch}
						oninput={updateModelsDevProviderSearch}
					/>
				</div>
				<div aria-live="polite">
					<label class="mb-1 block text-sm text-[var(--color-ink-2)]" for="models-dev-provider">가격표 프로바이더</label>
					{#if filteredModelsDevProviders.length > 0}
						<select id="models-dev-provider" class={inputCls} bind:value={selectedModelsDevProviderId} onchange={loadModelsDevProvider}>
							<option value="" disabled>가격표 프로바이더 선택</option>
							{#each filteredModelsDevProviders as provider (provider.id)}<option value={provider.id}>{provider.name} ({provider.model_count})</option>{/each}
						</select>
					{:else if modelsDevProviders.length > 0}
						<p class="rounded-lg border border-[var(--color-line)] px-3 py-2 text-sm text-[var(--color-ink-3)]">검색 조건에 맞는 가격표 프로바이더가 없습니다.</p>
					{:else}
						<p class="rounded-lg border border-[var(--color-line)] px-3 py-2 text-sm text-[var(--color-ink-3)]">등록된 프로바이더와 일치하는 models.dev 가격표가 없습니다.</p>
					{/if}
				</div>
				<p class="text-xs text-[var(--color-ink-3)]">등록된 프로바이더와 일치하는 가격표만 표시합니다.</p>
			</div>
			{#if modelsDevLoading}
				<p class="mt-4 text-sm text-[var(--color-ink-3)]">가격표를 불러오는 중…</p>
			{:else}
				<div class="mt-4 space-y-2">
					{#each models.filter((model) => model.provider_id === modelsDevProvider?.id) as model (model.id)}
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
									{model.model_name}{model.price_source === 'manual' ? ' · 수동 가격 보존' : ''}
								</span>
								<select class={inputCls} disabled={model.price_source === 'manual'} bind:value={modelsDevSelections[model.id]}>
									<option value="">가격표 모델 선택</option>
									{#each modelsDevModels.filter((external) => external.price_available) as external (external.id)}
										<option value={external.id}>{external.id} · ${formatPricePerMillion(external.input_price_per_million)}/${formatPricePerMillion(external.output_price_per_million)} / 1M</option>
									{/each}
								</select>
							</div>
							{#if modelsDevSelections[model.id]}
								{@const selected = modelsDevModels.find((external) => external.id === modelsDevSelections[model.id])}
								{#if selected && selected.unsupported_price_fields.length > 0}
									<Alert tone="warning" class="mt-2">tier/cache/reasoning/audio 단가는 적용하지 않습니다: {selected.unsupported_price_fields.join(', ')}. 캐시 단가는 적용 후 가격 수정에서 설정할 수 있습니다.</Alert>
								{/if}
							{/if}
						</div>
					{/each}
				</div>
			{/if}
			<div class="mt-5 flex justify-end gap-2">
				<Button variant="secondary" onclick={() => (modelsDevOpen = false)}>취소</Button>
				<Button onclick={importModelsDevPrices} disabled={modelsDevImporting || modelsDevLoading || !selectedModelsDevProviderId}>
					{modelsDevImporting ? '적용 중…' : '선택 가격 적용'}
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
