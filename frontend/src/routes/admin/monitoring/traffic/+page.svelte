<script lang="ts">
	import { api } from '$lib/api/client';
	import { auth, authReady, projectSwitching } from '$lib/stores/auth';
	import { ActivityIndicator, Alert, Button, Card, PageHeader, PageShell, SelectInput, TableShell } from '$lib/components/ui';
	import TrafficCountryMap from '$lib/components/admin/traffic/TrafficCountryMap.svelte';
	import TrafficTrend from '$lib/components/admin/traffic/TrafficTrend.svelte';
	import TrafficCoverage from '$lib/components/admin/traffic/TrafficCoverage.svelte';
	import { t } from '$lib/i18n/ns/traffic-analytics';
    import { metricValue, parseTrafficSnapshot, trafficOrigins, type TrafficOriginFilter, type TrafficMetric, type TrafficSource, type TrafficRange, type TrafficSnapshot } from '$lib/types/trafficAnalytics';
	import { formatTrafficValue } from '$lib/utils/trafficFormat';

	let source = $state<TrafficSource>('backend');
	let range = $state<TrafficRange>('24h');
    let origin = $state<TrafficOriginFilter>('all');
	let revision = $state(0);
	let result = $state<{ key: string; snapshot: TrafficSnapshot } | null>(null);
	let failedKey = $state<string | null>(null);
	let pendingKey = $state<string | null>(null);
	const ready = $derived($authReady && !$projectSwitching);
	const allowed = $derived(ready && !!$auth.token && $auth.isSystemAdmin);
    const context = $derived(JSON.stringify([source, range, origin, $auth.token, $auth.userId, $auth.projectId, $auth.isSystemAdmin, ready, revision]));
	const snapshot = $derived(allowed && result?.key === context ? result.snapshot : null);
	const loading = $derived(allowed && pendingKey === context);
	const failed = $derived(allowed && failedKey === context);
	const metrics: TrafficMetric[] = ['requests', 'success', 'errors', 'pageviews', 'unique_visitors', 'unlocated', 'status_1xx', 'status_2xx', 'status_3xx', 'status_4xx', 'status_5xx', 'request_bytes', 'response_bytes', 'latency_avg', 'latency_ms_max'];

	$effect(() => {
		const key = context;
		const selectedSource = source;
		const selectedRange = range;
        const selectedOrigin = origin;
		const token = $auth.token ?? undefined;
		const project = $auth.projectId ?? undefined;
		let stopped = false;
		result = null; failedKey = null; pendingKey = null;
		if (allowed) {
			pendingKey = key;
			void (async () => {
				try {
                    const response = await api.get<unknown>(`/api/v1/admin/monitoring/traffic?range=${selectedRange}&source=${selectedSource}&origin=${selectedOrigin}`, token, project, { refresh: true });
                    const parsed = parseTrafficSnapshot(response, selectedSource, selectedRange, selectedOrigin);
					if (!stopped) result = { key, snapshot: parsed };
				} catch { if (!stopped) failedKey = key; }
				finally { if (!stopped) pendingKey = null; }
			})();
		}
		return () => { stopped = true; };
	});
</script>

<PageShell>
	<PageHeader breadcrumb={t('page.breadcrumb')} title={t('page.title')} subtitle={t('page.subtitle')}>
		{#snippet actions()}<Button variant="secondary" disabled={loading || !allowed} onclick={() => { revision++; }}>{t('controls.refresh')}</Button>{/snippet}
	</PageHeader>
    <div class="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
		<label for="traffic-source" class="text-xs text-ink-2">{t('controls.source')}
			<SelectInput id="traffic-source" bind:value={source}>
				<option value="backend">{t('sources.backend')}</option><option value="frontend">{t('sources.frontend')}</option>
			</SelectInput>
		</label>
		<label for="traffic-range" class="text-xs text-ink-2">{t('controls.range')}
			<SelectInput id="traffic-range" bind:value={range}>
				<option value="24h">{t('ranges.24h')}</option><option value="7d">{t('ranges.7d')}</option><option value="30d">{t('ranges.30d')}</option>
			</SelectInput>
		</label>
        <label for="traffic-origin" class="text-xs text-ink-2">{t('controls.origin')}
            <SelectInput id="traffic-origin" bind:value={origin}>
                <option value="all">{t('origins.all')}</option>
                {#each trafficOrigins as value (value)}<option value={value}>{t(`origins.${value}`)}</option>{/each}
            </SelectInput>
        </label>
	</div>
	<div class="space-y-4" aria-busy={loading}>
		{#if !ready}<ActivityIndicator label={t('loading')} />
		{:else if !allowed}<Alert tone="warning">{t('adminRequired')}</Alert>
		{:else if loading}<ActivityIndicator label={t('loading')} />
		{:else if failed}<Alert tone="danger">{t('loadFailed')}</Alert>
		{/if}
		{#if snapshot}
			<Alert tone={snapshot.state === 'available' ? 'info' : 'warning'}>{t(`states.${snapshot.state}`)}{#if snapshot.state === 'partial'} · {t('coverage.partial')}{/if}</Alert>
			{#if snapshot.totals === null}<p class="text-sm text-ink-2">{t('empty')}</p>{/if}
			<p class="text-xs text-ink-2">{t('trend.note')}</p>
            <p class="text-xs text-ink-2">{t('origins.note')}</p>
            <dl class="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs tabular-nums">
                {#each trafficOrigins as value (value)}<div><dt class="text-ink-2">{t(`origins.${value}`)}</dt><dd>{formatTrafficValue(snapshot.origins?.[value] ?? null)}</dd></div>{/each}
            </dl>
			<div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
				{#each metrics as metric (metric)}<TrafficTrend {snapshot} {metric} />{/each}
			</div>
			<TrafficCountryMap countries={snapshot.countries} siteCountry={snapshot.coverage.site_country} />
			<Card surface="base">
				<h2 class="text-sm font-semibold">{t('routes.title')}</h2>
				<p class="mt-2 text-xs text-ink-2">{t('routes.note')}</p>
				<Button variant="link" href="/admin/infrastructure-topology">{t('routes.topology')}</Button>
				{#if snapshot.routes.length === 0}<p class="mt-2 text-xs text-ink-2">{t('noObservations')}</p>
				{:else}
					<TableShell class="mt-3">
						<!-- TableShell scrolls horizontally on narrow screens; the table is the keyboard scroll target. -->
						<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
						<table tabindex="0" aria-label={t('routes.title')} class="w-full text-xs tabular-nums focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent">
                        <thead><tr><th class="p-2 text-left">{t('routes.category')}</th><th class="p-2 text-right">{t('metrics.requests')}</th>{#each trafficOrigins as value (value)}<th class="p-2 text-right">{t(`origins.${value}`)}</th>{/each}<th class="p-2 text-right">{t('metrics.errors')}</th><th class="p-2 text-right">{t('metrics.response_bytes')}</th><th class="p-2 text-right">{t('metrics.latency_avg')}</th><th class="p-2 text-right">{t('metrics.latency_ms_max')}</th></tr></thead>
                        <tbody>{#each snapshot.routes as row (row.route)}<tr class="border-t border-line"><td class="p-2 font-mono whitespace-nowrap">{row.route}</td><td class="p-2 text-right">{formatTrafficValue(row.requests)}</td>{#each trafficOrigins as value (value)}<td class="p-2 text-right">{formatTrafficValue(row.origins[value])}</td>{/each}<td class="p-2 text-right">{formatTrafficValue(row.errors)}</td><td class="p-2 text-right whitespace-nowrap">{formatTrafficValue(row.response_bytes, 'response_bytes')}</td><td class="p-2 text-right whitespace-nowrap">{formatTrafficValue(metricValue(row, 'latency_avg'), 'latency_avg')}</td><td class="p-2 text-right whitespace-nowrap">{formatTrafficValue(row.latency_ms_max, 'latency_ms_max')}</td></tr>{/each}</tbody>
					</table></TableShell>
				{/if}
			</Card>
		{/if}
		<TrafficCoverage {snapshot} {source} />
	</div>
</PageShell>
