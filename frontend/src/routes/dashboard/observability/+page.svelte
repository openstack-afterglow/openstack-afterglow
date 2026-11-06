<script lang="ts">
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import { createTableView } from '$lib/utils/tableView.svelte';
	import { t as common } from '$lib/i18n/ns/common';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { onDestroy, untrack } from 'svelte';
	import { t } from '$lib/i18n/ns/dashboard-home';
	import { auth, authReady, projectSwitching } from '$lib/stores/auth';
	import { api } from '$lib/api/client';
	import type { Instance } from '$lib/types/compute';
	import { createPrivateViewScope } from '$lib/utils/privateViewScope';
	import { beginExperienceAction, beginExperienceLoad, experienceApplied, experienceDiscarded, experienceState } from '$lib/utils/experience';
	import MetricsPanel from '$lib/components/instance/MetricsPanel.svelte';
	import { Alert, Button, EmptyState, PageHeader, PageShell, StatusChip } from '$lib/components/ui';

	let instances = $state<Instance[]>([]);
	let selectedId = $state('');
	let search = $state('');
	let loading = $state(false);
	let failed = $state(false);
	const viewScope = createPrivateViewScope();
	let inventoryRevision = $state(-1);
	let generation = 0;
	onDestroy(() => { generation += 1; });
	const currentInstances = $derived($authReady && !$projectSwitching && inventoryRevision === $viewScope ? instances : []);
	const instanceView = createTableView({
		rows: () => currentInstances,
		search: () => search,
		searchable: row => [row.name, row.id],
		columns: () => [
			{ key: 'name', label: common('table.name'), value: row => row.name },
			{ key: 'id', label: common('table.key'), value: row => row.id },
			{ key: 'status', label: common('table.status'), value: row => row.status },
			{ key: 'flavor', label: common('table.flavor'), value: row => row.flavor_display_name ?? row.flavor_name },
		],
	});
	const filtered = $derived(instanceView.rows);
	const selected = $derived(filtered.find((instance) => instance.id === selectedId));
	$effect(() => {
		const visible = filtered;
		untrack(() => {
			if (!visible.some((instance) => instance.id === selectedId)) selectedId = '';
		});
	});

	async function loadInstances(refresh = false) {
		const request = { token: $auth.token ?? undefined, projectId: $auth.projectId ?? undefined, revision: $viewScope, generation: ++generation };
		const current = () => request.generation === generation && request.revision === $viewScope
			&& $authReady && !$projectSwitching && request.projectId === ($auth.projectId ?? undefined);
		if (!request.token || !request.projectId || !$authReady || $projectSwitching) { loading = false; return; }
		const experience = refresh ? beginExperienceAction('monitoring', 'refresh', 'resource.list') : beginExperienceLoad('monitoring', 'resource.list');
		loading = true;
		failed = false;
		if (currentInstances.length === 0) experienceState(experience, 'loading');
		try {
			const rows = await api.withExperience(experience).get<Instance[]>('/api/v1/instances', request.token, request.projectId, { refresh });
			if (!current()) { experienceDiscarded(experience, 'stale'); return; }
			// A user-surface selection never broadens an administrator's current workspace.
			instances = rows.filter((instance) => instance.project_id === request.projectId);
			inventoryRevision = request.revision;
			if (!instances.some((instance) => instance.id === selectedId)) selectedId = '';
		} catch {
			if (!current()) { experienceDiscarded(experience, 'stale'); return; }
			failed = true;
			instances = [];
			selectedId = '';
		} finally {
			if (request.generation === generation) loading = false;
			if (current()) {
				experienceState(experience, failed ? 'error' : filtered.length === 0 ? 'empty' : 'ready');
				void experienceApplied(experience, {}, current);
			}
		}
	}

	function selectInstance(id: string) {
		const experience = beginExperienceAction('monitoring', 'select', 'resource.detail');
		selectedId = id;
		experienceState(experience, selected ? 'ready' : 'empty');
		void experienceApplied(experience);
	}

	$effect(() => {
		const revision = $viewScope;
		const ready = $authReady && !$projectSwitching;
		untrack(() => {
			if (!ready) { generation += 1; loading = false; return; }
			if (inventoryRevision === revision) return;
			instances = [];
			selectedId = '';
			search = '';
			failed = false;
			void loadInstances();
		});
	});
</script>

<PageShell class="space-y-4">
	<PageHeader breadcrumb={t('observability.breadcrumb')} title={t('observability.title')} subtitle={t('observability.description')}>
		{#snippet actions()}
			<Button variant="secondary" size="sm" disabled={loading || !$authReady || $projectSwitching || !$auth.token || !$auth.projectId} onclick={() => loadInstances(true)}>{t('observability.refresh')}</Button>
		{/snippet}
	</PageHeader>

	{#if !$auth.projectId}
		<EmptyState headline={t('observability.selectProject')} />
	{:else}
		<div class="grid min-w-0 grid-cols-1 items-start gap-4 lg:grid-cols-[18rem_minmax(0,1fr)]">
			<section class="min-w-0 overflow-hidden rounded-lg border border-line bg-surface-base" aria-label={t('observability.instances')}>
				<div class="space-y-3 border-b border-line p-4">
					<h2 class="text-sm font-semibold text-ink-0">{t('observability.instances')}</h2>
					<RegexSearch id="observability-instance-search" bind:value={search} label={t('observability.search')} />
					<TableViewControls view={instanceView} class="" />
				</div>
				<div class="min-h-48 max-h-72 overflow-y-auto lg:max-h-[36rem]" aria-busy={loading}>
					{#if !$authReady || $projectSwitching || (loading && currentInstances.length === 0)}
						<LoadingState variant="surface" class="min-h-48" label={t('observability.loading')} />
					{:else if failed}
						<div class="p-4"><Alert>{t('observability.loadFailed')}</Alert></div>
					{:else if filtered.length === 0}
						<EmptyState headline={search.trim() ? t('observability.noResults') : t('observability.empty')} class="py-8" />
					{:else}
						{#each filtered as instance (instance.id)}
							<button type="button" onclick={() => selectInstance(instance.id)} aria-pressed={selected?.id === instance.id}
								class="block min-h-11 w-full border-b border-line p-4 text-left transition-colors hover:bg-surface-sunken focus-visible:outline-2 focus-visible:outline-accent {selected?.id === instance.id ? 'bg-surface-selected' : ''}">
								<span class="block break-words text-sm font-medium text-ink-0">{instance.name}</span>
								<span class="mt-1 block break-all font-mono text-xs text-ink-2">{instance.id}</span>
								<span class="mt-2 flex flex-wrap items-center gap-2"><StatusChip status={instance.status} kind="server" />{#if instance.flavor_display_name ?? instance.flavor_name}<span class="text-xs text-ink-2">{instance.flavor_display_name ?? instance.flavor_name}</span>{/if}</span>
							</button>
						{/each}
					{/if}
				</div>
			</section>
			<section class="min-w-0 @container/panel" aria-label={t('observability.title')}>
				{#if selected}
					<header class="mb-4 space-y-1">
						<h2 class="break-words text-base font-semibold text-ink-0">{selected.name}</h2>
						<p class="break-all font-mono text-xs text-ink-2">{selected.id}</p>
					</header>
					{#key `${$viewScope}:${selected.id}`}
						<MetricsPanel instanceId={selected.id} projectId={$auth.projectId ?? undefined} isGpu={(selected.flavor_name ?? '').toLowerCase().startsWith('gpu.')} />
					{/key}
				{:else}
					<div class="min-h-64 rounded-lg border border-line bg-surface-base"><EmptyState headline={t('observability.selectInstance')} /></div>
				{/if}
			</section>
		</div>
	{/if}
</PageShell>
