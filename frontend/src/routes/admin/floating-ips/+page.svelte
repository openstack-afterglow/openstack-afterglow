<script lang="ts">
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import { onMount } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import type { FloatingIpInfo, NetworkInfo } from '$lib/types/networks';
	import Modal from '$lib/components/ui/Modal.svelte';
	import { t } from '$lib/i18n/ns/admin-network';
	import RichText from '$lib/i18n/RichText.svelte';

	let fips = $state<FloatingIpInfo[]>([]);
	let loading = $state(true);

	// 생성 모달
	let showCreate = $state(false);
	let creating = $state(false);
	let createError = $state('');
	let externalNets = $state<NetworkInfo[]>([]);
	let selectedNetId = $state('');

	// 삭제 확인
	let deleteFip = $state<FloatingIpInfo | null>(null);
	let deleting = $state(false);
	let deleteError = $state('');

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	async function load() {
		loading = true;
		try {
			fips = await api.get<FloatingIpInfo[]>('/api/v1/admin/all-floating-ips', token, projectId);
		} catch {
			fips = [];
		} finally {
			loading = false;
		}
	}

	function prefetchExternalNetworks() {
		void api.prefetch('/api/v1/admin/all-networks', token, projectId);
	}

	async function openCreate() {
		showCreate = true; createError = '';
		try {
			const nets = await api.get<NetworkInfo[]>('/api/v1/admin/all-networks', token, projectId);
			externalNets = nets.filter(n => n.is_external);
			selectedNetId = externalNets.length > 0 ? externalNets[0].id : '';
		} catch {
			externalNets = [];
		}
	}

	async function createFip() {
		if (!selectedNetId) return;
		creating = true; createError = '';
		try {
			await api.post('/api/v1/admin/floating-ips', { floating_network_id: selectedNetId }, token, projectId);
			showCreate = false; await load();
		} catch (e) { createError = e instanceof ApiError ? e.message : t('floatingIpsPage.error.createFailed'); } finally { creating = false; }
	}

	async function confirmDelete() {
		if (!deleteFip) return;
		deleting = true; deleteError = '';
		try {
			await api.delete(`/api/v1/admin/floating-ips/${deleteFip.id}`, token, projectId);
			deleteFip = null; await load();
		} catch (e) { deleteError = e instanceof ApiError ? e.message : t('floatingIpsPage.error.deleteFailed'); } finally { deleting = false; }
	}

	const ar = createAutoRefresh(load, {
		storageKey: 'admin-floating-ips',
		invokeOnMount: false,
		defaultActive: true,
		defaultInterval: 30,
		intervalOptions: [15, 30, 60]
	});

	onMount(load);
</script>

<div class="p-4 md:p-6 max-w-7xl mx-auto">
	<PageHeader breadcrumb={t('floatingIpsPage.breadcrumb')} title={t('floatingIpsPage.title')}>
		{#snippet actions()}
			<button onclick={openCreate} onpointerenter={prefetchExternalNetworks} onfocus={prefetchExternalNetworks} class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-ink-0 text-sm font-medium rounded-lg">{t('floatingIpsPage.actions.create')}</button>
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={loading}
				onManualRefresh={load}
			/>
		{/snippet}
	</PageHeader>

	{#if loading}
		<div class="text-ink-2 text-sm"><ActivityIndicator size="sm" label={t('floatingIpsPage.loading')} /></div>
	{:else}
		<div class="overflow-x-auto">
			<table class="w-full text-sm">
				<thead>
					<tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
						<th class="text-left py-2 pr-4">{t('floatingIpsPage.table.floatingIp')}</th>
						<th class="text-left py-2 pr-4">{t('floatingIpsPage.table.fixedIp')}</th>
						<th class="text-left py-2 pr-4">{t('floatingIpsPage.table.status')}</th>
						<th class="text-left py-2 pr-4">{t('floatingIpsPage.table.project')}</th>
						<th class="text-left py-2">{t('floatingIpsPage.table.actions')}</th>
					</tr>
				</thead>
				<tbody>
					{#each fips as f (f.id)}
						<tr class="border-b border-line/50 text-xs hover:bg-surface-sunken/30 transition-colors">
							<td class="py-2 pr-4 font-mono text-green-400">{f.floating_ip_address}</td>
							<td class="py-2 pr-4 font-mono text-ink-2">{f.fixed_ip_address ?? '-'}</td>
							<td class="py-2 pr-4 {f.port_id ? 'text-green-400' : 'text-ink-2'}">
								{f.port_id ? t('floatingIpsPage.status.assigned') : t('floatingIpsPage.status.unassigned')}
							</td>
							<td class="py-2 pr-4 text-ink-2 font-mono">{f.project_id?.slice(0, 8) ?? '-'}</td>
							<td class="py-2">
								{#if !f.port_id}
									<button onclick={() => { deleteFip = f; deleteError = ''; }}
										class="px-2 py-0.5 text-xs bg-red-900/30 hover:bg-red-900/50 text-red-400 rounded">{t('floatingIpsPage.actions.delete')}</button>
								{/if}
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
		<div class="mt-3 flex gap-4 text-xs text-ink-2">
			<span>{t('floatingIpsPage.summary.total', { count: fips.length })}</span>
			<span class="text-green-400">{t('floatingIpsPage.summary.assigned', { count: fips.filter(f => f.port_id).length })}</span>
			<span>{t('floatingIpsPage.summary.unassigned', { count: fips.filter(f => !f.port_id).length })}</span>
		</div>
	{/if}
</div>

<!-- 생성 모달 -->
<Modal bind:open={showCreate} ariaLabel={t('floatingIpsPage.createDialog.title')}>
	<div class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]">
		<h2 class="text-lg font-semibold text-ink-0 mb-5">{t('floatingIpsPage.createDialog.title')}</h2>
		{#if createError}<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{createError}</div>{/if}
		<div>
			<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-page-146">{t('floatingIpsPage.createDialog.externalNetwork')}</label>
			{#if externalNets.length === 0}
				<div class="text-xs text-red-400">{t('floatingIpsPage.createDialog.noExternalNetworks')}</div>
			{:else}
				<select id="field-page-146" bind:value={selectedNetId} class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus-visible:shadow-[var(--focus-ring)]">
					{#each externalNets as n}
						<option value={n.id}>{n.name || n.id.slice(0, 8)}</option>
					{/each}
				</select>
			{/if}
		</div>
		<div class="flex justify-end gap-3 mt-6">
			<button onclick={() => { showCreate = false; }} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">{t('floatingIpsPage.actions.cancel')}</button>
			<button aria-busy={creating} onclick={createFip} disabled={creating || !selectedNetId} class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-ink-0 text-sm font-medium rounded-lg disabled:opacity-30">{#if creating}<span class="inline-flex items-center gap-2" role="status"><ActivityIndicator size="xs" />{t('floatingIpsPage.actions.creating')}</span>{:else}{t('floatingIpsPage.createDialog.submit')}{/if}</button>
		</div>
	</div>
</Modal>

<!-- 삭제 확인 모달 -->
{#if deleteFip}
	<Modal open={true} onClose={() => { deleteFip = null; }} ariaLabel={t('floatingIpsPage.deleteDialog.title')}>
		<div class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-sm mx-4 shadow-[var(--shadow-restraint)]">
			<h2 class="text-lg font-semibold text-ink-0 mb-3">{t('floatingIpsPage.deleteDialog.title')}</h2>
			{#snippet addressSnippet(text: string)}<span class="text-ink-0 font-mono">{text}</span>{/snippet}
			<p class="text-sm text-ink-2 mb-4"><RichText segments={t.rich('floatingIpsPage.deleteDialog.body', { address: deleteFip.floating_ip_address })} tags={{ address: addressSnippet }} /></p>
			{#if deleteError}<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{deleteError}</div>{/if}
			<div class="flex justify-end gap-3">
				<button onclick={() => { deleteFip = null; }} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">{t('floatingIpsPage.actions.cancel')}</button>
				<button aria-busy={deleting} onclick={confirmDelete} disabled={deleting} class="px-4 py-2 bg-[var(--color-state-danger)]/10 hover:bg-[var(--color-state-danger)]/20 text-[var(--color-state-danger-text)] text-sm font-medium rounded-lg disabled:opacity-30">{#if deleting}<span class="inline-flex items-center gap-2" role="status"><ActivityIndicator size="xs" />{t('floatingIpsPage.actions.deleting')}</span>{:else}{t('floatingIpsPage.actions.delete')}{/if}</button>
			</div>
		</div>
	</Modal>
{/if}
