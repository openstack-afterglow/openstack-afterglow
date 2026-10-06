<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { toast } from '$lib/stores/toast';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import FormModal from '$lib/components/ui/FormModal.svelte';
	import { secretsApi, type SecretInfo, type ContainerInfo, type OrderInfo, type QuotaInfo } from '$lib/api/secrets';
	import { ApiError } from '$lib/api/client';
	import { untrack } from 'svelte';
	import { betaFeatures } from '$lib/stores/betaFeatures';
	import BetaFeatureGate from '$lib/components/ui/BetaFeatureGate.svelte';
	import BulkSelectionOverlay from '$lib/components/ui/BulkSelectionOverlay.svelte';
	import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';
	import SelectionToolbar from '$lib/components/ui/SelectionToolbar.svelte';
	import { createResourceSelection } from '$lib/utils/resourceSelection.svelte';
	import { executeBulkMutations } from '$lib/utils/bulkActions';
	import { t } from '$lib/i18n/ns/dashboard-home';
	import { t as tc } from '$lib/i18n/ns/common';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import RichText from '$lib/i18n/RichText.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import AnimatedNumber from '$lib/components/ui/AnimatedNumber.svelte';

	type Tab = 'secrets' | 'containers' | 'orders' | 'quota';
	const selection = createResourceSelection();
	let selectionBusy = $state(false);

	let activeTab = $state<Tab>('secrets');
	let secrets = $state<SecretInfo[]>([]);
	let containers = $state<ContainerInfo[]>([]);
	let orders = $state<OrderInfo[]>([]);
	let quota = $state<QuotaInfo | null>(null);
	let loading = $state(true);
	let refreshing = $state(false);
	let error = $state('');

	// 비밀 생성 모달
	let showCreateSecret = $state(false);
	let newSecretName = $state('');
	let newSecretType = $state('passphrase');
	let newSecretPayload = $state('');
	let creating = $state(false);

	// 컨테이너 생성 모달
	let showCreateContainer = $state(false);
	let newContainerName = $state('');
	let newContainerType = $state('generic');
	let creatingContainer = $state(false);

	// Order 생성 모달
	let showCreateOrder = $state(false);
	let orderType = $state('key');
	let orderAlgorithm = $state('aes');
	let orderBitLength = $state(256);
	let creatingOrder = $state(false);

	// payload 보기
	let payloadVisible = $state<Record<string, string>>({});
	let payloadLoading = $state<string | null>(null);
	let deletingSecretId = $state<string | null>(null);
	let deletingContainerId = $state<string | null>(null);

	function selectableIds(tab: Tab = activeTab): string[] {
		if (tab === 'secrets') return secrets.filter((item) => !item.system_managed).map((item) => item.id);
		if (tab === 'containers') return containers.map((item) => item.id);
		return [];
	}

	function setActiveTab(tab: Tab) {
		if (activeTab !== tab) selection.clear();
		activeTab = tab;
	}
	const SECRET_TYPES = ['passphrase', 'certificate', 'symmetric', 'public', 'private', 'opaque'];
	const keyManagerEnabled = $derived($betaFeatures.keyManager);

	function clearKeyManagerState() {
		secrets = [];
		containers = [];
		orders = [];
		quota = null;
		error = '';
		selection.clear();
	}


	async function fetchAll() {
		const requestToken = $auth.token ?? undefined;
		const requestProject = $auth.projectId ?? undefined;
		if (!keyManagerEnabled) {
			clearKeyManagerState();
			loading = false;
			return;
		}
		try {
			const [s, c, o, q] = await Promise.allSettled([
				secretsApi.listSecrets(requestToken, requestProject),
				secretsApi.listContainers(requestToken, requestProject),
				secretsApi.listOrders(requestToken, requestProject),
				secretsApi.getEffectiveQuota(requestToken, requestProject),
			]);
			if ($auth.projectId !== requestProject || !keyManagerEnabled) return;
			if (s.status === 'fulfilled') secrets = s.value;
			if (c.status === 'fulfilled') containers = c.value;
			if (o.status === 'fulfilled') orders = o.value;
			if (q.status === 'fulfilled') quota = q.value;
			selection.retain(selectableIds());
			error = '';
		} catch (e) {
			if ($auth.projectId === requestProject && keyManagerEnabled) {
				error = e instanceof ApiError ? t('secrets.error.loadFailed', { status: e.status }) : t('secrets.error.server');
			}
		} finally {
			if ($auth.projectId === requestProject && keyManagerEnabled) loading = false;
		}
	}

	async function forceRefresh() {
		refreshing = true;
		try { await fetchAll(); }
		finally { refreshing = false; }
	}

	const ar = createAutoRefresh(() => fetchAll(), {
		storageKey: 'dashboard-secrets',
		invokeOnMount: false,
		defaultActive: true,
		defaultInterval: 30,
		intervalOptions: [10, 15, 30, 60],
	});

	$effect(() => {
		const pid = $auth.projectId;
		if (!keyManagerEnabled) {
			clearKeyManagerState();
			loading = false;
			return;
		}
		if (!pid) {
			clearKeyManagerState();
			loading = false;
			return;
		}
		untrack(() => {
			selection.clear();
			fetchAll();
		});
	});

	async function handleCreateSecret() {
		if (!keyManagerEnabled) return;
		creating = true;
		try {
			await secretsApi.createSecret({
				name: newSecretName,
				secret_type: newSecretType,
				payload: newSecretPayload || undefined,
			}, $auth.token ?? undefined, $auth.projectId ?? undefined);
			toast.success(t('secrets.toast.secretCreated'));
			showCreateSecret = false;
			newSecretName = '';
			newSecretType = 'passphrase';
			newSecretPayload = '';
			await fetchAll();
		} catch (e) {
			toast.error(t('secrets.toast.createFailed', { error: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			creating = false;
		}
	}

	async function handleDeleteSecret(s: SecretInfo) {
		if (deletingSecretId !== null) return;
		if (!keyManagerEnabled) return;
		if (s.system_managed) return;
		if (!await confirmDialog(t('secrets.confirm.deleteSecret', { name: s.name ?? s.id }))) return;
		deletingSecretId = s.id;
		try {
			await secretsApi.deleteSecret(s.id, $auth.token ?? undefined, $auth.projectId ?? undefined);
			toast.success(t('secrets.toast.deleted'));
			await fetchAll();
		} catch (e) {
			toast.error(t('secrets.toast.deleteFailed', { error: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			deletingSecretId = null;
		}
	}

	async function handleShowPayload(s: SecretInfo) {
		if (payloadVisible[s.id] !== undefined) {
			const next = { ...payloadVisible };
			delete next[s.id];
			payloadVisible = next;
			return;
		}
		if (payloadLoading !== null || !keyManagerEnabled) return;
		payloadLoading = s.id;
		try {
			const val = await secretsApi.getPayload(s.id, $auth.token ?? undefined, $auth.projectId ?? undefined);
			payloadVisible = { ...payloadVisible, [s.id]: val };
		} catch {
			toast.error(t('secrets.toast.payloadFailed'));
		} finally {
			payloadLoading = null;
		}
	}

	async function copyPayload(val: string) {
		if (!keyManagerEnabled) return;
		try {
			await navigator.clipboard.writeText(val);
			toast.success(t('secrets.toast.copied'));
		} catch {
			toast.error(t('secrets.toast.copyFailed'));
		}
	}

	async function handleCreateContainer() {
		if (!keyManagerEnabled) return;
		creatingContainer = true;
		try {
			await secretsApi.createContainer({
				name: newContainerName,
				container_type: newContainerType,
				secret_refs: [],
			}, $auth.token ?? undefined, $auth.projectId ?? undefined);
			toast.success(t('secrets.toast.containerCreated'));
			showCreateContainer = false;
			newContainerName = '';
			await fetchAll();
		} catch (e) {
			toast.error(t('secrets.toast.createFailed', { error: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			creatingContainer = false;
		}
	}

	async function handleDeleteContainer(id: string, name: string | null) {
		if (deletingContainerId !== null) return;
		if (!keyManagerEnabled) return;
		if (!await confirmDialog(t('secrets.confirm.deleteContainer', { name: name ?? id }))) return;
		deletingContainerId = id;
		try {
			await secretsApi.deleteContainer(id, $auth.token ?? undefined, $auth.projectId ?? undefined);
			toast.success(t('secrets.toast.deleted'));
			await fetchAll();
		} catch (e) {
			toast.error(t('secrets.toast.deleteFailed', { error: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			deletingContainerId = null;
		}
	}
	async function runBulkDelete() {
		const actionTab = activeTab;
		const submitted = [...selection.ids];
		if (submitted.length === 0 || (actionTab !== 'secrets' && actionTab !== 'containers')) return;
		if (!(await confirmDialog(t(actionTab === 'secrets' ? 'secrets.confirm.bulkDeleteSecrets' : 'secrets.confirm.bulkDeleteContainers', { count: submitted.length })))) return;
		selectionBusy = true;
		const requestToken = $auth.token ?? undefined;
		const requestProject = $auth.projectId ?? undefined;
		const results = await executeBulkMutations(submitted, (id) =>
			actionTab === 'secrets'
				? secretsApi.deleteSecret(id, requestToken, requestProject)
				: secretsApi.deleteContainer(id, requestToken, requestProject)
		);
		if ($auth.projectId === requestProject && activeTab === actionTab && keyManagerEnabled) {
			selection.remove(results.filter((result) => result.ok).map((result) => result.id));
			await fetchAll();
		}
		const successCount = results.filter((result) => result.ok).length;
		const failureCount = results.length - successCount;
		if (successCount) toast.success(t(actionTab === 'secrets' ? 'secrets.toast.bulkSecretsSucceeded' : 'secrets.toast.bulkContainersSucceeded', { count: successCount }));
		if (failureCount) toast.error(t(actionTab === 'secrets' ? 'secrets.toast.bulkSecretsFailed' : 'secrets.toast.bulkContainersFailed', { count: failureCount }));
		selectionBusy = false;
	}

	async function handleCreateOrder() {
		if (!keyManagerEnabled) return;
		creatingOrder = true;
		try {
			await secretsApi.createOrder({
				order_type: orderType,
				meta: {
					algorithm: orderAlgorithm,
					bit_length: orderBitLength,
					payload_content_type: 'application/octet-stream',
				},
			}, $auth.token ?? undefined, $auth.projectId ?? undefined);
			toast.success(t('secrets.toast.orderCreated'));
			showCreateOrder = false;
			await fetchAll();
		} catch (e) {
			toast.error(t('secrets.toast.orderFailed', { error: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			creatingOrder = false;
		}
	}

	const SECRET_TYPE_LABEL: Record<string, string> = $derived({
		passphrase: t('secrets.secretType.passphrase'),
		certificate: t('secrets.secretType.certificate'),
		symmetric: t('secrets.secretType.symmetric'),
		public: t('secrets.secretType.public'),
		private: t('secrets.secretType.private'),
		opaque: t('secrets.secretType.opaque'),
	});

	const STATUS_CLASS: Record<string, string> = {
		ACTIVE: 'bg-green-900/40 text-green-300',
		PENDING: 'bg-yellow-900/40 text-yellow-300',
		ERROR: 'bg-red-900/40 text-red-300',
	};
</script>

{#snippet highlightedText(text: string)}<span class="text-ink-1 font-medium">{text}</span>{/snippet}
{#snippet mutedText(text: string)}<span class="text-ink-2">{text}</span>{/snippet}
{#snippet valueText(text: string)}<span class="text-ink-0">{text}</span>{/snippet}
{#snippet tabCountText(text: string)}<span class="ml-1 text-xs text-ink-2"><AnimatedNumber value={secrets.length} format={(value) => String(Math.round(value))} /></span>{/snippet}

{#if !keyManagerEnabled}
	<div class="p-4 md:p-8">
		<BetaFeatureGate title={t('secrets.beta.title')} />
	</div>
{:else}
<!-- 비밀 생성 모달 -->
<FormModal
	bind:open={showCreateSecret}
	title={t('secrets.createSecret.title')}
	submitLabel={t('secrets.actions.create')}
	submitting={creating}
	onSubmit={handleCreateSecret}
	onClose={() => { showCreateSecret = false; }}
>
	<div class="space-y-4">
		<div>
			<label class="block text-sm text-ink-2 mb-1" for="field-page-318">{t('secrets.form.name')}</label>
			<input id="field-page-318" bind:value={newSecretName} class="w-full bg-surface-selected border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0" placeholder={t('secrets.form.namePlaceholder')} />
		</div>
		<div>
			<label class="block text-sm text-ink-2 mb-1" for="field-page-322">{t('secrets.form.type')}</label>
			<select id="field-page-322" bind:value={newSecretType} class="w-full bg-surface-selected border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0">
				{#each SECRET_TYPES as secretType}<option value={secretType}>{SECRET_TYPE_LABEL[secretType] ?? secretType}</option>{/each}
			</select>
		</div>
		<div>
			<label class="block text-sm text-ink-2 mb-1" for="field-page-328"><RichText segments={t.rich('secrets.form.payload')} tags={{ muted: mutedText }} /></label>
			<textarea id="field-page-328" bind:value={newSecretPayload} rows={3} class="w-full bg-surface-selected border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 font-mono" placeholder={newSecretType === 'certificate' ? '-----BEGIN CERTIFICATE-----\n...' : t('secrets.form.payloadPlaceholder')}></textarea>
		</div>
	</div>
</FormModal>

<!-- 컨테이너 생성 모달 -->
<FormModal
	bind:open={showCreateContainer}
	title={t('secrets.createContainer.title')}
	submitLabel={t('secrets.actions.create')}
	submitting={creatingContainer}
	onSubmit={handleCreateContainer}
	onClose={() => { showCreateContainer = false; }}
>
	<div class="space-y-4">
		<div>
			<label class="block text-sm text-ink-2 mb-1" for="field-page-345">{t('secrets.form.name')}</label>
			<input id="field-page-345" bind:value={newContainerName} class="w-full bg-surface-selected border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0" />
		</div>
		<div>
			<label class="block text-sm text-ink-2 mb-1" for="field-page-349">{t('secrets.form.type')}</label>
			<select id="field-page-349" bind:value={newContainerType} class="w-full bg-surface-selected border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0">
				<option value="generic">{t('secrets.containerType.generic')}</option>
				<option value="rsa">{t('secrets.containerType.rsa')}</option>
				<option value="certificate">{t('secrets.containerType.certificate')}</option>
			</select>
		</div>
	</div>
</FormModal>

<!-- Order 생성 모달 -->
<FormModal
	bind:open={showCreateOrder}
	title={t('secrets.createOrder.title')}
	submitLabel={t('secrets.actions.request')}
	submitting={creatingOrder}
	onSubmit={handleCreateOrder}
	onClose={() => { showCreateOrder = false; }}
>
	<div class="space-y-4">
		<div>
			<label class="block text-sm text-ink-2 mb-1" for="field-page-370">{t('secrets.form.keyType')}</label>
			<select id="field-page-370" bind:value={orderType} class="w-full bg-surface-selected border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0">
				<option value="key">{t('secrets.orderType.key')}</option>
				<option value="asymmetric">{t('secrets.orderType.asymmetric')}</option>
			</select>
		</div>
		<div>
			<label class="block text-sm text-ink-2 mb-1" for="field-page-377">{t('secrets.form.algorithm')}</label>
			<select id="field-page-377" bind:value={orderAlgorithm} class="w-full bg-surface-selected border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0">
				{#if orderType === 'key'}<option value="aes">AES</option>{/if}
				{#if orderType === 'asymmetric'}<option value="rsa">RSA</option>{/if}
			</select>
		</div>
		<div>
			<label class="block text-sm text-ink-2 mb-1" for="field-page-384">{t('secrets.form.bitLength')}</label>
			<select id="field-page-384" bind:value={orderBitLength} class="w-full bg-surface-selected border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0">
				<option value={128}>128</option>
				<option value={256}>256</option>
				<option value={2048}>2048</option>
				<option value={4096}>4096</option>
			</select>
		</div>
	</div>
</FormModal>

<div class="bulk-selection-page p-4 md:p-8">
	<PageHeader breadcrumb={t('secrets.page.breadcrumb')} title={t('secrets.page.title')}>
		{#snippet actions()}
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={refreshing}
				onManualRefresh={forceRefresh}
			/>
			{#if activeTab === 'secrets'}
				<button onclick={() => showCreateSecret = true} class="bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium px-4 py-2 rounded-lg transition-colors">{t('secrets.actions.createSecret')}</button>
			{:else if activeTab === 'containers'}
				<button onclick={() => showCreateContainer = true} class="bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium px-4 py-2 rounded-lg transition-colors">{t('secrets.actions.createContainer')}</button>
			{:else if activeTab === 'orders'}
				<button onclick={() => showCreateOrder = true} class="bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium px-4 py-2 rounded-lg transition-colors">{t('secrets.actions.createOrder')}</button>
			{/if}
		{/snippet}
	</PageHeader>

	<!-- 탭 -->
	<div class="flex gap-1 mb-0 border-b border-line-2">
		{#each (['secrets', 'containers', 'orders', 'quota'] as Tab[]) as tab}
			<button
				onclick={() => setActiveTab(tab)}
				disabled={selectionBusy}
				class="px-4 py-2 text-sm font-medium transition-colors {activeTab === tab ? 'text-ink-0 border-b-2 border-action-warm' : 'text-ink-2 hover:text-ink-1'}"
			>
				{#if tab === 'secrets' && secrets.length > 0}
					<RichText segments={t.rich('secrets.tabs.secretsWithCount', { count: secrets.length })} tags={{ count: tabCountText }} />
				{:else}
					{t(`secrets.tabs.${tab}`)}
				{/if}
			</button>
		{/each}
	</div>

	<!-- 탭별 설명 -->
	{#if activeTab === 'secrets'}
		<div class="my-4 flex items-start gap-3 bg-surface-sunken/40 border border-line-2/60 rounded-lg px-4 py-3 text-sm text-ink-2">
			<span class="text-lg leading-none mt-0.5">🔑</span>
			<div>
				<RichText segments={t.rich('secrets.description.secrets')} tags={{ highlight: highlightedText, muted: mutedText, value: valueText }} />
			</div>
		</div>
	{:else if activeTab === 'containers'}
		<div class="my-4 flex items-start gap-3 bg-surface-sunken/40 border border-line-2/60 rounded-lg px-4 py-3 text-sm text-ink-2">
			<span class="text-lg leading-none mt-0.5">📦</span>
			<div>
				<RichText segments={t.rich('secrets.description.containers')} tags={{ highlight: highlightedText, muted: mutedText, value: valueText }} />
			</div>
		</div>
	{:else if activeTab === 'orders'}
		<div class="my-4 flex items-start gap-3 bg-surface-sunken/40 border border-line-2/60 rounded-lg px-4 py-3 text-sm text-ink-2">
			<span class="text-lg leading-none mt-0.5">⚙️</span>
			<div>
				<RichText segments={t.rich('secrets.description.orders')} tags={{ highlight: highlightedText, muted: mutedText, value: valueText }} />
			</div>
		</div>
	{:else if activeTab === 'quota'}
		<div class="my-4 flex items-start gap-3 bg-surface-sunken/40 border border-line-2/60 rounded-lg px-4 py-3 text-sm text-ink-2">
			<span class="text-lg leading-none mt-0.5">📊</span>
			<div>
				<RichText segments={t.rich('secrets.description.quota')} tags={{ highlight: highlightedText, muted: mutedText, value: valueText }} />
			</div>
		</div>
	{/if}

	{#if error}<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>{/if}

	{#if loading}
		<ActivityIndicator label={`${t('secrets.page.title')} · ${tc('state.loading')}`} />
		<LoadingSkeleton variant="table" rows={4} />
	{:else if activeTab === 'secrets'}
		{#if secrets.length === 0}
			<div class="motion-fade text-center py-16 text-ink-2">
				<div class="text-4xl mb-3">🔑</div>
				<p class="text-sm">{t('secrets.empty.secrets')}</p>
				<button onclick={() => showCreateSecret = true} class="mt-4 text-warm-text hover:text-warm-text-hover text-sm">{t('secrets.actions.createSecret')}</button>
			</div>
		{:else}
			<div class="mb-3">
				<SelectionToolbar
					label={t('secrets.tabs.secrets')}
					ariaLabel={t('secrets.selection.allSecrets')}
					checked={selection.count === selectableIds('secrets').length && selection.count > 0}
					indeterminate={selection.count > 0 && selection.count < selectableIds('secrets').length}
					selectedCount={selection.count}
					disabled={selectionBusy}
					onToggle={() => selection.toggleAll(selectableIds('secrets'))}
				/>
			</div>
			<div class="overflow-x-auto">
				<table class="w-full text-sm">
					<thead>
						<tr class="text-left text-ink-2 border-b border-line-2">
							<th class="pb-3 pr-4 font-medium w-10">{t('secrets.table.select')}</th>
							<th class="pb-3 pr-4 font-medium">{t('secrets.form.name')}</th>
							<th class="pb-3 pr-4 font-medium">{t('secrets.form.type')}</th>
							<th class="pb-3 pr-4 font-medium">{t('secrets.table.status')}</th>
							<th class="pb-3 pr-4 font-medium">{t('secrets.table.created')}</th>
							<th class="pb-3 pr-4 font-medium">{t('secrets.table.expires')}</th>
							<th class="pb-3 font-medium">{t('secrets.table.actions')}</th>
						</tr>
					</thead>
					<tbody class="divide-y divide-line">
						{#each secrets as s (s.id)}
							<tr class="resource-selection-surface hover:bg-surface-sunken/30" data-selected={selection.has(s.id)}>
								<td class="py-3 pr-4">
									<SelectionCheckbox
										checked={selection.has(s.id)}
										disabled={s.system_managed || selectionBusy}
										unavailable={s.system_managed}
										title={s.system_managed ? t('secrets.selection.systemManaged') : undefined}
										ariaLabel={t('secrets.selection.item', { name: s.name ?? s.id })}
										onclick={() => selection.toggle(s.id)}
									/>
								</td>
								<td class="py-3 pr-4 font-mono text-xs">
									<div class="flex items-center gap-2 max-md:max-w-[66vw]">
										<span class="max-md:truncate" title={s.name ?? s.id}>{s.name ?? s.id}</span>
										{#if s.system_managed}<span class="text-xs bg-surface-selected text-ink-2 px-2 py-0.5 rounded-full">{t('secrets.secret.system')}</span>{/if}
									</div>
									<div class="text-ink-2 text-xs mt-0.5">{s.id}</div>
								</td>
								<td class="py-3 pr-4 text-ink-2">{SECRET_TYPE_LABEL[s.secret_type] ?? s.secret_type}</td>
								<td class="py-3 pr-4"><span class="px-2 py-0.5 rounded text-xs {STATUS_CLASS[s.status ?? ''] ?? 'bg-surface-selected text-ink-2'}">{s.status ?? '-'}</span></td>
								<td class="py-3 pr-4 text-ink-2 text-xs">{s.created ? new Date(s.created).toLocaleDateString(intlLocale()) : '-'}</td>
								<td class="py-3 pr-4 text-ink-2 text-xs">{s.expires ? new Date(s.expires).toLocaleDateString(intlLocale()) : t('secrets.secret.noExpiry')}</td>
								<td class="py-3">
									<div class="flex gap-2">
										<button onclick={() => handleShowPayload(s)} disabled={payloadLoading !== null && payloadVisible[s.id] === undefined} aria-busy={payloadLoading === s.id} class="text-xs text-warm-text hover:text-warm-text-hover disabled:opacity-50">{#if payloadLoading === s.id}<ActivityIndicator size="xs" label={t('secrets.actions.loading')} />{:else}{payloadVisible[s.id] !== undefined ? t('secrets.actions.hide') : t('secrets.actions.showValue')}{/if}</button>
										{#if !s.system_managed}<button onclick={() => handleDeleteSecret(s)} disabled={selectionBusy || deletingSecretId !== null} class="text-xs text-state-danger-text hover:text-ink-0 disabled:opacity-50">{#if deletingSecretId === s.id}<ActivityIndicator size="xs" tone="danger" label={`${t('secrets.actions.delete')} · ${tc('state.processing')}`} />{:else}{t('secrets.actions.delete')}{/if}</button>{/if}
									</div>
									{#if payloadVisible[s.id] !== undefined}
										<div class="motion-fade mt-2 flex items-center gap-2">
											<code class="text-xs bg-surface-base border border-line-2 rounded px-2 py-1 font-mono max-w-xs overflow-x-auto block">{payloadVisible[s.id].substring(0, 60)}{payloadVisible[s.id].length > 60 ? '...' : ''}</code>
											<button onclick={() => copyPayload(payloadVisible[s.id])} class="text-xs text-ink-2 hover:text-ink-1 shrink-0">{t('secrets.actions.copy')}</button>
										</div>
									{/if}
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}

	{:else if activeTab === 'containers'}
		{#if containers.length === 0}
			<div class="motion-fade text-center py-16 text-ink-2">
				<div class="text-4xl mb-3">📦</div>
				<p class="text-sm">{t('secrets.empty.containers')}</p>
				<button onclick={() => showCreateContainer = true} class="mt-4 text-warm-text hover:text-warm-text-hover text-sm">{t('secrets.actions.createContainer')}</button>
			</div>
		{:else}
			<div class="mb-3">
				<SelectionToolbar
					label={t('secrets.tabs.containers')}
					ariaLabel={t('secrets.selection.allContainers')}
					checked={selection.count === containers.length && selection.count > 0}
					indeterminate={selection.count > 0 && selection.count < containers.length}
					selectedCount={selection.count}
					disabled={selectionBusy}
					onToggle={() => selection.toggleAll(selectableIds('containers'))}
				/>
			</div>
			<div class="overflow-x-auto">
				<table class="w-full text-sm">
					<thead>
						<tr class="text-left text-ink-2 border-b border-line-2">
							<th class="pb-3 pr-4 font-medium w-10">{t('secrets.table.select')}</th>
							<th class="pb-3 pr-4 font-medium">{t('secrets.form.name')}</th>
							<th class="pb-3 pr-4 font-medium">{t('secrets.form.type')}</th>
							<th class="pb-3 pr-4 font-medium">{t('secrets.table.status')}</th>
							<th class="pb-3 pr-4 font-medium">{t('secrets.table.secrets')}</th>
							<th class="pb-3 font-medium">{t('secrets.table.actions')}</th>
						</tr>
					</thead>
					<tbody class="divide-y divide-line">
						{#each containers as c (c.id)}
							<tr class="resource-selection-surface hover:bg-surface-sunken/30" data-selected={selection.has(c.id)}>
								<td class="py-3 pr-4"><SelectionCheckbox checked={selection.has(c.id)} disabled={selectionBusy} ariaLabel={t('secrets.selection.item', { name: c.name ?? c.id })} onclick={() => selection.toggle(c.id)} /></td>
								<td class="py-3 pr-4"><div class="max-md:max-w-[66vw] max-md:truncate" title={c.name ?? c.id}>{c.name ?? '-'}</div><div class="text-xs text-ink-2 font-mono max-md:max-w-[66vw] max-md:truncate">{c.id}</div></td>
								<td class="py-3 pr-4 text-ink-2">{c.type}</td>
								<td class="py-3 pr-4"><span class="px-2 py-0.5 rounded text-xs {STATUS_CLASS[c.status ?? ''] ?? 'bg-surface-selected text-ink-2'}">{c.status ?? '-'}</span></td>
								<td class="py-3 pr-4 text-ink-2"><AnimatedNumber value={c.secret_refs.length} format={(value) => t('secrets.container.secretCount', { count: Math.round(value) })} /></td>
								<td class="py-3"><button onclick={() => handleDeleteContainer(c.id, c.name)} disabled={selectionBusy || deletingContainerId !== null} class="text-xs text-state-danger-text hover:text-ink-0 disabled:opacity-50">{#if deletingContainerId === c.id}<ActivityIndicator size="xs" tone="danger" label={`${t('secrets.actions.delete')} · ${tc('state.processing')}`} />{:else}{t('secrets.actions.delete')}{/if}</button></td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}

	{:else if activeTab === 'orders'}
		{#if orders.length === 0}
			<div class="motion-fade text-center py-16 text-ink-2">
				<div class="text-4xl mb-3">⚙️</div>
				<p class="text-sm">{t('secrets.empty.orders')}</p>
				<button onclick={() => showCreateOrder = true} class="mt-4 text-warm-text hover:text-warm-text-hover text-sm">{t('secrets.actions.createOrder')}</button>
			</div>
		{:else}
			<div class="overflow-x-auto">
				<table class="w-full text-sm">
					<thead>
						<tr class="text-left text-ink-2 border-b border-line-2">
							<th class="pb-3 pr-4 font-medium">ID</th>
							<th class="pb-3 pr-4 font-medium">{t('secrets.form.type')}</th>
							<th class="pb-3 pr-4 font-medium">{t('secrets.table.status')}</th>
							<th class="pb-3 pr-4 font-medium">{t('secrets.table.created')}</th>
							<th class="pb-3 font-medium">{t('secrets.table.result')}</th>
						</tr>
					</thead>
					<tbody class="divide-y divide-line">
						{#each orders as o (o.id)}
							<tr class="hover:bg-surface-sunken/30">
								<td class="py-3 pr-4 font-mono text-xs text-ink-2">{o.id}</td>
								<td class="py-3 pr-4 text-ink-2">{o.type}</td>
								<td class="py-3 pr-4">
									<span class="px-2 py-0.5 rounded text-xs {STATUS_CLASS[o.status ?? ''] ?? 'bg-surface-selected text-ink-2'}">{o.status ?? '-'}</span>
									{#if o.status === 'PENDING' && !o.secret_ref && !o.error_reason}
										<ActivityIndicator size="xs" label={t('secrets.order.pending')} />
									{/if}
								</td>
								<td class="py-3 pr-4 text-ink-2 text-xs">{o.created ? new Date(o.created).toLocaleDateString(intlLocale()) : '-'}</td>
								<td class="py-3 text-xs text-ink-2">
									{#if o.secret_ref}<span class="text-green-400">{t('secrets.order.secretCreated')}</span>{:else if o.error_reason}<span class="text-red-400">{o.error_reason}</span>{:else}{t('secrets.order.pending')}{/if}
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}

	{:else if activeTab === 'quota'}
		{#if quota}
			<div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
				{#each ([[t('secrets.tabs.secrets'), quota.secrets], [t('secrets.quota.orders'), quota.orders], [t('secrets.tabs.containers'), quota.containers], [t('secrets.quota.consumers'), quota.consumers], [t('secrets.quota.cas'), quota.cas]] as [string, number][]) as [label, val]}
					<div class="bg-surface-sunken rounded-xl p-4 border border-line-2">
						<div class="text-xs text-ink-2 mb-1">{label}</div>
						<div class="text-2xl font-bold text-ink-0">{#if val === -1}∞{:else}<AnimatedNumber value={val} />{/if}</div>
						<div class="text-xs text-ink-2 mt-1">{val === -1 ? t('secrets.quota.unlimited') : t('secrets.quota.limit', { count: val })}</div>
					</div>
				{/each}
			</div>
		{:else}
			<div class="text-center py-8 text-ink-2 text-sm">{t('secrets.quota.unavailable')}</div>
		{/if}
	{/if}
	<BulkSelectionOverlay
		count={activeTab === 'secrets' || activeTab === 'containers' ? selection.count : 0}
		ariaLabel={activeTab === 'secrets' ? t('secrets.selection.bulkSecrets') : t('secrets.selection.bulkContainers')}
		busy={selectionBusy}
		actions={[{ key: 'delete', label: t('secrets.actions.delete'), tone: 'danger', onAction: runBulkDelete }]}
		onClear={() => selection.clear()}
	/>
</div>
{/if}
