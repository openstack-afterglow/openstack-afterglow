<script lang="ts">
	import { page } from '$app/stores';
	import { auth } from '$lib/stores/auth';
	import { toast } from '$lib/stores/toast';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import FormModal from '$lib/components/ui/FormModal.svelte';
	import { secretsApi } from '$lib/api/secrets';
	import { ApiError } from '$lib/api/client';
	import { untrack } from 'svelte';
	import { betaFeatures } from '$lib/stores/betaFeatures';
	import BetaFeatureGate from '$lib/components/ui/BetaFeatureGate.svelte';
	import TutorialStartButton from '$lib/tutorial/TutorialStartButton.svelte';

	interface ProjectQuota {
		project_id: string;
		project_quotas: {
			secrets?: number;
			orders?: number;
			containers?: number;
			consumers?: number;
			cas?: number;
		};
	}

	let quotas = $state<ProjectQuota[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let error = $state('');

	// 쿼터 설정 모달
	let showSetQuota = $state(false);
	let editProjectId = $state('');
	let editSecrets = $state<number | null>(null);
	let editOrders = $state<number | null>(null);
	let editContainers = $state<number | null>(null);
	let submitting = $state(false);
	const keyManagerEnabled = $derived(
		$betaFeatures.keyManager || ($page.data.mockup?.active === true && $page.data.mockup.profile === 'admin'),
	);

	function clearKeyManagerState() {
		quotas = [];
		error = '';
	}


	async function fetchQuotas() {
		if (!keyManagerEnabled) {
			clearKeyManagerState();
			loading = false;
			return;
		}
		try {
			quotas = (await secretsApi.listProjectQuotas($auth.token ?? undefined, $auth.projectId ?? undefined)) as ProjectQuota[];
			error = '';
		} catch (e) {
			error = e instanceof ApiError ? (e.message || `조회 실패 (${e.status})`) : '서버 오류';
		} finally {
			loading = false;
		}
	}

	async function forceRefresh() {
		refreshing = true;
		try { await fetchQuotas(); }
		finally { refreshing = false; }
	}

	const ar = createAutoRefresh(() => fetchQuotas(), {
		storageKey: 'admin-key-manager',
		defaultActive: false,
		defaultInterval: 60,
	});

	$effect(() => {
		const token = $auth.token;
		if (!keyManagerEnabled) {
			clearKeyManagerState();
			loading = false;
			return;
		}
		if (!token) return;
		untrack(() => fetchQuotas());
	});

	function openEdit(q: ProjectQuota) {
		if (!keyManagerEnabled) return;
		editProjectId = q.project_id;
		editSecrets = q.project_quotas.secrets ?? null;
		editOrders = q.project_quotas.orders ?? null;
		editContainers = q.project_quotas.containers ?? null;
		showSetQuota = true;
	}

	async function handleSetQuota() {
		if (!keyManagerEnabled) return;
		submitting = true;
		const body: Record<string, number> = {};
		if (editSecrets !== null) body.secrets = editSecrets;
		if (editOrders !== null) body.orders = editOrders;
		if (editContainers !== null) body.containers = editContainers;
		try {
			await secretsApi.setProjectQuota(editProjectId, body, $auth.token ?? undefined, $auth.projectId ?? undefined);
			toast.success('쿼터가 설정되었습니다');
			showSetQuota = false;
			await fetchQuotas();
		} catch (e) {
			toast.error('설정 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		} finally {
			submitting = false;
		}
	}

	async function handleResetQuota(projectId: string) {
		if (!keyManagerEnabled) return;
		try {
			await secretsApi.deleteProjectQuota(projectId, $auth.token ?? undefined, $auth.projectId ?? undefined);
			toast.success('기본값으로 초기화되었습니다');
			await fetchQuotas();
		} catch (e) {
			toast.error('초기화 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		}
	}

	type FieldEntry = [string, number | null, (v: number | null) => void];

	const quotaFields = $derived<FieldEntry[]>([
		['비밀 (secrets)', editSecrets, (v) => { editSecrets = v; }],
		['Orders', editOrders, (v) => { editOrders = v; }],
		['컨테이너', editContainers, (v) => { editContainers = v; }],
	]);
</script>

{#if !keyManagerEnabled}
	<div class="p-4 md:p-8">
		<BetaFeatureGate title="Key Manager는 베타 기능입니다" />
	</div>
{:else}
<FormModal
	bind:open={showSetQuota}
	title="프로젝트 쿼터 설정"
	submitLabel="저장"
	submitting={submitting}
	onSubmit={handleSetQuota}
	onClose={() => { showSetQuota = false; }}
>
	<div class="space-y-4">
		<div class="text-xs text-ink-2 font-mono">{editProjectId}</div>
		<p class="text-xs text-ink-3">-1 = 무제한, 0 = 비활성</p>
		{#each quotaFields as [label, val, setter]}
			<div>
				<label class="block text-sm text-ink-2 mb-1" for="field-page-155">{label}</label>
				<input id="field-page-155"
					type="number"
					value={val ?? ''}
					oninput={(e) => setter(e.currentTarget.value ? Number(e.currentTarget.value) : null)}
					class="w-full bg-surface-selected border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0"
					placeholder="-1 (무제한)"
				/>
			</div>
		{/each}
	</div>
</FormModal>

<div class="p-4 md:p-8">
	<div data-tour="admin-key-manager-header">
	<PageHeader breadcrumb="ADMIN / KEY MANAGER" title="Key Manager 쿼터">
		{#snippet actions()}
			<TutorialStartButton tour="admin-key-manager" compactOnMobile />
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={refreshing}
				onManualRefresh={forceRefresh}
			/>
		{/snippet}
	</PageHeader>
	</div>

	{#if error}<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>{/if}

	<div data-tour="admin-key-manager-table">
	{#if loading}
		<LoadingSkeleton variant="table" rows={4} />
	{:else if quotas.length === 0}
		<div class="text-center py-16 text-ink-3" data-tour="admin-key-manager-ready">
			<div class="text-4xl mb-3">📊</div>
			<p class="text-sm">설정된 프로젝트 쿼터가 없습니다. (모두 기본값 사용 중)</p>
		</div>
	{:else}
		<div class="overflow-x-auto" data-tour="admin-key-manager-ready">
			<table class="w-full text-sm">
				<thead>
					<tr class="text-left text-ink-2 border-b border-line-2">
						<th class="pb-3 pr-4 font-medium">프로젝트 ID</th>
						<th class="pb-3 pr-4 font-medium">Secrets</th>
						<th class="pb-3 pr-4 font-medium">Orders</th>
						<th class="pb-3 pr-4 font-medium">Containers</th>
						<th class="pb-3 font-medium">액션</th>
					</tr>
				</thead>
				<tbody class="divide-y divide-line">
					{#each quotas as q, index}
						<tr class="hover:bg-surface-sunken/30">
							<td class="py-3 pr-4 font-mono text-xs text-ink-2">{q.project_id}</td>
							<td class="py-3 pr-4 text-ink-2">{q.project_quotas.secrets ?? -1}</td>
							<td class="py-3 pr-4 text-ink-2">{q.project_quotas.orders ?? -1}</td>
							<td class="py-3 pr-4 text-ink-2">{q.project_quotas.containers ?? -1}</td>
							<td class="py-3 flex gap-3" data-tour={index === 0 ? 'admin-key-manager-actions' : undefined}>
								<button onclick={() => openEdit(q)} class="text-xs text-action-warm hover:text-action-warm-hover">설정</button>
								<button onclick={() => handleResetQuota(q.project_id)} class="text-xs text-ink-2 hover:text-ink-1">초기화</button>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
	</div>
</div>
{/if}
