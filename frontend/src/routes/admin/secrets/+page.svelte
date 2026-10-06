<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-system';
	import { t as tc } from '$lib/i18n/ns/common';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import Button from '$lib/components/ui/Button.svelte';
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
	let resettingProjects = $state<Record<string, boolean>>({});
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
			error = e instanceof ApiError ? (e.message || t('secrets.loadFailed', { status: e.status })) : t('secrets.serverError');
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
			toast.success(t('secrets.setSuccess'));
			showSetQuota = false;
			await fetchQuotas();
		} catch (e) {
			toast.error(t('secrets.setFailed', { message: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			submitting = false;
		}
	}

	async function handleResetQuota(projectId: string) {
		if (!keyManagerEnabled) return;
		resettingProjects[projectId] = true;
		try {
			await secretsApi.deleteProjectQuota(projectId, $auth.token ?? undefined, $auth.projectId ?? undefined);
			toast.success(t('secrets.resetSuccess'));
			await fetchQuotas();
		} catch (e) {
			toast.error(t('secrets.resetFailed', { message: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			delete resettingProjects[projectId];
		}
	}

	type FieldEntry = [string, number | null, (v: number | null) => void];

	const quotaFields = $derived<FieldEntry[]>([
		[t('secrets.secretField'), editSecrets, (v) => { editSecrets = v; }],
		[t('secrets.orderField'), editOrders, (v) => { editOrders = v; }],
		[t('secrets.containerField'), editContainers, (v) => { editContainers = v; }],
	]);
</script>

{#if !keyManagerEnabled}
	<div class="p-4 md:p-8">
		<BetaFeatureGate title={t('secrets.betaTitle')} />
	</div>
{:else}
<FormModal
	bind:open={showSetQuota}
	title={t('secrets.dialogTitle')}
	submitLabel={t('secrets.save')}
	submitting={submitting}
	onSubmit={handleSetQuota}
	onClose={() => { showSetQuota = false; }}
>
	{#snippet actions()}
		<Button variant="secondary" onclick={() => { showSetQuota = false; }} disabled={submitting}>{tc('actions.cancel')}</Button>
		<Button variant="primary" onclick={handleSetQuota} disabled={submitting}>
			{#if submitting}
				<span class="inline-flex items-center gap-2" role="status"><ActivityIndicator size="xs" tone="ink" /><span>{t('secrets.saving')}</span></span>
			{:else}{t('secrets.save')}{/if}
		</Button>
	{/snippet}
	<div class="space-y-4">
		<div class="text-xs text-ink-2 font-mono">{editProjectId}</div>
		<p class="text-xs text-ink-2">{t('secrets.quotaHelp')}</p>
		{#each quotaFields as [label, val, setter]}
			<div>
				<label class="block text-sm text-ink-2 mb-1" for="field-page-155">{label}</label>
				<input id="field-page-155"
					type="number"
					value={val ?? ''}
					oninput={(e) => setter(e.currentTarget.value ? Number(e.currentTarget.value) : null)}
					class="w-full bg-surface-selected border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0"
					placeholder={t('secrets.unlimitedPlaceholder')}
				/>
			</div>
		{/each}
	</div>
</FormModal>

<div class="p-4 md:p-8">
	<div data-tour="admin-key-manager-header">
	<PageHeader breadcrumb={t('secrets.breadcrumb')} title={t('secrets.title')}>
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
		<div class="text-center py-16 text-ink-2" data-tour="admin-key-manager-ready">
			<div class="text-4xl mb-3">📊</div>
			<p class="text-sm">{t('secrets.empty')}</p>
		</div>
	{:else}
		<div class="overflow-x-auto" data-tour="admin-key-manager-ready">
			<table class="w-full text-sm">
				<thead>
					<tr class="text-left text-ink-2 border-b border-line-2">
						<th class="pb-3 pr-4 font-medium">{t('secrets.projectId')}</th>
						<th class="pb-3 pr-4 font-medium">{t('secrets.secrets')}</th>
						<th class="pb-3 pr-4 font-medium">{t('secrets.orders')}</th>
						<th class="pb-3 pr-4 font-medium">{t('secrets.containers')}</th>
						<th class="pb-3 font-medium">{t('secrets.action')}</th>
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
								<button onclick={() => openEdit(q)} class="text-xs text-warm-text hover:text-warm-text-hover">{t('secrets.configure')}</button>
								<button onclick={() => handleResetQuota(q.project_id)} disabled={resettingProjects[q.project_id]} class="text-xs text-ink-2 hover:text-ink-1">
									{#if resettingProjects[q.project_id]}
										<span class="inline-flex items-center gap-2" role="status"><ActivityIndicator size="xs" tone="ink" /><span>{t('secrets.resetting')}</span></span>
									{:else}{t('secrets.reset')}{/if}
								</button>
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
