<script lang="ts">
	import { onDestroy } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { toast } from '$lib/stores/toast';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import ChatExtensionsManager from '$lib/components/chat/ChatExtensionsManager.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import Field from '$lib/components/ui/Field.svelte';
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
		billing_capability?: 'openrouter_key' | 'deepseek_balance' | null;
	}

	interface ProviderBillingBalance {
		currency: string;
		total: string;
		granted: string;
		purchased: string;
	}

	interface ProviderBilling {
		provider_id: number;
		provider_type: string;
		capability: 'openrouter_key' | 'deepseek_balance';
		status: 'available' | 'unavailable' | 'unsupported';
		reason: string | null;
		fetched_at: string;
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
		effective_price_source: 'manual' | 'models.dev' | 'litellm' | 'partial' | 'unpriced' | null;
		models_dev_model_id: string | null;
		price_source: 'manual' | 'models.dev' | null;
		capabilities?: ModelCapabilities | null;
		effective_capabilities?: ModelCapabilities | null;
	}

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	let providers = $state<Provider[]>([]);
	let models = $state<Model[]>([]);
	let loading = $state(true);
	let error = $state('');
	let billingByProvider = $state<Record<number, ProviderBilling>>({});
	let billingLoading = $state<Record<number, boolean>>({});

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
	let addingModel = $state(false);

	let editingPrice = $state<Model | null>(null);
	let editInputPrice = $state('');
	let editOutputPrice = $state('');

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

	// 모델 discovery (프로바이더 API에서 목록 불러오기 → 필터 → 선택 등록)
	let discoverId = $state<number | null>(null);
	let available = $state<string[]>([]);
	let availSource = $state('');
	let availFilter = $state('');
	let selectedAvail = $state<Record<string, boolean>>({});
	let discovering = $state(false);
	let registeringBulk = $state(false);

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
		if (discoverId === null) return [];
		const reg = registeredNames(discoverId);
		const f = availFilter.toLowerCase();
		return available.filter((m) => m.toLowerCase().includes(f) && !reg.has(m));
	});

	function formatBillingAmount(value: string | null): string {
		if (value === null) return '—';
		return Number(value).toLocaleString('en-US', { maximumFractionDigits: 6 });
	}

	function billingFailureLabel(reason: string | null): string {
		if (reason === 'credential_not_configured') return 'API 키가 설정되지 않았습니다.';
		if (reason === 'credential_unavailable') return '저장된 API 키를 복호화할 수 없습니다.';
		if (reason === 'provider_authorization_failed') return '프로바이더가 이 API 키의 결제 조회를 거부했습니다.';
		if (reason === 'provider_request_failed') return '프로바이더 결제 API 요청이 실패했습니다.';
		return '프로바이더 결제 API에 연결할 수 없습니다.';
	}

	async function loadProviderBilling(provider: Provider) {
		if (!token || !provider.billing_capability) return;
		billingLoading = { ...billingLoading, [provider.id]: true };
		try {
			const snapshot = await api.get<ProviderBilling>(
				`/api/v1/chat/admin/providers/${provider.id}/billing`,
				token,
				projectId
			);
			billingByProvider = { ...billingByProvider, [provider.id]: snapshot };
		} catch (caught) {
			billingByProvider = {
				...billingByProvider,
				[provider.id]: {
					provider_id: provider.id,
					provider_type: provider.provider_type,
					capability: provider.billing_capability,
					status: 'unavailable',
					reason: caught instanceof ApiError && caught.status === 401
						? 'provider_authorization_failed'
						: 'provider_unavailable',
					fetched_at: new Date().toISOString(),
					is_available: null,
					is_free_tier: null,
					limit: null,
					remaining: null,
					usage_total: null,
					usage_daily: null,
					usage_weekly: null,
					usage_monthly: null,
					balances: []
				}
			};
		} finally {
			billingLoading = { ...billingLoading, [provider.id]: false };
		}
	}

	async function load() {
		if (!token) return;
		loading = true;
		try {
			const [ps, ms] = await Promise.all([
				api.get<Provider[]>('/api/v1/chat/admin/providers', token, projectId),
				api.get<Model[]>('/api/v1/chat/admin/models', token, projectId)
			]);
			providers = ps;
			if (mProviderId === '' && ps.length === 1) mProviderId = ps[0].id;
			models = ms;
			const supportedIds = new Set(ps.filter((provider) => provider.billing_capability).map((provider) => provider.id));
			billingByProvider = Object.fromEntries(
				Object.entries(billingByProvider).filter(([id]) => supportedIds.has(Number(id)))
			);
			void Promise.allSettled(
				ps.filter((provider) => provider.billing_capability).map((provider) => loadProviderBilling(provider))
			);
			error = '';
		} catch (e) {
			error = e instanceof ApiError ? `조회 실패 (${e.status})` : '서버 오류';
		} finally {
			loading = false;
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
			await load();
			toast.success('API 키가 갱신되었습니다');
		} catch {
			toast.error('갱신 실패');
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
		const prices = pricePayload(mInputPrice, mOutputPrice);
		if (prices === undefined) return;
		addingModel = true;
		try {
			await api.post(
				'/api/v1/chat/admin/models',
				{ provider_id: mProviderId, model_name: mName.trim(), display_name: mDisplay.trim() || null, ...prices },
				token,
				projectId
			);
			mName = '';
			mDisplay = '';
			mInputPrice = '';
			mOutputPrice = '';
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
	}

	async function savePrice() {
		if (!editingPrice) return;
		const prices = pricePayload(editInputPrice, editOutputPrice);
		if (!prices) return;
		try {
			await api.patch(`/api/v1/chat/admin/models/${editingPrice.id}`, prices, token, projectId);
			editingPrice = null;
			await load();
			toast.success('모델 가격을 저장했습니다');
		} catch (e) {
			toast.error(e instanceof ApiError ? e.message : '가격 저장 실패');
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
			discoverId = null;
			return;
		}
		discoverId = providerId;
		discovering = true;
		available = [];
		availSource = '';
		availFilter = '';
		selectedAvail = {};
		try {
			const res = await api.get<{ models: string[]; source: string }>(
				`/api/v1/chat/admin/providers/${providerId}/available-models`,
				token,
				projectId
			);
			available = res.models;
			availSource = res.source;
			if (res.models.length === 0) {
				toast.error('모델을 찾지 못했습니다 (API 키/Base URL 확인)');
			}
		} catch (e) {
			toast.error(e instanceof ApiError ? e.message : '모델 조회 실패');
			discoverId = null;
		} finally {
			discovering = false;
		}
	}

	async function registerSelected() {
		if (discoverId === null) return;
		const names = Object.keys(selectedAvail).filter((k) => selectedAvail[k]);
		if (names.length === 0) {
			toast.error('등록할 모델을 선택하세요');
			return;
		}
		registeringBulk = true;
		let ok = 0;
		const failed: string[] = [];
		try {
			for (const name of names) {
				try {
					await api.post(
						'/api/v1/chat/admin/models',
						{ provider_id: discoverId, model_name: name },
						token,
						projectId
					);
					ok++;
				} catch {
					failed.push(name);
				}
			}
			await load();
			if (ok > 0) toast.success(`${ok}개 모델을 등록했습니다`);
			if (failed.length > 0) toast.error(`${failed.length}개 등록 실패 (중복 등)`);
			selectedAvail = {};
		} finally {
			registeringBulk = false;
		}
	}

	function toggleAllFiltered(checked: boolean) {
		const next = { ...selectedAvail };
		for (const m of filteredAvailable) next[m] = checked;
		selectedAvail = next;
	}

	async function deleteModel(id: number) {
		if (!(await confirmDialog('모델을 삭제하시겠습니까?'))) return;
		try {
			await api.delete(`/api/v1/chat/admin/models/${id}`, token, projectId);
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
		try {
			await api.patch(`/api/v1/chat/admin/models/${m.id}`, { is_active: !m.is_active }, token, projectId);
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

						{#if p.billing_capability}
							<div class="mt-3 border-t border-[var(--color-line)] pt-3">
								<div class="flex items-center justify-between gap-3">
									<div class="flex items-center gap-2">
										<span class="text-xs font-semibold text-[var(--color-ink-2)]">프로바이더 결제 현황</span>
										<Pill tone="neutral" size="xs">{p.billing_capability === 'openrouter_key' ? '현재 API 키' : '계정 잔액'}</Pill>
									</div>
									<Button variant="ghost" size="sm" disabled={billingLoading[p.id]} onclick={() => void loadProviderBilling(p)}>
										{billingLoading[p.id] ? '조회 중…' : '새로고침'}
									</Button>
								</div>
								{#if billingLoading[p.id] && !billing}
									<p class="mt-2 text-xs text-[var(--color-ink-3)]">결제 정보를 조회하는 중…</p>
								{:else if billing?.status === 'unavailable'}
									<Alert tone="warning" class="mt-2">{billingFailureLabel(billing.reason)}</Alert>
								{:else if billing?.status === 'available' && billing.capability === 'openrouter_key'}
									<div class="mt-2 grid grid-cols-2 gap-2 lg:grid-cols-4">
										<div class="rounded-lg bg-[var(--color-surface-sunken)] p-3"><div class="text-xs text-[var(--color-ink-3)]">남은 한도</div><div class="mt-1 font-medium tabular-nums text-[var(--color-ink-1)]">{formatBillingAmount(billing.remaining)}</div></div>
										<div class="rounded-lg bg-[var(--color-surface-sunken)] p-3"><div class="text-xs text-[var(--color-ink-3)]">한도</div><div class="mt-1 font-medium tabular-nums text-[var(--color-ink-1)]">{formatBillingAmount(billing.limit)}</div></div>
										<div class="rounded-lg bg-[var(--color-surface-sunken)] p-3"><div class="text-xs text-[var(--color-ink-3)]">이번 달 사용</div><div class="mt-1 font-medium tabular-nums text-[var(--color-ink-1)]">{formatBillingAmount(billing.usage_monthly)}</div></div>
										<div class="rounded-lg bg-[var(--color-surface-sunken)] p-3"><div class="text-xs text-[var(--color-ink-3)]">누적 사용</div><div class="mt-1 font-medium tabular-nums text-[var(--color-ink-1)]">{formatBillingAmount(billing.usage_total)}</div></div>
									</div>
									<p class="mt-2 text-xs text-[var(--color-ink-3)]">오늘 {formatBillingAmount(billing.usage_daily)} · 이번 주 {formatBillingAmount(billing.usage_weekly)} · {billing.is_free_tier ? '무료 티어' : '유료 크레딧'}</p>
								{:else if billing?.status === 'available' && billing.capability === 'deepseek_balance'}
									<div class="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
										{#each billing.balances as balance (balance.currency)}
											<div class="rounded-lg bg-[var(--color-surface-sunken)] p-3">
												<div class="flex items-center justify-between gap-2"><span class="text-xs text-[var(--color-ink-3)]">{balance.currency}</span><Pill tone={billing.is_available ? 'success' : 'warning'} size="xs">{billing.is_available ? '사용 가능' : '잔액 부족'}</Pill></div>
												<div class="mt-1 font-medium tabular-nums text-[var(--color-ink-1)]">잔액 {formatBillingAmount(balance.total)}</div>
												<div class="mt-1 text-xs tabular-nums text-[var(--color-ink-3)]">구매 {formatBillingAmount(balance.purchased)} · 지급 {formatBillingAmount(balance.granted)}</div>
											</div>
										{/each}
									</div>
								{/if}
							</div>
						{/if}
					</div>
				{/each}
			</div>
		{/if}
	</section>
	{/if}

	{#if section === 'providers'}
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
				<select class={inputCls} bind:value={mProviderId}>
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
			{#if discoverId === mProviderId}
				<div class="mt-4 border-t border-[var(--color-line)] pt-4">
					{#if discovering}
						<p class="text-sm text-[var(--color-ink-3)]">모델 목록을 불러오는 중…</p>
					{:else if available.length === 0}
						<p class="text-sm text-[var(--color-ink-3)]">불러온 모델이 없습니다. API 키/Base URL을 확인하거나 직접 추가하세요.</p>
					{:else}
						<div class="mb-3 flex flex-wrap items-center justify-between gap-2">
							<span class="text-xs text-[var(--color-ink-3)]">
								{availSource === 'api' ? '프로바이더 API' : 'LiteLLM 정적 목록'} · 전체 {available.length}개 · 미등록 {filteredAvailable.length}개
							</span>
							<div class="flex items-center gap-2 text-xs">
								<button class={rowActionCls} onclick={() => toggleAllFiltered(true)}>전체 선택</button>
								<button class={rowActionCls} onclick={() => toggleAllFiltered(false)}>선택 해제</button>
							</div>
						</div>
						{#if isSubscriptionProviderId(mProviderId)}
							<Alert tone="info" class="mb-3">정적 카탈로그 후보입니다. 현재 구독 등급에서 실제 사용할 수 있는 모델인지는 보장되지 않습니다.</Alert>
						{/if}
						<input class="{inputCls} mb-3" placeholder="모델 필터 (예: gpt-4)" bind:value={availFilter} />
						<div class="max-h-64 space-y-1 overflow-y-auto rounded border border-[var(--color-line)] bg-[var(--color-surface-base)] p-2">
							{#each filteredAvailable as mid (mid)}
								<label class="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-sm text-[var(--color-ink-1)] hover:bg-[var(--color-line)]">
									<input type="checkbox" bind:checked={selectedAvail[mid]} />
									<span class="truncate">{mid}</span>
								</label>
							{:else}
								<p class="px-2 py-1 text-sm text-[var(--color-ink-3)]">필터에 맞는 미등록 모델이 없습니다.</p>
							{/each}
						</div>
						<div class="mt-3 flex justify-end">
							<Button onclick={registerSelected} disabled={registeringBulk}>
								{registeringBulk ? '등록 중…' : '선택 모델 등록'}
							</Button>
						</div>
					{/if}
				</div>
			{/if}
		</div>
		<div class="{cardCls} mb-4 p-5">
			<div class="grid grid-cols-1 gap-3 md:grid-cols-5">
				<select class={inputCls} bind:value={mProviderId}>
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
								<span
									class="rounded px-1.5 py-0.5 text-xs {m.is_active
										? 'bg-[var(--color-state-success)]/15 text-[var(--color-state-success)]'
										: 'bg-[var(--color-line)] text-[var(--color-ink-3)]'}"
								>
									{m.is_active ? '활성' : '비활성'}
								</span>
								{#if m.is_title_model}
									<span class="rounded bg-[var(--color-accent)]/15 px-1.5 py-0.5 text-xs text-[var(--color-accent)]">
										제목 요약
									</span>
								{/if}
								<Pill tone={m.price_source === 'manual' ? 'success' : m.price_source === 'models.dev' ? 'accent' : 'neutral'} size="xs">
									{m.price_source === 'manual' ? '수동' : m.price_source === 'models.dev' ? 'models.dev' : 'LiteLLM 기본값'}
								</Pill>
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
						</div>
						</div>
						<div class="flex flex-wrap items-center justify-end gap-x-3 gap-y-2 border-t border-[var(--color-line)] pt-3 text-xs sm:shrink-0 sm:border-t-0 sm:pt-0">
							<button class={rowActionCls} onclick={() => setTitleModel(m)}>
								{m.is_title_model ? '제목요약 해제' : '제목요약 지정'}
							</button>
							<button class={rowActionCls} onclick={() => openPriceEditor(m)}>가격 수정</button>
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
	<Modal open={editingPrice !== null} onClose={() => (editingPrice = null)} ariaLabel="모델 가격 수정">
		<div class="w-[min(32rem,calc(100vw-2rem))] rounded-xl border border-[var(--color-line)] bg-[var(--color-surface-raised)] p-5 shadow-[var(--shadow-restraint)]">
			<h3 class="text-base font-semibold text-[var(--color-ink-1)]">모델 가격 수정</h3>
			<p class="mt-1 text-sm text-[var(--color-ink-3)]">두 가격을 함께 저장하거나 모두 비우면 LiteLLM 기본 가격을 사용합니다.</p>
			<div class="mt-4 grid gap-3 sm:grid-cols-2">
				<input class={inputCls} inputmode="decimal" placeholder="입력 USD / 1M tokens" bind:value={editInputPrice} />
				<input class={inputCls} inputmode="decimal" placeholder="출력 USD / 1M tokens" bind:value={editOutputPrice} />
			</div>
			<div class="mt-5 flex justify-end gap-2">
				<Button variant="secondary" onclick={() => (editingPrice = null)}>취소</Button>
				<Button onclick={savePrice}>저장</Button>
			</div>
		</div>
	</Modal>

	<Modal bind:open={modelsDevOpen} ariaLabel="models.dev 추천 가격">
		<div class="max-h-[calc(100vh-2rem)] w-[min(48rem,calc(100vw-2rem))] overflow-y-auto rounded-xl border border-[var(--color-line)] bg-[var(--color-surface-raised)] p-5 shadow-[var(--shadow-restraint)]">
			<h3 class="text-base font-semibold text-[var(--color-ink-1)]">models.dev 추천 가격</h3>
			<p class="mt-1 text-sm text-[var(--color-ink-3)]">
				<a class="underline" href="https://models.dev" target="_blank" rel="noreferrer">models.dev</a>의 기본 input/output 단가만 적용합니다. 수동 확정 가격은 덮어쓰지 않습니다.
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
									<Alert tone="warning" class="mt-2">tier/cache/reasoning/audio 단가는 적용하지 않습니다: {selected.unsupported_price_fields.join(', ')}</Alert>
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
