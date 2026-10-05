<script lang="ts">
	import { t } from '$lib/i18n/ns/drover-pages';
	import RichText from '$lib/i18n/RichText.svelte';
	import { onMount } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import K3sClusterTemplateCard from '$lib/components/admin/drover/K3sClusterTemplateCard.svelte';
	import K3sClusterTemplateModal from '$lib/components/admin/drover/K3sClusterTemplateModal.svelte';
	import type { K3sClusterTemplate } from '$lib/types/k3s';
	import Modal from '$lib/components/ui/Modal.svelte';

	let templates = $state<K3sClusterTemplate[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let showCreate = $state(false);
	let editTarget = $state<K3sClusterTemplate | null>(null);
	let deleteTarget = $state<K3sClusterTemplate | null>(null);
	let deleteError = $state('');

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	async function load() {
		if (templates.length === 0) loading = true;
		else refreshing = true;
		try {
			templates = await api.get<K3sClusterTemplate[]>('/api/v1/admin/k3s-cluster-templates', token, projectId);
		} catch {
			templates = [];
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

<div class="p-4 md:p-6 max-w-7xl mx-auto">
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
				onManualRefresh={load}
			/>
		{/snippet}
	</PageHeader>

	{#if loading}
		<LoadingSkeleton variant="table" rows={3} />
	{:else}
			{#if templates.length === 0}
				<div class="text-ink-2 text-sm py-12 text-center">{t('templates.empty')}</div>
			{:else}
				<div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
					{#each templates as template (template.id)}
						<K3sClusterTemplateCard
							template={template}
							onEdit={(tmpl) => (editTarget = tmpl)}
							onDelete={(tmpl) => { deleteTarget = tmpl; deleteError = ''; }}
						/>
					{/each}
				</div>
			{/if}
	{/if}
</div>

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
