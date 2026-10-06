<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-system';
	import { onMount } from 'svelte';
	import { api, ApiError } from '$lib/api/client';
	import { ActivityIndicator, Alert, Button, Card, SearchSelect, SelectInput } from '$lib/components/ui';
	import type { SearchSelectOption } from '$lib/components/ui';

	interface ResourceOption {
		id: string;
		name: string;
		is_external?: boolean;
		is_shared?: boolean;
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
		state: 'configured' | 'missing';
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
			state: 'missing',
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
			value: '',
			state: 'missing'
		},
		{
			key: 'notion.sync_enabled',
			get title() { return t('policies.runtime.notionTitle'); },
			get help_text() { return t('policies.runtime.notionHelp'); },
			value: false,
			state: 'missing'
		}
	];

	let { token, projectId }: Props = $props();
	let policies = $state<ResourcePolicy[]>(policyDefinitions.map((policy) => ({ ...policy })));
	let runtimeSettings = $state<RuntimeSetting[]>(runtimeDefinitions.map((setting) => ({ ...setting })));
	let options = $state<Record<string, ResourceOption[]>>({});
	let selections = $state<Record<string, string>>({});
	let runtimeValues = $state<Record<string, string>>({});
	let catalogLoading = $state<Record<string, boolean>>({});
	let loadingValues = $state(true);
	let saving = $state<string | null>(null);
	let error = $state('');
	let notice = $state('');
	let draftScope: DraftScope = { policies: {}, runtime: {} };

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
		selections = { ...selections, [key]: value };
		draftScope = {
			...draftScope,
			policies: { ...draftScope.policies, [key]: value }
		};
		persistDrafts();
	}

	function setRuntimeValue(key: string, value: string) {
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

	function mergePolicyValues(loaded: ResourcePolicy[]) {
		const byKey = new Map(loaded.map((policy) => [policy.key, policy]));
		policies = policyDefinitions.map((definition) => ({ ...definition, ...(byKey.get(definition.key) ?? {}) }));
		selections = Object.fromEntries(
			policies.map((policy) => [policy.key, draftScope.policies[policy.key] ?? policy.resource_id ?? ''])
		);
	}

	function mergeRuntimeValues(loaded: RuntimeSetting[]) {
		const byKey = new Map(loaded.map((setting) => [setting.key, setting]));
		runtimeSettings = runtimeDefinitions.map((definition) => ({ ...definition, ...(byKey.get(definition.key) ?? {}) }));
		runtimeValues = Object.fromEntries(
			runtimeSettings.map((setting) => [
				setting.key,
				draftScope.runtime[setting.key] ??
					String(setting.value ?? (setting.key === 'notion.sync_enabled' ? false : ''))
			])
		);
	}

	async function loadPolicies() {
		loadDrafts();
		error = '';
		const [policyResult, runtimeResult] = await Promise.allSettled([
			api.get<ResourcePolicy[]>('/api/v1/admin/resource-policies', token, projectId),
			api.get<RuntimeSetting[]>('/api/v1/admin/runtime-settings', token, projectId)
		]);
		if (policyResult.status === 'fulfilled') {
			mergePolicyValues(policyResult.value);
			void loadAllCatalogs(policies);
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
	async function loadOptions(policy: ResourcePolicy) {
		if (options[policy.key] || catalogLoading[policy.key]) return;
		catalogLoading = { ...catalogLoading, [policy.key]: true };
		try {
			const catalog = await api.get<{ options: ResourceOption[] }>(
				`/api/v1/admin/resource-policies/catalog/${encodeURIComponent(policy.key)}`,
				token,
				projectId
			);
			options = { ...options, [policy.key]: catalog.options };
			const current = selections[policy.key] ?? '';
			if (!current && catalog.options.length === 1) {
				setPolicySelection(policy.key, catalog.options[0].id);
				notice = t('policies.onlyOption', { title: policy.title });
			}
		} catch (cause) {
			error = cause instanceof ApiError ? t('policies.catalogFailedDetail', { message: cause.message }) : t('policies.catalogFailed');
		} finally {
			const next = { ...catalogLoading };
			delete next[policy.key];
			catalogLoading = next;
		}
	}

	async function loadAllCatalogs(loadedPolicies: ResourcePolicy[]) {
		await Promise.allSettled(loadedPolicies.map((policy) => loadOptions(policy)));
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
			policies = policies.map((item) => (item.key === updated.key ? { ...item, ...updated } : item));
			clearDraft('policies', policy.key);
			notice = t('policies.saved', { title: policy.title });
		} catch (cause) {
			error = cause instanceof ApiError ? t('policies.saveFailedDetail', { message: cause.message }) : t('policies.saveFailed');
		} finally {
			saving = null;
		}
	}

	async function saveRuntimeSetting(setting: RuntimeSetting) {
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
			runtimeSettings = runtimeSettings.map((item) => (item.key === updated.key ? updated : item));
			clearDraft('runtime', setting.key);
			notice = t('policies.runtimeSaved', { title: setting.title });
		} catch (cause) {
			error = cause instanceof ApiError ? t('policies.runtimeSaveFailedDetail', { message: cause.message }) : t('policies.runtimeSaveFailed');
		} finally {
			saving = null;
		}
	}

	function groupedPolicies() {
		return Object.entries(
			policies.reduce<Record<string, ResourcePolicy[]>>((groups, policy) => {
				(groups[policy.group] ??= []).push(policy);
				return groups;
			}, {})
		);
	}

	onMount(loadPolicies);
</script>

<Card padding="lg" surface="subtle">
	<div class="heading">
		<div>
			<p class="eyebrow">{t('policies.eyebrow')}</p>
			<h2>{t('policies.title')}</h2>
			<p>{t('policies.description')}</p>
		</div>
	</div>

	{#if error}<Alert tone="danger">{error}</Alert>{/if}
	{#if notice}<Alert tone="success">{notice}</Alert>{/if}
	{#if loadingValues}<div class="loading-note"><ActivityIndicator label={t('policies.loading')} /></div>{/if}

	<section class="runtime-settings" aria-labelledby="runtime-settings-title">
		<div class="section-heading">
			<h3 id="runtime-settings-title">{t('policies.runtimeTitle')}</h3>
			<p>{t('policies.runtimeDescription')}</p>
		</div>
		{#each runtimeSettings as setting (setting.key)}
			<div class="runtime-row">
				<div class="policy-copy">
					<strong>{setting.title}</strong>
					<span>{setting.help_text}</span>
				</div>
				{#if setting.key === 'notion.sync_enabled'}
					<SelectInput
						value={runtimeValues[setting.key] ?? 'false'}
						onchange={(event) => setRuntimeValue(setting.key, (event.currentTarget as HTMLSelectElement).value)}
						ariaLabel={t('policies.selectLabel', { title: setting.title })}
					>
						<option value="true">{t('policies.enabled')}</option>
						<option value="false">{t('policies.disabled')}</option>
					</SelectInput>
				{:else}
					<input
						class="runtime-input"
						value={runtimeValues[setting.key] ?? ''}
						oninput={(event) => setRuntimeValue(setting.key, (event.currentTarget as HTMLInputElement).value)}
						aria-label={t('policies.valueLabel', { title: setting.title })}
					/>
				{/if}
				<Button variant="primary" size="sm" onclick={() => saveRuntimeSetting(setting)} disabled={saving === setting.key} ariaBusy={saving === setting.key}>
					{#if saving === setting.key}<ActivityIndicator size="xs" tone="ink" />{/if}{saving === setting.key ? t('policies.saving') : t('policies.save')}
				</Button>
			</div>
		{/each}
	</section>

	{#each groupedPolicies() as [group, groupPolicies] (group)}
		<section class="policy-group" aria-labelledby={`policy-group-${group}`}>
			<h3 id={`policy-group-${group}`}>{group}</h3>
			<div class="policy-list">
				{#each groupPolicies as policy (policy.key)}
					<section class="policy-row">
						<div class="policy-copy">
							<strong>{policy.title}</strong>
							<span>{policy.help_text} · {policy.execution_scope} · {policy.state}</span>
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
								ariaLabel={t('policies.searchLabel', { title: policy.title })}
								onopen={() => void loadOptions(policy)}
								onchange={(value) => setPolicySelection(policy.key, value === CLEAR_OPTION_ID ? '' : value)}
							/>
							{#if selections[policy.key]}<span class="selection-id">{selections[policy.key]}</span>{/if}
						</div>
						<div class="actions">
							<Button variant="primary" size="sm" onclick={() => save(policy)} disabled={saving === policy.key} ariaBusy={saving === policy.key}>
								{#if saving === policy.key}<ActivityIndicator size="xs" tone="ink" />{/if}{saving === policy.key ? t('policies.saving') : t('policies.save')}
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
	.eyebrow { margin: 0; font-size: 0.68rem; font-weight: 700; letter-spacing: 0.16em; text-transform: uppercase; color: var(--admin-tone, var(--color-warm)); }
	h2, h3 { margin: 0; color: var(--color-ink-0); }
	h2 { font-size: 1rem; }
	h3 { font-size: 0.88rem; }
	p, .policy-copy span, .selection-id { margin: 0; color: var(--color-ink-2); font-size: 0.82rem; line-height: 1.5; }
	.loading-note { padding: 0.5rem 0; }
	.runtime-settings, .policy-group { border-top: 1px solid var(--color-line-2); padding: 0.75rem 0; }
	.runtime-row, .policy-row { display: grid; grid-template-columns: minmax(11rem, 1fr) minmax(13rem, 1.2fr) auto; align-items: center; gap: 0.75rem; border-top: 1px solid var(--color-line-2); padding: 0.75rem 0; }
	.runtime-settings .runtime-row:first-of-type { border-top: 0; }
	.policy-copy strong { color: var(--color-ink-0); font-size: 0.86rem; }
	.runtime-input { min-width: 0; width: 100%; border: 1px solid var(--color-line); border-radius: 0.375rem; background: var(--color-surface-sunken); color: var(--color-ink-0); padding: 0.5rem 0.75rem; }
	.runtime-input:focus { outline: none; border-color: var(--color-accent); box-shadow: var(--focus-ring); }
	.selection-id { font-family: var(--font-mono); font-size: 0.7rem; }
	.actions { display: flex; gap: 0.4rem; }
	@media (max-width: 720px) { .runtime-row, .policy-row { grid-template-columns: 1fr; } .actions { justify-content: flex-end; } }
</style>
