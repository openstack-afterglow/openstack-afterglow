<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-ops';
	import { onDestroy, untrack } from 'svelte';
	import { get } from 'svelte/store';
	import { auth } from '$lib/stores/auth';
	import { api } from '$lib/api/client';
	import MetricsPanel from '$lib/components/instance/MetricsPanel.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import { createTableView } from '$lib/utils/tableView.svelte';
	import { createPrivateViewScope } from '$lib/utils/privateViewScope';
	import { t as common } from '$lib/i18n/ns/common';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';

	export interface AdminInstance {
		id: string;
		name: string;
		status: string;
		project_id: string | null;
		flavor: string;
		host: string | null;
	}

	interface PagedResponse<T> {
		items: T[];
		next_marker: string | null;
		count: number;
	}

	let {
		token,
		projectId,
		onReload,
		loadingInstances = $bindable(false),
	}: {
		token: string | undefined;
		projectId: string | undefined;
		onReload?: (fn: () => void) => void;
		loadingInstances?: boolean;
	} = $props();

	let instanceList = $state<AdminInstance[]>([]);
	let nextMarker = $state<string | null>(null);
	let search = $state('');
	let selectedInst = $state<AdminInstance | null>(null);
	let listContext = $state('');
	let requestVersion = 0;
	const viewScope = createPrivateViewScope();
	const context = $derived(JSON.stringify([$viewScope, projectId]));
	const selected = $derived(listContext === context ? selectedInst : null);
	onDestroy(() => { requestVersion++; });
	const instanceView = createTableView({
		rows: () => listContext === context ? instanceList : [],
		search: () => search,
		searchable: row => [row.name, row.id, row.project_id ?? ''],
		columns: () => [
			{ key: 'name', label: common('table.name'), value: row => row.name },
			{ key: 'id', label: common('table.key'), value: row => row.id },
			{ key: 'status', label: common('table.status'), value: row => row.status },
			{ key: 'project', label: common('table.project'), value: row => row.project_id },
			{ key: 'flavor', label: common('table.flavor'), value: row => row.flavor },
			{ key: 'host', label: common('table.host'), value: row => row.host },
		],
	});
	const filtered = $derived(instanceView.rows);

	async function loadInstances(reset = false) {
		if (loadingInstances && !reset) return;
		const owner = context;
		const version = ++requestVersion;
		const requestToken = token;
		const requestProject = projectId;
		const current = () => version === requestVersion && owner === context;
		if (reset) { instanceList = []; nextMarker = null; selectedInst = null; listContext = ''; }
		if (!requestToken || !get(auth).isSystemAdmin) { loadingInstances = false; return; }
		loadingInstances = true;
		try {
			const marker = nextMarker && !reset ? `&marker=${encodeURIComponent(nextMarker)}` : '';
			const resp = await api.get<PagedResponse<AdminInstance>>(
				`/api/v1/admin/all-instances?limit=50${marker}`,
				requestToken,
				requestProject,
			);
			if (!current()) return;
			instanceList = reset ? resp.items : [...instanceList, ...resp.items];
			nextMarker = resp.next_marker;
			listContext = owner;
		} catch {
			// A failed page must not publish rows from a different context.
		} finally {
			if (current()) loadingInstances = false;
		}
	}

	$effect(() => {
		onReload?.(() => loadInstances(true));
	});

	$effect(() => {
		void context;
		untrack(() => { search = ''; instanceView.reset(); void loadInstances(true); });
	});
</script>

<div class="flex flex-col md:flex-row gap-4 h-[calc(100vh-180px)] overflow-hidden">
	<!-- 왼쪽: 인스턴스 목록 -->
	<div data-tour="admin-monitoring-list" class="w-full md:w-72 flex-shrink-0 bg-surface-base border border-line rounded-xl overflow-hidden flex flex-col
		{selected ? 'hidden md:flex' : 'flex'}">
		<div class="p-3 border-b border-line">
			<RegexSearch id="admin-metrics-instance-search" bind:value={search} label={t('monitoring.instances.search')} />
			<TableViewControls view={instanceView} class="" />
			<p class="mt-2 text-xs text-ink-2">{common('table.loadedScope')}</p>
		</div>

		<div class="overflow-y-auto flex-1">
			{#if loadingInstances && instanceList.length === 0}
				<LoadingState variant="surface" label={t('monitoring.instances.loadingList')} />
			{:else if filtered.length === 0}
				<div class="p-4 text-ink-2 text-sm text-center" data-tour="admin-monitoring-list-ready">
					{search ? t('monitoring.instances.noResults') : t('monitoring.instances.empty')}
				</div>
			{:else}
				<div data-tour="admin-monitoring-list-ready"></div>
				{#each filtered as inst, index (inst.id)}
					<button
						onclick={() => (selectedInst = inst)}
						class="w-full text-left px-3 py-2.5 border-b border-line hover:bg-surface-sunken transition-colors
							{selected?.id === inst.id ? 'bg-surface-sunken border-l-2 border-l-blue-500 pl-2.5' : ''}"
						data-tour={index === 0 ? 'admin-monitoring-row' : undefined}
						aria-pressed={selected?.id === inst.id}
					>
						<div class="flex items-center gap-2">
							<div class="w-1.5 h-1.5 rounded-full flex-shrink-0
								{inst.status === 'ACTIVE' ? 'bg-green-400' : inst.status === 'ERROR' ? 'bg-red-400' : 'bg-surface-selected'}"></div>
							<span class="text-sm text-ink-1 truncate">{inst.name}</span>
							{#if inst.flavor.toLowerCase().startsWith('gpu.')}
								<span class="text-xs text-purple-400 bg-purple-900/30 px-1 rounded flex-shrink-0">GPU</span>
							{/if}
						</div>
						<div class="text-xs text-ink-2 pl-3.5 mt-0.5 truncate font-mono">
							{inst.project_id?.slice(0, 12) ?? '-'}
						</div>
					</button>
				{/each}
			{/if}

			{#if nextMarker}
				<button
					onclick={() => loadInstances()}
					disabled={loadingInstances}
					class="w-full py-2.5 text-xs text-warm-text hover:text-warm-text-hover disabled:text-ink-3 transition-colors"
				>
					{#if loadingInstances}<LoadingState variant="control" label="" aria-hidden="true" class="mr-1.5" />{/if}{loadingInstances ? t('monitoring.loading') : t('monitoring.instances.loadMore')}
				</button>
			{/if}
		</div>

		<div class="px-3 py-2 border-t border-line text-xs text-ink-2">
			{t('monitoring.instances.counts', { shown: filtered.length, loaded: instanceList.length })}
		</div>
	</div>

	<!-- 오른쪽: MetricsPanel -->
	<div class="flex-1 min-w-0 overflow-y-auto {selected ? 'block' : 'hidden md:block'}">
		{#if selected}
			<div class="motion-fade bg-surface-base border border-line rounded-xl p-5">
				<button
					onclick={() => (selectedInst = null)}
					class="md:hidden mb-3 text-sm text-warm-text hover:text-warm-text-hover flex items-center gap-1"
					data-tour="admin-monitoring-back"
				>
					{t('monitoring.instances.back')}
				</button>
				<div class="flex min-w-0 flex-wrap items-center gap-3 mb-5 break-all">
					<span class="text-ink-0 font-semibold">{selected.name}</span>
					<span class="text-xs text-ink-2 font-mono">{selected.id.slice(0, 8)}…</span>
					<span class="text-xs px-2 py-0.5 rounded
						{selected.status === 'ACTIVE' ? 'bg-green-900/30 text-green-400' :
						 selected.status === 'ERROR' ? 'bg-red-900/30 text-red-400' :
						 'bg-surface-sunken text-ink-2'}"
					>{selected.status}</span>
					{#if selected.flavor}
						<span class="text-xs text-ink-2">{selected.flavor}</span>
					{/if}
				</div>
				<div data-tour="admin-monitoring-metrics">
					{#if selected.project_id}
						{#key JSON.stringify([context, selected.id, selected.project_id])}
							<MetricsPanel
								instanceId={selected.id}
								projectId={selected.project_id}
								isGpu={selected.flavor.toLowerCase().startsWith('gpu.')}
								adminMode
							/>
						{/key}
					{:else}
						<p class="text-sm text-ink-2" role="status">{t('monitoring.instances.unknownProject')}</p>
					{/if}
				</div>
			</div>
		{:else}
			<div class="flex items-center justify-center h-64 bg-surface-base border border-line rounded-xl">
				<div class="text-center">
					<div class="text-ink-2 text-sm mb-1">{t('monitoring.instances.select')}</div>
					<div class="text-ink-2 text-xs">{t('monitoring.instances.selectHelp')}</div>
				</div>
			</div>
		{/if}
	</div>
</div>
