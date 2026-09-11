<script lang="ts">
	import { onMount } from 'svelte';
	import { api, ApiError } from '$lib/api/client';
	import { Alert, Button, Card, SelectInput } from '$lib/components/ui';

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

	function optionDomId(policy: ResourcePolicy, optionId: string): string {
		return `catalog-option-${encodeURIComponent(policy.key)}-${encodeURIComponent(optionId)}`;
	}

	function definePolicy(
		key: string,
		resource_kind: string,
		title: string,
		group: string,
		help_text: string,
		execution_scope: ResourcePolicy['execution_scope'],
		overrides: Partial<Pick<ResourcePolicy, 'dependency' | 'required_when' | 'external_only' | 'shared_only'>> = {}
	): ResourcePolicy {
		return {
			key,
			resource_kind,
			title,
			group,
			help_text,
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
		definePolicy('openstack.service_project', 'project', 'Service project', 'OpenStack', 'Project used for Builder and service-owned Manila resources.', 'admin'),
		definePolicy('nova.default_network', 'network', 'Default tenant network', 'Nova / Cinder', 'Shared fallback network used only when project auto-networking is disabled.', 'tenant', { shared_only: true }),
		definePolicy('nova.default_external_network', 'network', 'Default external network', 'Nova / Cinder', 'External network required when project default networking is enabled.', 'tenant', { required_when: 'default_network_enabled', external_only: true }),
		definePolicy('nova.default_compute_availability_zone', 'compute_availability_zone', 'Default compute availability zone', 'Nova / Cinder', 'Nova scheduling zone when a request does not provide one.', 'admin'),
		definePolicy('cinder.default_volume_availability_zone', 'volume_availability_zone', 'Default volume availability zone', 'Nova / Cinder', 'Cinder placement zone when a request does not provide one.', 'admin'),
		definePolicy('manila.share_network', 'share_network', 'Service share network', 'Manila', 'Share network used only by Builder and service-owned NFS/DHSS shares.', 'service', { dependency: 'openstack.service_project' }),
		definePolicy('manila.cephfs_share_type', 'share_type', 'Public CephFS share type', 'Manila', 'Public share type available in service and tenant projects for CephFS.', 'tenant'),
		definePolicy('manila.nfs_share_type', 'share_type', 'Public NFS share type', 'Manila', 'Public share type available in service and tenant projects for NFS.', 'tenant'),
		definePolicy('k3s.server_image', 'image', 'K3s server image', 'K3s', 'Public Ubuntu server image.', 'tenant'),
		definePolicy('k3s.fcos_image', 'image', 'K3s Fedora CoreOS image', 'K3s', 'Public Fedora CoreOS image.', 'tenant'),
		definePolicy('k3s.server_flavor', 'flavor', 'K3s server flavor', 'K3s', 'Default server-node flavor.', 'tenant'),
		definePolicy('k3s.default_agent_flavor', 'flavor', 'K3s default agent flavor', 'K3s', 'Default agent-node flavor.', 'tenant'),
		definePolicy('k3s.volume_availability_zone', 'volume_availability_zone', 'K3s volume availability zone', 'K3s', 'Cinder placement zone for K3s boot volumes.', 'admin'),
		definePolicy('k3s.default_network', 'network', 'K3s default network', 'K3s', 'Shared fallback network used when a cluster request omits network_id.', 'tenant', { shared_only: true }),
		definePolicy('k3s.occm_floating_network', 'network', 'K3s OCCM floating network', 'K3s', 'External network for OCCM floating IP allocation.', 'tenant', { external_only: true }),
		definePolicy('k3s.occm_public_network', 'network', 'K3s OCCM public network', 'K3s', 'Shared/external network rendered into OCCM as its saved name.', 'tenant', { shared_only: true }),
		definePolicy('k3s.lb_subnet', 'subnet', 'K3s load-balancer subnet', 'K3s', 'Subnet used for active load-balancer modes.', 'tenant'),
		definePolicy('k3s.api_lb_vip_network', 'network', 'K3s API load-balancer network', 'K3s', 'Shared network for the API load balancer VIP.', 'tenant', { shared_only: true }),
		definePolicy('k3s.api_lb_floating_network', 'network', 'K3s API load-balancer floating network', 'K3s', 'External network for the API load balancer.', 'tenant', { external_only: true }),
		definePolicy('k3s.octavia_ingress_floating_network', 'network', 'K3s Octavia ingress floating network', 'K3s', 'External network for Octavia ingress.', 'tenant', { external_only: true }),
		definePolicy('builder.flavor', 'flavor', 'Builder flavor', 'Builder', 'Default Builder flavor; individual jobs may override it.', 'service', { dependency: 'openstack.service_project' }),
		definePolicy('builder.network', 'network', 'Builder network', 'Builder', 'Default Builder network; individual jobs may override it.', 'service', { dependency: 'openstack.service_project' }),
		definePolicy('builder.floating_network', 'network', 'Builder floating network', 'Builder', 'Optional external network for Builder utility VMs.', 'service', { dependency: 'openstack.service_project', external_only: true }),
		definePolicy('waygate.provider_network', 'network', 'Waygate provider network', 'Waygate', 'Target-tenant-visible shared provider network.', 'tenant', { shared_only: true }),
		definePolicy('waygate.image', 'image', 'Waygate image', 'Waygate', 'Target-tenant-visible public image.', 'tenant'),
		definePolicy('waygate.flavor', 'flavor', 'Waygate flavor', 'Waygate', 'Target-tenant-visible public flavor.', 'tenant'),
		definePolicy('waygate.floating_network', 'network', 'Waygate floating network', 'Waygate', 'Optional external network for Waygate endpoints.', 'tenant', { external_only: true })
	];

	const runtimeDefinitions: RuntimeSetting[] = [
		{
			key: 'k3s.version',
			title: 'K3s version',
			help_text: 'Version used for new K3s clusters.',
			value: '',
			state: 'missing'
		},
		{
			key: 'notion.sync_enabled',
			title: 'Notion synchronization',
			help_text: 'Global switch for all scheduled and manual Notion synchronization.',
			value: false,
			state: 'missing'
		}
	];

	let { token, projectId }: Props = $props();
	let policies = $state<ResourcePolicy[]>(policyDefinitions.map((policy) => ({ ...policy })));
	let runtimeSettings = $state<RuntimeSetting[]>(runtimeDefinitions.map((setting) => ({ ...setting })));
	let activeOptionIds = $state<Record<string, string>>({});
	let options = $state<Record<string, ResourceOption[]>>({});
	let selections = $state<Record<string, string>>({});
	let optionQueries = $state<Record<string, string>>({});
	let runtimeValues = $state<Record<string, string>>({});
	let openPolicyKey = $state<string | null>(null);
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
		activeOptionIds = { ...activeOptionIds, [key]: value || CLEAR_OPTION_ID };
		optionQueries = { ...optionQueries, [key]: value ? (options[key]?.find((option) => option.id === value)?.name ?? value) : '' };
		draftScope = {
			...draftScope,
			policies: { ...draftScope.policies, [key]: value }
		};
		persistDrafts();
	}

	function openCatalog(policy: ResourcePolicy) {
		openPolicyKey = policy.key;
		activeOptionIds = {
			...activeOptionIds,
			[policy.key]: selections[policy.key] || CLEAR_OPTION_ID
		};
		void loadOptions(policy);
	}

	function visibleOptionIds(policy: ResourcePolicy): string[] {
		return [CLEAR_OPTION_ID, ...filteredOptions(policy).map((option) => option.id)];
	}

	function setActiveOption(policy: ResourcePolicy, optionId: string) {
		activeOptionIds = { ...activeOptionIds, [policy.key]: optionId };
	}

	function activeDescendant(policy: ResourcePolicy): string | undefined {
		if (openPolicyKey !== policy.key) return undefined;
		return optionDomId(policy, activeOptionIds[policy.key] || selections[policy.key] || CLEAR_OPTION_ID);
	}

	function handleCatalogKeydown(policy: ResourcePolicy, event: KeyboardEvent) {
		const optionIds = visibleOptionIds(policy);
		const currentId = activeOptionIds[policy.key] || selections[policy.key] || CLEAR_OPTION_ID;
		const currentIndex = Math.max(optionIds.indexOf(currentId), 0);
		let nextIndex: number | null = null;

		if (event.key === 'Escape') {
			openPolicyKey = null;
			return;
		}
		if (event.key === 'ArrowDown') {
			nextIndex = (currentIndex + 1) % optionIds.length;
		} else if (event.key === 'ArrowUp') {
			nextIndex = (currentIndex - 1 + optionIds.length) % optionIds.length;
		} else if (event.key === 'Home') {
			nextIndex = 0;
		} else if (event.key === 'End') {
			nextIndex = optionIds.length - 1;
		} else if (event.key === 'Enter' && openPolicyKey === policy.key) {
			event.preventDefault();
			const activeId = activeOptionIds[policy.key] || CLEAR_OPTION_ID;
			setPolicySelection(policy.key, activeId === CLEAR_OPTION_ID ? '' : activeId);
			openPolicyKey = null;
			return;
		}

		if (nextIndex !== null) {
			event.preventDefault();
			openPolicyKey = policy.key;
			setActiveOption(policy, optionIds[nextIndex]);
		}
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
				? `리소스 정책 값을 조회하지 못했습니다: ${policyResult.reason.message}`
				: '리소스 정책 값을 조회하지 못했습니다';
		}
		if (runtimeResult.status === 'fulfilled') {
			mergeRuntimeValues(runtimeResult.value);
		} else if (!error) {
			error = runtimeResult.reason instanceof ApiError
				? `Runtime 설정 값을 조회하지 못했습니다: ${runtimeResult.reason.message}`
				: 'Runtime 설정 값을 조회하지 못했습니다';
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
				notice = `${policy.title}의 유일한 선택지를 기본값으로 선택했습니다. 저장을 누르면 반영됩니다.`;
			}
		} catch (cause) {
			error = cause instanceof ApiError ? `OpenStack 목록을 조회하지 못했습니다: ${cause.message}` : 'OpenStack 목록을 조회하지 못했습니다';
		} finally {
			const next = { ...catalogLoading };
			delete next[policy.key];
			catalogLoading = next;
		}
	}

	async function loadAllCatalogs(loadedPolicies: ResourcePolicy[]) {
		await Promise.allSettled(loadedPolicies.map((policy) => loadOptions(policy)));
	}

	function filteredOptions(policy: ResourcePolicy): ResourceOption[] {
		const query = optionQueries[policy.key]?.trim().toLocaleLowerCase() ?? '';
		const selectedId = selections[policy.key];
		return (options[policy.key] ?? []).filter(
			(option) =>
				option.id === selectedId ||
				!query ||
				option.name.toLocaleLowerCase().includes(query) ||
				option.id.toLocaleLowerCase().includes(query)
		);
	}

	function selectedLabel(policy: ResourcePolicy): string {
		const selectedId = selections[policy.key];
		return options[policy.key]?.find((option) => option.id === selectedId)?.name ??
			(policy.resolved_name ?? policy.resource_name ?? selectedId ?? '');
	}

	function setCatalogQuery(policy: ResourcePolicy, event: Event) {
		const value = (event.currentTarget as HTMLInputElement).value;
		const exact = options[policy.key]?.find(
			(option) => option.id === value || option.name.toLocaleLowerCase() === value.trim().toLocaleLowerCase()
		);
		optionQueries = { ...optionQueries, [policy.key]: value };
		if (exact) setPolicySelection(policy.key, exact.id);
		else if (!value) setPolicySelection(policy.key, '');
	}

	function hasUncommittedCatalogQuery(policy: ResourcePolicy): boolean {
		const query = optionQueries[policy.key]?.trim() ?? '';
		if (!query) return false;
		const selectedId = selections[policy.key];
		if (!selectedId) return true;
		const selectedName = selectedLabel(policy);
		return query !== selectedId && query.toLocaleLowerCase() !== selectedName.toLocaleLowerCase();
	}

	async function save(policy: ResourcePolicy) {
		if (hasUncommittedCatalogQuery(policy)) {
			error = `${policy.title}: 목록에서 리소스를 선택한 뒤 저장하세요.`;
			openPolicyKey = policy.key;
			return;
		}
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
			notice = `${policy.title} 정책을 저장했습니다.`;
		} catch (cause) {
			error = cause instanceof ApiError ? `정책 저장 실패: ${cause.message}` : '정책 저장 실패';
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
			notice = `${setting.title} 설정을 저장했습니다.`;
		} catch (cause) {
			error = cause instanceof ApiError ? `설정 저장 실패: ${cause.message}` : '설정 저장 실패';
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
			<p class="eyebrow">Infrastructure policies</p>
			<h2>OpenStack 리소스 정책</h2>
			<p>정책 목록은 즉시 표시되며, 저장된 값과 선택 목록만 백엔드에서 조회합니다. 변경사항은 저장 전까지 이 브라우저에 임시 보관됩니다.</p>
		</div>
	</div>

	{#if error}<Alert tone="danger">{error}</Alert>{/if}
	{#if notice}<Alert tone="success">{notice}</Alert>{/if}
	{#if loadingValues}<p class="muted loading-note">저장된 정책 값을 불러오는 중…</p>{/if}

	<section class="runtime-settings" aria-labelledby="runtime-settings-title">
		<div class="section-heading">
			<h3 id="runtime-settings-title">Runtime settings</h3>
			<p>OpenStack resource가 아닌 환경별 운영 값을 데이터베이스에 저장합니다.</p>
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
						ariaLabel={`${setting.title} 선택`}
					>
						<option value="true">Enabled</option>
						<option value="false">Disabled</option>
					</SelectInput>
				{:else}
					<input
						class="runtime-input"
						value={runtimeValues[setting.key] ?? ''}
						oninput={(event) => setRuntimeValue(setting.key, (event.currentTarget as HTMLInputElement).value)}
						aria-label={`${setting.title} 값`}
					/>
				{/if}
				<Button variant="primary" size="sm" onclick={() => saveRuntimeSetting(setting)} disabled={saving === setting.key}>
					{saving === setting.key ? '저장 중…' : '저장'}
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
							<div class="combobox">
								<input
									class="catalog-search"
									type="search"
									role="combobox"
									value={optionQueries[policy.key] ?? selectedLabel(policy)}
									onfocus={() => openCatalog(policy)}
									oninput={(event) => setCatalogQuery(policy, event)}
									onkeydown={(event) => handleCatalogKeydown(policy, event)}
									placeholder={catalogLoading[policy.key] ? '목록 조회 중…' : '이름 또는 ID로 검색·선택'}
									aria-label={`${policy.title} 검색 및 선택`}
									aria-controls={`catalog-options-${policy.key}`}
									aria-expanded={openPolicyKey === policy.key}
									aria-activedescendant={activeDescendant(policy)}
									disabled={Boolean(catalogLoading[policy.key])}
								/>
								{#if openPolicyKey === policy.key && options[policy.key]}
									<div class="option-menu" id={`catalog-options-${policy.key}`} role="listbox" aria-label={`${policy.title} 목록`}>
										<button
											id={optionDomId(policy, CLEAR_OPTION_ID)}
											type="button"
											role="option"
											class:selected={!selections[policy.key]}
											class:active={activeOptionIds[policy.key] === CLEAR_OPTION_ID}
											aria-selected={!selections[policy.key]}
											onmouseenter={() => setActiveOption(policy, CLEAR_OPTION_ID)}
											onclick={() => { setPolicySelection(policy.key, ''); openPolicyKey = null; }}
										>
											선택 안 함
										</button>
										{#each filteredOptions(policy) as option (option.id)}
											<button
												id={optionDomId(policy, option.id)}
												type="button"
												class:selected={selections[policy.key] === option.id}
												class:active={activeOptionIds[policy.key] === option.id}
												role="option"
												aria-selected={selections[policy.key] === option.id}
												onmouseenter={() => setActiveOption(policy, option.id)}
												onclick={() => { setPolicySelection(policy.key, option.id); openPolicyKey = null; }}
											>
												<span>{option.name}</span>
												<small>{option.id}</small>
											</button>
										{/each}
										{#if !filteredOptions(policy).length}<span class="empty-options">일치하는 리소스가 없습니다.</span>{/if}
									</div>
								{/if}
							</div>
							{#if selections[policy.key]}<span class="selection-id">{selections[policy.key]}</span>{/if}
						</div>
						<div class="actions">
							<Button variant="primary" size="sm" onclick={() => save(policy)} disabled={saving === policy.key}>
								{saving === policy.key ? '저장 중…' : '저장'}
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
	p, .muted, .policy-copy span, .selection-id, .empty-options { margin: 0; color: var(--color-ink-2); font-size: 0.82rem; line-height: 1.5; }
	.loading-note { padding: 0.5rem 0; }
	.runtime-settings, .policy-group { border-top: 1px solid var(--color-line-2); padding: 0.75rem 0; }
	.runtime-row, .policy-row { display: grid; grid-template-columns: minmax(11rem, 1fr) minmax(13rem, 1.2fr) auto; align-items: center; gap: 0.75rem; border-top: 1px solid var(--color-line-2); padding: 0.75rem 0; }
	.runtime-settings .runtime-row:first-of-type { border-top: 0; }
	.policy-copy strong { color: var(--color-ink-0); font-size: 0.86rem; }
	.runtime-input, .catalog-search { min-width: 0; width: 100%; border: 1px solid var(--color-line); border-radius: 0.375rem; background: var(--color-surface-sunken); color: var(--color-ink-0); padding: 0.5rem 0.75rem; }
	.runtime-input:focus, .catalog-search:focus { outline: none; border-color: var(--color-accent); box-shadow: var(--focus-ring); }
	.catalog-search::placeholder { color: var(--color-ink-3); }
	.combobox { position: relative; }
	.option-menu { position: absolute; z-index: 5; top: calc(100% + 0.25rem); width: 100%; max-height: 15rem; overflow: auto; border: 1px solid var(--color-line-2); border-radius: 0.5rem; background: var(--color-surface-raised); box-shadow: var(--shadow-md); }
	.option-menu button { display: flex; width: 100%; justify-content: space-between; gap: 0.75rem; border: 0; border-bottom: 1px solid var(--color-line); background: transparent; color: var(--color-ink-1); padding: 0.55rem 0.7rem; text-align: left; cursor: pointer; }
	.option-menu button:hover, .option-menu button.selected, .option-menu button.active { background: var(--color-surface-sunken); color: var(--color-ink-0); }
	.option-menu small { color: var(--color-ink-3); font-family: var(--font-mono); }
	.empty-options { display: block; padding: 0.65rem 0.7rem; }
	.selection-id { font-family: var(--font-mono); font-size: 0.7rem; }
	.actions { display: flex; gap: 0.4rem; }
	@media (max-width: 720px) { .runtime-row, .policy-row { grid-template-columns: 1fr; } .actions { justify-content: flex-end; } }
</style>
