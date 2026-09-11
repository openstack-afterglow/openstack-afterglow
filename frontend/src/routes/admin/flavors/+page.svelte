<script lang="ts">
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { onMount } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
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

	let flavors = $state<Flavor[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
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

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	let gpuOptions = $derived(buildGpuFilterOptions(flavors));

	let filteredFlavors = $derived(flavors.filter((f) => {
		if (nameFilter && !f.name.toLowerCase().includes(nameFilter.toLowerCase())) return false;
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

	async function load() {
		if (flavors.length === 0) loading = true;
		else refreshing = true;
		error = '';
		try {
			const res = await api.get<PagedResponse<Flavor>>(
				'/api/v1/admin/flavors?limit=999',
				token,
				projectId,
			);
			flavors = res.items;
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Flavor 목록 조회 실패';
			flavors = [];
		} finally {
			loading = false;
			refreshing = false;
		}
	}

	async function deleteFlavor(id: string) {
		if (!await confirmDialog('이 Flavor를 삭제하시겠습니까?')) return;
		try {
			await api.delete(`/api/v1/admin/flavors/${id}`, token, projectId);
			await load();
		} catch (e) {
			toast.error('Flavor 삭제 실패: ' + (e instanceof ApiError ? e.message : '오류'));
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
		load();
		projectNames.load(token, projectId);
	});
</script>

<div class="p-4 md:p-6 max-w-7xl mx-auto">
	<PageHeader breadcrumb="COMPUTE / FLAVORS" title="Flavor">
		{#snippet actions()}
			<button
				onclick={() => (showCreate = true)}
				class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-action-on-warm text-sm font-medium rounded-lg transition-colors"
			>+ 생성</button>
			<button
				onclick={() => (showGpuCatalog = true)}
				class="px-4 py-2 bg-surface-sunken hover:bg-surface-selected text-ink-2 text-sm font-medium rounded-lg transition-colors"
			>GPU 장치 카탈로그</button>
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
					load();
				}}
			/>
			<div class="flex items-center gap-1 text-xs text-ink-3 max-md:hidden">
				표시:
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

	{#if loading}
		<LoadingSkeleton variant="table" rows={5} />
	{:else}
		<AdminFlavorsTable
			flavors={filteredFlavors}
			totalUnfiltered={flavors.length}
			{pageSize}
			{refreshing}
			onManage={(f) => (selectedFlavor = f)}
			onDelete={deleteFlavor}
		/>
	{/if}
</div>

<FlavorCreateModal bind:open={showCreate} onCreated={load} />

<GpuDeviceCatalogModal bind:open={showGpuCatalog} />

<FlavorManagePanel
	flavor={selectedFlavor}
	onClose={() => (selectedFlavor = null)}
	onChanged={load}
/>
