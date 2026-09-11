<script lang="ts">
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
		{ key: 'hour', label: '시간' },
		{ key: 'day', label: '일' },
		{ key: 'month', label: '월' }
	];

	const points = $derived(pivotTimeseries(series, 'total_tokens'));
	const maxTotal = $derived(Math.max(1, ...points.map((p) => Number(p.total) || 0)));
	const web = $derived(sourceRow(bySource, 'web'));
	const apiUse = $derived(sourceRow(bySource, 'api'));

	function fmt(n: number): string {
		return new Intl.NumberFormat().format(Math.round(n));
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
		<h4 class="mb-2 text-xs font-semibold text-[var(--color-ink-2)]">접근 경로 (누적)</h4>
		<div class="grid grid-cols-2 gap-2">
			<div class="{cardCls} px-3 py-2">
				<div class="text-xs text-[var(--color-ink-3)]">웹</div>
				<div class="text-sm font-semibold text-[var(--color-ink-1)]">{fmt(web.tokens)} 토큰</div>
				<div class="text-xs text-[var(--color-ink-3)]">{fmt(web.request_count)} 요청</div>
			</div>
			<div class="{cardCls} px-3 py-2">
				<div class="text-xs text-[var(--color-ink-3)]">API</div>
				<div class="text-sm font-semibold text-[var(--color-ink-1)]">{fmt(apiUse.tokens)} 토큰</div>
				<div class="text-xs text-[var(--color-ink-3)]">{fmt(apiUse.request_count)} 요청</div>
			</div>
		</div>
	</div>

	<!-- 시계열 (web/api 스택) -->
	<div>
		<div class="mb-2 flex items-center justify-between">
			<h4 class="text-xs font-semibold text-[var(--color-ink-2)]">사용량 추이</h4>
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
			<div class="{cardCls} h-24 animate-pulse"></div>
		{:else if points.length === 0}
			<p class="px-1 text-xs text-[var(--color-ink-3)]">사용 기록이 없습니다.</p>
		{:else}
			<div class="{cardCls} space-y-1 p-3">
				{#each points as p (p.bucket)}
					<div class="flex items-center gap-2">
						<span class="w-24 shrink-0 truncate font-mono text-[10px] text-[var(--color-ink-3)]">{bucketLabel(String(p.bucket))}</span>
						<div class="flex h-3 flex-1 overflow-hidden rounded bg-[var(--color-surface-sunken)]">
							<div class="h-full bg-[var(--color-accent)]" style="width: {((Number(p.web) || 0) / maxTotal) * 100}%" title="웹 {fmt(Number(p.web) || 0)}"></div>
							<div class="h-full bg-[var(--color-state-success)]" style="width: {((Number(p.api) || 0) / maxTotal) * 100}%" title="API {fmt(Number(p.api) || 0)}"></div>
						</div>
						<span class="w-16 shrink-0 text-right text-[10px] text-[var(--color-ink-3)]">{fmt(Number(p.total) || 0)}</span>
					</div>
				{/each}
				<div class="mt-1 flex gap-3 text-[10px] text-[var(--color-ink-3)]">
					<span><span class="inline-block h-2 w-2 rounded-sm bg-[var(--color-accent)]"></span> 웹</span>
					<span><span class="inline-block h-2 w-2 rounded-sm bg-[var(--color-state-success)]"></span> API</span>
				</div>
			</div>
		{/if}
	</div>

	<!-- API 키별 -->
	{#if keys.length}
		<div>
			<h4 class="mb-2 text-xs font-semibold text-[var(--color-ink-2)]">API 키별 사용량</h4>
			<div class="{cardCls} divide-y divide-[var(--color-line)]">
				{#each keys as k (k.api_key_id)}
					<div class="flex items-center justify-between px-3 py-2">
						<span class="truncate text-xs text-[var(--color-ink-1)]">{k.name || k.key_prefix || `키 #${k.api_key_id}`}</span>
						<span class="shrink-0 text-xs text-[var(--color-ink-3)]">{fmt(k.total_tokens)} 토큰 · {fmt(k.request_count)} 요청</span>
					</div>
				{/each}
			</div>
		</div>
	{/if}
</div>
