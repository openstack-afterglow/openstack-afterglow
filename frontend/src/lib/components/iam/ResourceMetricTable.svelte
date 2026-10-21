<script lang="ts">
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import type { WorkspaceMetric } from '$lib/api/workspaceIam';
	import { t } from '$lib/i18n/ns/workspace-iam';
	import { resourceLabel, observationLabel } from './workspaceLabels';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	let { metrics }: { metrics: WorkspaceMetric[] } = $props();
</script>

<ResponsiveTable>
	{#snippet cards()}
		{#each metrics as metric}
			<CompactResourceCard>
				<div class="flex flex-wrap items-start justify-between gap-2"><h3 class="text-sm font-medium">{resourceLabel(metric.metric)}</h3><Pill>{metric.error === 'domain_aggregate_unsupported' ? t('unsupported') : observationLabel(metric.status)}</Pill></div>
				<p class="text-sm tabular-nums">{metric.status === 'unlimited' ? t('unlimited') : metric.value == null ? t('unknown') : metric.status === 'partial' ? t('lowerBound', { value: metric.value }) : metric.value}{metric.value != null ? ` ${metric.unit}` : ''}</p>
				{#snippet details()}<dl class="space-y-1 text-xs"><div>{t('service')}: {metric.service}</div><div>{t('kind')}: {t(`kind.${metric.kind}`)}</div><div>{t('metric')}: <code>{metric.metric}</code></div><div>{t('reason')}: <code>{metric.error || '—'}</code></div></dl>{/snippet}
			</CompactResourceCard>
		{:else}<p class="text-sm text-ink-2">{t('noObservations')}</p>{/each}
	{/snippet}
<TableShell><table><thead><tr><th>{t('service')}</th><th>{t('metric')}</th><th>{t('kind')}</th><th>{t('value')}</th><th>{t('status')}</th><th>{t('reason')}</th></tr></thead><tbody>
	{#each metrics as metric}
		<tr><td>{metric.service}</td><td>{resourceLabel(metric.metric)}<code class="block text-xs text-ink-2">{metric.metric}</code></td><td>{t(`kind.${metric.kind}`)}</td>
			<td>{metric.status === 'unlimited' ? t('unlimited') : metric.value == null ? t('unknown') : metric.status === 'partial' ? t('lowerBound', { value: metric.value }) : metric.value}{metric.value != null ? ` ${metric.unit}` : ''}</td>
			<td><Pill>{metric.error === 'domain_aggregate_unsupported' ? t('unsupported') : observationLabel(metric.status)}</Pill></td><td>{#if metric.error}<code class="text-xs">{metric.error}</code>{:else}—{/if}</td>
		</tr>
	{:else}<tr><td colspan="6">{t('noObservations')}</td></tr>{/each}
</tbody></table></TableShell>
</ResponsiveTable>
