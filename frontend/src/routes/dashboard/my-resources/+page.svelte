<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { get } from 'svelte/store';
	import { t } from '$lib/i18n/ns/dashboard-home';
	import { t as tc } from '$lib/i18n/ns/common';
	import { auth, projectSwitching } from '$lib/stores/auth';
	import type { AuthState } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import { Alert, EmptyState, PageHeader, PageShell } from '$lib/components/ui';
	import MyResourcesSummary from '$lib/components/dashboard/my-resources/MyResourcesSummary.svelte';
	import ProjectUsageTable from '$lib/components/dashboard/my-resources/ProjectUsageTable.svelte';
	import ResourceInventoryCard from '$lib/components/dashboard/my-resources/ResourceInventoryCard.svelte';
	import { RESOURCE_CATEGORIES } from '$lib/types/userDashboard';
	import type { UserDashboardSummary } from '$lib/types/userDashboard';

	let data = $state<UserDashboardSummary | null>(null);
	let initialLoading = $state(false);
	let refreshing = $state(false);
	let error = $state<string | null>(null);
	let snapshotOwner = $state('');
	let active = false;
	let owner = '';
	let ownerEpoch = 0;
	let requestId = 0;
	let unsubscribeAuth: (() => void) | undefined;
	let unsubscribeSwitch: (() => void) | undefined;

	function ownerKey(state: AuthState, switching: boolean): string {
		return !switching && state.token && state.userId && state.projectId
			? JSON.stringify([state.token, state.userId, state.projectId]) : '';
	}
	const currentOwner = $derived(ownerKey($auth, $projectSwitching));
	// Render-time masking is independent of effect/request scheduling.
	const visibleData = $derived(currentOwner && snapshotOwner === currentOwner ? data : null);

	async function load(opts?: { refresh?: boolean }) {
		const state = get(auth);
		const capturedOwner = ownerKey(state, get(projectSwitching));
		if (!active || !capturedOwner || capturedOwner !== owner) return;
		const epoch = ownerEpoch;
		const request = ++requestId;
		const isCurrent = () => active && epoch === ownerEpoch && request === requestId
			&& capturedOwner === owner && capturedOwner === ownerKey(get(auth), get(projectSwitching));
		error = null;
		refreshing = Boolean(opts?.refresh);
		try {
			const response = await api.get<UserDashboardSummary>('/api/v1/user-dashboard/summary', state.token!, state.projectId!, opts);
			if (!isCurrent()) return;
			if (response.user_id !== state.userId || response.current_project_id !== state.projectId) {
				data = null;
				snapshotOwner = '';
				error = '';
				return;
			}
			data = response;
			snapshotOwner = capturedOwner;
		} catch (cause) {
			if (!isCurrent()) return;
			data = null;
			snapshotOwner = '';
			error = cause instanceof ApiError ? cause.message : '';
		} finally {
			if (isCurrent()) {
				initialLoading = false;
				refreshing = false;
			}
		}
	}

	function syncOwner() {
		const next = ownerKey(get(auth), get(projectSwitching));
		if (next === owner) return;
		owner = next;
		ownerEpoch++;
		data = null;
		snapshotOwner = '';
		error = null;
		refreshing = false;
		initialLoading = Boolean(next);
		if (next) void load();
	}

	onMount(() => {
		active = true;
		// Synchronous subscriptions catch A→B→A even within one render batch.
		unsubscribeAuth = auth.subscribe(syncOwner);
		unsubscribeSwitch = projectSwitching.subscribe(syncOwner);
	});
	onDestroy(() => {
		active = false;
		ownerEpoch++;
		requestId++;
		unsubscribeAuth?.();
		unsubscribeSwitch?.();
	});

	const ar = createAutoRefresh((force) => load(force ? { refresh: true } : undefined), {
		storageKey: 'dashboard-my-resources', invokeOnMount: false,
		defaultActive: true, defaultInterval: 30, intervalOptions: [10, 15, 30, 60],
	});
</script>

<PageShell>
	<div class="flex flex-wrap items-center gap-3 mb-4">
		<a href="/dashboard" class="text-xs text-ink-2 hover:text-ink-0">{t('myResources.back')}</a>
		<a href="/dashboard/account" class="text-xs text-warm-text hover:text-warm-text-hover">{t('myResources.account')}</a>
	</div>
	<PageHeader breadcrumb="" title={t('myResources.title')}>
		{#snippet actions()}
			<AutoRefreshControl bind:active={ar.active} bind:intervalSeconds={ar.intervalSeconds} intervalOptions={ar.intervalOptions} {refreshing} onManualRefresh={ar.refresh} />
		{/snippet}
	</PageHeader>

	{#if currentOwner && error !== null}
		<div data-resource-error><Alert tone="danger" class="mb-4">{error || t('myResources.loadFailed')}</Alert></div>
	{/if}
	{#if !currentOwner}
		<div data-resource-auth-gate><EmptyState headline={t('myResources.selectProject')} /></div>
	{:else if initialLoading && !visibleData}
		<div data-resource-loading role="status" aria-busy="true" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
			<span class="sr-only">{tc('state.loading')}</span>
			{#each [1, 2, 3] as _}<div class="motion-skeleton border border-line rounded-lg h-48" aria-hidden="true"></div>{/each}
		</div>
	{:else if visibleData}
		<div data-resource-snapshot>
			<MyResourcesSummary totals={visibleData.totals} />
			<ProjectUsageTable projects={visibleData.projects} />
			{#if visibleData.projects.length === 0}
				<EmptyState headline={t('myResources.noProjects')} description={t('myResources.invitationHelp')} />
			{/if}
			<div class="motion-stagger grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
				{#each RESOURCE_CATEGORIES as category (category)}
					<ResourceInventoryCard {category} projects={visibleData.projects} total={visibleData.totals.resources[category]} currentProjectId={visibleData.current_project_id} />
				{/each}
			</div>
		</div>
	{/if}
</PageShell>
