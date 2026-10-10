<script lang="ts">
	import { t } from '$lib/i18n/ns/dashboard-home';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
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
			error = e instanceof Error ? e.message : t('activity.loadFailed');
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
	const successRate = $derived(kpi.total > 0 ? Math.round((kpi.success / kpi.total) * 100) : '—');
	const hourDist = $derived(data?.hour_distribution ?? Array(24).fill(0));
	const recentActions = $derived(data?.recent_actions ?? []);

	// Bar chart derived values
	const maxHour = $derived(Math.max(...hourDist) || 1);
	const BAR_MAX_PX = 72;

	/** Bars scale from the bottom of a fixed 72px column; empty hours keep a 1px baseline, active ones at least 2px. */
	function barScale(val: number): number {
		const minPx = val > 0 ? 2 : 1;
		return Math.max(Math.round((val / maxHour) * BAR_MAX_PX), minPx) / BAR_MAX_PX;
	}

	function barColor(idx: number, val: number): string {
		if (val === 0) return 'color-mix(in oklab, var(--color-ink-3) 25%, transparent)';
		if (val === Math.max(...hourDist) && val > 0) return 'var(--color-warm)';
		return 'color-mix(in oklab, var(--color-accent) 55%, transparent)';
	}

	function formatHour(created_at: string): string {
		try {
			const d = new Date(created_at);
			return d.toLocaleTimeString(intlLocale(), { hour: '2-digit', minute: '2-digit', hour12: false });
		} catch {
			return '—';
		}
	}

	type ActionBadgeStyle = {
		bg: string;
		text: string;
	};

	// 리소스 종류는 운영 상태가 아니다. 다섯 가지 상태 톤을 카테고리 라벨에 쓰면 감사 로그가
	// 건강 상태 열처럼 읽힌다. 파괴적 동작 하나만 danger 를 유지하고 나머지는 중립이다.
	function actionBadgeStyle(action: string): ActionBadgeStyle {
		if (action.startsWith('instance.delete')) {
			return { bg: 'color-mix(in oklab, var(--color-state-danger) 14%, transparent)', text: 'var(--color-state-danger-text)' };
		}
		return { bg: 'color-mix(in oklab, var(--color-ink-2) 14%, transparent)', text: 'var(--color-ink-2)' };
	}

	const PERIOD_LABELS: Record<string, string> = { '24h': '24h', '7d': '7d', '30d': '30d' };
</script>

<PageShell class="flex flex-col gap-5">
	<PageHeader breadcrumb={t('activity.breadcrumb')} title={t('activity.title')} subtitle={t('activity.subtitle')} />
	<ResourceToolbar label={t('activity.toolbar')}>
		{#snippet filters()}
			<ToggleGroup
				value={period}
				options={[
					{ value: '24h', label: PERIOD_LABELS['24h'] },
					{ value: '7d', label: PERIOD_LABELS['7d'] },
					{ value: '30d', label: PERIOD_LABELS['30d'] },
				]}
				onchange={(next) => { period = next as typeof period; }}
				ariaLabel={t('activity.period')}
			/>
		{/snippet}
		{#snippet actions()}
			<button
				type="button"
				onclick={() => { ar.active = !ar.active; }}
				class="min-h-8 rounded-md border border-line-2 px-3 text-xs font-medium text-ink-2 transition-colors hover:bg-surface-selected hover:text-ink-0"
				aria-pressed={ar.active}
			>{t(ar.active ? 'activity.autoRefreshOn' : 'activity.autoRefreshOff')}</button>
		{/snippet}
	</ResourceToolbar>

	{#if loading && !data}
		<LoadingSkeleton variant="table" rows={5} />
	{:else if error && !data}
		<Alert tone="danger">{error}</Alert>
	{:else}
		{#if data?.db_status === 'unavailable'}
			<Alert tone="warning">{t('activity.dbUnavailable')}</Alert>
		{/if}
		<!-- KPI Tiles -->
		<div class="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-3 lg:grid-cols-5">
			<StatTile label={t('activity.today')} value={kpi.total} accent="blue" flat />
			<StatTile label={t('activity.failed')} value={kpi.failed} unit="/ {kpi.total}" accent="rose" flat />
			<StatTile label={t('activity.last24Hours')} value={kpi.last_24h} unit={t('activity.events', { count: kpi.last_24h })} accent="amber" flat />
			<StatTile label={t('activity.activeUsers')} value={kpi.unique_users} accent="emerald" flat />
			<StatTile label={t('activity.successRate')} value={successRate} unit="%" accent="cyan" flat />
		</div>

		<!-- Hour Distribution Card -->
		<div class="bg-surface-base border border-line rounded-lg p-5">
			<SectionHeader title={t('activity.distribution')} meta={t('activity.hourly')} />
			<div class="mt-4 flex items-end gap-0.5 h-20" aria-hidden="true">
				{#each hourDist as val, i}
					<div class="flex-1 flex flex-col justify-end">
						<div
							class="hour-bar w-full rounded-sm"
							style="transform: scaleY({barScale(val)}); background: {barColor(i, val)};"
						></div>
					</div>
				{/each}
			</div>
			<!-- Hour labels: show at 0,3,6,9,12,15,18,21 -->
			<div class="flex mt-1" aria-hidden="true">
				{#each hourDist as _, i}
					<div class="flex-1 text-center">
						{#if i % 3 === 0}
							<span class="text-xs text-[var(--color-ink-3)]">{String(i).padStart(2, '0')}</span>
						{/if}
					</div>
				{/each}
			</div>
		</div>

		<!-- Audit Log Table -->
		<div class="bg-surface-base border border-line rounded-lg p-5">
			<SectionHeader title={t('activity.audit')} meta={t('activity.recent')} />
			{#if recentActions.length === 0}
				<div class="mt-6 text-center text-sm text-[var(--color-ink-3)] py-6">{t('activity.empty')}</div>
			{:else}
				<div class="mt-4 overflow-x-auto">
					<table class="w-full text-sm">
						<thead>
							<tr class="text-xs uppercase tracking-wide text-[var(--color-ink-3)] border-b border-line">
								<th class="text-left pb-2 pr-4 font-medium">{t('activity.time')}</th>
								<th class="text-left pb-2 pr-4 font-medium">{t('activity.action')}</th>
								<th class="text-left pb-2 pr-4 font-medium">{t('activity.resource')}</th>
								<th class="text-left pb-2 pr-4 font-medium">{t('activity.target')}</th>
								<th class="text-left pb-2 font-medium">{t('activity.result')}</th>
							</tr>
						</thead>
						<tbody class="motion-stagger divide-y divide-line/60">
							{#each recentActions as action (action.id)}
								{@const badge = actionBadgeStyle(action.action)}
								<tr class="hover:bg-surface-sunken/30 transition-colors">
									<td class="py-2.5 pr-4 text-[var(--color-ink-3)] text-xs tabular-nums whitespace-nowrap">
										{formatHour(action.created_at)}
									</td>
									<td class="py-2.5 pr-4">
										<span
											class="font-mono text-xs px-2 py-0.5 rounded"
											style="background: {badge.bg}; color: {badge.text};"
										>{action.action}</span>
									</td>
									<td class="py-2.5 pr-4 text-[var(--color-ink-3)] text-xs">{action.resource_type}</td>
									<td class="py-2.5 pr-4 text-[var(--color-ink-0)] text-xs">{action.resource_name}</td>
									<td class="py-2.5">
										{#if action.status === 'success'}
											<Pill tone="success">{t('activity.success')}</Pill>
										{:else}
											<Pill tone="danger">{t('activity.failure')}</Pill>
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

<style>
	/* Hour bars grow from the baseline once, then ease to new counts on refresh. */
	.hour-bar {
		height: 72px;
		transform-origin: center bottom;
		animation: motion-grow-y var(--motion-duration-data) var(--motion-ease-emphasized) backwards;
		transition: transform var(--motion-duration-data) var(--motion-ease-emphasized), background-color var(--motion-duration-base) var(--motion-ease-standard);
	}
</style>
