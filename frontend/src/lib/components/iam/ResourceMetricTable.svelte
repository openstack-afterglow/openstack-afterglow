<script lang="ts">
	import type { WorkspaceMetric } from '$lib/api/workspaceIam';
	import { t } from '$lib/i18n/ns/workspace-iam';
	import { resourceLabel, observationLabel } from './workspaceLabels';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	let { metrics }: { metrics: WorkspaceMetric[] } = $props();
</script>

<TableShell><table><thead><tr><th>{t('service')}</th><th>{t('metric')}</th><th>{t('kind')}</th><th>{t('value')}</th><th>{t('status')}</th><th>{t('reason')}</th></tr></thead><tbody>
	{#each metrics as metric}
		<tr><td>{metric.service}</td><td>{resourceLabel(metric.metric)}<code class="block text-xs text-ink-2">{metric.metric}</code></td><td>{t(`kind.${metric.kind}`)}</td>
			<td>{metric.status === 'unlimited' ? t('unlimited') : metric.value == null ? t('unknown') : metric.status === 'partial' ? t('lowerBound', { value: metric.value }) : metric.value}{metric.value != null ? ` ${metric.unit}` : ''}</td>
			<td><Pill>{metric.error === 'domain_aggregate_unsupported' ? t('unsupported') : observationLabel(metric.status)}</Pill></td><td>{#if metric.error}<code class="text-xs">{metric.error}</code>{:else}—{/if}</td>
		</tr>
	{:else}<tr><td colspan="6">{t('noObservations')}</td></tr>{/each}
</tbody></table></TableShell>
