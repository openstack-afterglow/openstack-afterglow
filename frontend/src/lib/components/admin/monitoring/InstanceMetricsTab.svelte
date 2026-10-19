<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-ops';
	import { onDestroy, untrack } from 'svelte';
	import { get } from 'svelte/store';
	import { auth } from '$lib/stores/auth';
	import { api } from '$lib/api/client';
	import MetricsPanel from '$lib/components/instance/MetricsPanel.svelte';
	import { ActivityIndicator } from '$lib/components/ui';

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
	let authRevision = $state(0);
	function authKey(state: typeof $auth) {
		return JSON.stringify([state.sessionId, state.userId, state.identityDomainId, state.domainId, state.token, state.projectId, state.isSystemAdmin]);
	}
	const context = $derived(JSON.stringify([authKey($auth), token, projectId, authRevision]));
	const selected = $derived(listContext === context ? selectedInst : null);
	let previousAuth = '';
	const unsubscribe = auth.subscribe((state) => {
		const next = authKey(state);
		if (next === previousAuth) return;
		previousAuth = next;
		requestVersion++;
		authRevision++;
		instanceList = [];
		nextMarker = null;
		selectedInst = null;
		loadingInstances = false;
	});
	onDestroy(() => { requestVersion++; unsubscribe(); });

	const filtered = $derived(
		listContext !== context ? [] : search
			? instanceList.filter(i =>
				i.name.toLowerCase().includes(search.toLowerCase()) ||
				(i.project_id ?? '').includes(search)
			)
			: instanceList
	);

	async function loadInstances(reset = false) {
		if (loadingInstances && !reset) return;
		const owner = context;
		const version = ++requestVersion;
		const requestToken = token;
		const requestProject = projectId;
		const current = () => version === requestVersion && owner === JSON.stringify([authKey(get(auth)), token, projectId, authRevision]);
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
		untrack(() => { search = ''; void loadInstances(true); });
	});
</script>

<div class="flex flex-col md:flex-row gap-4 h-[calc(100vh-180px)] overflow-hidden">
	<!-- 왼쪽: 인스턴스 목록 -->
	<div data-tour="admin-monitoring-list" class="w-full md:w-72 flex-shrink-0 bg-surface-base border border-line rounded-xl overflow-hidden flex flex-col
		{selected ? 'hidden md:flex' : 'flex'}">
		<div class="p-3 border-b border-line">
			<input
				type="text"
				placeholder={t('monitoring.instances.search')}
				aria-label={t('monitoring.instances.search')}
				bind:value={search}
				class="w-full bg-surface-sunken rounded-lg px-3 py-1.5 text-sm text-ink-2 placeholder-ink-3 outline-none focus:ring-1 focus:ring-line-2"
			/>
		</div>

		<div class="overflow-y-auto flex-1">
			{#if loadingInstances && instanceList.length === 0}
				<div class="p-4 flex justify-center"><ActivityIndicator label={t('monitoring.instances.loadingList')} /></div>
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

			{#if nextMarker && !search}
				<button
					onclick={() => loadInstances()}
					disabled={loadingInstances}
					class="w-full py-2.5 text-xs text-warm-text hover:text-warm-text-hover disabled:text-ink-3 transition-colors"
				>
					{#if loadingInstances}<ActivityIndicator size="xs" tone="ink" class="mr-1.5" />{/if}{loadingInstances ? t('monitoring.loading') : t('monitoring.instances.loadMore')}
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
