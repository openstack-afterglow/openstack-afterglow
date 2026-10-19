<script lang="ts">
	import { type DomainBudgets, type QuotaField, quotaBlocked } from '$lib/api/workspaceIam';
	import { t } from '$lib/i18n/ns/workspace-iam';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	let { data }: { data: DomainBudgets } = $props();
	function amount(value: number | null | undefined) { return value == null ? t('unknown') : value === -1 ? t('unlimited') : String(value); }
	function status(value: string) {
		const known = ['applying', 'unknown', 'partial', 'updated', 'reconciled', 'pending', 'writing', 'verified', 'observed', 'not_attempted'] as const;
		return known.includes(value as typeof known[number]) ? t(`operation.${value as typeof known[number]}`) : `${t('unknown')} (${value})`;
	}
</script>

<div class="space-y-4">
	<Alert tone="info">{t('allocationHelp')}</Alert>
	{#if data.drift}<Alert tone="warning">{t('drift')}</Alert>{/if}
	{#if quotaBlocked(data)}<Alert tone="warning">{t('durableBlocker')}{#if data.blocking_operation_id}<code class="mt-1 block text-xs [overflow-wrap:anywhere]">{data.blocking_operation_id}</code>{/if}</Alert>{/if}
	<TableShell><table><thead><tr><th>{t('metric')}</th><th>{t('ceiling')}</th><th>{t('allocated')}</th><th>{t('default')}</th><th>{t('budgetState')}</th></tr></thead><tbody>
		{#each Object.entries(data.allocations) as [key, metric]}
			{#if metric}<tr><td>{t(`field.${key as QuotaField}`)}<code class="block text-xs text-ink-2">{key}</code></td><td>{key in data.ceilings ? amount(data.ceilings[key as QuotaField]) : t('notConfigured')}</td><td>{amount(metric.limit)}{#if metric.error}<code class="block text-xs text-ink-2">{metric.error}</code>{/if}</td><td>{key in data.defaults ? amount(data.defaults[key as QuotaField]) : t('notConfigured')}</td><td>{metric.within_budget == null ? t('unknown') : metric.within_budget ? t('withinBudget') : t('overBudget')}</td></tr>{/if}
		{/each}
	</tbody></table></TableShell>
	<section class="space-y-2">
		<h3 class="text-sm font-semibold text-ink-0">{t('operations')}</h3>
		{#if !data.operations.length}<p class="text-sm text-ink-2">{t('noOperations')}</p>{/if}
		{#each data.operations as operation (operation.id)}
			<details class="rounded-lg border border-line p-3">
				<summary class="cursor-pointer text-sm text-ink-1 [overflow-wrap:anywhere]">{status(operation.status)} · {operation.project_id} · {operation.id}</summary>
				<p class="my-2 text-xs text-ink-2">{operation.created_at}</p>
				<TableShell><table><thead><tr><th>{t('metric')}</th><th>{t('requested')}</th></tr></thead><tbody>{#each Object.entries(operation.requested) as [field, value]}<tr><td>{t(`field.${field as QuotaField}`)}</td><td>{amount(value)}</td></tr>{/each}</tbody></table></TableShell>
				<ul class="mt-2 space-y-1 text-sm text-ink-2">{#each Object.entries(operation.sections) as [section, state]}<li>{section}: {status(state.status)}{#if state.error} · <code>{state.error}</code>{/if}{#if state.observed}<dl class="pl-4">{#each Object.entries(state.observed) as [key, value]}<div><dt class="inline">{key}: </dt><dd class="inline">{amount(value)}</dd></div>{/each}</dl>{/if}</li>{/each}</ul>
			</details>
		{/each}
	</section>
</div>
