<script lang="ts">
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import { t } from '$lib/i18n/ns/admin-compute';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { onDestroy, onMount, untrack } from 'svelte';
	import { get } from 'svelte/store';
	import { auth, authReady, projectSwitching, logoutInProgress } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { projectNames } from '$lib/stores/projectNames';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import FlavorCreateModal from '$lib/components/admin/flavors/FlavorCreateModal.svelte';
	import GpuDeviceCatalogModal from '$lib/components/admin/flavors/GpuDeviceCatalogModal.svelte';
	import FlavorManagePanel from '$lib/components/admin/flavors/FlavorManagePanel.svelte';
	import AdminFlavorsFilters from '$lib/components/admin/flavors/AdminFlavorsFilters.svelte';
	import AdminFlavorsTable from '$lib/components/admin/flavors/AdminFlavorsTable.svelte';
	import { buildGpuFilterOptions, matchesGpuFilter } from '$lib/components/admin/flavors/flavorGpuFilters';
	import type { Flavor, PagedResponse } from '$lib/types/flavor';
	import { toast } from '$lib/stores/toast';
	import FlavorAutomationPanel from '$lib/components/admin/flavors/FlavorAutomationPanel.svelte';
	import { isManagedFlavor } from '$lib/api/computePools';

	let flavors = $state<Flavor[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let deletingId = $state<string | null>(null);
	let pageSize = $state(20);
	let error = $state('');

	let nameFilter = $state('');
	let vcpuFilter = $state('');
	let ramFilter = $state('');
	let diskFilter = $state('');
	let gpuFilter = $state('');

	let showCreate = $state(false);
	let showGpuCatalog = $state(false);
	let selectedFlavor = $state<Flavor | null>(null);

	let mounted = $state(false), scopeEpoch = $state(0);
	let live = true, ownerKey = '', scopeGeneration = 0, requestGeneration = 0;
	function allowed() {
		void scopeEpoch;
		const state = get(auth);
		return live && mounted && !!state.token && state.isSystemAdmin === true && get(authReady) && !get(projectSwitching) && !get(logoutInProgress);
	}
	function capture() {
		const generation = scopeGeneration, state = get(auth);
		return { token: state.token ?? undefined, projectId: state.projectId ?? undefined, current: () => allowed() && generation === scopeGeneration };
	}
	function syncScope() {
		const state = get(auth);
		const next = JSON.stringify([state.sessionId, state.userId, state.identityDomainId, state.domainId, state.projectId, state.isSystemAdmin, !!state.token, get(authReady), get(projectSwitching), get(logoutInProgress)]);
		if (next === ownerKey) return;
		ownerKey = next; ++scopeGeneration; ++requestGeneration; ++scopeEpoch;
		flavors = []; error = ''; loading = true; refreshing = false; deletingId = null;
		selectedFlavor = null; showCreate = false; showGpuCatalog = false;
	}
	const subscriptions = [auth.subscribe(syncScope), authReady.subscribe(syncScope), projectSwitching.subscribe(syncScope), logoutInProgress.subscribe(syncScope)];
	onDestroy(() => { live = false; ++scopeGeneration; ++requestGeneration; subscriptions.forEach(stop => stop()); });
	$effect(() => {
		void scopeEpoch; void mounted;
		untrack(() => {
			if (!allowed()) return;
			void load();
			const owner = capture();
			void projectNames.load(owner.token, owner.projectId);
		});
	});

	let gpuOptions = $derived(buildGpuFilterOptions(flavors));

	let filteredFlavors = $derived(flavors.filter((f) => {
		if (nameFilter && ![f.name, f.display_name ?? '', f.id].some(name => name.toLowerCase().includes(nameFilter.trim().toLowerCase()))) return false;
		if (vcpuFilter && f.vcpus !== parseInt(vcpuFilter)) return false;
		if (ramFilter) { const r = parseInt(ramFilter); if (f.ram < r * 0.9 || f.ram > r * 1.1) return false; }
		if (diskFilter) { const d = parseInt(diskFilter); if (f.disk < d * 0.9 || f.disk > d * 1.1) return false; }
		return matchesGpuFilter(f, gpuFilter);
	}));

	$effect(() => {
		if (gpuFilter && !gpuOptions.some((option) => option.value === gpuFilter)) {
			gpuFilter = '';
		}
	});

	async function load(force = false) {
		if (!allowed()) return;
		const owner = capture(), request = ++requestGeneration;
		const current = () => owner.current() && request === requestGeneration;
		if (flavors.length === 0) loading = true;
		else refreshing = true;
		error = '';
		try {
			const res = await api.get<PagedResponse<Flavor>>(
				'/api/v1/admin/flavors?limit=999',
				owner.token,
				owner.projectId,
				{ refresh: force },
			);
			if (!current()) return;
			flavors = res.items;
		} catch (e) {
			if (!current()) return;
			error = e instanceof ApiError ? e.message : t('flavors.loadFailed');
			flavors = [];
		} finally {
			if (current()) { loading = false; refreshing = false; }
		}
	}

	async function deleteFlavor(id: string) {
		if (!allowed() || deletingId || flavors.some(flavor => flavor.id === id && isManagedFlavor(flavor))) return;
		const owner = capture();
		if (!await confirmDialog(t('flavors.delete.confirm')) || !owner.current()) return;
		deletingId = id;
		try {
			await api.delete(`/api/v1/admin/flavors/${id}`, owner.token, owner.projectId);
			if (!owner.current()) return;
			await load();
		} catch (e) {
			if (!owner.current()) return;
			toast.error(t('flavors.delete.failed', { error: e instanceof ApiError ? e.message : t('flavors.error') }));
		} finally {
			if (owner.current()) deletingId = null;
		}
	}

	const ar = createAutoRefresh(load, {
		storageKey: 'admin-flavors',
		invokeOnMount: false,
		defaultInterval: 60,
		intervalOptions: [30, 60],
	});

	onMount(() => {
		if (window.matchMedia('(max-width: 767px)').matches) pageSize = 10;
		mounted = true;
	});
</script>

<PageShell>
	<PageHeader breadcrumb={t('flavors.breadcrumb')} title={t('flavors.title')}>
		{#snippet actions()}
			<button
				disabled={!allowed()}
				onclick={() => (showCreate = true)}
				class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-action-on-warm text-sm font-medium rounded-lg transition-colors"
			>{t('flavors.create.toolbarAction')}</button>
			<button
				disabled={!allowed()}
				onclick={() => (showGpuCatalog = true)}
				class="px-4 py-2 bg-surface-sunken hover:bg-surface-selected text-ink-2 text-sm font-medium rounded-lg transition-colors"
			>{t('gpuCatalog.title')}</button>
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={loading || refreshing}
				onManualRefresh={() => {
					nameFilter = '';
					vcpuFilter = '';
					ramFilter = '';
					diskFilter = '';
					gpuFilter = '';
					load(true);
				}}
			/>
			<div class="flex items-center gap-1 text-xs text-ink-2 max-md:hidden">
				{t('flavors.display')}
				{#each [10, 20, 30] as n}
					<button
						onclick={() => { pageSize = n; }}
						class="px-2 py-0.5 rounded {pageSize === n
							? 'bg-action-warm text-action-on-warm'
							: 'bg-surface-sunken hover:bg-surface-selected text-ink-2'}"
					>{n}</button>
				{/each}
			</div>
		{/snippet}
	</PageHeader>

	<FlavorAutomationPanel onChanged={() => load(true)} />
	<AdminFlavorsFilters
		bind:nameFilter
		bind:vcpuFilter
		bind:ramFilter
		bind:diskFilter
		bind:gpuFilter
		gpuOptions={gpuOptions}
	/>

	{#if error}
		<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>
	{/if}

	{#if !allowed() || loading}
		<LoadingState variant="surface" />
	{:else}
		<AdminFlavorsTable
			flavors={filteredFlavors}
			totalUnfiltered={flavors.length}
			{pageSize}
			{refreshing}
			{deletingId}
			onManage={(f) => (selectedFlavor = f)}
			onDelete={deleteFlavor}
		/>
	{/if}
</PageShell>

<FlavorCreateModal bind:open={showCreate} onCreated={load} />

<GpuDeviceCatalogModal bind:open={showGpuCatalog} />

<FlavorManagePanel
	flavor={selectedFlavor}
	onClose={() => (selectedFlavor = null)}
	onChanged={load}
/>
