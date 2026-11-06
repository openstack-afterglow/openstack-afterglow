<script lang="ts">
	import { t as commonT } from '$lib/i18n/ns/common';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { onDestroy, onMount } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api as baseApi, ApiError } from '$lib/api/client';
	import { createAdminInventoryApi } from '$lib/api/adminInventoryScope';
	import { Alert, Button, EmptyState, PageHeader, PageShell, Pagination, TableShell } from '$lib/components/ui';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { t } from '$lib/i18n/ns/admin-network';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import TableColumnHeader from '$lib/components/ui/TableColumnHeader.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import { createTableView, type TableColumn } from '$lib/utils/tableView.svelte';
	let search = $state('');
	const columns: TableColumn<AdminSubnet>[] = $derived([
		{ key: 'name', label: t('subnetSection.name'), value: (row) => row.name || row.id },
		{ key: 'cidr', label: t('subnetDetailPage.cidrVersion'), value: (row) => row.cidr },
		{ key: 'network', label: t('subnetDetailPage.network'), value: (row) => row.network_id },
		{ key: 'project', label: t('subnetDetailPage.projectId'), value: (row) => row.project_id },
		{ key: 'gateway', label: t('subnetSection.gateway'), value: (row) => row.gateway_ip },
	]);
	const view = createTableView({ locale: intlLocale, rows: () => subnets, columns: () => columns, search: () => search,
		searchable: (row) => [row.id, row.name, row.cidr, row.network_id, row.project_id, row.gateway_ip].filter((value) => value != null).map(String) });
	let viewOwner = '';
	$effect(() => {
		const owner = JSON.stringify([$auth.userId, $auth.projectId, Boolean($auth.token)]);
		if (owner !== viewOwner) { viewOwner = owner; search = ''; view.reset(); }
	});

	interface AdminSubnet { id: string; name: string; network_id: string; cidr: string; gateway_ip: string | null; project_id: string | null }
	const api = createAdminInventoryApi(baseApi);
	onDestroy(api.dispose);
	let subnets = $state<AdminSubnet[]>([]);
	let loading = $state(true);
	let error = $state('');
	let page = $state(1);
	const pageSize = 20;
	const totalPages = $derived(Math.max(1, Math.ceil(view.rows.length / pageSize)));
	const rows = $derived(view.rows.slice((Math.min(page, totalPages) - 1) * pageSize, Math.min(page, totalPages) * pageSize));
	$effect(() => { search; view.sort; view.filters; page = 1; });
	$effect(() => { if (page > totalPages) page = totalPages; });
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
	<RegexSearch id="subnet-search" bind:value={search} />
	<TableViewControls {view} />
	{#if subnets.length > 0 && view.rows.length === 0}<p class="my-3 text-sm text-ink-2">{commonT('table.noMatches')}</p>{/if}
	{#if error}<Alert tone="danger">{error}</Alert>{/if}
	{#if loading}<LoadingState variant="surface" />
	{:else if !error && subnets.length === 0}<EmptyState headline={t('subnetSection.empty')} />
	{/if}
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
				{#each columns as column (column.key)}<TableColumnHeader {view} columnKey={column.key} />{/each}
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
		<Pagination {page} {totalPages} total={view.rows.length} {pageSize} hasPrev={page > 1} hasNext={page < totalPages} onPrev={() => page -= 1} onNext={() => page += 1} />
</PageShell>
