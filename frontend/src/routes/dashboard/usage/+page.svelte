<script lang="ts">
	import { untrack } from 'svelte';
	import { auth, authReady } from '$lib/stores/auth';
	import { api } from '$lib/api/client';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import {
		Alert,
		EmptyState,
		PageHeader,
		PageShell,
		Pill,
		QuotaBar,
		ResourceToolbar,
		SectionHeader,
		Spark,
		StatusChip,
		ToggleGroup,
	} from '$lib/components/ui';

	interface TopInstance {
		id: string;
		name: string;
		flavor_name: string;
		vcpus: number;
		ram_mb: number;
		disk_gb: number;
		status: string;
		usage_hours: number;
		cpu_pct?: number | null;
		ram_pct?: number | null;
	}

	interface UsageStats {
		range: string;
		top_instances: TopInstance[];
	}

	interface TrendSeries {
		data: number[];
		points: number;
		available: boolean;
	}

	interface TrendData {
		vcpu: TrendSeries;
		memory: TrendSeries;
		storage: TrendSeries;
		network: TrendSeries & { unit: string };
		prometheus_available: boolean;
		range: '24h' | '7d' | '14d';
	}

	let data = $state<UsageStats | null>(null);
	let trendData = $state<TrendData | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let trendLoading = $state(true);
	let loadGeneration = 0;
	let period = $state<'24h' | '7d' | '30d'>('7d');

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);
	const trendRange = $derived<'24h' | '7d' | '14d'>(period === '30d' ? '14d' : period);

	async function fetchData() {
		if (!token || !projectId) return;
		const requestToken = token;
		const requestProjectId = projectId;
		const requestPeriod = period;
		const requestTrendRange = trendRange;
		const generation = ++loadGeneration;
		loading = !data;
		trendLoading = !trendData;
		error = null;
		const statsPromise = api.get<UsageStats>(
			`/api/v1/dashboard/usage-stats?range=${requestPeriod}`,
			requestToken,
			requestProjectId,
		);
		const trendPromise = api.get<TrendData>(
			`/api/v1/dashboard/metrics/trend?range=${requestTrendRange}`,
			requestToken,
			requestProjectId,
		).then((value) => {
			if (generation === loadGeneration && projectId === requestProjectId && period === requestPeriod) {
				trendData = value;
			}
		}).catch(() => {
			if (generation === loadGeneration && projectId === requestProjectId && period === requestPeriod) {
				trendData = null;
			}
		}).finally(() => {
			if (generation === loadGeneration && projectId === requestProjectId && period === requestPeriod) {
				trendLoading = false;
			}
		});
		try {
			const value = await statsPromise;
			if (generation === loadGeneration && projectId === requestProjectId && period === requestPeriod) {
				data = value;
			}
		} catch (loadError) {
			if (generation === loadGeneration && projectId === requestProjectId && period === requestPeriod) {
				error = loadError instanceof Error ? loadError.message : '데이터 로딩 실패';
			}
		} finally {
			if (generation === loadGeneration && projectId === requestProjectId && period === requestPeriod) {
				loading = false;
			}
		}
		void trendPromise;
	}

	$effect(() => {
		const pid = $auth.projectId;
		const ready = $authReady;
		void [token, projectId, period];
		if (!pid || !ready) return;
		untrack(() => fetchData());
	});

	const ar = createAutoRefresh(fetchData, {
		storageKey: 'dashboard-usage',
		defaultActive: true,
		defaultInterval: 60,
		invokeOnMount: false,
	});

	function isGpu(flavorName: string): boolean {
		const lower = flavorName.toLowerCase();
		return lower.startsWith('g1.') || lower.startsWith('gpu');
	}

	function scaleNetwork(data: number[]): { data: number[]; unit: string } {
		const maxVal = data.length > 0 ? Math.max(...data) : 0;
		if (maxVal >= 1024 * 1024) return { data: data.map(v => v / (1024 * 1024)), unit: 'GiB/s' };
		if (maxVal >= 1024) return { data: data.map(v => v / 1024), unit: 'MiB/s' };
		return { data, unit: 'KiB/s' };
	}
</script>

<PageShell class="space-y-6">
	<PageHeader breadcrumb="USAGE" title="사용량" subtitle={$auth.projectName ?? '—'} />
	<ResourceToolbar label="사용량 조회 설정">
		{#snippet filters()}
			<ToggleGroup
				value={period}
				options={[
					{ value: '24h', label: '24h' },
					{ value: '7d', label: '7d' },
					{ value: '30d', label: '30d' },
				]}
				onchange={(next) => { period = next as typeof period; }}
				ariaLabel="사용량 조회 기간"
			/>
		{/snippet}
		{#snippet actions()}
			<button
				type="button"
				onclick={() => { ar.active = !ar.active; }}
				class="min-h-8 rounded-md border border-line-2 px-3 text-xs font-medium text-ink-2 transition-colors hover:bg-surface-selected hover:text-ink-0"
				aria-pressed={ar.active}
			>자동 새로고침 {ar.active ? '켜짐' : '꺼짐'}</button>
		{/snippet}
	</ResourceToolbar>

	{#if loading}
		<LoadingSkeleton variant="table" rows={6} />
	{:else if error}
		<Alert tone="danger">{error}</Alert>
	{:else if data}
		<!-- Spark trend cards — 24h 추세 (3-row: 현재값 + 그래프 + min/max) -->
		<div class="grid grid-cols-1 sm:grid-cols-4 gap-3.5">
		{#if trendLoading}
			<div class="text-[var(--color-ink-3)] text-xs">추세 메트릭을 불러오는 중...</div>
		{/if}
			{#each [
				{ label: `vCPU ${trendRange} 추세`,    unit: '%',     color: 'var(--color-accent)',      key: 'vcpu'    as const },
				{ label: `RAM ${trendRange} 추세`,      unit: '%',     color: 'var(--color-accent-2)',    key: 'memory'  as const },
				{ label: `디스크 ${trendRange} 추세`,   unit: '%',     color: 'var(--color-warm)',        key: 'storage' as const,
				  fallback: '게스트 OS 내부 메트릭 미수집' },
				{ label: `네트워크 ${trendRange} 추세`, unit: trendData?.network?.unit ?? 'KiB/s', color: 'var(--color-state-info)', key: 'network' as const },
			] as card}
				{@const rawSeries  = trendData?.[card.key]}
				{@const netScaled  = card.key === 'network' && rawSeries?.data?.length ? scaleNetwork(rawSeries.data) : null}
				{@const seriesData = netScaled ? netScaled.data : (rawSeries?.data ?? [])}
				{@const displayUnit = netScaled ? netScaled.unit : card.unit}
				{@const hasData = seriesData.length > 0}
				{@const current = hasData ? seriesData.at(-1)! : null}
				{@const min     = hasData ? Math.min(...seriesData) : null}
				{@const max     = hasData ? Math.max(...seriesData) : null}
				<div class="bg-surface-base border border-line rounded-lg p-5 flex flex-col gap-2">
					<div class="flex items-baseline justify-between">
						<p class="text-[10px] uppercase tracking-wide text-[var(--color-ink-3)]">{card.label}</p>
						{#if current !== null}
							<span class="text-xl font-semibold tabular-nums text-[var(--color-ink-0)]">
								{current.toFixed(1)}<span class="text-[10px] text-[var(--color-ink-3)] ml-0.5">{displayUnit}</span>
							</span>
						{/if}
					</div>
					<div class="min-h-[72px] flex items-center">
						{#if hasData}
							<Spark data={seriesData} color={card.color} height={72} class="w-full" />
						{:else if !trendData || !trendData.prometheus_available}
							<p class="text-[11px] italic text-[var(--color-ink-3)]">메트릭 수집 미설정</p>
						{:else if 'fallback' in card}
							<p class="text-[11px] italic text-[var(--color-ink-3)]">{card.fallback}</p>
						{:else}
							<p class="text-[11px] text-[var(--color-ink-3)]">수집 대기 중</p>
						{/if}
					</div>
					{#if hasData}
						<p class="text-[10px] tabular-nums text-[var(--color-ink-3)]">
							min {min!.toFixed(1)}{displayUnit} · max {max!.toFixed(1)}{displayUnit}
						</p>
					{/if}
				</div>
			{/each}
		</div>

		<!-- Top consumers table -->
		<div class="bg-surface-base border border-line rounded-lg p-5">
			<SectionHeader title="상위 인스턴스" meta="{data.top_instances.length}개" />
			{#if data.top_instances.length === 0}
				<div class="mt-6 text-center text-sm text-ink-3 py-6">인스턴스 없음</div>
			{:else}
				<div class="mt-4 overflow-x-auto">
					<table class="w-full text-xs">
						<thead>
							<tr class="border-b border-line">
								<th class="text-left pb-2 text-[10px] uppercase tracking-wide text-[var(--color-ink-3)] font-medium w-8">#</th>
								<th class="text-left pb-2 text-[10px] uppercase tracking-wide text-[var(--color-ink-3)] font-medium">인스턴스</th>
								<th class="text-left pb-2 text-[10px] uppercase tracking-wide text-[var(--color-ink-3)] font-medium">플레이버</th>
								<th class="text-left pb-2 text-[10px] uppercase tracking-wide text-[var(--color-ink-3)] font-medium w-44">vCPU</th>
								<th class="text-left pb-2 text-[10px] uppercase tracking-wide text-[var(--color-ink-3)] font-medium w-44">RAM</th>
								<th class="text-left pb-2 text-[10px] uppercase tracking-wide text-[var(--color-ink-3)] font-medium">상태</th>
							</tr>
						</thead>
						<tbody>
							{#each data.top_instances as inst, i}
								<tr class="border-b border-line/50 hover:bg-surface-sunken/30 transition-colors">
									<td class="py-2.5 text-ink-3 font-mono">{i + 1}</td>
									<td class="py-2.5">
										<div class="flex items-center gap-2">
											<span class="text-ink-0 font-medium truncate max-w-[140px]">{inst.name}</span>
											{#if isGpu(inst.flavor_name)}
												<Pill tone="accent">GPU</Pill>
											{/if}
										</div>
									</td>
									<td class="py-2.5 text-ink-2 font-mono">{inst.flavor_name}</td>
									<td class="py-2.5 pr-4">
										<div class="flex items-center gap-2">
											<span class="tabular-nums text-ink-0 font-medium whitespace-nowrap">{inst.vcpus} vCPU</span>
											<span class="tabular-nums text-[var(--color-ink-3)] w-8 text-right shrink-0">
												{inst.cpu_pct != null ? `${inst.cpu_pct.toFixed(0)}%` : '—'}
											</span>
											<div class="flex-1 min-w-[48px]">
												<QuotaBar label="" used={inst.cpu_pct ?? 0} limit={100} size="xs" showValue={false} />
											</div>
										</div>
									</td>
									<td class="py-2.5 pr-4">
										<div class="flex items-center gap-2">
											<span class="tabular-nums text-ink-0 font-medium whitespace-nowrap">{Math.round(inst.ram_mb / 1024)} GB</span>
											<span class="tabular-nums text-[var(--color-ink-3)] w-8 text-right shrink-0">
												{inst.ram_pct != null ? `${inst.ram_pct.toFixed(0)}%` : '—'}
											</span>
											<div class="flex-1 min-w-[48px]">
												<QuotaBar label="" used={inst.ram_pct ?? 0} limit={100} size="xs" showValue={false} />
											</div>
										</div>
									</td>
									<td class="py-2.5">
										<StatusChip status={inst.status} />
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
		</div>
	{:else}
		<EmptyState headline="사용량 데이터가 없습니다" description="프로젝트 리소스가 생성되면 사용량이 표시됩니다." />
	{/if}
</PageShell>
