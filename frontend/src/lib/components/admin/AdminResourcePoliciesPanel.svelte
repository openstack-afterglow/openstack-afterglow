<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-system';
	import { untrack } from 'svelte';
	import { derived } from 'svelte/store';
	import { api, ApiError } from '$lib/api/client';
	import { authDisplayContext } from '$lib/stores/authDisplayContext';
	import { siteConfig } from '$lib/config/site';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { Alert, Button, Card, SearchSelect, SelectInput, TextInput } from '$lib/components/ui';
	import type { SearchSelectOption } from '$lib/components/ui';

	interface ResourceOption {
		id: string;
		name: string;
		is_external?: boolean;
		is_shared?: boolean;
	}

	interface ResourceCatalog {
		key: string;
		options?: ResourceOption[];
		error?: { status: number; detail: string };
	}
	type PolicyState = 'configured' | 'missing' | 'stale' | 'unavailable';

	interface ResourcePolicy {
		key: string;
		resource_kind: string;
		title: string;
		group: string;
		help_text: string;
		execution_scope: 'admin' | 'tenant' | 'service';
		dependency: string | null;
		required_when: string | null;
		external_only: boolean;
		shared_only: boolean;
		state: PolicyState;
		resource_id: string | null;
		resource_name: string | null;
		resolved_name?: string | null;
	}

	interface RuntimeSetting {
		key: 'k3s.version' | 'notion.sync_enabled';
		title: string;
		help_text: string;
		value: string | boolean | null;
		state: 'configured' | 'missing' | 'unavailable';
	}

	interface ServiceError {
		service: 'drover' | 'waygate';
		status: number;
	}

	interface PolicyResponse {
		policies: ResourcePolicy[];
		errors: ServiceError[];
	}

	interface RuntimeResponse {
		settings: RuntimeSetting[];
		errors: ServiceError[];
	}

	interface Props {
		token?: string;
		projectId?: string;
	}

	interface DraftScope {
		policies: Record<string, string>;
		runtime: Record<string, string>;
	}

	const DRAFT_COOKIE = 'afterglow_resource_policy_draft';
	const DRAFT_MAX_AGE = 60 * 60 * 24 * 30;
	const CLEAR_OPTION_ID = '__clear__';

	function definePolicy(
		key: string,
		resource_kind: string,
		titleKey: Parameters<typeof t>[0],
		group: string,
		helpKey: Parameters<typeof t>[0],
		execution_scope: ResourcePolicy['execution_scope'],
		overrides: Partial<Pick<ResourcePolicy, 'dependency' | 'required_when' | 'external_only' | 'shared_only'>> = {}
	): ResourcePolicy {
		return {
			key,
			resource_kind,
			get title() { return t(titleKey); },
			group,
			get help_text() { return t(helpKey); },
			execution_scope,
			dependency: null,
			required_when: null,
			external_only: false,
			shared_only: false,
			state: 'unavailable',
			resource_id: null,
			resource_name: null,
			...overrides
		};
	}

	const policyDefinitions: ResourcePolicy[] = [
		definePolicy('openstack.service_project', 'project', 'policies.definition.openstackServiceProject.title', 'OpenStack', 'policies.definition.openstackServiceProject.help', 'admin'),
		definePolicy('nova.default_network', 'network', 'policies.definition.novaDefaultNetwork.title', 'Nova / Cinder', 'policies.definition.novaDefaultNetwork.help', 'tenant', { shared_only: true }),
		definePolicy('nova.default_external_network', 'network', 'policies.definition.novaDefaultExternalNetwork.title', 'Nova / Cinder', 'policies.definition.novaDefaultExternalNetwork.help', 'tenant', { required_when: 'default_network_enabled', external_only: true }),
		definePolicy('nova.default_compute_availability_zone', 'compute_availability_zone', 'policies.definition.novaDefaultComputeAvailabilityZone.title', 'Nova / Cinder', 'policies.definition.novaDefaultComputeAvailabilityZone.help', 'admin'),
		definePolicy('cinder.default_volume_availability_zone', 'volume_availability_zone', 'policies.definition.cinderDefaultVolumeAvailabilityZone.title', 'Nova / Cinder', 'policies.definition.cinderDefaultVolumeAvailabilityZone.help', 'admin'),
		definePolicy('manila.share_network', 'share_network', 'policies.definition.manilaShareNetwork.title', 'Manila', 'policies.definition.manilaShareNetwork.help', 'service', { dependency: 'openstack.service_project' }),
		definePolicy('manila.cephfs_share_type', 'share_type', 'policies.definition.manilaCephfsShareType.title', 'Manila', 'policies.definition.manilaCephfsShareType.help', 'tenant'),
		definePolicy('manila.nfs_share_type', 'share_type', 'policies.definition.manilaNfsShareType.title', 'Manila', 'policies.definition.manilaNfsShareType.help', 'tenant'),
		definePolicy('k3s.server_image', 'image', 'policies.definition.k3sServerImage.title', 'K3s', 'policies.definition.k3sServerImage.help', 'tenant'),
		definePolicy('k3s.fcos_image', 'image', 'policies.definition.k3sFcosImage.title', 'K3s', 'policies.definition.k3sFcosImage.help', 'tenant'),
		definePolicy('k3s.server_flavor', 'flavor', 'policies.definition.k3sServerFlavor.title', 'K3s', 'policies.definition.k3sServerFlavor.help', 'tenant'),
		definePolicy('k3s.default_agent_flavor', 'flavor', 'policies.definition.k3sDefaultAgentFlavor.title', 'K3s', 'policies.definition.k3sDefaultAgentFlavor.help', 'tenant'),
		definePolicy('k3s.volume_availability_zone', 'volume_availability_zone', 'policies.definition.k3sVolumeAvailabilityZone.title', 'K3s', 'policies.definition.k3sVolumeAvailabilityZone.help', 'admin'),
		definePolicy('k3s.default_network', 'network', 'policies.definition.k3sDefaultNetwork.title', 'K3s', 'policies.definition.k3sDefaultNetwork.help', 'tenant', { shared_only: true }),
		definePolicy('k3s.occm_floating_network', 'network', 'policies.definition.k3sOccmFloatingNetwork.title', 'K3s', 'policies.definition.k3sOccmFloatingNetwork.help', 'tenant', { external_only: true }),
		definePolicy('k3s.occm_public_network', 'network', 'policies.definition.k3sOccmPublicNetwork.title', 'K3s', 'policies.definition.k3sOccmPublicNetwork.help', 'tenant', { shared_only: true }),
		definePolicy('k3s.lb_subnet', 'subnet', 'policies.definition.k3sLbSubnet.title', 'K3s', 'policies.definition.k3sLbSubnet.help', 'tenant'),
		definePolicy('k3s.api_lb_vip_network', 'network', 'policies.definition.k3sApiLbVipNetwork.title', 'K3s', 'policies.definition.k3sApiLbVipNetwork.help', 'tenant', { shared_only: true }),
		definePolicy('k3s.api_lb_floating_network', 'network', 'policies.definition.k3sApiLbFloatingNetwork.title', 'K3s', 'policies.definition.k3sApiLbFloatingNetwork.help', 'tenant', { external_only: true }),
		definePolicy('k3s.octavia_ingress_floating_network', 'network', 'policies.definition.k3sOctaviaIngressFloatingNetwork.title', 'K3s', 'policies.definition.k3sOctaviaIngressFloatingNetwork.help', 'tenant', { external_only: true }),
		definePolicy('builder.flavor', 'flavor', 'policies.definition.builderFlavor.title', 'Builder', 'policies.definition.builderFlavor.help', 'service', { dependency: 'openstack.service_project' }),
		definePolicy('builder.network', 'network', 'policies.definition.builderNetwork.title', 'Builder', 'policies.definition.builderNetwork.help', 'service', { dependency: 'openstack.service_project' }),
		definePolicy('builder.floating_network', 'network', 'policies.definition.builderFloatingNetwork.title', 'Builder', 'policies.definition.builderFloatingNetwork.help', 'service', { dependency: 'openstack.service_project', external_only: true }),
		definePolicy('waygate.provider_network', 'network', 'policies.definition.waygateProviderNetwork.title', 'Waygate', 'policies.definition.waygateProviderNetwork.help', 'tenant', { shared_only: true }),
		definePolicy('waygate.image', 'image', 'policies.definition.waygateImage.title', 'Waygate', 'policies.definition.waygateImage.help', 'tenant'),
		definePolicy('waygate.flavor', 'flavor', 'policies.definition.waygateFlavor.title', 'Waygate', 'policies.definition.waygateFlavor.help', 'tenant'),
		definePolicy('waygate.floating_network', 'network', 'policies.definition.waygateFloatingNetwork.title', 'Waygate', 'policies.definition.waygateFloatingNetwork.help', 'tenant', { external_only: true })
	];

	const runtimeDefinitions: RuntimeSetting[] = [
		{
			key: 'k3s.version',
			get title() { return t('policies.runtime.versionTitle'); },
			get help_text() { return t('policies.runtime.versionHelp'); },
			value: null,
			state: 'unavailable'
		},
		{
			key: 'notion.sync_enabled',
			get title() { return t('policies.runtime.notionTitle'); },
			get help_text() { return t('policies.runtime.notionHelp'); },
			value: null,
			state: 'unavailable'
		}
	];

	let { token, projectId }: Props = $props();
	let previousApiBase: string | undefined;
	let backendRevision = 0;
	const catalogBackendRevision = derived(siteConfig, ({ runtime }) => {
		// Observe every backend transition synchronously, including same-tick A → B → A.
		if (runtime.api_base !== previousApiBase) {
			previousApiBase = runtime.api_base;
			backendRevision += 1;
		}
		return backendRevision;
	});
	const catalogContext = $derived(JSON.stringify([projectId, $authDisplayContext.key, $catalogBackendRevision]));
	let policies = $state<ResourcePolicy[]>(policyDefinitions.map((policy) => ({ ...policy })));
	let runtimeSettings = $state<RuntimeSetting[]>(runtimeDefinitions.map((setting) => ({ ...setting })));
	let options = $state<Record<string, ResourceOption[]>>({});
	let selections = $state<Record<string, string>>({});
	let runtimeValues = $state<Record<string, string>>({});
	let catalogLoading = $state<Record<string, boolean>>({});
	let catalogErrors = $state<Record<string, boolean>>({});
	let catalogErrorStatuses = $state<Record<string, number | undefined>>({});
	let policyServiceErrors = $state<ServiceError[]>([]);
	let loadedPolicyKeys = $state<Record<string, boolean>>({});
	let loadedRuntimeKeys = $state<Record<string, boolean>>({});
	let valuesOwner = $state('');
	let runtimeServiceErrors = $state<ServiceError[]>([]);
	let loadingValues = $state(true);
	let saving = $state<string | null>(null);
	let error = $state('');
	let notice = $state('');
	let draftScope: DraftScope = { policies: {}, runtime: {} };
	let generation = 0;

	function isObjectRecord(value: unknown): value is Record<string, unknown> {
		return typeof value === 'object' && value !== null && !Array.isArray(value);
	}

	function isSafeCookieKey(key: string): boolean {
		return key !== '__proto__' && key !== 'constructor' && key !== 'prototype';
	}

	function stringRecord(value: unknown): Record<string, string> {
		if (!isObjectRecord(value)) return {};
		const entries = Object.entries(value).filter(
			(entry): entry is [string, string] => isSafeCookieKey(entry[0]) && typeof entry[1] === 'string'
		);
		return Object.fromEntries(entries);
	}

	function cookieValue(): Record<string, DraftScope> {
		if (typeof document === 'undefined') return {};
		const raw = document.cookie
			.split('; ')
			.find((part) => part.startsWith(`${DRAFT_COOKIE}=`))
			?.slice(DRAFT_COOKIE.length + 1);
		if (!raw) return {};
		try {
			const parsed: unknown = JSON.parse(decodeURIComponent(raw));
			if (!isObjectRecord(parsed)) return {};
			const scopes = Object.create(null) as Record<string, DraftScope>;
			for (const [scope, value] of Object.entries(parsed)) {
				if (
					!isSafeCookieKey(scope) ||
					!isObjectRecord(value) ||
					!isObjectRecord(value.policies) ||
					!isObjectRecord(value.runtime)
				) {
					continue;
				}
				scopes[scope] = {
					policies: stringRecord(value.policies),
					runtime: stringRecord(value.runtime)
				};
			}
			return scopes;
		} catch {
			return {};
		}
	}

	function currentScope(): string {
		return projectId || 'default';
	}

	function persistDrafts() {
		if (typeof document === 'undefined') return;
		const scopes = cookieValue();
		if (Object.keys(draftScope.policies).length || Object.keys(draftScope.runtime).length) {
			scopes[currentScope()] = draftScope;
			const secure = location.protocol === 'https:' ? '; Secure' : '';
			document.cookie = `${DRAFT_COOKIE}=${encodeURIComponent(JSON.stringify(scopes))}; path=/; SameSite=Lax; max-age=${DRAFT_MAX_AGE}${secure}`;
		} else {
			delete scopes[currentScope()];
			const value = Object.keys(scopes).length ? encodeURIComponent(JSON.stringify(scopes)) : '';
			document.cookie = `${DRAFT_COOKIE}=${value}; path=/; SameSite=Lax; max-age=${value ? DRAFT_MAX_AGE : 0}`;
		}
	}

	function loadDrafts() {
		const scopes = cookieValue();
		draftScope = scopes[currentScope()] ?? { policies: {}, runtime: {} };
	}

	function setPolicySelection(key: string, value: string) {
		if (!policyAvailable(key)) return;
		selections = { ...selections, [key]: value };
		draftScope = {
			...draftScope,
			policies: { ...draftScope.policies, [key]: value }
		};
		persistDrafts();
	}

	function setRuntimeValue(key: string, value: string) {
		if (!runtimeAvailable(key)) return;
		runtimeValues = { ...runtimeValues, [key]: value };
		draftScope = { ...draftScope, runtime: { ...draftScope.runtime, [key]: value } };
		persistDrafts();
	}

	function clearDraft(kind: 'policies' | 'runtime', key: string) {
		const values = { ...draftScope[kind] };
		delete values[key];
		draftScope = { ...draftScope, [kind]: values };
		persistDrafts();
	}

	function policyService(key: string): ServiceError['service'] | null {
		return key.startsWith('k3s.') ? 'drover' : key.startsWith('waygate.') ? 'waygate' : null;
	}

	function serviceError(key: string, errors: ServiceError[]): ServiceError | undefined {
		return errors.find((error) => error.service === policyService(key));
	}

	function serviceUnavailable(error: { service: ServiceError['service']; status?: number }): string {
		const name = error.service === 'drover' ? 'Drover' : 'Waygate';
		return `${name} · ${t('policies.state.unavailable')}${error.status === undefined ? '' : ` (HTTP ${error.status})`}`;
	}

	function catalogFailure(policy: ResourcePolicy): string {
		const service = policyService(policy.key);
		return service
			? serviceUnavailable({ service, status: catalogErrorStatuses[policy.key] })
			: t('policies.catalogFailed');
	}

	function policyAvailable(key: string): boolean {
		return valuesOwner === catalogContext && Boolean(loadedPolicyKeys[key]);
	}

	function runtimeAvailable(key: string): boolean {
		return valuesOwner === catalogContext && Boolean(loadedRuntimeKeys[key]);
	}

	function runtimeCanSave(setting: RuntimeSetting): boolean {
		return runtimeAvailable(setting.key) && (setting.key !== 'notion.sync_enabled' ||
			runtimeValues[setting.key] === 'true' || runtimeValues[setting.key] === 'false');
	}

	function mergePolicyValues({ policies: loaded, errors }: PolicyResponse) {
		const byKey = new Map(loaded.map((policy) => [policy.key, policy]));
		loadedPolicyKeys = Object.fromEntries(loaded
			.filter((policy) => !serviceError(policy.key, errors))
			.map((policy) => [policy.key, true]));
		policies = policyDefinitions.map<ResourcePolicy>((definition) => loadedPolicyKeys[definition.key]
			? { ...definition, ...byKey.get(definition.key) }
			: { ...definition, state: 'unavailable' });
		policyServiceErrors = errors;
		selections = Object.fromEntries(
			policies.filter((policy) => loadedPolicyKeys[policy.key])
				.map((policy) => [policy.key, draftScope.policies[policy.key] ?? policy.resource_id ?? ''])
		);
	}

	function mergeRuntimeValues({ settings: loaded, errors }: RuntimeResponse) {
		const byKey = new Map(loaded.map((setting) => [setting.key, setting]));
		loadedRuntimeKeys = Object.fromEntries(loaded
			.filter((setting) => setting.state !== 'unavailable' && !serviceError(setting.key, errors))
			.map((setting) => [setting.key, true]));
		runtimeSettings = runtimeDefinitions.map<RuntimeSetting>((definition) => loadedRuntimeKeys[definition.key]
			? { ...definition, ...byKey.get(definition.key) }
			: { ...definition, state: 'unavailable' });
		runtimeServiceErrors = errors;
		runtimeValues = Object.fromEntries(
			runtimeSettings.filter((setting) => loadedRuntimeKeys[setting.key]).map((setting) => [
				setting.key,
				draftScope.runtime[setting.key] ??
					String(setting.value ?? '')
			])
		);
	}

	function requestCurrent(epoch: number, owner: string, project: string | undefined): boolean {
		return epoch === generation && owner === catalogContext && project === projectId;
	}

	async function loadPolicies() {
		const requestGeneration = ++generation;
		const requestToken = token;
		const requestProject = projectId;
		const requestOwner = catalogContext;
		loadingValues = true;
		valuesOwner = '';
		loadedPolicyKeys = {};
		loadedRuntimeKeys = {};
		policyServiceErrors = [];
		runtimeServiceErrors = [];
		options = {};
		catalogLoading = {};
		catalogErrors = {};
		catalogErrorStatuses = {};
		selections = {};
		runtimeValues = {};
		policies = policyDefinitions.map((policy) => ({ ...policy }));
		runtimeSettings = runtimeDefinitions.map((setting) => ({ ...setting }));
		saving = null;
		notice = '';
		loadDrafts();
		error = '';
		const [policyResult, runtimeResult] = await Promise.allSettled([
			api.get<PolicyResponse>('/api/v1/admin/resource-policies', requestToken, requestProject, { cache: 'no-store' }),
			api.get<RuntimeResponse>('/api/v1/admin/runtime-settings', requestToken, requestProject, { cache: 'no-store' })
		]);
		if (!requestCurrent(requestGeneration, requestOwner, requestProject)) return;
		valuesOwner = requestOwner;
		if (policyResult.status === 'fulfilled') {
			mergePolicyValues(policyResult.value);
			void loadCatalogs(policies, requestGeneration);
		} else {
			error = policyResult.reason instanceof ApiError
				? t('policies.loadFailedDetail', { message: policyResult.reason.message })
				: t('policies.loadFailed');
		}
		if (runtimeResult.status === 'fulfilled') {
			mergeRuntimeValues(runtimeResult.value);
		} else if (!error) {
			error = runtimeResult.reason instanceof ApiError
				? t('policies.runtimeLoadFailedDetail', { message: runtimeResult.reason.message })
				: t('policies.runtimeLoadFailed');
		}
		loadingValues = false;
	}

	async function loadCatalogs(loadedPolicies: ResourcePolicy[], requestGeneration: number) {
		const available = loadedPolicies.filter((policy) => policyAvailable(policy.key));
		const remote = available.filter((policy) => policy.key.startsWith('k3s.') || policy.key.startsWith('waygate.'));
		const local = available.filter((policy) => !remote.includes(policy));
		// Remote reads retain independent timeout/error boundaries and never
		// inherit the local batch's query string.
		await Promise.allSettled([
			loadCatalogGroup(local, requestGeneration),
			...remote.map((policy) => loadCatalogGroup([policy], requestGeneration, true))
		]);
	}

	async function loadCatalogGroup(loadedPolicies: ResourcePolicy[], requestGeneration: number, remote = false) {
		const pending = loadedPolicies.filter((policy) => policyAvailable(policy.key) && !options[policy.key] && !catalogLoading[policy.key]);
		if (!pending.length) return;
		const requestToken = token;
		const requestProject = projectId;
		const requestOwner = catalogContext;
		catalogLoading = { ...catalogLoading, ...Object.fromEntries(pending.map((policy) => [policy.key, true])) };
		catalogErrors = { ...catalogErrors, ...Object.fromEntries(pending.map((policy) => [policy.key, false])) };
		catalogErrorStatuses = { ...catalogErrorStatuses, ...Object.fromEntries(pending.map((policy) => [policy.key, undefined])) };
		try {
			const query = new URLSearchParams(pending.map((policy) => ['keys', policy.key]));
			const result = remote
				? { catalogs: [await api.get<ResourceCatalog>(
					`/api/v1/admin/resource-policies/catalog/${encodeURIComponent(pending[0].key)}`,
					requestToken, requestProject, { cache: 'no-store' }
				)] }
				: await api.get<{ catalogs: ResourceCatalog[] }>(
					`/api/v1/admin/resource-policies/catalog?${query}`,
					requestToken, requestProject, { cache: 'no-store' }
				);
			if (!requestCurrent(requestGeneration, requestOwner, requestProject)) return;
			const byKey = new Map(result.catalogs.map((catalog) => [catalog.key, catalog]));
			for (const policy of pending) {
				const catalog = byKey.get(policy.key);
				if (!catalog || catalog.error || !catalog.options) {
					catalogErrors = { ...catalogErrors, [policy.key]: true };
					catalogErrorStatuses = { ...catalogErrorStatuses, [policy.key]: catalog?.error?.status };
					continue;
				}
				options = { ...options, [policy.key]: catalog.options };
				const current = selections[policy.key] ?? '';
				if (!current && catalog.options.length === 1) {
					setPolicySelection(policy.key, catalog.options[0].id);
					notice = t('policies.onlyOption', { title: policyCopy(policy).title });
				}
			}
		} catch (cause) {
			if (!requestCurrent(requestGeneration, requestOwner, requestProject)) return;
			catalogErrors = { ...catalogErrors, ...Object.fromEntries(pending.map((policy) => [policy.key, true])) };
			catalogErrorStatuses = { ...catalogErrorStatuses, ...Object.fromEntries(pending.map((policy) => [
				policy.key, cause instanceof ApiError ? cause.status : undefined
			])) };
		} finally {
			if (requestCurrent(requestGeneration, requestOwner, requestProject)) {
				const next = { ...catalogLoading };
				for (const policy of pending) delete next[policy.key];
				catalogLoading = next;
			}
		}
	}

	function policyOptions(policy: ResourcePolicy): SearchSelectOption[] {
		const catalog = options[policy.key] ?? [];
		const selectedId = selections[policy.key] ?? '';
		const entries: SearchSelectOption[] = [{ value: CLEAR_OPTION_ID, label: t('policies.clear') }];
		if (selectedId && !catalog.some((option) => option.id === selectedId)) {
			entries.push({ value: selectedId, label: selectedLabel(policy), description: selectedId });
		}
		for (const option of catalog) {
			entries.push({ value: option.id, label: option.name, description: option.id });
		}
		return entries;
	}

	function selectedLabel(policy: ResourcePolicy): string {
		const selectedId = selections[policy.key];
		return options[policy.key]?.find((option) => option.id === selectedId)?.name ??
			(policy.resolved_name ?? policy.resource_name ?? selectedId ?? '');
	}

	async function save(policy: ResourcePolicy) {
		if (!policyAvailable(policy.key) || loadingValues) return;
		const requestGeneration = generation;
		const requestOwner = catalogContext;
		const requestProject = projectId;
		saving = policy.key;
		error = '';
		notice = '';
		try {
			const updated = await api.put<ResourcePolicy>(
				`/api/v1/admin/resource-policies/${encodeURIComponent(policy.key)}`,
				{ resource_id: selections[policy.key] || null },
				token,
				projectId
			);
			if (!requestCurrent(requestGeneration, requestOwner, requestProject)) return;
			policies = policies.map((item) => (item.key === updated.key ? { ...item, ...updated } : item));
			clearDraft('policies', policy.key);
			notice = t('policies.saved', { title: policyCopy(policy).title });
		} catch (cause) {
			if (!requestCurrent(requestGeneration, requestOwner, requestProject)) return;
			error = cause instanceof ApiError ? t('policies.saveFailedDetail', { message: cause.message }) : t('policies.saveFailed');
		} finally {
			if (requestCurrent(requestGeneration, requestOwner, requestProject)) saving = null;
		}
	}

	async function saveRuntimeSetting(setting: RuntimeSetting) {
		if (!runtimeCanSave(setting) || loadingValues) return;
		const requestGeneration = generation;
		const requestOwner = catalogContext;
		const requestProject = projectId;
		saving = setting.key;
		error = '';
		notice = '';
		try {
			const updated = await api.put<RuntimeSetting>(
				`/api/v1/admin/runtime-settings/${encodeURIComponent(setting.key)}`,
				{ value: setting.key === 'notion.sync_enabled' ? runtimeValues[setting.key] === 'true' : runtimeValues[setting.key] },
				token,
				projectId
			);
			if (!requestCurrent(requestGeneration, requestOwner, requestProject)) return;
			runtimeSettings = runtimeSettings.map((item) => (item.key === updated.key ? updated : item));
			clearDraft('runtime', setting.key);
			notice = t('policies.runtimeSaved', { title: runtimeCopy(setting).title });
		} catch (cause) {
			if (!requestCurrent(requestGeneration, requestOwner, requestProject)) return;
			error = cause instanceof ApiError ? t('policies.runtimeSaveFailedDetail', { message: cause.message }) : t('policies.runtimeSaveFailed');
		} finally {
			if (requestCurrent(requestGeneration, requestOwner, requestProject)) saving = null;
		}
	}

	function policyCopy(policy: ResourcePolicy) {
		return policyDefinitions.find(definition => definition.key === policy.key) ?? policy;
	}
	function runtimeCopy(setting: RuntimeSetting) {
		return runtimeDefinitions.find(definition => definition.key === setting.key) ?? setting;
	}
	function groupedPolicies() {
		return Object.entries(
			policies.reduce<Record<string, ResourcePolicy[]>>((groups, policy) => {
				(groups[policy.group] ??= []).push(policy);
				return groups;
			}, {})
		);
	}

	$effect(() => {
		catalogContext;
		untrack(() => void loadPolicies());
		return () => { generation += 1; };
	});
</script>

<Card padding="lg" surface="subtle">
	<div class="heading">
		<div>
			<h2>{t('policies.title')}</h2>
			<p>{t('policies.description')}</p>
		</div>
		<Button variant="secondary" size="sm" onclick={() => void loadPolicies()} disabled={loadingValues}>
			{t('branding.refresh')}
		</Button>
	</div>

	{#if error}<Alert tone="danger">{error}</Alert>{/if}
	{#if notice}<Alert tone="success">{notice}</Alert>{/if}
	{#if loadingValues}<div class="loading-note"><LoadingState variant="inline" label={t('policies.loading')} /></div>{/if}

	<section class="runtime-settings" aria-labelledby="runtime-settings-title">
		<div class="section-heading">
			<h3 id="runtime-settings-title">{t('policies.runtimeTitle')}</h3>
			<p>{t('policies.runtimeDescription')}</p>
		</div>
		{#each runtimeSettings as setting (setting.key)}
			{@const failure = serviceError(setting.key, runtimeServiceErrors)}
			<div class="runtime-row">
				<div class="policy-copy">
					<strong>{runtimeCopy(setting).title}</strong>
					<span>{runtimeCopy(setting).help_text}</span>
					<code class="selection-id">{setting.key}</code>
					{#if setting.state === 'missing' || setting.state === 'unavailable'}<span>{t(`policies.state.${setting.state}`)}</span>{/if}
					{#if failure}<Alert tone="danger">{serviceUnavailable(failure)}</Alert>{/if}
				</div>
				{#if setting.key === 'notion.sync_enabled'}
					<SelectInput
						value={runtimeValues[setting.key] ?? ''}
						disabled={!runtimeAvailable(setting.key)}
						onchange={(event) => setRuntimeValue(setting.key, (event.currentTarget as HTMLSelectElement).value)}
						ariaLabel={t('policies.selectLabel', { title: runtimeCopy(setting).title })}
					>
						<option value="">{t(runtimeAvailable(setting.key) ? 'policies.state.missing' : 'policies.state.unavailable')}</option>
						<option value="true">{t('policies.enabled')}</option>
						<option value="false">{t('policies.disabled')}</option>
					</SelectInput>
				{:else}
					<TextInput
						value={runtimeValues[setting.key] ?? ''}
						disabled={!runtimeAvailable(setting.key)}
						oninput={(event) => setRuntimeValue(setting.key, (event.currentTarget as HTMLInputElement).value)}
						ariaLabel={t('policies.valueLabel', { title: runtimeCopy(setting).title })}
					/>
				{/if}
				<Button variant="primary" size="sm" onclick={() => saveRuntimeSetting(setting)} disabled={!runtimeCanSave(setting) || loadingValues || saving === setting.key} ariaBusy={saving === setting.key}>
					{#if saving === setting.key}<LoadingState variant="control" label="" aria-hidden="true" />{/if}{saving === setting.key ? t('policies.saving') : t('policies.save')}
				</Button>
			</div>
		{/each}
	</section>

	{#each groupedPolicies() as [group, groupPolicies] (group)}
		<section class="policy-group" aria-labelledby={`policy-group-${group}`}>
			<h3 id={`policy-group-${group}`}>{group}</h3>
			<div class="policy-list">
				{#each groupPolicies as policy (policy.key)}
					{@const failure = serviceError(policy.key, policyServiceErrors)}
					<section class="policy-row">
						<div class="policy-copy">
							<strong>{policyCopy(policy).title}</strong>
							<span>{policyCopy(policy).help_text}</span>
							<span>{t(`policies.scope.${policy.execution_scope}`)} · {t(`policies.state.${policy.state}`)}</span>
							<code class="selection-id">{policy.key}</code>
						</div>
						<div class="catalog-selection">
							<SearchSelect
								id={`policy-${policy.key.replace(/\./g, '-')}`}
								value={selections[policy.key] ?? ''}
								options={policyOptions(policy)}
								placeholder={t('policies.placeholder')}
								searchPlaceholder={t('policies.searchPlaceholder')}
								emptyText={t('policies.empty')}
								loading={Boolean(catalogLoading[policy.key])}
								disabled={!policyAvailable(policy.key)}
								ariaLabel={t('policies.searchLabel', { title: policyCopy(policy).title })}
								onopen={() => void loadCatalogs([policy], generation)}
								onchange={(value) => setPolicySelection(policy.key, value === CLEAR_OPTION_ID ? '' : value)}
							/>
							{#if failure}<Alert tone="danger">{serviceUnavailable(failure)}</Alert>{/if}
							{#if catalogErrors[policy.key]}<Alert tone="danger">{catalogFailure(policy)}</Alert>{/if}
							{#if selections[policy.key]}<span class="selection-id">{selections[policy.key]}</span>{/if}
						</div>
						<div class="actions">
							<Button variant="primary" size="sm" onclick={() => save(policy)} disabled={!policyAvailable(policy.key) || loadingValues || saving === policy.key} ariaBusy={saving === policy.key}>
								{#if saving === policy.key}<LoadingState variant="control" label="" aria-hidden="true" />{/if}{saving === policy.key ? t('policies.saving') : t('policies.save')}
							</Button>
						</div>
					</section>
				{/each}
			</div>
		</section>
	{/each}
</Card>

<style>
	.heading, .policy-copy, .policy-list, .policy-group, .section-heading, .catalog-selection { display: grid; gap: 0.5rem; }
	.heading { margin-bottom: 1rem; }
	h2, h3 { margin: 0; color: var(--color-ink-0); }
	h2 { font-size: 1rem; }
	h3 { font-size: 0.88rem; }
	p, .policy-copy span, .selection-id { margin: 0; color: var(--color-ink-2); font-size: 0.8125rem; line-height: 1.5; }
	.loading-note { padding: 0.5rem 0; }
	.runtime-settings, .policy-group { border-top: 1px solid var(--color-line-2); padding: 0.75rem 0; }
	.runtime-row, .policy-row { display: grid; grid-template-columns: minmax(11rem, 1fr) minmax(13rem, 1.2fr) auto; align-items: center; gap: 0.75rem; border-top: 1px solid var(--color-line-2); padding: 0.75rem 0; }
	.runtime-settings .runtime-row:first-of-type { border-top: 0; }
	.policy-copy strong { color: var(--color-ink-0); font-size: 0.86rem; }
	.selection-id { font-family: var(--font-mono); font-size: 0.75rem; overflow-wrap: anywhere; }
	.actions { display: flex; gap: 0.4rem; }
	@media (max-width: 1023px) { .runtime-row, .policy-row { grid-template-columns: 1fr; } .actions { justify-content: flex-end; } }
</style>
