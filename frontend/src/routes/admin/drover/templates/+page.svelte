<script lang="ts">
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import { t } from '$lib/i18n/ns/drover-pages';
	import RichText from '$lib/i18n/RichText.svelte';
	import { onMount } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import K3sClusterTemplateCard from '$lib/components/admin/drover/K3sClusterTemplateCard.svelte';
	import K3sClusterTemplateModal from '$lib/components/admin/drover/K3sClusterTemplateModal.svelte';
	import type { K3sClusterTemplate } from '$lib/types/k3s';
	import Modal from '$lib/components/ui/Modal.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import { createTableView } from '$lib/utils/tableView.svelte';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { t as tc } from '$lib/i18n/ns/common';
	import Alert from '$lib/components/ui/Alert.svelte';
	import { t as scopeT } from '$lib/i18n/ns/domain-admin';

	let templates = $state<K3sClusterTemplate[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let showCreate = $state(false);
	let editTarget = $state<K3sClusterTemplate | null>(null);
	let deleteTarget = $state<K3sClusterTemplate | null>(null);
	let deleteError = $state('');
	let loadError = $state('');
	let search = $state('');
	const enabledPlugins = (template: K3sClusterTemplate) => Object.entries(template.plugins_enabled).filter(([, enabled]) => enabled).map(([name]) => name).join(', ');
	const view = createTableView<K3sClusterTemplate>({
		rows: () => templates,
		search: () => search,
		searchable: (template) => [template.name, template.id, template.description, template.k3s_version, template.default_node_count, template.os_type, ...Object.entries(template.plugins_enabled).filter(([, enabled]) => enabled).map(([name]) => name), template.public_visible ? t('templateModal.public') : t('templateCard.private')].map((value) => String(value ?? '')),
		locale: intlLocale,
		columns: () => [
			{ key: 'name', label: t('form.name'), value: (template) => template.name },
			{ key: 'description', label: t('templateModal.description'), value: (template) => template.description },
			{ key: 'version', label: t('templateCard.version'), value: (template) => template.k3s_version },
			{ key: 'agents', label: t('templateCard.agents'), value: (template) => template.default_node_count },
			{ key: 'os', label: t('form.osType'), value: (template) => template.os_type },
			{ key: 'plugins', label: t('templateCard.plugins'), value: enabledPlugins, filterValues: (template) => Object.entries(template.plugins_enabled).filter(([, enabled]) => enabled).map(([name]) => name) },
			{ key: 'public', label: t('templateModal.public'), value: (template) => template.public_visible, format: (value) => value ? t('templateModal.public') : t('templateCard.private') },
		],
	});

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	async function load(force = false) {
		if (templates.length === 0) loading = true;
		else refreshing = true;
		try {
			templates = await api.get<K3sClusterTemplate[]>('/api/v1/admin/k3s-cluster-templates', token, projectId, { refresh: force });
			loadError = '';
		} catch (error) {
			loadError = error instanceof Error ? error.message : scopeT('state.unavailable');
		} finally {
			loading = false;
			refreshing = false;
		}
	}

	async function confirmDelete() {
		if (!deleteTarget) return;
		deleteError = '';
		try {
			await api.delete(`/api/v1/k3s/cluster-templates/${deleteTarget.id}`, token, projectId);
			deleteTarget = null;
			await load();
		} catch (e) {
			deleteError = e instanceof ApiError ? e.message : t('templates.deleteFailed');
		}
	}

	const ar = createAutoRefresh(load, {
		storageKey: 'admin-k3s-templates',
		invokeOnMount: false,
		defaultActive: false,
		defaultInterval: 60,
		intervalOptions: [30, 60],
	});

	onMount(load);
</script>

<PageShell>
	<PageHeader breadcrumb={t('templates.breadcrumb')} title={t('templates.title')}>
		{#snippet actions()}
			<button
				onclick={() => (showCreate = true)}
				class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-action-on-warm text-sm font-medium rounded-lg"
			>
				{t('templates.create')}
			</button>
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={loading || refreshing}
				onManualRefresh={ar.refresh}
			/>
		{/snippet}
	</PageHeader>
	<div class="mb-4 space-y-3">
		<RegexSearch id="admin-drover-templates-search" bind:value={search} label={tc('table.search')} />
		<TableViewControls {view} class="" />
	</div>
	{#if loadError}<Alert tone="danger" class="mb-4">{loadError}</Alert>{/if}

	{#if loading}
		<LoadingState variant="surface" />
	{:else}
			{#if view.rows.length === 0 && !loadError}
				<div class="text-ink-2 text-sm py-12 text-center">{templates.length ? tc('table.noMatches') : t('templates.empty')}</div>
			{:else if view.rows.length > 0}
				<div class="motion-stagger grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
					{#each view.rows as template (template.id)}
						<K3sClusterTemplateCard
							template={template}
							onEdit={(tmpl) => (editTarget = tmpl)}
							onDelete={(tmpl) => { deleteTarget = tmpl; deleteError = ''; }}
						/>
					{/each}
				</div>
			{/if}
	{/if}
</PageShell>

{#if showCreate}
	<K3sClusterTemplateModal
		onClose={() => (showCreate = false)}
		onSaved={() => { showCreate = false; void load(); }}
	/>
{/if}

{#if editTarget}
	<K3sClusterTemplateModal
		template={editTarget}
		onClose={() => (editTarget = null)}
		onSaved={() => { editTarget = null; void load(); }}
	/>
{/if}

{#if deleteTarget}
	<Modal open={true} onClose={() => (deleteTarget = null)} ariaLabel={t('templates.deleteLabel')}>
		<div class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-sm mx-4 shadow-[var(--shadow-restraint)]">
			<h2 class="text-lg font-semibold text-ink-0 mb-3">{t('templates.deleteTitle')}</h2>
			<p class="text-sm text-ink-2 mb-5">
				<RichText segments={t.rich('templates.deleteBody', { name: deleteTarget.name })} classes={{ strong: 'text-ink-0' }} />
			</p>
			{#if deleteError}
				<div class="mb-3 text-red-400 text-xs bg-red-900/20 border border-red-800 rounded px-3 py-2">{deleteError}</div>
			{/if}
			<div class="flex justify-end gap-3">
				<button onclick={() => (deleteTarget = null)} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0">{t('actions.cancel')}</button>
				<button onclick={confirmDelete} class="px-4 py-2 bg-red-700 hover:bg-red-600 text-ink-0 text-sm font-medium rounded-lg">{t('actions.delete')}</button>
			</div>
		</div>
	</Modal>
{/if}
