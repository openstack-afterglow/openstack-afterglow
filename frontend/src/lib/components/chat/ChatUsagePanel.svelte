<script lang="ts">
	import { t } from '$lib/i18n/ns/chat-settings';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { auth } from '$lib/stores/auth';
	import { api } from '$lib/api/client';
	import {
		pivotTimeseries,
		sourceRow,
		type TimeseriesRow,
		type KeyUsage,
		type UsageBySource
	} from '$lib/api/chatUsage';

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	// 접근경로(web/api) 누적 분해 — /usage 요약의 by_source.
	let bySource = $state<UsageBySource[]>([]);
	// 시계열 — 버킷 토글(시간/일/월). range 는 버킷에 맞춰 자동.
	let bucket = $state<'hour' | 'day' | 'month'>('day');
	let series = $state<TimeseriesRow[]>([]);
	let keys = $state<KeyUsage[]>([]);
	let loading = $state(true);

	const _RANGE_FOR: Record<string, string> = { hour: '30d', day: '30d', month: '1y' };
	const BUCKETS: { key: 'hour' | 'day' | 'month'; label: string }[] = [
		{ key: 'hour', get label() { return t('usage.buckets.hour'); } },
		{ key: 'day', get label() { return t('usage.buckets.day'); } },
		{ key: 'month', get label() { return t('usage.buckets.month'); } }
	];

	const points = $derived(pivotTimeseries(series, 'total_tokens'));
	const maxTotal = $derived(Math.max(1, ...points.map((p) => Number(p.total) || 0)));
	const web = $derived(sourceRow(bySource, 'web'));
	const apiUse = $derived(sourceRow(bySource, 'api'));

	function fmt(n: number): string {
		return new Intl.NumberFormat(intlLocale()).format(Math.round(n));
	}
	function bucketLabel(b: string): string {
		return bucket === 'month' ? b : bucket === 'hour' ? b.slice(5, 16) : b.slice(5);
	}

	async function loadSummary() {
		if (!token) return;
		try {
			const s = await api.get<{ by_source: UsageBySource[] }>('/api/v1/chat/usage', token, projectId);
			bySource = s.by_source ?? [];
		} catch {
			bySource = [];
		}
	}
	async function loadKeys() {
		if (!token) return;
		try {
			const r = await api.get<{ keys: KeyUsage[] }>('/api/v1/chat/usage/keys', token, projectId);
			keys = r.keys ?? [];
		} catch {
			keys = [];
		}
	}
	async function loadSeries() {
		if (!token) return;
		try {
			const r = await api.get<{ series: TimeseriesRow[] }>(
				`/api/v1/chat/usage/timeseries?bucket=${bucket}&range=${_RANGE_FOR[bucket]}`,
				token,
				projectId
			);
			series = r.series ?? [];
		} catch {
			series = [];
		}
	}

	function setBucket(b: 'hour' | 'day' | 'month') {
		bucket = b;
		void loadSeries();
	}

	$effect(() => {
		if (!token) return;
		loading = true;
		void Promise.all([loadSummary(), loadSeries(), loadKeys()]).finally(() => (loading = false));
	});

	const cardCls = 'rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-raised)]';
</script>

<div class="space-y-4">
	<!-- 접근경로 분해 -->
	<div>
		<h4 class="mb-2 text-xs font-semibold text-[var(--color-ink-2)]">{t('usage.sourcesTitle')}</h4>
		<div class="grid grid-cols-2 gap-2">
			<div class="{cardCls} px-3 py-2">
				<div class="text-xs text-[var(--color-ink-3)]">{t('usage.web')}</div>
				<div class="text-sm font-semibold text-[var(--color-ink-1)]">{t('usage.tokens', { count: Math.round(web.tokens) })}</div>
				<div class="text-xs text-[var(--color-ink-3)]">{t('usage.requests', { count: Math.round(web.request_count) })}</div>
			</div>
			<div class="{cardCls} px-3 py-2">
				<div class="text-xs text-[var(--color-ink-3)]">API</div>
				<div class="text-sm font-semibold text-[var(--color-ink-1)]">{t('usage.tokens', { count: Math.round(apiUse.tokens) })}</div>
				<div class="text-xs text-[var(--color-ink-3)]">{t('usage.requests', { count: Math.round(apiUse.request_count) })}</div>
			</div>
		</div>
	</div>

	<!-- 시계열 (web/api 스택) -->
	<div>
		<div class="mb-2 flex items-center justify-between">
			<h4 class="text-xs font-semibold text-[var(--color-ink-2)]">{t('usage.trendTitle')}</h4>
			<div class="flex gap-1">
				{#each BUCKETS as b (b.key)}
					<button
						class="rounded px-2 py-0.5 text-xs {bucket === b.key
							? 'bg-[var(--color-accent)] text-ink-0'
							: 'text-[var(--color-ink-3)] hover:text-[var(--color-ink-1)]'}"
						onclick={() => setBucket(b.key)}>{b.label}</button
					>
				{/each}
			</div>
		</div>
		{#if loading}
			<div class="motion-skeleton rounded-lg border border-line h-24" role="status" aria-label={t('usage.trendLoading')}>
				<span class="sr-only">{t('usage.trendLoading')}</span>
			</div>
		{:else if points.length === 0}
			<p class="px-1 text-xs text-[var(--color-ink-3)]">{t('usage.empty')}</p>
		{:else}
			<div class="{cardCls} space-y-1 p-3">
				{#each points as p (p.bucket)}
					<div class="flex items-center gap-2">
						<span class="w-24 shrink-0 truncate font-mono text-xs text-[var(--color-ink-3)]">{bucketLabel(String(p.bucket))}</span>
						<div class="flex h-3 flex-1 overflow-hidden rounded bg-[var(--color-surface-sunken)]">
							<div class="h-full bg-[var(--color-accent)]" style="width: {((Number(p.web) || 0) / maxTotal) * 100}%" title={t('usage.webTooltip', { count: fmt(Number(p.web) || 0) })}></div>
							<div class="h-full bg-[var(--color-state-success)]" style="width: {((Number(p.api) || 0) / maxTotal) * 100}%" title={t('usage.apiTooltip', { count: fmt(Number(p.api) || 0) })}></div>
						</div>
						<span class="w-16 shrink-0 text-right text-xs text-[var(--color-ink-3)]">{fmt(Number(p.total) || 0)}</span>
					</div>
				{/each}
				<div class="mt-1 flex gap-3 text-xs text-[var(--color-ink-3)]">
					<span><span class="inline-block h-2 w-2 rounded-sm bg-[var(--color-accent)]"></span> {t('usage.web')}</span>
					<span><span class="inline-block h-2 w-2 rounded-sm bg-[var(--color-state-success)]"></span> API</span>
				</div>
			</div>
		{/if}
	</div>

	<!-- API 키별 -->
	{#if keys.length}
		<div>
			<h4 class="mb-2 text-xs font-semibold text-[var(--color-ink-2)]">{t('usage.keysTitle')}</h4>
			<div class="{cardCls} divide-y divide-[var(--color-line)]">
				{#each keys as k (k.api_key_id)}
					<div class="flex items-center justify-between px-3 py-2">
						<span class="truncate text-xs text-[var(--color-ink-1)]">{k.name || k.key_prefix || t('usage.keyFallback', { id: k.api_key_id })}</span>
						<span class="shrink-0 text-xs text-[var(--color-ink-3)]">{t('usage.keySummary', { tokens: Math.round(k.total_tokens), requests: Math.round(k.request_count) })}</span>
					</div>
				{/each}
			</div>
		</div>
	{/if}
</div>
