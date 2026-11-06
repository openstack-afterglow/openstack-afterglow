<script lang="ts">
	import { t as tc } from '$lib/i18n/ns/common';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { createTableView } from '$lib/utils/tableView.svelte';
	import TableColumnHeader from '$lib/components/ui/TableColumnHeader.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import type { WorkspaceMetric } from '$lib/api/workspaceIam';
	import { t } from '$lib/i18n/ns/workspace-iam';
	import { resourceLabel, observationLabel } from './workspaceLabels';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	let { metrics, settled = true }: { metrics: WorkspaceMetric[]; settled?: boolean } = $props();
	const searchId = $props.id();
	let tableSearch = $state('');
	const tableView = createTableView<WorkspaceMetric>({ rows: () => metrics, locale: () => intlLocale(), search: () => tableSearch, searchable: row => [row.service, row.metric, resourceLabel(row.metric), row.kind, String(row.value ?? ''), row.status, row.error ?? ''], columns: () => [{ key: 'service', label: t('service'), value: row => row.service }, { key: 'metric', label: t('metric'), value: row => resourceLabel(row.metric) }, { key: 'kind', label: t('kind'), value: row => row.kind }, { key: 'value', label: t('value'), value: row => row.value }, { key: 'status', label: t('status'), value: row => row.status }, { key: 'reason', label: t('reason'), value: row => row.error }] });
</script>

<RegexSearch id={searchId} bind:value={tableSearch} /><TableViewControls view={tableView} />
<ResponsiveTable>
	{#snippet cards()}
		{#each tableView.rows as metric}
			<CompactResourceCard>
				<div class="flex flex-wrap items-start justify-between gap-2"><h3 class="text-sm font-medium">{resourceLabel(metric.metric)}</h3><Pill>{metric.error === 'domain_aggregate_unsupported' ? t('unsupported') : observationLabel(metric.status)}</Pill></div>
				<p class="text-sm tabular-nums">{metric.status === 'unlimited' ? t('unlimited') : metric.value == null ? t('unknown') : metric.status === 'partial' ? t('lowerBound', { value: metric.value }) : metric.value}{metric.value != null ? ` ${metric.unit}` : ''}</p>
				{#snippet details()}<dl class="space-y-1 text-xs"><div>{t('service')}: {metric.service}</div><div>{t('kind')}: {t(`kind.${metric.kind}`)}</div><div>{t('metric')}: <code>{metric.metric}</code></div><div>{t('reason')}: <code>{metric.error || '—'}</code></div></dl>{/snippet}
			</CompactResourceCard>
		{:else}{#if settled}<p class="text-sm text-ink-2">{metrics.length ? tc('table.noMatches') : t('noObservations')}</p>{/if}{/each}
	{/snippet}
<TableShell><table><thead><tr><TableColumnHeader view={tableView} columnKey="service" /><TableColumnHeader view={tableView} columnKey="metric" /><TableColumnHeader view={tableView} columnKey="kind" /><TableColumnHeader view={tableView} columnKey="value" /><TableColumnHeader view={tableView} columnKey="status" /><TableColumnHeader view={tableView} columnKey="reason" /></tr></thead><tbody>
	{#each tableView.rows as metric}
		<tr><td>{metric.service}</td><td>{resourceLabel(metric.metric)}<code class="block text-xs text-ink-2">{metric.metric}</code></td><td>{t(`kind.${metric.kind}`)}</td>
			<td>{metric.status === 'unlimited' ? t('unlimited') : metric.value == null ? t('unknown') : metric.status === 'partial' ? t('lowerBound', { value: metric.value }) : metric.value}{metric.value != null ? ` ${metric.unit}` : ''}</td>
			<td><Pill>{metric.error === 'domain_aggregate_unsupported' ? t('unsupported') : observationLabel(metric.status)}</Pill></td><td>{#if metric.error}<code class="text-xs">{metric.error}</code>{:else}—{/if}</td>
		</tr>
	{:else}{#if settled}<tr><td colspan="6">{metrics.length ? tc('table.noMatches') : t('noObservations')}</td></tr>{/if}{/each}
</tbody></table></TableShell>
</ResponsiveTable>
