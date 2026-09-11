<script lang="ts">
	import { untrack } from 'svelte';
	import { auth, authReady } from '$lib/stores/auth';
	import { api } from '$lib/api/client';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import { Alert, PageHeader, PageShell, Pill, ResourceToolbar, SectionHeader, StatTile, ToggleGroup } from '$lib/components/ui';

	interface KPI {
		total: number;
		success: number;
		failed: number;
		last_24h: number;
		unique_users: number;
	}

	interface RecentAction {
		id: number;
		created_at: string;
		action: string;
		resource_type: string;
		resource_name: string;
		status: string;
		user_id: string;
		error_message: string | null;
	}

	interface ActivityData {
		range: string;
		kpi: KPI;
		hour_distribution: number[];
		recent_actions: RecentAction[];
		db_status?: 'ok' | 'unavailable';
	}

	let data = $state<ActivityData | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let period = $state<'24h' | '7d' | '30d'>('7d');

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	async function fetchData() {
		if (!token || !projectId) return;
		loading = !data;
		error = null;
		try {
			const res = await api.get<ActivityData>(`/api/v1/dashboard/activity?range=${period}`, token, projectId);
			data = res;
		} catch (e) {
			error = e instanceof Error ? e.message : '데이터 로딩 실패';
		} finally {
			loading = false;
		}
	}

	const ar = createAutoRefresh(fetchData, {
		storageKey: 'dashboard-activity',
		defaultActive: true,
		defaultInterval: 30,
		invokeOnMount: false,
	});

	$effect(() => {
		const pid = $auth.projectId;
		const ready = $authReady;
		void [token, projectId, period];
		if (!pid || !ready) return;
		untrack(() => fetchData());
	});

	// Derived KPI values
	const kpi = $derived(data?.kpi ?? { total: 0, success: 0, failed: 0, last_24h: 0, unique_users: 0 });
	const successRate = $derived(kpi.total > 0 ? `${Math.round((kpi.success / kpi.total) * 100)}` : '—');
	const hourDist = $derived(data?.hour_distribution ?? Array(24).fill(0));
	const recentActions = $derived(data?.recent_actions ?? []);

	// Bar chart derived values
	const maxHour = $derived(Math.max(...hourDist) || 1);

	function barColor(idx: number, val: number): string {
		if (val === 0) return 'color-mix(in oklab, var(--color-ink-3) 25%, transparent)';
		if (val === Math.max(...hourDist) && val > 0) return 'var(--color-warm)';
		return 'color-mix(in oklab, var(--color-accent) 55%, transparent)';
	}

	function formatHour(created_at: string): string {
		try {
			const d = new Date(created_at);
			return d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', hour12: false });
		} catch {
			return '—';
		}
	}

	type ActionBadgeStyle = {
		bg: string;
		text: string;
	};

	function actionBadgeStyle(action: string): ActionBadgeStyle {
		if (action.startsWith('instance.delete')) {
			return { bg: 'color-mix(in oklab, var(--color-state-danger) 14%, transparent)', text: 'var(--color-state-danger)' };
		} else if (action.startsWith('instance.')) {
			return { bg: 'color-mix(in oklab, var(--color-accent) 14%, transparent)', text: 'var(--color-accent)' };
		} else if (action.startsWith('volume.')) {
			return { bg: 'color-mix(in oklab, var(--color-state-info) 14%, transparent)', text: 'var(--color-state-info)' };
		} else if (action.startsWith('snapshot.')) {
			return { bg: 'color-mix(in oklab, var(--color-accent-2) 14%, transparent)', text: 'var(--color-accent-2)' };
		} else if (action.startsWith('floating_ip.')) {
			return { bg: 'color-mix(in oklab, var(--color-state-warning) 14%, transparent)', text: 'var(--color-state-warning)' };
		} else if (action.startsWith('security_group.')) {
			return { bg: 'color-mix(in oklab, var(--color-state-success) 14%, transparent)', text: 'var(--color-state-success)' };
		} else if (action.startsWith('auth.')) {
			return { bg: 'color-mix(in oklab, var(--color-ink-3) 14%, transparent)', text: 'var(--color-ink-3)' };
		}
		return { bg: 'color-mix(in oklab, var(--color-ink-3) 14%, transparent)', text: 'var(--color-ink-3)' };
	}

	const PERIOD_LABELS: Record<string, string> = { '24h': '24h', '7d': '7d', '30d': '30d' };
</script>

<PageShell class="flex flex-col gap-5">
	<PageHeader breadcrumb="ACTIVITY" title="활동 & 작업" subtitle="내 프로젝트의 최근 작업" />
	<ResourceToolbar label="활동 기간 및 새로고침">
		{#snippet filters()}
			<ToggleGroup
				value={period}
				options={[
					{ value: '24h', label: PERIOD_LABELS['24h'] },
					{ value: '7d', label: PERIOD_LABELS['7d'] },
					{ value: '30d', label: PERIOD_LABELS['30d'] },
				]}
				onchange={(next) => { period = next as typeof period; }}
				ariaLabel="활동 조회 기간"
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

	{#if loading && !data}
		<LoadingSkeleton variant="table" rows={5} />
	{:else if error && !data}
		<Alert tone="danger">{error}</Alert>
	{:else}
		{#if data?.db_status === 'unavailable'}
			<Alert tone="warning">활동 로그 DB 미연결 — 서버 설정을 확인하세요 (database_url)</Alert>
		{/if}
		<!-- KPI Tiles -->
		<div class="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-3 lg:grid-cols-5">
			<StatTile label="오늘 작업" value={kpi.total} accent="blue" flat />
			<StatTile label="실패한 작업" value={kpi.failed} unit="/ {kpi.total}" accent="rose" flat />
			<StatTile label="지난 24시간" value={kpi.last_24h} unit="이벤트" accent="amber" flat />
			<StatTile label="활성 사용자" value={kpi.unique_users} accent="emerald" flat />
			<StatTile label="성공률" value={successRate} unit="%" accent="cyan" flat />
		</div>

		<!-- Hour Distribution Card -->
		<div class="bg-surface-base border border-line rounded-lg p-5">
			<SectionHeader title="오늘의 활동 분포" meta="시간대별 작업 수" />
			<div class="mt-4 flex items-end gap-0.5 h-20" aria-hidden="true">
				{#each hourDist as val, i}
					<div class="flex-1 flex flex-col justify-end">
						<div
							class="w-full rounded-sm transition-all"
							style="height: {Math.round((val / maxHour) * 72)}px; min-height: {val > 0 ? 2 : 1}px; background: {barColor(i, val)};"
						></div>
					</div>
				{/each}
			</div>
			<!-- Hour labels: show at 0,3,6,9,12,15,18,21 -->
			<div class="flex mt-1" aria-hidden="true">
				{#each hourDist as _, i}
					<div class="flex-1 text-center">
						{#if i % 3 === 0}
							<span class="text-[9px] text-[var(--color-ink-3)]">{String(i).padStart(2, '0')}</span>
						{/if}
					</div>
				{/each}
			</div>
		</div>

		<!-- Audit Log Table -->
		<div class="bg-surface-base border border-line rounded-lg p-5">
			<SectionHeader title="감사 로그" meta="최근 작업 내역" />
			{#if recentActions.length === 0}
				<div class="mt-6 text-center text-sm text-[var(--color-ink-3)] py-6">로그 없음</div>
			{:else}
				<div class="mt-4 overflow-x-auto">
					<table class="w-full text-sm">
						<thead>
							<tr class="text-[10px] uppercase tracking-wide text-[var(--color-ink-3)] border-b border-line">
								<th class="text-left pb-2 pr-4 font-medium">시각</th>
								<th class="text-left pb-2 pr-4 font-medium">액션</th>
								<th class="text-left pb-2 pr-4 font-medium">리소스</th>
								<th class="text-left pb-2 pr-4 font-medium">대상</th>
								<th class="text-left pb-2 font-medium">결과</th>
							</tr>
						</thead>
						<tbody class="divide-y divide-line/60">
							{#each recentActions as action}
								{@const badge = actionBadgeStyle(action.action)}
								<tr class="hover:bg-surface-sunken/30 transition-colors">
									<td class="py-2.5 pr-4 text-[var(--color-ink-3)] text-xs tabular-nums whitespace-nowrap">
										{formatHour(action.created_at)}
									</td>
									<td class="py-2.5 pr-4">
										<span
											class="font-mono text-[11px] px-2 py-0.5 rounded"
											style="background: {badge.bg}; color: {badge.text};"
										>{action.action}</span>
									</td>
									<td class="py-2.5 pr-4 text-[var(--color-ink-3)] text-xs">{action.resource_type}</td>
									<td class="py-2.5 pr-4 text-[var(--color-ink-0)] text-xs">{action.resource_name}</td>
									<td class="py-2.5">
										{#if action.status === 'success'}
											<Pill tone="success">OK</Pill>
										{:else}
											<Pill tone="danger">FAIL</Pill>
										{/if}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
		</div>
	{/if}
</PageShell>
