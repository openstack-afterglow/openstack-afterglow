<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api as baseApi, ApiError } from '$lib/api/client';
	import { createAdminInventoryApi } from '$lib/api/adminInventoryScope';
	import { Alert, Button, EmptyState, PageHeader, PageShell, Pagination, TableShell } from '$lib/components/ui';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import { t } from '$lib/i18n/ns/admin-network';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';

	interface AdminSubnet { id: string; name: string; network_id: string; cidr: string; gateway_ip: string | null; project_id: string | null }
	const api = createAdminInventoryApi(baseApi);
	onDestroy(api.dispose);
	let subnets = $state<AdminSubnet[]>([]);
	let loading = $state(true);
	let error = $state('');
	let page = $state(1);
	const pageSize = 20;
	const totalPages = $derived(Math.max(1, Math.ceil(subnets.length / pageSize)));
	const rows = $derived(subnets.slice((page - 1) * pageSize, page * pageSize));
	let generation = 0;
	async function load() {
		const request = ++generation;
		loading = true; error = '';
		try {
			const result = await api.get<AdminSubnet[]>('/api/v1/admin/all-subnets', $auth.token ?? undefined, $auth.projectId ?? undefined);
			if (request !== generation) return;
			subnets = result; page = Math.min(page, Math.max(1, Math.ceil(result.length / pageSize)));
		} catch (reason) {
			if (request === generation) error = reason instanceof ApiError ? reason.message : t('subnetDetailPage.loadFailed');
		} finally { if (request === generation) loading = false; }
	}
	onMount(() => { void load(); });
	onDestroy(() => { generation += 1; });
</script>

<PageShell>
	<PageHeader breadcrumb={t('networksPage.breadcrumb')} title={t('subnetSection.title')}>
		{#snippet actions()}<Button variant="secondary" size="sm" disabled={loading} onclick={load}>{t('subnetDetailPage.refresh')}</Button>{/snippet}
	</PageHeader>
	{#if error}<Alert tone="danger">{error}</Alert>{/if}
	{#if loading}<LoadingSkeleton variant="table" rows={5} />
	{:else if !error && subnets.length === 0}<EmptyState headline={t('subnetSection.empty')} />
	{:else if subnets.length > 0}
		<ResponsiveTable>
			{#snippet cards()}
				{#each rows as subnet (subnet.id)}
					<CompactResourceCard>
						<a class="min-h-11 break-all font-medium text-accent" href={`/admin/subnets/${encodeURIComponent(subnet.id)}`}>{subnet.name || subnet.id}</a>
						<div class="space-y-1 break-all text-xs text-ink-2"><p class="font-mono">{subnet.cidr}</p><p>{t('subnetSection.gateway')}: {subnet.gateway_ip ?? '—'}</p></div>
						{#snippet details()}<div class="space-y-2 break-all font-mono text-xs text-ink-2"><p>{subnet.id}</p><p>{t('subnetDetailPage.projectId')}: {subnet.project_id ?? '—'}</p><a class="inline-flex min-h-11 items-center text-accent" href={`/admin/networks/${encodeURIComponent(subnet.network_id)}`}>{t('subnetDetailPage.network')}: {subnet.network_id}</a></div>{/snippet}
					</CompactResourceCard>
				{/each}
			{/snippet}
		<TableShell>
			<table>
			<thead><tr>
				<th>{t('subnetSection.name')}</th><th>{t('subnetDetailPage.cidrVersion')}</th><th>{t('subnetDetailPage.network')}</th><th>{t('subnetDetailPage.projectId')}</th><th>{t('subnetSection.gateway')}</th>
			</tr></thead>
			<tbody>{#each rows as subnet (subnet.id)}<tr>
				<td><a class="text-accent hover:underline" href={`/admin/subnets/${encodeURIComponent(subnet.id)}`}>{subnet.name || subnet.id}</a></td>
				<td class="font-mono text-xs">{subnet.cidr}</td>
				<td><a class="text-accent hover:underline font-mono text-xs" href={`/admin/networks/${encodeURIComponent(subnet.network_id)}`}>{subnet.network_id}</a></td>
				<td class="font-mono text-xs">{subnet.project_id ?? '—'}</td><td class="font-mono text-xs">{subnet.gateway_ip ?? '—'}</td>
			</tr>{/each}</tbody>
			</table>
		</TableShell>
		</ResponsiveTable>
		<Pagination {page} {totalPages} total={subnets.length} {pageSize} hasPrev={page > 1} hasNext={page < totalPages} onPrev={() => page -= 1} onNext={() => page += 1} />
	{/if}
</PageShell>
