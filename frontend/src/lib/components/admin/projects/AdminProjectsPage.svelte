<script lang="ts">
	import { createTableView } from '$lib/utils/tableView.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import { t as tc } from '$lib/i18n/ns/common';
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { onDestroy, onMount } from 'svelte';
	import { auth, authReady, projectSwitching, logoutInProgress } from '$lib/stores/auth';
	import { derived, get } from 'svelte/store';
	import { api, ApiError } from '$lib/api/client';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import ResourceToolbar from '$lib/components/ui/ResourceToolbar.svelte';
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

	let { domainId }: { domainId: string; domainName: string } = $props();

	let projects = $state<Project[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let pageSize = $state(20);
	let markerStack = $state<string[]>([]);
	let nextMarker = $state<string | null>(null);
	let total = $state(0);
	let search = $state('');
	let nativeSearch = $state('');
	let filterStatus = $state<'all' | 'enabled' | 'disabled'>('all');

	let error = $state('');

	const hasFilters = $derived.by(() => Boolean(search || Object.keys(tableView.filters).length || tableView.sort));

	let showCreate = $state(false);
	let editProject = $state<Project | null>(null);
	let deleteProject = $state<Project | null>(null);
	let accessProject = $state<Project | null>(null);

	let copiedId = $state<string | null>(null);
	let loadGeneration = 0;
	let disposed = false;

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);
	const nextPrefetch = createIntentPrefetchScheduler();
	let ownerRevision = 0;
	let observedOwner: string | undefined;
	const unsubscribeOwner = derived([auth, authReady, projectSwitching, logoutInProgress], ([state, ready, switching, loggingOut]) => JSON.stringify([
		state.sessionId, state.userId, state.identityDomainId, state.domainId, state.projectId,
		state.isSystemAdmin, state.isDomainManager,
		!!state.token, ready, switching, loggingOut
	])).subscribe(owner => {
		if (owner === observedOwner) return;
		const changed = observedOwner !== undefined;
		observedOwner = owner; ownerRevision++;
		if (!changed) return;
		loadGeneration++; nextPrefetch.cancel();
		projects = []; markerStack = []; nextMarker = null; total = 0;
		search = ''; nativeSearch = ''; filterStatus = 'all'; tableView.reset();
		loading = false; refreshing = false; error = '';
		editProject = null; deleteProject = null; accessProject = null; showCreate = false;
	});
	function listPath(marker?: string): string {
		const params = new URLSearchParams({ limit: String(pageSize), domain_id: domainId });
		if (marker) params.set('marker', marker);
		if (nativeSearch.trim()) params.set('search', nativeSearch.trim());
		if (filterStatus !== 'all') params.set('enabled', String(filterStatus === 'enabled'));


		return `/api/v1/admin/projects?${params}`;
	}
	function prefetchNext() {
		if (!nextMarker) return;
		const path = listPath(nextMarker);
		const key = JSON.stringify([path, token ?? null, projectId ?? null]);
		nextPrefetch.intent(key, (signal) => api.prefetch(path, token, projectId, { signal }));
	}

	function resetList() {
		loadGeneration += 1;
		nextPrefetch.cancel();
		markerStack = [];
		nextMarker = null;
		void load();
	}

	function clearFilters() {
		const reload = Boolean(nativeSearch || filterStatus !== 'all');
		search = ''; nativeSearch = ''; filterStatus = 'all';
		tableView.reset();
		if (reload) resetList();
	}

	function copyId(id: string) {
		navigator.clipboard.writeText(id).then(() => {
			copiedId = id;
			setTimeout(() => { copiedId = null; }, 1500);
		});
	}

	async function load(marker?: string) {

		if (disposed || !domainId || !get(authReady) || get(projectSwitching) || get(logoutInProgress)) return;
		const generation = ++loadGeneration;
		const requestToken = $auth.token ?? undefined;
		const requestProjectId = $auth.projectId ?? undefined;
		const requestPageSize = pageSize;
		const requestPath = listPath(marker);
		const requestDomainId = domainId;
		const requestOwner = ownerRevision;
		const owns = () => !disposed && domainId === requestDomainId && generation === loadGeneration
			&& ownerRevision === requestOwner
			&& ($auth.projectId ?? undefined) === requestProjectId
			&& pageSize === requestPageSize
			&& listPath(marker) === requestPath;
		nextPrefetch.cancel();
		if (projects.length === 0) loading = true;
		else refreshing = true;
		error = '';
		try {
			const res = await api.get<PagedResponse<Project> & { total: number }>(requestPath, requestToken, requestProjectId);
			if (!owns()) return;
			if (res.items.some((item) => item.domain_id !== requestDomainId)) throw new Error('foreign domain');
			projects = res.items;
			nextMarker = res.next_marker;
			total = res.total;
			const path = nextMarker ? listPath(nextMarker) : null;
			const prefetchToken = token, prefetchProject = projectId;
			const key = path ? JSON.stringify([path, prefetchToken ?? null, prefetchProject ?? null]) : null;
			nextPrefetch.schedule(key, (signal) => path ? api.prefetch(path, prefetchToken, prefetchProject, { signal }) : undefined);
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

	onDestroy(() => { disposed = true; loadGeneration += 1; unsubscribeOwner(); nextPrefetch.cancel(); });
	const tableView = createTableView<Project>({ rows: () => projects, locale: () => intlLocale(), search: () => search, columns: () => [
		{ key: 'name', label: t('form.name'), value: row => row.name,
			filterMode: 'single', filterFreeValue: true,
			filterOptions: () => projects.map(row => ({ value: row.name, label: row.name, count: null })),
			filterSelection: () => nativeSearch ? [nativeSearch] : null,
			onFilterChange: values => { const next = values?.[0] ?? ''; if (next !== nativeSearch) { nativeSearch = next; resetList(); } } },
		{ key: 'description', label: t('form.description'), value: row => row.description },
		{ key: 'status', label: t('projectTable.status'), value: row => row.enabled, format: (_, row) => t(row.enabled ? 'state.enabled' : 'state.disabled'),
			filterMode: 'single',
			filterOptions: () => [{ value: 'enabled', label: t('state.enabled'), count: null }, { value: 'disabled', label: t('state.disabled'), count: null }],
			filterSelection: () => filterStatus === 'all' ? null : [filterStatus],
			onFilterChange: values => { const next = values?.[0] === 'enabled' ? 'enabled' : values?.[0] === 'disabled' ? 'disabled' : 'all'; if (next !== filterStatus) { filterStatus = next; resetList(); } } },
		{ key: 'id', label: t('projectDetail.projectId'), value: row => row.id },
		{ key: 'created', label: t('projectTable.createdAt'), value: row => row.created_at }
	] });
</script>

<PageShell>
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
				onManualRefresh={autoRefreshLoad}
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
		<RegexSearch id="admin-project-search" bind:value={search} />
		<Button variant="ghost" size="sm" disabled={!hasFilters} onclick={clearFilters}>{t('projectPage.reset')}</Button>
	</ResourceToolbar>
	<div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-2 mb-3">
		{#if !loading}<span aria-live="polite">{error ? t('projectPage.resultsUnavailable') : t('projectPage.results', { total: total.toLocaleString(intlLocale()) })}</span>{/if}
		<span>{tc('table.loadedScope')}</span>
	</div>
	{#if error}<Alert class="mb-3">{error}</Alert>{/if}

	{#if loading}
		<LoadingState variant="surface" label={t('projectPage.loading')} />
	{:else}
		<div class="bg-surface-base border border-line rounded-lg p-5">
			<AdminProjectTable
				projects={tableView.rows}
				view={tableView}
				{domainId}
				{copiedId}
				onCopyId={copyId}
				onEdit={(p) => (editProject = p)}
				onAccess={(p) => (accessProject = p)}
				onDelete={(p) => (deleteProject = p)}
			/>

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
</PageShell>

<AdminProjectCreateModal {domainId} bind:open={showCreate} onCreated={() => resetList()} />
<AdminProjectEditModal {domainId} project={editProject} onClose={() => (editProject = null)} onSuccess={() => resetList()} />
<AdminProjectDeleteModal {domainId} project={deleteProject} onClose={() => (deleteProject = null)} onSuccess={() => resetList()} />
<AdminProjectAccessModal {domainId} project={accessProject} onClose={() => (accessProject = null)} />
