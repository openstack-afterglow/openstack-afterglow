<script lang="ts">
	import { untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api } from '$lib/api/client';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import {
		Alert,
		CapacityBar,
		Card,
		EmptyState,
		PageHeader,
		PageShell,
		Pill,
		ResourceToolbar,
		SectionHeader,
		StatTile,
		ToggleGroup,
	} from '$lib/components/ui';
	import type { ChatUsage } from '$lib/api/chatTree';

	interface FlavorHour {
		flavor: string;
		instance_count: number;
		usage_hours: number;
	}

	interface UsageReport {
		range: string;
		start: string;
		end: string;
		stats: {
			instance_hours: number;
			vcpu_hours: number;
			active_instances: number;
			total_instances: number;
		};
		flavor_hours: FlavorHour[];
		forecast: {
			vcpu_pct: number;
		};
	}



	let data = $state<UsageReport | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let period = $state<'7d' | '30d' | '90d'>('30d');

	let chatUsage = $state<ChatUsage | null>(null);

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	async function fetchData() {
		if (!token || !projectId) return;
		loading = !data;
		error = null;
		try {
			const res = await api.get<UsageReport>(`/api/v1/dashboard/usage-report?range=${period}`, token, projectId);
			data = res;
		} catch (e) {
			error = e instanceof Error ? e.message : '데이터 로딩 실패';
		} finally {
			loading = false;
		}
	}

	async function fetchChatUsage() {
		if (!token || !projectId) return;
		try {
			chatUsage = await api.get<ChatUsage>('/api/v1/chat/usage', token, projectId);
		} catch {
			chatUsage = null;
		}
	}

	$effect(() => {
		void [token, projectId, period];
		untrack(() => fetchData());
	});

	$effect(() => {
		void [token, projectId];
		untrack(() => fetchChatUsage());
	});

	const ar = createAutoRefresh(fetchData, {
		storageKey: 'dashboard-usage-report',
		defaultActive: true,
		defaultInterval: 300,
		intervalOptions: [60, 120, 300, 600],
		invokeOnMount: false,
	});

	const days = $derived(period === '7d' ? 7 : period === '30d' ? 30 : 90);

	const dailyAvg = $derived(
		data ? Math.round(data.stats.instance_hours / days) : 0
	);

	const sortedFlavors = $derived(
		data
			? [...data.flavor_hours].sort((a, b) => b.usage_hours - a.usage_hours)
			: []
	);

	function isGpu(flavorName: string): boolean {
		const lower = flavorName.toLowerCase();
		return lower.startsWith('g1.') || lower.startsWith('gpu');
	}
</script>

<PageShell class="space-y-6">
	<PageHeader
		breadcrumb="USAGE REPORT"
		title="기간 사용량 & 쿼터 예측"
		subtitle={data ? `${data.start} ~ ${data.end} · 인스턴스 활성 시간(instance-hours)` : '인스턴스 활성 시간(instance-hours)'}
	/>
	<ResourceToolbar label="사용량 리포트 조회 설정">
		{#snippet filters()}
			<ToggleGroup
				value={period}
				options={[
					{ value: '7d', label: '7d' },
					{ value: '30d', label: '30d' },
					{ value: '90d', label: '90d' },
				]}
				onchange={(next) => { period = next as typeof period; }}
				ariaLabel="리포트 조회 기간"
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
		<!-- KPI StatTiles -->
		<div class="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line lg:grid-cols-4">
			<StatTile
				label="누계 인스턴스-시간"
				value={data.stats.instance_hours.toFixed(1)}
				unit="h"
				accent="blue"
				flat
			>
				{#snippet icon()}
					<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
						<circle cx="12" cy="12" r="10"/>
						<polyline points="12 6 12 12 16 14"/>
					</svg>
				{/snippet}
			</StatTile>

			<StatTile
				label="일평균 인스턴스-시간"
				value={dailyAvg}
				unit="h/일"
				accent="cyan"
				flat
			>
				{#snippet icon()}
					<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
						<rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
						<line x1="16" y1="2" x2="16" y2="6"/>
						<line x1="8" y1="2" x2="8" y2="6"/>
						<line x1="3" y1="10" x2="21" y2="10"/>
					</svg>
				{/snippet}
			</StatTile>

			<StatTile
				label="활성 인스턴스"
				value={data.stats.active_instances}
				unit="/ {data.stats.total_instances}"
				accent="emerald"
				flat
			>
				{#snippet icon()}
					<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
						<rect x="2" y="3" width="20" height="14" rx="2"/>
						<line x1="8" y1="21" x2="16" y2="21"/>
						<line x1="12" y1="17" x2="12" y2="21"/>
					</svg>
				{/snippet}
			</StatTile>

			<StatTile
				label="vCPU 시간"
				value={data.stats.vcpu_hours.toFixed(1)}
				unit="h"
				accent="violet"
				flat
			>
				{#snippet icon()}
					<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
						<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
					</svg>
				{/snippet}
			</StatTile>
		</div>

		<!-- Optimization hint -->
		{#if data.forecast.vcpu_pct >= 80}
			<div class="bg-surface-base border border-[var(--color-state-warning)] rounded-lg p-4 flex items-start gap-3">
				<svg class="flex-shrink-0 mt-0.5" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--color-state-warning)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
					<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
					<line x1="12" y1="9" x2="12" y2="13"/>
					<line x1="12" y1="17" x2="12.01" y2="17"/>
				</svg>
				<p class="text-sm text-[var(--color-state-warning)]">
					<span class="font-semibold">최적화 제안:</span> vCPU 사용률이 높습니다. 사용량이 낮은 인스턴스를 확인하세요.
				</p>
			</div>
		{/if}

		<!-- 2-col layout -->
		<div class="grid grid-cols-1 lg:grid-cols-[2fr_1fr] gap-3.5">
			<!-- Flavor usage table -->
			<div class="bg-surface-base border border-line rounded-lg p-5">
				<SectionHeader title="플레이버별 사용 시간" meta="{sortedFlavors.length}종" />
				{#if sortedFlavors.length === 0}
					<div class="mt-6 text-center text-sm text-ink-3 py-6">데이터 없음</div>
				{:else}
					<div class="mt-4 overflow-x-auto">
						<table class="w-full text-xs">
							<thead>
								<tr class="border-b border-line">
									<th class="text-left pb-2 text-[10px] uppercase tracking-wide text-[var(--color-ink-3)] font-medium">Flavor</th>
									<th class="text-right pb-2 text-[10px] uppercase tracking-wide text-[var(--color-ink-3)] font-medium">사용 시간(h)</th>
									<th class="text-right pb-2 text-[10px] uppercase tracking-wide text-[var(--color-ink-3)] font-medium">VM 수</th>
								</tr>
							</thead>
							<tbody>
								{#each sortedFlavors as f}
									<tr class="border-b border-line/50 hover:bg-surface-sunken/30 transition-colors">
										<td class="py-2.5">
											<div class="flex items-center gap-2">
												<span class="text-ink-0 font-mono">{f.flavor}</span>
												{#if isGpu(f.flavor)}
													<Pill tone="accent">GPU</Pill>
												{/if}
											</div>
										</td>
										<td class="py-2.5 text-right text-ink-0 font-medium">{f.usage_hours.toFixed(1)}</td>
										<td class="py-2.5 text-right text-ink-2">{f.instance_count}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
			</div>

			<!-- Quota forecast -->
			<div class="bg-surface-base border border-line rounded-lg p-5 flex flex-col gap-4">
				<SectionHeader title="쿼터 예측" />
				<div class="space-y-3">
					<CapacityBar
						label="vCPU 사용률"
						used={data.forecast.vcpu_pct}
						total={100}
						unit="%"
						size="sm"
					/>
				</div>
				<p class="text-[11px] text-ink-3 mt-auto">선형 예측 (7일 추세 기반)</p>
			</div>
		</div>

		<!-- LLM 채팅 사용량 (빌트인) -->
		{#if chatUsage?.found}
			<Card padding="lg">
				<SectionHeader title="AI 채팅 사용량" meta="빌트인 채팅" />
				<div class="grid grid-cols-2 lg:grid-cols-3 gap-3.5 mt-4">
					<StatTile
						label="이번 달 토큰"
						value={(chatUsage.month_prompt_tokens + chatUsage.month_completion_tokens).toLocaleString()}
						accent="blue"
					>
						{#snippet icon()}
							<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
								<path d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
							</svg>
						{/snippet}
					</StatTile>
					<StatTile label="입력 토큰" value={chatUsage.month_prompt_tokens.toLocaleString()} accent="blue" />
					<StatTile label="출력 토큰" value={chatUsage.month_completion_tokens.toLocaleString()} accent="cyan" />
					<StatTile
						label="이번 달 크레딧"
						value={chatUsage.month_credited_cost.toLocaleString()}
						accent="violet"
					>
						{#snippet icon()}
							<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
								<circle cx="12" cy="12" r="10"/>
							</svg>
						{/snippet}
					</StatTile>
					<StatTile
						label="이번 달 요청"
						value={chatUsage.month_request_count}
						accent="cyan"
					>
						{#snippet icon()}
							<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
								<rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
							</svg>
						{/snippet}
					</StatTile>
					<StatTile label="월 quota" value={`${chatUsage.quota_used.toLocaleString()} / ${chatUsage.quota_max.toLocaleString()}`} accent="amber" />
				</div>
			</Card>
		{/if}
	{:else}
		<EmptyState headline="사용량 리포트가 없습니다" description="선택한 기간에 집계된 사용량이 없습니다." />
	{/if}
</PageShell>
