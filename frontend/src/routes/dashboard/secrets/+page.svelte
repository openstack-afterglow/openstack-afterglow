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
				error = e instanceof ApiError ? `조회 실패 (${e.status})` : '서버 오류';
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
			toast.success('비밀이 생성되었습니다');
			showCreateSecret = false;
			newSecretName = '';
			newSecretType = 'passphrase';
			newSecretPayload = '';
			await fetchAll();
		} catch (e) {
			toast.error('생성 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		} finally {
			creating = false;
		}
	}

	async function handleDeleteSecret(s: SecretInfo) {
		if (!keyManagerEnabled) return;
		if (s.system_managed) return;
		if (!await confirmDialog(`비밀 "${s.name ?? s.id}"를 삭제하시겠습니까?`)) return;
		try {
			await secretsApi.deleteSecret(s.id, $auth.token ?? undefined, $auth.projectId ?? undefined);
			toast.success('삭제되었습니다');
			await fetchAll();
		} catch (e) {
			toast.error('삭제 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		}
	}

	async function handleShowPayload(s: SecretInfo) {
		if (!keyManagerEnabled) return;
		if (payloadVisible[s.id]) {
			const next = { ...payloadVisible };
			delete next[s.id];
			payloadVisible = next;
			return;
		}
		payloadLoading = s.id;
		try {
			const val = await secretsApi.getPayload(s.id, $auth.token ?? undefined, $auth.projectId ?? undefined);
			payloadVisible = { ...payloadVisible, [s.id]: val };
		} catch {
			toast.error('payload 조회 실패');
		} finally {
			payloadLoading = null;
		}
	}

	async function copyPayload(val: string) {
		if (!keyManagerEnabled) return;
		try {
			await navigator.clipboard.writeText(val);
			toast.success('복사됨');
		} catch {
			toast.error('복사 실패');
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
			toast.success('컨테이너가 생성되었습니다');
			showCreateContainer = false;
			newContainerName = '';
			await fetchAll();
		} catch (e) {
			toast.error('생성 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		} finally {
			creatingContainer = false;
		}
	}

	async function handleDeleteContainer(id: string, name: string | null) {
		if (!keyManagerEnabled) return;
		if (!await confirmDialog(`컨테이너 "${name ?? id}"를 삭제하시겠습니까?`)) return;
		try {
			await secretsApi.deleteContainer(id, $auth.token ?? undefined, $auth.projectId ?? undefined);
			toast.success('삭제되었습니다');
			await fetchAll();
		} catch (e) {
			toast.error('삭제 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		}
	}
	async function runBulkDelete() {
		const actionTab = activeTab;
		const submitted = [...selection.ids];
		if (submitted.length === 0 || (actionTab !== 'secrets' && actionTab !== 'containers')) return;
		const label = actionTab === 'secrets' ? '비밀' : '컨테이너';
		if (!(await confirmDialog(`${submitted.length}개 ${label}를 삭제하시겠습니까?`))) return;
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
		if (successCount) toast.success(`${successCount}개 ${label} 요청을 완료했습니다.`);
		if (failureCount) toast.error(`${failureCount}개 ${label}에 실패했습니다.`);
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
			toast.success('키 생성 Order가 요청되었습니다');
			showCreateOrder = false;
			await fetchAll();
		} catch (e) {
			toast.error('Order 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		} finally {
			creatingOrder = false;
		}
	}

	const SECRET_TYPE_LABEL: Record<string, string> = {
		passphrase: '패스프레이즈',
		certificate: '인증서',
		symmetric: '대칭키',
		public: '공개키',
		private: '개인키',
		opaque: 'Opaque',
	};

	const STATUS_CLASS: Record<string, string> = {
		ACTIVE: 'bg-green-900/40 text-green-300',
		PENDING: 'bg-yellow-900/40 text-yellow-300',
		ERROR: 'bg-red-900/40 text-red-300',
	};
</script>

{#if !keyManagerEnabled}
	<div class="p-4 md:p-8">
		<BetaFeatureGate title="Key Manager는 베타 기능입니다" />
	</div>
{:else}
<!-- 비밀 생성 모달 -->
<FormModal
	bind:open={showCreateSecret}
	title="비밀 생성"
	submitLabel="생성"
	submitting={creating}
	onSubmit={handleCreateSecret}
	onClose={() => { showCreateSecret = false; }}
>
	<div class="space-y-4">
		<div>
			<label class="block text-sm text-ink-2 mb-1" for="field-page-318">이름</label>
			<input id="field-page-318" bind:value={newSecretName} class="w-full bg-surface-selected border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0" placeholder="my-secret" />
		</div>
		<div>
			<label class="block text-sm text-ink-2 mb-1" for="field-page-322">타입</label>
			<select id="field-page-322" bind:value={newSecretType} class="w-full bg-surface-selected border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0">
				{#each SECRET_TYPES as t}<option value={t}>{SECRET_TYPE_LABEL[t] ?? t}</option>{/each}
			</select>
		</div>
		<div>
			<label class="block text-sm text-ink-2 mb-1" for="field-page-328">payload <span class="text-ink-3">(선택 — 나중에 PUT으로도 가능)</span></label>
			<textarea id="field-page-328" bind:value={newSecretPayload} rows={3} class="w-full bg-surface-selected border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 font-mono" placeholder={newSecretType === 'certificate' ? '-----BEGIN CERTIFICATE-----\n...' : '비밀 값'}></textarea>
		</div>
	</div>
</FormModal>

<!-- 컨테이너 생성 모달 -->
<FormModal
	bind:open={showCreateContainer}
	title="컨테이너 생성"
	submitLabel="생성"
	submitting={creatingContainer}
	onSubmit={handleCreateContainer}
	onClose={() => { showCreateContainer = false; }}
>
	<div class="space-y-4">
		<div>
			<label class="block text-sm text-ink-2 mb-1" for="field-page-345">이름</label>
			<input id="field-page-345" bind:value={newContainerName} class="w-full bg-surface-selected border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0" />
		</div>
		<div>
			<label class="block text-sm text-ink-2 mb-1" for="field-page-349">타입</label>
			<select id="field-page-349" bind:value={newContainerType} class="w-full bg-surface-selected border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0">
				<option value="generic">Generic</option>
				<option value="rsa">RSA (공개키+개인키)</option>
				<option value="certificate">Certificate (인증서 번들)</option>
			</select>
		</div>
	</div>
</FormModal>

<!-- Order 생성 모달 -->
<FormModal
	bind:open={showCreateOrder}
	title="키 비동기 생성 (Order)"
	submitLabel="요청"
	submitting={creatingOrder}
	onSubmit={handleCreateOrder}
	onClose={() => { showCreateOrder = false; }}
>
	<div class="space-y-4">
		<div>
			<label class="block text-sm text-ink-2 mb-1" for="field-page-370">키 타입</label>
			<select id="field-page-370" bind:value={orderType} class="w-full bg-surface-selected border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0">
				<option value="key">대칭키 (AES)</option>
				<option value="asymmetric">비대칭키 (RSA)</option>
			</select>
		</div>
		<div>
			<label class="block text-sm text-ink-2 mb-1" for="field-page-377">알고리즘</label>
			<select id="field-page-377" bind:value={orderAlgorithm} class="w-full bg-surface-selected border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0">
				{#if orderType === 'key'}<option value="aes">AES</option>{/if}
				{#if orderType === 'asymmetric'}<option value="rsa">RSA</option>{/if}
			</select>
		</div>
		<div>
			<label class="block text-sm text-ink-2 mb-1" for="field-page-384">비트 길이</label>
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
	<PageHeader breadcrumb="KEY MANAGER / 비밀 관리" title="Key Manager">
		{#snippet actions()}
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={refreshing}
				onManualRefresh={forceRefresh}
			/>
			{#if activeTab === 'secrets'}
				<button onclick={() => showCreateSecret = true} class="bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium px-4 py-2 rounded-lg transition-colors">+ 비밀 생성</button>
			{:else if activeTab === 'containers'}
				<button onclick={() => showCreateContainer = true} class="bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium px-4 py-2 rounded-lg transition-colors">+ 컨테이너 생성</button>
			{:else if activeTab === 'orders'}
				<button onclick={() => showCreateOrder = true} class="bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium px-4 py-2 rounded-lg transition-colors">+ 키 생성 요청</button>
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
				{tab === 'secrets' ? '비밀' : tab === 'containers' ? '컨테이너' : tab === 'orders' ? 'Key Orders' : '쿼터'}
				{#if tab === 'secrets' && secrets.length > 0}<span class="ml-1 text-xs text-ink-3">({secrets.length})</span>{/if}
			</button>
		{/each}
	</div>

	<!-- 탭별 설명 -->
	{#if activeTab === 'secrets'}
		<div class="my-4 flex items-start gap-3 bg-surface-sunken/40 border border-line-2/60 rounded-lg px-4 py-3 text-sm text-ink-2">
			<span class="text-lg leading-none mt-0.5">🔑</span>
			<div>
				<span class="text-ink-1 font-medium">비밀(Secret)</span>은 비밀번호, API 키, 인증서, 암호화 키 등 민감한 값을 안전하게 저장하는 단위입니다.
				저장된 값은 암호화되어 보관되며, <span class="text-ink-0">"값 보기"</span> 버튼으로만 복호화할 수 있습니다.
				타입에 따라 <span class="text-ink-2">passphrase</span>(비밀번호), <span class="text-ink-2">certificate</span>(인증서 PEM),
				<span class="text-ink-2">symmetric</span>(대칭키), <span class="text-ink-2">public/private</span>(비대칭키쌍) 등을 구분해 저장합니다.
				🔒 표시된 항목은 시스템이 관리하는 secret으로 삭제할 수 없습니다.
			</div>
		</div>
	{:else if activeTab === 'containers'}
		<div class="my-4 flex items-start gap-3 bg-surface-sunken/40 border border-line-2/60 rounded-lg px-4 py-3 text-sm text-ink-2">
			<span class="text-lg leading-none mt-0.5">📦</span>
			<div>
				<span class="text-ink-1 font-medium">컨테이너(Container)</span>는 여러 Secret을 하나로 묶는 논리적 그룹입니다.
				<span class="text-ink-2">generic</span>은 임의의 secret 묶음,
				<span class="text-ink-2">rsa</span>는 공개키·개인키 쌍,
				<span class="text-ink-2">certificate</span>는 TLS 인증서·개인키·체인을 한 벌로 관리합니다.
				Octavia 로드밸런서의 TLS termination이나 서비스 간 인증서 공유에 활용됩니다.
			</div>
		</div>
	{:else if activeTab === 'orders'}
		<div class="my-4 flex items-start gap-3 bg-surface-sunken/40 border border-line-2/60 rounded-lg px-4 py-3 text-sm text-ink-2">
			<span class="text-lg leading-none mt-0.5">⚙️</span>
			<div>
				<span class="text-ink-1 font-medium">Key Orders</span>는 Barbican에 암호화 키 생성을 비동기로 요청하는 작업입니다.
				<span class="text-ink-2">대칭키(AES)</span> 또는 <span class="text-ink-2">비대칭키(RSA)</span>를 지정한 비트 길이로 생성해달라고 요청하면,
				Barbican이 백그라운드에서 안전하게 키를 생성하고 Secret으로 저장합니다.
				직접 키를 입력하지 않고 서버 측에서 생성하므로 키가 네트워크를 거치지 않아 더 안전합니다.
			</div>
		</div>
	{:else if activeTab === 'quota'}
		<div class="my-4 flex items-start gap-3 bg-surface-sunken/40 border border-line-2/60 rounded-lg px-4 py-3 text-sm text-ink-2">
			<span class="text-lg leading-none mt-0.5">📊</span>
			<div>
				<span class="text-ink-1 font-medium">쿼터(Quota)</span>는 이 프로젝트에서 생성할 수 있는 리소스 한도입니다.
				<span class="text-ink-0">∞</span>는 무제한을 의미합니다. 한도 변경은 관리자에게 문의하세요.
			</div>
		</div>
	{/if}

	{#if error}<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>{/if}

	{#if loading}
		<LoadingSkeleton variant="table" rows={4} />
	{:else if activeTab === 'secrets'}
		{#if secrets.length === 0}
			<div class="text-center py-16 text-ink-3">
				<div class="text-4xl mb-3">🔑</div>
				<p class="text-sm">저장된 비밀이 없습니다.</p>
				<button onclick={() => showCreateSecret = true} class="mt-4 text-action-warm hover:text-action-warm-hover text-sm">+ 비밀 생성</button>
			</div>
		{:else}
			<div class="mb-3">
				<SelectionToolbar
					label="비밀"
					ariaLabel="비밀 전체 선택"
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
							<th class="pb-3 pr-4 font-medium w-10">선택</th>
							<th class="pb-3 pr-4 font-medium">이름</th>
							<th class="pb-3 pr-4 font-medium">타입</th>
							<th class="pb-3 pr-4 font-medium">상태</th>
							<th class="pb-3 pr-4 font-medium">생성일</th>
							<th class="pb-3 pr-4 font-medium">만료</th>
							<th class="pb-3 font-medium">액션</th>
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
										title={s.system_managed ? '시스템 관리 Secret은 삭제할 수 없습니다.' : undefined}
										ariaLabel={`${s.name ?? s.id} 선택`}
										onclick={() => selection.toggle(s.id)}
									/>
								</td>
								<td class="py-3 pr-4 font-mono text-xs">
									<div class="flex items-center gap-2 max-md:max-w-[66vw]">
										<span class="max-md:truncate" title={s.name ?? s.id}>{s.name ?? s.id}</span>
										{#if s.system_managed}<span class="text-xs bg-surface-selected text-ink-2 px-2 py-0.5 rounded-full">시스템</span>{/if}
									</div>
									<div class="text-ink-3 text-xs mt-0.5">{s.id}</div>
								</td>
								<td class="py-3 pr-4 text-ink-2">{SECRET_TYPE_LABEL[s.secret_type] ?? s.secret_type}</td>
								<td class="py-3 pr-4"><span class="px-2 py-0.5 rounded text-xs {STATUS_CLASS[s.status ?? ''] ?? 'bg-surface-selected text-ink-2'}">{s.status ?? '-'}</span></td>
								<td class="py-3 pr-4 text-ink-2 text-xs">{s.created ? new Date(s.created).toLocaleDateString('ko') : '-'}</td>
								<td class="py-3 pr-4 text-ink-2 text-xs">{s.expires ? new Date(s.expires).toLocaleDateString('ko') : '없음'}</td>
								<td class="py-3">
									<div class="flex gap-2">
										<button onclick={() => handleShowPayload(s)} disabled={payloadLoading === s.id} class="text-xs text-action-warm hover:text-action-warm-hover disabled:opacity-50">{payloadLoading === s.id ? '로딩...' : payloadVisible[s.id] ? '숨기기' : '값 보기'}</button>
										{#if !s.system_managed}<button onclick={() => handleDeleteSecret(s)} class="text-xs text-red-400 hover:text-red-300">삭제</button>{/if}
									</div>
									{#if payloadVisible[s.id]}
										<div class="mt-2 flex items-center gap-2">
											<code class="text-xs bg-surface-base border border-line-2 rounded px-2 py-1 font-mono max-w-xs overflow-x-auto block">{payloadVisible[s.id].substring(0, 60)}{payloadVisible[s.id].length > 60 ? '...' : ''}</code>
											<button onclick={() => copyPayload(payloadVisible[s.id])} class="text-xs text-ink-2 hover:text-ink-1 shrink-0">복사</button>
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
			<div class="text-center py-16 text-ink-3">
				<div class="text-4xl mb-3">📦</div>
				<p class="text-sm">저장된 컨테이너가 없습니다.</p>
				<button onclick={() => showCreateContainer = true} class="mt-4 text-action-warm hover:text-action-warm-hover text-sm">+ 컨테이너 생성</button>
			</div>
		{:else}
			<div class="mb-3">
				<SelectionToolbar
					label="컨테이너"
					ariaLabel="컨테이너 전체 선택"
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
							<th class="pb-3 pr-4 font-medium w-10">선택</th>
							<th class="pb-3 pr-4 font-medium">이름</th>
							<th class="pb-3 pr-4 font-medium">타입</th>
							<th class="pb-3 pr-4 font-medium">상태</th>
							<th class="pb-3 pr-4 font-medium">Secrets</th>
							<th class="pb-3 font-medium">액션</th>
						</tr>
					</thead>
					<tbody class="divide-y divide-line">
						{#each containers as c (c.id)}
							<tr class="resource-selection-surface hover:bg-surface-sunken/30" data-selected={selection.has(c.id)}>
								<td class="py-3 pr-4"><SelectionCheckbox checked={selection.has(c.id)} disabled={selectionBusy} ariaLabel={`${c.name ?? c.id} 선택`} onclick={() => selection.toggle(c.id)} /></td>
								<td class="py-3 pr-4"><div class="max-md:max-w-[66vw] max-md:truncate" title={c.name ?? c.id}>{c.name ?? '-'}</div><div class="text-xs text-ink-3 font-mono max-md:max-w-[66vw] max-md:truncate">{c.id}</div></td>
								<td class="py-3 pr-4 text-ink-2">{c.type}</td>
								<td class="py-3 pr-4"><span class="px-2 py-0.5 rounded text-xs {STATUS_CLASS[c.status ?? ''] ?? 'bg-surface-selected text-ink-2'}">{c.status ?? '-'}</span></td>
								<td class="py-3 pr-4 text-ink-2">{c.secret_refs.length}개</td>
								<td class="py-3"><button onclick={() => handleDeleteContainer(c.id, c.name)} disabled={selectionBusy} class="text-xs text-red-400 hover:text-red-300">삭제</button></td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}

	{:else if activeTab === 'orders'}
		{#if orders.length === 0}
			<div class="text-center py-16 text-ink-3">
				<div class="text-4xl mb-3">⚙️</div>
				<p class="text-sm">진행 중인 Key Order가 없습니다.</p>
				<button onclick={() => showCreateOrder = true} class="mt-4 text-action-warm hover:text-action-warm-hover text-sm">+ 키 생성 요청</button>
			</div>
		{:else}
			<div class="overflow-x-auto">
				<table class="w-full text-sm">
					<thead>
						<tr class="text-left text-ink-2 border-b border-line-2">
							<th class="pb-3 pr-4 font-medium">ID</th>
							<th class="pb-3 pr-4 font-medium">타입</th>
							<th class="pb-3 pr-4 font-medium">상태</th>
							<th class="pb-3 pr-4 font-medium">생성일</th>
							<th class="pb-3 font-medium">결과</th>
						</tr>
					</thead>
					<tbody class="divide-y divide-line">
						{#each orders as o}
							<tr class="hover:bg-surface-sunken/30">
								<td class="py-3 pr-4 font-mono text-xs text-ink-2">{o.id}</td>
								<td class="py-3 pr-4 text-ink-2">{o.type}</td>
								<td class="py-3 pr-4">
									<span class="px-2 py-0.5 rounded text-xs {STATUS_CLASS[o.status ?? ''] ?? 'bg-surface-selected text-ink-2'}">{o.status ?? '-'}</span>
								</td>
								<td class="py-3 pr-4 text-ink-2 text-xs">{o.created ? new Date(o.created).toLocaleDateString('ko') : '-'}</td>
								<td class="py-3 text-xs text-ink-2">
									{#if o.secret_ref}<span class="text-green-400">Secret 생성됨</span>{:else if o.error_reason}<span class="text-red-400">{o.error_reason}</span>{:else}대기 중{/if}
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
				{#each ([['비밀', quota.secrets], ['Orders', quota.orders], ['컨테이너', quota.containers], ['Consumers', quota.consumers], ['CAs', quota.cas]] as [string, number][]) as [label, val]}
					<div class="bg-surface-sunken rounded-xl p-4 border border-line-2">
						<div class="text-xs text-ink-2 mb-1">{label}</div>
						<div class="text-2xl font-bold text-ink-0">{val === -1 ? '∞' : val}</div>
						<div class="text-xs text-ink-3 mt-1">{val === -1 ? '무제한' : `한도 ${val}개`}</div>
					</div>
				{/each}
			</div>
		{:else}
			<div class="text-center py-8 text-ink-3 text-sm">쿼터 정보를 불러올 수 없습니다.</div>
		{/if}
	{/if}
	<BulkSelectionOverlay
		count={activeTab === 'secrets' || activeTab === 'containers' ? selection.count : 0}
		ariaLabel={activeTab === 'secrets' ? '선택한 비밀 일괄 작업' : '선택한 컨테이너 일괄 작업'}
		busy={selectionBusy}
		actions={[{ key: 'delete', label: '삭제', tone: 'danger', onAction: runBulkDelete }]}
		onClear={() => selection.clear()}
	/>
</div>
{/if}
