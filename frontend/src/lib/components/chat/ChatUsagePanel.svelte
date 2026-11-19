<script lang="ts">
	import { untrack } from 'svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import { t } from '$lib/i18n/ns/chat-settings';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { auth } from '$lib/stores/auth';
	import { api } from '$lib/api/client';
	import BklitChart from '$lib/components/charts/BklitChart.svelte';
	import type { ChartDatum, ChartSpec } from '$lib/components/charts/types';
	import {
		domainViewDenied,
		sourceRow,
		usagePath,
		type BillingScope,
		type TimeseriesRow,
		type KeyUsage,
		type UsageBySource,
		type UsageView
	} from '$lib/api/chatUsage';

	interface Props {
		view?: UsageView;
		/** Lumen refused the domain view; the owner falls back to the personal view. */
		ondenied?: () => void;
	}
	let { view = 'self', ondenied }: Props = $props();

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	// 접근경로(web/api) 누적 분해 — /usage 요약의 by_source.
	let bySource = $state<UsageBySource[]>([]);
	// 시계열 — 버킷 토글(시간/일/월). range 는 버킷에 맞춰 자동.
	let bucket = $state<'hour' | 'day' | 'month'>('day');
	let series = $state<TimeseriesRow[]>([]);
	let keys = $state<KeyUsage[]>([]);
	let loading = $state(true);
	// Responses from a superseded view or session never overwrite the current one.
	let generation = 0;

	const _RANGE_FOR: Record<string, string> = { hour: '30d', day: '30d', month: '1y' };
	const BUCKETS: { key: 'hour' | 'day' | 'month'; label: string }[] = [
		{ key: 'hour', get label() { return t('usage.buckets.hour'); } },
		{ key: 'day', get label() { return t('usage.buckets.day'); } },
		{ key: 'month', get label() { return t('usage.buckets.month'); } }
	];

	const points = $derived.by(() => {
		const buckets = new Map<string, ChartDatum>();
		for (const sample of series) {
			const point = buckets.get(sample.bucket) ?? { bucket: sample.bucket, total: 0 };
			const key = sample.source || 'web';
			const value = sample.total_tokens;
			const measured = typeof value === 'number' && Number.isFinite(value);
			point[key] = !measured || point[key] === null ? null : (typeof point[key] === 'number' ? point[key] : 0) + value;
			point.total = !measured || point.total === null ? null : Number(point.total) + value;
			buckets.set(sample.bucket, point);
		}
		return [...buckets.values()].sort((a, b) => String(a.bucket).localeCompare(String(b.bucket)));
	});
	const maxTotal = $derived(Math.max(1, ...points.map((point) => typeof point.total === 'number' && Number.isFinite(point.total) ? point.total : 0)));
	const web = $derived(sourceRow(bySource, 'web'));
	const apiUse = $derived(sourceRow(bySource, 'api'));
	const payerCredits = $derived.by(() => {
		const byBucket = new Map<string, Record<BillingScope, number>>();
		for (const sample of series) {
			const split = sample.credited_cost_by_payer;
			if (!split) continue;
			const total = byBucket.get(sample.bucket) ?? { user: 0, domain: 0 };
			total.user += split.user ?? 0;
			total.domain += split.domain ?? 0;
			byBucket.set(sample.bucket, total);
		}
		return byBucket;
	});

	function fmt(n: number): string {
		return new Intl.NumberFormat(intlLocale()).format(Math.round(n));
	}
	function fmtCredit(n: number): string {
		return new Intl.NumberFormat(intlLocale(), { maximumFractionDigits: 2 }).format(n);
	}
	function payerLabel(scope: BillingScope): string {
		return scope === 'domain' ? t('usage.payer.domain') : t('usage.payer.user');
	}
	function payerSplit(split: Record<BillingScope, number>): string {
		return (['user', 'domain'] as const)
			.filter((scope) => split[scope] > 0)
			.map((scope) => t('usage.payerCredits', { payer: payerLabel(scope), credits: fmtCredit(split[scope]) }))
			.join(' · ');
	}
	function bucketLabel(b: string): string {
		return bucket === 'month' ? b : bucket === 'hour' ? b.slice(5, 16) : b.slice(5);
	}

	const usageChart: ChartSpec = $derived({
		kind: 'bar',
		data: points.map((point) => ({ ...point, bucket: bucketLabel(String(point.bucket)) })),
		xKey: 'bucket',
		series: [
			{ key: 'web', label: t('usage.web'), color: 'var(--color-accent)' },
			{ key: 'api', label: 'API', color: 'var(--color-state-success)' },
		],
		stacked: true,
		orientation: 'horizontal',
		domain: [0, maxTotal],
		formatValue: fmt,
	});

	// One load generation: the view, session and project it was issued for.
	interface UsageRequest { view: UsageView; token: string; projectId: string | undefined; generation: number }

	/** `undefined` when superseded; `null` when the read failed. */
	async function read<T>(path: string, request: UsageRequest): Promise<T | null | undefined> {
		try {
			const result = await api.get<T>(usagePath(path, request.view), request.token, request.projectId);
			return request.generation === generation ? result : undefined;
		} catch (cause) {
			if (request.generation !== generation) return undefined;
			if (request.view === 'domain' && domainViewDenied(cause)) ondenied?.();
			return null;
		}
	}
	async function loadSummary(request: UsageRequest) {
		const s = await read<{ by_source: UsageBySource[] }>('/api/v1/chat/usage', request);
		if (s !== undefined) bySource = s?.by_source ?? [];
	}
	async function loadKeys(request: UsageRequest) {
		const r = await read<{ keys: KeyUsage[] }>('/api/v1/chat/usage/keys', request);
		if (r !== undefined) keys = r?.keys ?? [];
	}
	async function loadSeries(request: UsageRequest) {
		const r = await read<{ series: TimeseriesRow[] }>(
			`/api/v1/chat/usage/timeseries?bucket=${bucket}&range=${_RANGE_FOR[bucket]}`,
			request
		);
		if (r !== undefined) series = r?.series ?? [];
	}

	function setBucket(b: 'hour' | 'day' | 'month') {
		bucket = b;
		if (token) void loadSeries({ view, token, projectId, generation });
	}

	$effect(() => {
		const requestToken = token;
		if (!requestToken) return;
		const current: UsageRequest = { view, token: requestToken, projectId, generation: ++generation };
		untrack(() => {
			loading = true;
			void Promise.all([loadSummary(current), loadSeries(current), loadKeys(current)])
				.finally(() => { if (current.generation === generation) loading = false; });
		});
	});

</script>

<div class="space-y-4">
	<!-- 접근경로 분해 -->
	<div>
		<h3 class="mb-2 text-xs font-semibold text-[var(--color-ink-2)]">{t('usage.sourcesTitle')}</h3>
		<div class="grid grid-cols-2 gap-4 divide-x divide-[var(--color-line)]">
			<div class="py-2">
				<div class="text-xs text-[var(--color-ink-2)]">{t('usage.web')}</div>
				<div class="text-sm font-semibold text-[var(--color-ink-1)]">{t('usage.tokens', { count: Math.round(web.tokens) })}</div>
				<div class="text-xs text-[var(--color-ink-2)]">{t('usage.requests', { count: Math.round(web.request_count) })}</div>
			</div>
			<div class="py-2 pl-4">
				<div class="text-xs text-[var(--color-ink-2)]">API</div>
				<div class="text-sm font-semibold text-[var(--color-ink-1)]">{t('usage.tokens', { count: Math.round(apiUse.tokens) })}</div>
				<div class="text-xs text-[var(--color-ink-2)]">{t('usage.requests', { count: Math.round(apiUse.request_count) })}</div>
			</div>
		</div>
	</div>

	<!-- 시계열 (web/api 스택) -->
	<div class="border-t border-[var(--color-line)] pt-4">
		<div class="mb-2 flex flex-wrap items-center justify-between gap-2">
			<h3 class="text-xs font-semibold text-[var(--color-ink-2)]">{t('usage.trendTitle')}</h3>
			<div class="flex gap-1">
				{#each BUCKETS as b (b.key)}
					<button
						type="button"
						aria-pressed={bucket === b.key}
						class="rounded px-2 py-0.5 text-xs {bucket === b.key
							? 'bg-[var(--color-surface-selected)] text-ink-0'
							: 'text-[var(--color-ink-2)] hover:text-[var(--color-ink-1)]'}"
						onclick={() => setBucket(b.key)}>{b.label}</button
					>
				{/each}
			</div>
		</div>
		{#if loading}
			<LoadingState label={t('usage.trendLoading')} />
		{:else if points.length === 0}
			<p class="px-1 text-xs text-[var(--color-ink-2)]">{t('usage.empty')}</p>
		{:else}
			<div class="space-y-1">
				<BklitChart spec={usageChart} height={Math.max(144, points.length * 24 + 48)} label={t('usage.trendTitle')} />
				<div class="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-ink-2 tabular-nums">
					{#each points as point (point.bucket)}
						{@const split = payerCredits.get(String(point.bucket))}
						{@const payers = split ? payerSplit(split) : ''}
						<div>
							<div class="flex justify-between gap-2">
								<span class="truncate">{bucketLabel(String(point.bucket))}</span>
								<span>{typeof point.total === 'number' ? fmt(point.total) : '—'}</span>
							</div>
							{#if payers}<div class="truncate text-right">{payers}</div>{/if}
						</div>
					{/each}
				</div>
				<div class="mt-1 flex gap-3 text-xs text-[var(--color-ink-2)]">
					<span><span class="inline-block h-2 w-2 rounded-sm bg-[var(--color-accent)]"></span> {t('usage.web')}</span>
					<span><span class="inline-block h-2 w-2 rounded-sm bg-[var(--color-state-success)]"></span> API</span>
				</div>
			</div>
		{/if}
	</div>

	<!-- API 키별 -->
	{#if keys.length}
		<div class="border-t border-[var(--color-line)] pt-4">
			<h3 class="mb-2 text-xs font-semibold text-[var(--color-ink-2)]">{t('usage.keysTitle')}</h3>
			<div class="divide-y divide-[var(--color-line)]">
				{#each keys as k (`${k.api_key_id}:${k.billing_scope ?? ''}`)}
					<div class="flex flex-wrap items-center justify-between gap-2 py-2">
						<span class="flex min-w-0 items-center gap-2">
							<span class="truncate text-xs text-[var(--color-ink-1)]">{k.name || k.key_prefix || t('usage.keyFallback', { id: k.api_key_id })}</span>
							{#if k.billing_scope}<Pill size="xs">{payerLabel(k.billing_scope)}</Pill>{/if}
						</span>
						<span class="text-xs text-[var(--color-ink-2)]">{t('usage.keySummary', { tokens: Math.round(k.total_tokens), requests: Math.round(k.request_count) })}</span>
					</div>
				{/each}
			</div>
		</div>
	{/if}
</div>
