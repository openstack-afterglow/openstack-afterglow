<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { ApiError } from '$lib/api/client';
	import type { IamSession } from '$lib/api/domainIam';
	import { workspaceIam, type DomainForecast } from '$lib/api/workspaceIam';
	import { t } from '$lib/i18n/ns/workspace-iam';
	import { resourceLabel, observationLabel } from './workspaceLabels';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	let { session, blocked = false, onDenied }: { session: IamSession; blocked?: boolean; onDenied: () => void } = $props();
	const client = untrack(() => workspaceIam(session));
	let data = $state<DomainForecast | null>(null);
	let loading = $state(true);
	let error = $state('');
	let live = true;
	let generation = 0;
	let started = false;
	async function load() {
		if (blocked || !session.isCurrent()) return;
		const pending = ++generation;
		loading = true; error = ''; data = null;
		try {
			const result = await client.forecast();
			if (!live || pending !== generation || !session.isCurrent()) return;
			if (result.domain_id !== session.domainId) throw new Error(t('scopeMismatch'));
			data = result;
		} catch (cause) {
			if (!live || pending !== generation || !session.isCurrent()) return;
			error = cause instanceof Error ? cause.message : t('loadFailed');
			if (cause instanceof ApiError && cause.status === 403) onDenied();
		} finally { if (live && pending === generation) loading = false; }
	}
	function amount(value: number | null, unit: string) { return value == null ? t('unknown') : value === -1 ? t('unlimited') : `${value} ${unit}`; }
	$effect(() => { if (!blocked) untrack(() => { if (!started && session.isCurrent()) { started = true; void load(); } }); });
	onDestroy(() => { live = false; generation++; data = null; });
</script>

<div class="space-y-4">
	<div class="flex flex-wrap items-center gap-2"><h2 class="mr-auto text-lg font-semibold text-ink-0">{t('monitoringForecast')}</h2><Button variant="secondary" disabled={blocked || loading} onclick={load}>{t('reload')}</Button></div>
	<p class="text-sm text-ink-2">{t('monitoringForecastHelp')}</p>
	{#if error}<Alert tone="danger">{error}</Alert>{/if}
	{#if loading}<ActivityIndicator label={t('loading')} />{/if}
	{#if data}
		{@const snapshot = data}
		<p class="text-xs text-ink-2">{t('monitoringForecastWindow', { window: data.window_days, horizon: data.horizon_days })} · {t('observedAt')}: {data.observed_at} · <code>{data.source}</code></p>
		{#snippet trend(entry: DomainForecast['entries'][number])}
			{#if entry.trend?.trend_available}
				<p>{t('monitoringDailyChange')}: {entry.trend.slope_per_day == null ? t('unknown') : `${entry.trend.slope_per_day > 0 ? '+' : ''}${entry.trend.slope_per_day} ${entry.unit}`}</p>
				<p>{t('monitoringProjected')}: {entry.trend.projected_pct == null ? t('unknown') : `${entry.trend.projected_pct}%`}</p>
				<p>{t('monitoringDaysToLimit')}: {entry.trend.days_to_limit == null ? t('monitoringNoCrossing') : entry.trend.days_to_limit}</p>
			{:else}<p>{t('monitoringForecastUnavailable')}</p>{/if}
			{#if entry.error}<code class="text-xs [overflow-wrap:anywhere]">{entry.error}</code>{/if}
		{/snippet}
		<ResponsiveTable>
			{#snippet cards()}
				{#each snapshot.entries as entry}<CompactResourceCard>
					<h3 class="text-sm font-medium">{resourceLabel(entry.metric)}</h3>
					<p class="text-xs">{observationLabel(entry.status)}</p>
					<p class="text-sm tabular-nums">{t('inUse')}: {amount(entry.current, entry.unit)} · {t('allocated')}: {amount(entry.limit, entry.unit)}</p>
					<div class="space-y-1 text-sm tabular-nums">{@render trend(entry)}</div>
				</CompactResourceCard>{/each}
			{/snippet}
			<TableShell><table><thead><tr><th>{t('metric')}</th><th>{t('inUse')}</th><th>{t('allocated')}</th><th>{t('monitoringForecast')}</th></tr></thead><tbody>
				{#each snapshot.entries as entry}<tr><td>{resourceLabel(entry.metric)}<p class="text-xs text-ink-2">{observationLabel(entry.status)}</p></td><td class="tabular-nums">{amount(entry.current, entry.unit)}</td><td class="tabular-nums">{amount(entry.limit, entry.unit)}</td><td class="space-y-1 tabular-nums">{@render trend(entry)}</td></tr>{/each}
			</tbody></table></TableShell>
		</ResponsiveTable>
	{/if}
</div>
