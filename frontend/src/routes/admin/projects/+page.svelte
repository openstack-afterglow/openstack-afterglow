<script lang="ts">
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import { onDestroy, onMount } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import ResourceToolbar from '$lib/components/ui/ResourceToolbar.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import { createIntentPrefetchScheduler } from '$lib/utils/intentPrefetch';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import AdminProjectTable from '$lib/components/admin/projects/AdminProjectTable.svelte';
	import Pagination from '$lib/components/ui/Pagination.svelte';
	import AdminProjectCreateModal from '$lib/components/admin/projects/AdminProjectCreateModal.svelte';
	import AdminProjectEditModal from '$lib/components/admin/projects/AdminProjectEditModal.svelte';
	import AdminProjectDeleteModal from '$lib/components/admin/projects/AdminProjectDeleteModal.svelte';
	import AdminProjectAccessModal from '$lib/components/admin/projects/AdminProjectAccessModal.svelte';

	import type { Project } from '$lib/types/project';
	import type { PagedResponse } from '$lib/types/common';
	import { t } from '$lib/i18n/ns/admin-identity';
	import { intlLocale } from '$lib/i18n/runtime.svelte';

	let projects = $state<Project[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let pageSize = $state(20);
	let markerStack = $state<string[]>([]);
	let nextMarker = $state<string | null>(null);
	let total = $state(0);
	let domainIds = $state<string[]>([]);
	let search = $state('');
	let filterStatus = $state('all');
	let filterDomain = $state('');
	let error = $state('');
	let searchTimer: ReturnType<typeof setTimeout> | undefined;
	const hasFilters = $derived(Boolean(search.trim() || filterStatus !== 'all' || filterDomain));

	let showCreate = $state(false);
	let editProject = $state<Project | null>(null);
	let deleteProject = $state<Project | null>(null);
	let accessProject = $state<Project | null>(null);

	let copiedId = $state<string | null>(null);
	let loadGeneration = 0;

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);
	const nextPrefetch = createIntentPrefetchScheduler();
	function listPath(marker?: string): string {
		const params = new URLSearchParams({ limit: String(pageSize) });
		if (marker) params.set('marker', marker);
		if (search.trim()) params.set('search', search.trim());
		if (filterStatus !== 'all') params.set('enabled', String(filterStatus === 'enabled'));
		if (filterDomain) params.set('domain_id', filterDomain);
		return `/api/v1/admin/projects?${params}`;
	}
	function prefetchNext() {
		if (!nextMarker) return;
		const path = listPath(nextMarker);
		const key = JSON.stringify([path, token ?? null, projectId ?? null]);
		nextPrefetch.intent(key, (signal) => api.prefetch(path, token, projectId, { signal }));
	}

	function resetList(delayed = false) {
		clearTimeout(searchTimer);
		loadGeneration += 1;
		nextPrefetch.cancel();
		markerStack = [];
		nextMarker = null;
		if (delayed) {
			refreshing = true;
			searchTimer = setTimeout(() => load(), 250);
		} else {
			load();
		}
	}

	function clearFilters() {
		search = '';
		filterStatus = 'all';
		filterDomain = '';
		resetList();
	}

	function copyId(id: string) {
		navigator.clipboard.writeText(id).then(() => {
			copiedId = id;
			setTimeout(() => { copiedId = null; }, 1500);
		});
	}

	async function load(marker?: string) {
		clearTimeout(searchTimer);
		const generation = ++loadGeneration;
		const requestToken = $auth.token ?? undefined;
		const requestProjectId = $auth.projectId ?? undefined;
		const requestPageSize = pageSize;
		const requestPath = listPath(marker);
		const owns = () => generation === loadGeneration
			&& ($auth.token ?? undefined) === requestToken
			&& ($auth.projectId ?? undefined) === requestProjectId
			&& pageSize === requestPageSize
			&& listPath(marker) === requestPath;
		nextPrefetch.cancel();
		if (projects.length === 0) loading = true;
		else refreshing = true;
		error = '';
		try {
			const res = await api.get<PagedResponse<Project> & { total: number; domain_ids: string[] }>(requestPath, requestToken, requestProjectId);
			if (!owns()) return;
			projects = res.items;
			nextMarker = res.next_marker;
			total = res.total;
			domainIds = res.domain_ids;
			const path = nextMarker ? listPath(nextMarker) : null;
			const key = path ? JSON.stringify([path, requestToken ?? null, requestProjectId ?? null]) : null;
			nextPrefetch.schedule(key, (signal) => path ? api.prefetch(path, requestToken, requestProjectId, { signal }) : undefined);
		} catch (e) {
			if (owns()) {
				projects = [];
				total = 0;
				nextMarker = null;
				error = e instanceof ApiError ? e.message : t('projectPage.loadFailed');
			}
		} finally {
			if (owns()) {
				loading = false;
				refreshing = false;
			}
		}
	}

	function autoRefreshLoad() { load(markerStack[markerStack.length - 1]); }

	const ar = createAutoRefresh(autoRefreshLoad, {
		storageKey: 'admin-projects',
		invokeOnMount: false,
		defaultActive: true,
		defaultInterval: 60,
		intervalOptions: [30, 60],
	});

	onMount(() => {
		if (window.matchMedia('(max-width: 767px)').matches) pageSize = 10;
		load();
	});

	onDestroy(() => { loadGeneration += 1; clearTimeout(searchTimer); nextPrefetch.cancel(); });
</script>

<div class="p-4 md:p-6 max-w-7xl mx-auto">
	<PageHeader breadcrumb={t('projectPage.breadcrumb')} title={t('projectPage.title')}>
		{#snippet actions()}
			<button
				onclick={() => { showCreate = true; }}
				class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-action-on-warm text-sm font-medium rounded-lg"
			>{t('projectPage.create')}</button>
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={loading || refreshing}
				onManualRefresh={() => resetList()}
			/>
			<div class="flex items-center gap-1 text-xs text-ink-2 max-md:hidden">
				{t('projectPage.show')}
				{#each [10, 20, 30] as n}
					<button
						onclick={() => { pageSize = n; resetList(); }}
						class="px-2 py-0.5 rounded {pageSize === n ? 'bg-action-warm text-ink-0' : 'bg-surface-sunken hover:bg-surface-selected text-ink-2'}"
					>{n.toLocaleString(intlLocale())}</button>
				{/each}
			</div>
		{/snippet}
	</PageHeader>

	<ResourceToolbar label={t('projectPage.filters')} class="mb-3">
		<div class="flex-1 basis-full sm:basis-64 min-w-0">
			<TextInput type="search" value={search} ariaLabel={t('projectPage.search')} placeholder={t('projectPage.searchPlaceholder')}
				oninput={(event) => { search = (event.target as HTMLInputElement).value; resetList(true); }} />
		</div>
		<div class="w-full sm:w-36">
			<SelectInput value={filterStatus} ariaLabel={t('projectPage.status')}
				onchange={(event) => { filterStatus = (event.target as HTMLSelectElement).value; resetList(); }}>
				<option value="all">{t('projectPage.allStatuses')}</option>
				<option value="enabled">{t('state.enabled')}</option>
				<option value="disabled">{t('state.disabled')}</option>
			</SelectInput>
		</div>
		<div class="w-full sm:w-44">
			<SelectInput value={filterDomain} ariaLabel={t('projectPage.domain')}
				onchange={(event) => { filterDomain = (event.target as HTMLSelectElement).value; resetList(); }}>
				<option value="">{t('projectPage.allDomains')}</option>
				{#each domainIds as id}<option value={id}>{id}</option>{/each}
			</SelectInput>
		</div>
		<Button variant="ghost" size="sm" disabled={!hasFilters} onclick={clearFilters}>{t('projectPage.reset')}</Button>
	</ResourceToolbar>
	<div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-2 mb-3">
		{#if loading}<ActivityIndicator size="xs" />{/if}
		<span aria-live="polite">{loading ? t('projectPage.loading') : error ? t('projectPage.resultsUnavailable') : t('projectPage.results', { total: total.toLocaleString(intlLocale()) })}</span>
		<span>{t('projectPage.sortNotice')}</span>
	</div>
	{#if error}<Alert class="mb-3">{error}</Alert>{/if}

	{#if loading}
		<LoadingSkeleton variant="table" rows={5} />
	{:else if !error}
		<div class="bg-surface-base border border-line rounded-lg p-5">
			{#if projects.length === 0}
				<p class="text-center text-ink-2 text-sm py-8">{hasFilters ? t('projectPage.noMatches') : t('projectPage.empty')}</p>
			{:else}
			<AdminProjectTable
				{projects}
				{copiedId}
				onCopyId={copyId}
				onEdit={(p) => (editProject = p)}
				onAccess={(p) => (accessProject = p)}
				onDelete={(p) => (deleteProject = p)}
			/>
			{/if}
		</div>
		<Pagination
			page={markerStack.length + 1}
			hasPrev={markerStack.length > 0}
			hasNext={!!nextMarker}
			onPrev={() => { const prev = markerStack.slice(0, -1); markerStack = prev; load(prev[prev.length - 1]); }}
			onNext={() => { if (nextMarker) { markerStack = [...markerStack, nextMarker]; load(nextMarker); } }}
			onintent={prefetchNext}
		/>
	{/if}
</div>

<AdminProjectCreateModal bind:open={showCreate} onCreated={() => resetList()} />
<AdminProjectEditModal   project={editProject}   onClose={() => (editProject = null)}   onSuccess={() => resetList()} />
<AdminProjectDeleteModal project={deleteProject} onClose={() => (deleteProject = null)} onSuccess={() => resetList()} />
<AdminProjectAccessModal project={accessProject} onClose={() => (accessProject = null)} />
