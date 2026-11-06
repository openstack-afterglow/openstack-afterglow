<script lang="ts">
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { t } from '$lib/i18n/ns/admin-ops';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import type { DomainUsage } from '$lib/types/adminOverview';
	import { Alert, CompactResourceCard, ResourceIdentifier, ResponsiveTable, TableShell } from '$lib/components/ui';
	import TableColumnHeader from '$lib/components/ui/TableColumnHeader.svelte';
	import TableColumnControl from '$lib/components/ui/TableColumnControl.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import { createTableView, type TableColumn } from '$lib/utils/tableView.svelte';
	import { t as tc } from '$lib/i18n/ns/common';

	let { domains, loading, error = '' }: { domains: DomainUsage[]; loading: boolean; error?: string } = $props();
	const ownerKeys = {
		known: 'overview.domains.known', deleted_project: 'overview.domains.deletedProject',
		unknown_owner: 'overview.domains.unknownOwner', deleted_domain: 'overview.domains.deletedDomain',
	} as const;
	function number(value: number | null): string {
		return value === null ? t('overview.domains.unavailable') : value.toLocaleString(intlLocale());
	}
	function href(domain: DomainUsage, resource: 'instances' | 'volumes'): string | null {
		return domain.domain_id ? `/admin/${resource}?domain_id=${encodeURIComponent(domain.domain_id)}` : null;
	}
	const columns = $derived<TableColumn<DomainUsage>[]>([
		{ key: 'domain', label: t('overview.domains.domain'), value: (row) => row.domain_name || t(ownerKeys[row.owner_status]) },
		{ key: 'projects', label: t('overview.domains.projects'), value: (row) => row.project_count, format: (_value, row) => number(row.project_count) },
		{ key: 'instances', label: 'VM', value: (row) => row.instances, format: (_value, row) => number(row.instances) },
		{ key: 'vcpus', label: 'vCPU', value: (row) => row.vcpus, format: (_value, row) => number(row.vcpus) },
		{ key: 'ram', label: 'RAM (GiB)', value: (row) => row.ram_mb === null ? null : row.ram_mb / 1024, format: (_value, row) => number(row.ram_mb === null ? null : row.ram_mb / 1024) },
		{ key: 'gpu', label: 'GPU VM', value: (row) => row.gpu_instances, format: (_value, row) => number(row.gpu_instances) },
		{ key: 'volumes', label: t('overview.domains.volumes'), value: (row) => row.volumes, format: (_value, row) => number(row.volumes) },
		{ key: 'capacity', label: t('overview.domains.capacity'), value: (row) => row.volume_gb, format: (_value, row) => `${number(row.volume_gb)} GiB` },
		{ key: 'attachedVolumes', label: `${t('overview.domains.attached')} · ${t('overview.domains.volumes')}`, value: (row) => row.attached_volumes, format: (_value, row) => number(row.attached_volumes) },
		{ key: 'attachedCapacity', label: `${t('overview.domains.attached')} · GiB`, value: (row) => row.attached_gb, format: (_value, row) => `${number(row.attached_gb)} GiB` },
		{ key: 'availableVolumes', label: `${t('overview.domains.available')} · ${t('overview.domains.volumes')}`, value: (row) => row.available_volumes, format: (_value, row) => number(row.available_volumes) },
		{ key: 'availableCapacity', label: `${t('overview.domains.available')} · GiB`, value: (row) => row.available_gb, format: (_value, row) => `${number(row.available_gb)} GiB` },
	]);
	const detailColumns = new Set(['attachedVolumes', 'attachedCapacity', 'availableVolumes', 'availableCapacity']);
	const view = createTableView<DomainUsage>({ rows: () => domains, columns: () => columns, locale: intlLocale });
</script>

<section class="min-w-0 rounded-lg border border-line bg-surface-base p-5" aria-label={t('overview.domains.title')}>
	<h2 class="mb-2 text-sm font-semibold text-ink-0">{t('overview.domains.title')}</h2>
	<p class="mb-3 text-xs text-ink-2">{t('overview.domains.description')}</p>
	{#if error}<Alert tone="danger">{error}</Alert>{/if}
	<TableViewControls {view} class={loading ? '' : 'lg:hidden'} />
	{#if loading}
		<LoadingState variant="table" columns={6} rows={4} label={t('overview.domains.loading')} />
	{:else}
		{#if view.rows.length === 0 && !error}<p class="py-6 text-center text-sm text-ink-2">{domains.length ? tc('table.noMatches') : t('overview.domains.empty')}</p>{/if}
		{#snippet identity(domain: DomainUsage)}
			<div class="min-w-0 space-y-1">
				<p class="break-words font-medium text-ink-0">{domain.domain_name || t(ownerKeys[domain.owner_status])}</p>
				{#if domain.domain_name && domain.owner_status !== 'known'}<p class="text-xs text-ink-2">{t(ownerKeys[domain.owner_status])}</p>{/if}
				{#if domain.domain_id}<ResourceIdentifier id={domain.domain_id} />{/if}
				{#if !domain.domain_id && domain.project_ids.length > 0}
					{#each domain.project_ids as id}<ResourceIdentifier {id} />{/each}
				{/if}
			</div>
		{/snippet}
		{#snippet links(domain: DomainUsage)}
			{@const instancesHref = href(domain, 'instances')}
			{@const volumesHref = href(domain, 'volumes')}
			{#if instancesHref && volumesHref}
				<div class="flex flex-wrap gap-x-3 gap-y-1">
					<a class="inline-flex min-h-11 items-center text-xs text-warm-text underline" href={instancesHref}>{t('overview.domains.instancesLink')}</a>
					<a class="inline-flex min-h-11 items-center text-xs text-warm-text underline" href={volumesHref}>{t('overview.domains.volumesLink')}</a>
				</div>
			{:else}<p class="text-xs text-ink-2">{t('overview.domains.noDrilldown')}</p>{/if}
		{/snippet}
		{#snippet volumeDetails(domain: DomainUsage)}
			<dl class="space-y-1 text-xs text-ink-2">
				<div><dt>{t('overview.domains.attached')}</dt><dd class="tabular-nums">{number(domain.attached_volumes)} · {number(domain.attached_gb)} GiB</dd></div>
				<div><dt>{t('overview.domains.available')}</dt><dd class="tabular-nums">{number(domain.available_volumes)} · {number(domain.available_gb)} GiB</dd></div>
			</dl>
		{/snippet}
		<ResponsiveTable>
			{#snippet cards()}
				{#each view.rows as domain (JSON.stringify([domain.owner_status, domain.domain_id, domain.project_ids]))}
					<CompactResourceCard>
						{@render identity(domain)}
						<dl class="flex flex-wrap gap-3 text-xs">
							<div><dt class="text-ink-2">VM</dt><dd>{number(domain.instances)}</dd></div>
							<div><dt class="text-ink-2">vCPU</dt><dd>{number(domain.vcpus)}</dd></div>
							<div><dt class="text-ink-2">{t('overview.domains.volumes')}</dt><dd>{number(domain.volumes)} · {number(domain.volume_gb)} GiB</dd></div>
						</dl>
						{#snippet actions()}{@render links(domain)}{/snippet}
						{#snippet details()}
							<dl class="mb-2 space-y-1 text-xs text-ink-2">
								<div><dt>{t('overview.domains.projects')}</dt><dd>{number(domain.project_count)}</dd></div>
								<div><dt>RAM (GiB)</dt><dd>{number(domain.ram_mb === null ? null : domain.ram_mb / 1024)}</dd></div>
								<div><dt>GPU VM</dt><dd>{number(domain.gpu_instances)}</dd></div>
							</dl>
							{@render volumeDetails(domain)}
						{/snippet}
					</CompactResourceCard>
				{/each}
			{/snippet}
		<TableShell><table>
			<thead><tr>
				{#each columns as column (column.key)}
					{#if !detailColumns.has(column.key)}<TableColumnHeader {view} columnKey={column.key} />{/if}
				{/each}
				<th scope="col">
					<span>{t('overview.domains.details')}</span>
					<div class="mt-1 space-y-1">
						{#each columns as column (column.key)}
							{#if detailColumns.has(column.key)}<TableColumnControl {view} columnKey={column.key} />{/if}
						{/each}
					</div>
				</th>
			</tr></thead>
				<tbody>
					{#each view.rows as domain (JSON.stringify([domain.owner_status, domain.domain_id, domain.project_ids]))}
						<tr>
						<td>{@render identity(domain)}</td><td class="text-right tabular-nums">{number(domain.project_count)}</td><td class="text-right tabular-nums">{number(domain.instances)}</td><td class="text-right tabular-nums">{number(domain.vcpus)}</td><td class="text-right tabular-nums">{number(domain.ram_mb === null ? null : domain.ram_mb / 1024)}</td><td class="text-right tabular-nums">{number(domain.gpu_instances)}</td><td class="text-right tabular-nums">{number(domain.volumes)}</td><td class="text-right tabular-nums">{number(domain.volume_gb)} GiB</td>
							<td><details><summary class="min-h-11 cursor-pointer text-xs text-ink-2">{t('overview.domains.volumeDetails')}</summary>{@render volumeDetails(domain)}</details>{@render links(domain)}</td>
						</tr>
					{/each}
				</tbody>
			</table></TableShell>
		</ResponsiveTable>
	{/if}
</section>
