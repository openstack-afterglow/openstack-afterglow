<script lang="ts">
	import { untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api } from '$lib/api/client';
	import { siteConfig } from '$lib/config/site';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import { formatDate, formatSize } from '$lib/utils/format';
	import { t } from '$lib/i18n/ns/dashboard-home';
	import { getLocale, intlLocale } from '$lib/i18n/runtime.svelte';
	import RichText from '$lib/i18n/RichText.svelte';
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
		SectionLabel,
		Spark,
		StatTile,
		StatusChip,
		TableShell,
		ToggleGroup,
	} from '$lib/components/ui';
	import type { ChatUsage } from '$lib/api/chatTree';
	import type { DashboardQuotas, QuotaItem } from '$lib/types/quotas';

	interface FlavorHour {
		flavor: string;
		instance_count: number;
		usage_hours: number;
		vcpus: number;
		ram_mb: number;
		gpu_count: number;
		vcpu_hours: number;
		gpu_hours: number;
	}

	interface InstanceUsage {
		instance_id: string;
		name: string;
		flavor: string;
		state: string;
		hours: number;
		started_at: string | null;
		ended_at: string | null;
		vcpus: number;
		memory_mb: number;
		gpu_count: number;
	}

	interface ForecastEntry {
		current_pct: number | null;
		slope_per_day: number | null;
		projected_pct: number | null;
		days_to_limit: number | null;
		trend_available: boolean;
		series: number[];
	}

	interface GpuQuotaRow {
		gpu_type: string;
		in_use: number;
		limit: number;
	}

	interface UsageReport {
		range: string;
		start: string;
		end: string;
		stats: {
			instance_hours: number;
			vcpu_hours: number;
			ram_gb_hours: number;
			gpu_hours: number;
			active_instances: number;
			total_instances: number;
		};
		flavor_hours: FlavorHour[];
		instance_usage: InstanceUsage[];
		quota: {
			compute_available: boolean;
			storage_available: boolean;
			instances: QuotaItem;
			vcpus: QuotaItem;
			ram_mb: QuotaItem;
			volume_gb: QuotaItem;
			volumes: QuotaItem;
			gpu: GpuQuotaRow[];
			gpu_available: boolean;
		};
		forecast: {
			window_days: number;
			horizon_days: number;
			vcpus: ForecastEntry;
			ram_mb: ForecastEntry;
			volume_gb: ForecastEntry;
			gpu: Record<string, ForecastEntry>;
		};
	}

	/** One quota bar in the forecast panel; `scale` converts raw series units to the displayed unit. */
	interface ForecastRow {
		label: string;
		used: number;
		total: number;
		unit: string;
		limit: number;
		entry: ForecastEntry | null;
		scale: number;
	}

	interface InventoryRow {
		label: string;
		item: QuotaItem;
		unit: string;
	}

	interface InventoryGroup {
		id: string;
		title: string;
		rows: InventoryRow[];
	}

	let data = $state<UsageReport | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let period = $state<'7d' | '30d' | '90d'>('30d');
	let inventory = $state<DashboardQuotas | null>(null);
	let inventoryState = $state<'loading' | 'ready' | 'error'>('loading');
	let chatUsage = $state<ChatUsage | null>(null);
	// Period/project changes can overlap in-flight requests; only the latest may publish.
	let requestSerial = 0;
	let chatUsageSerial = 0;
	let reportToken: string | undefined;
	let reportProjectId: string | undefined;

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	async function fetchData() {
		const serial = ++requestSerial;
		if (!token || !projectId) {
			data = null;
			inventory = null;
			chatUsage = null;
			loading = false;
			return;
		}
		const requestToken = token, requestProjectId = projectId, requestPeriod = period;
		const owns = () => serial === requestSerial && token === requestToken && projectId === requestProjectId && period === requestPeriod;
		if (requestToken !== reportToken || requestProjectId !== reportProjectId) {
			data = null;
			inventory = null;
			chatUsage = null;
		}
		reportToken = requestToken;
		reportProjectId = requestProjectId;
		loading = !data;
		error = null;
		// Refreshes keep the current inventory on screen; only a first load (or a project switch) shows the skeleton.
		if (!inventory) inventoryState = 'loading';
		void api.get<DashboardQuotas>('/api/v1/dashboard/quotas', requestToken, requestProjectId).then(
			(quotas) => {
				if (!owns()) return;
				inventory = quotas;
				inventoryState = 'ready';
			},
			() => {
				if (!owns()) return;
				inventory = null;
				inventoryState = 'error';
			},
		);
		try {
			const report = await api.get<UsageReport>(`/api/v1/dashboard/usage-report?range=${requestPeriod}`, requestToken, requestProjectId);
			if (owns()) data = report;
		} catch (reason) {
			if (owns()) error = reason instanceof Error ? reason.message : t('usageReport.loadFailed');
		} finally {
			if (owns()) loading = false;
		}
	}

	async function fetchChatUsage() {
		const serial = ++chatUsageSerial;
		if (!token || !projectId) {
			chatUsage = null;
			return;
		}
		const requestToken = token, requestProjectId = projectId;
		const owns = () => serial === chatUsageSerial && token === requestToken && projectId === requestProjectId;
		try {
			const usage = await api.get<ChatUsage>('/api/v1/chat/usage', requestToken, requestProjectId);
			if (owns()) chatUsage = usage;
		} catch {
			if (owns()) chatUsage = null;
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

	const dailyAvg = $derived(data ? Math.round(data.stats.instance_hours / days) : 0);

	const sortedFlavors = $derived(
		data ? [...data.flavor_hours].sort((a, b) => b.usage_hours - a.usage_hours) : [],
	);

	const attention = $derived.by((): string[] => {
		if (!data) return [];
		const forecast = data.forecast;
		const entries: [string, ForecastEntry][] = [
			['vCPU', forecast.vcpus],
			['RAM', forecast.ram_mb],
			[t('usageReport.resources.blockStorage'), forecast.volume_gb],
			...Object.entries(forecast.gpu).map(([type, entry]): [string, ForecastEntry] => [t('usageReport.resources.gpuType', { type }), entry]),
		];
		return entries
			.filter(
				([, entry]) =>
					(entry.current_pct != null && entry.current_pct >= 80) ||
					(entry.days_to_limit != null && entry.days_to_limit <= forecast.horizon_days),
			)
			.map(([label]) => label);
	});

	const computeRows = $derived.by((): ForecastRow[] => {
		if (!data) return [];
		const { quota, forecast } = data;
		return [
			{ label: 'vCPU', used: quota.vcpus.in_use, total: quota.vcpus.limit, unit: '', limit: quota.vcpus.limit, entry: forecast.vcpus, scale: 1 },
			{
				label: 'RAM',
				used: quota.ram_mb.in_use / 1024,
				total: quota.ram_mb.limit === -1 ? -1 : quota.ram_mb.limit / 1024,
				unit: 'GB',
				limit: quota.ram_mb.limit,
				entry: forecast.ram_mb,
				scale: 1024,
			},
		];
	});

	const gpuRows = $derived.by((): ForecastRow[] => {
		if (!data) return [];
		const forecast = data.forecast;
		return data.quota.gpu.map((row) => ({
			label: t('usageReport.resources.gpuType', { type: row.gpu_type }),
			used: row.in_use,
			total: row.limit,
			unit: '',
			limit: row.limit,
			entry: forecast.gpu[row.gpu_type] ?? null,
			scale: 1,
		}));
	});

	const storageRows = $derived.by((): ForecastRow[] => {
		if (!data) return [];
		const { quota, forecast } = data;
		return [
			{ label: t('usageReport.resources.capacity'), used: quota.volume_gb.in_use, total: quota.volume_gb.limit, unit: 'GB', limit: quota.volume_gb.limit, entry: forecast.volume_gb, scale: 1 },
			{ label: t('usageReport.resources.volumeCount'), used: quota.volumes.in_use, total: quota.volumes.limit, unit: '', limit: quota.volumes.limit, entry: null, scale: 1 },
		];
	});

	function isQuotaItem(value: unknown): value is QuotaItem {
		return (
			typeof value === 'object' &&
			value !== null &&
			typeof (value as QuotaItem).limit === 'number' &&
			typeof (value as QuotaItem).in_use === 'number'
		);
	}

	/** Keep only entries the quota view actually returned as `{ limit, in_use }`. */
	function quotaRows(entries: [string, unknown, string?][]): InventoryRow[] {
		return entries.flatMap(([label, value, unit = '']) => (isQuotaItem(value) ? [{ label, item: value, unit }] : []));
	}

	const inventoryGroups = $derived.by((): InventoryGroup[] => {
		if (!inventory) return [];
		const { compute, storage, network, file_storage: files } = inventory;
		const groups: InventoryGroup[] = [
			{
				id: 'network',
				title: t('usageReport.resources.network'),
				rows: quotaRows([
					[t('usageReport.resources.floatingIp'), network?.floatingip],
					[t('usageReport.resources.network'), network?.network],
					[t('usageReport.resources.subnet'), network?.subnet],
					[t('usageReport.resources.port'), network?.port],
					[t('usageReport.resources.router'), network?.router],
					[t('usageReport.resources.securityGroup'), network?.security_group],
					[t('usageReport.resources.securityGroupRule'), network?.security_group_rule],
				]),
			},
			{
				id: 'storage',
				title: t('usageReport.resources.blockStorage'),
				rows: data?.quota.storage_available === false ? [] : quotaRows([
					[t('usageReport.resources.volume'), storage?.volumes],
					[t('usageReport.resources.snapshot'), storage?.snapshots],
					[t('usageReport.resources.backup'), storage?.backups],
					[t('usageReport.resources.backupCapacity'), storage?.backup_gigabytes, 'GB'],
				]),
			},
			{
				id: 'compute',
				title: t('usageReport.resources.computeLimit'),
				rows: data?.quota.compute_available === false ? [] : quotaRows([
					[t('usageReport.resources.instance'), compute?.instances],
					[t('usageReport.resources.serverGroup'), compute?.server_groups],
				]),
			},
		];
		// Disabled Manila returns a flat sentinel instead of per-resource entries.
		if ($siteConfig.services.manila && typeof files?.shares === 'object') {
			groups.push({
				id: 'files',
				title: t('usageReport.resources.fileStorage'),
				rows: quotaRows([
					[t('usageReport.resources.share'), files.shares],
					[t('usageReport.resources.capacity'), files.gigabytes, 'GB'],
					[t('usageReport.resources.shareNetwork'), files.share_networks],
					[t('usageReport.resources.snapshotCapacity'), files.snapshot_gigabytes, 'GB'],
				]),
			});
		}
		return groups.filter((group) => group.rows.length > 0);
	});

	const objectStorage = $derived($siteConfig.services.swift ? (inventory?.object_storage ?? null) : null);
	const database = $derived($siteConfig.services.trove ? (inventory?.database ?? null) : null);

	function formatAmount(value: number, scale = 1): string {
		return (value / scale).toLocaleString(intlLocale(), { maximumFractionDigits: 2 });
	}

	function formatValue(value: number, fractionDigits?: number): string {
		return (fractionDigits == null ? value : Number(value.toFixed(fractionDigits))).toLocaleString(intlLocale(), {
			useGrouping: false,
			minimumFractionDigits: fractionDigits ?? 0,
			maximumFractionDigits: fractionDigits ?? 20,
		});
	}

	function formatRangeDate(value: string): string {
		if (getLocale() === 'ko') return value;
		return new Date(value).toLocaleDateString(intlLocale(), { year: 'numeric', month: '2-digit', day: '2-digit', timeZone: 'UTC' });
	}

	function forecastText(row: ForecastRow, horizon: number): string {
		const entry = row.entry;
		if (!entry) return '';
		if (row.limit === -1) return t('usageReport.forecast.unlimited');
		if (!entry.trend_available || entry.slope_per_day == null) return t('usageReport.forecast.noTrend');
		return t('usageReport.forecast.summary', {
			projection: entry.projected_pct != null ? 'available' : 'none',
			horizon,
			percent: entry.projected_pct == null ? '' : formatValue(entry.projected_pct),
			slope: `${entry.slope_per_day >= 0 ? '+' : ''}${formatAmount(entry.slope_per_day, row.scale)}`,
			unit: row.unit,
			limit: entry.days_to_limit === 0 ? 'reached' : entry.days_to_limit != null ? 'upcoming' : 'none',
			days: entry.days_to_limit ?? 0,
		});
	}
</script>

{#snippet amount(text: string)}<span>{text}</span>{/snippet}

{#snippet forecastRow(row: ForecastRow, horizon: number)}
	<div class="space-y-1.5">
		<CapacityBar label={row.label} used={row.used} total={row.total} unit={row.unit} size="sm" />
		{#if row.entry}
			<p class="text-xs text-ink-2 tabular-nums">{forecastText(row, horizon)}</p>
			{#if row.entry.series.length >= 2}
				<div class="space-y-1">
					<Spark data={row.entry.series} height={24} class="w-full" />
					<p class="text-xs text-ink-2 tabular-nums">
						<RichText segments={t.rich('usageReport.forecast.range', { min: formatAmount(Math.min(...row.entry.series), row.scale), max: formatAmount(Math.max(...row.entry.series), row.scale), unit: row.unit })} tags={{ min: amount, max: amount }} />
					</p>
				</div>
			{/if}
		{/if}
	</div>
{/snippet}

<PageShell class="space-y-6">
	<PageHeader
		breadcrumb={t('usageReport.breadcrumb')}
		title={t('usageReport.title')}
		subtitle={data ? t('usageReport.subtitleRange', { start: formatRangeDate(data.start), end: formatRangeDate(data.end) }) : t('usageReport.subtitle')}
	/>
	<ResourceToolbar label={t('usageReport.toolbarLabel')}>
		{#snippet filters()}
			<ToggleGroup
				value={period}
				options={[
					{ value: '7d', label: t('usageReport.period', { days: 7 }) },
					{ value: '30d', label: t('usageReport.period', { days: 30 }) },
					{ value: '90d', label: t('usageReport.period', { days: 90 }) },
				]}
				onchange={(next) => { period = next as typeof period; }}
				ariaLabel={t('usageReport.periodLabel')}
			/>
		{/snippet}
		{#snippet actions()}
			<button
				type="button"
				onclick={() => { ar.active = !ar.active; }}
				class="min-h-8 rounded-md border border-line-2 px-3 text-xs font-medium text-ink-2 transition-colors hover:bg-surface-selected hover:text-ink-0"
				aria-pressed={ar.active}
			>{t('usageReport.autoRefresh', { state: ar.active ? 'on' : 'off' })}</button>
		{/snippet}
	</ResourceToolbar>

	{#if loading}
		<LoadingSkeleton variant="table" rows={6} />
	{:else if error}
		<Alert tone="danger">{error}</Alert>
	{:else if data}
		<!-- KPI StatTiles -->
		<div class="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line md:grid-cols-3">
			<StatTile
				label={t('usageReport.stats.instanceHours')}
				value={formatValue(data.stats.instance_hours, 1)}
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
				label={t('usageReport.stats.dailyInstanceHours')}
				value={formatValue(dailyAvg)}
				unit={t('usageReport.stats.hoursPerDay')}
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
				label={t('usageReport.stats.activeInstances')}
				value={formatValue(data.stats.active_instances)}
				unit={t('usageReport.stats.periodTotal', { count: formatValue(data.stats.total_instances) })}
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
				label={t('usageReport.stats.vcpuHours')}
				value={formatValue(data.stats.vcpu_hours, 1)}
				unit="vCPU·h"
				accent="violet"
				flat
			>
				{#snippet icon()}
					<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
						<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
					</svg>
				{/snippet}
			</StatTile>

			<StatTile
				label={t('usageReport.stats.ramHours')}
				value={formatValue(data.stats.ram_gb_hours, 1)}
				unit="GB·h"
				accent="teal"
				flat
			>
				{#snippet icon()}
					<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
						<rect x="2" y="7" width="20" height="10" rx="2"/>
						<line x1="6" y1="17" x2="6" y2="20"/>
						<line x1="12" y1="17" x2="12" y2="20"/>
						<line x1="18" y1="17" x2="18" y2="20"/>
					</svg>
				{/snippet}
			</StatTile>

			<StatTile
				label={t('usageReport.stats.gpuHours')}
				value={formatValue(data.stats.gpu_hours, 1)}
				unit="GPU·h"
				accent="amber"
				flat
			>
				{#snippet icon()}
					<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
						<rect x="4" y="4" width="16" height="16" rx="2"/>
						<rect x="9" y="9" width="6" height="6"/>
						<line x1="9" y1="1" x2="9" y2="4"/>
						<line x1="15" y1="1" x2="15" y2="4"/>
						<line x1="9" y1="20" x2="9" y2="23"/>
						<line x1="15" y1="20" x2="15" y2="23"/>
					</svg>
				{/snippet}
			</StatTile>
		</div>

		{#if attention.length > 0}
			<Alert tone="warning" title={t('usageReport.quotaWarning.title')}>
				{t('usageReport.quotaWarning.body', { resources: attention.join(', '), days: formatValue(data.forecast.horizon_days) })}
			</Alert>
		{/if}

		<div class="grid grid-cols-1 gap-3.5 lg:grid-cols-[2fr_1fr]">
			<Card padding="lg" class="min-w-0">
				<SectionHeader title={t('usageReport.flavors.title')} meta={t('usageReport.flavors.count', { count: sortedFlavors.length })} />
				{#if sortedFlavors.length === 0}
					<div class="mt-6 py-6 text-center text-sm text-ink-2">{t('usageReport.noData')}</div>
				{:else}
					<TableShell density="compact" class="mt-4">
						<table>
							<thead>
								<tr>
									<th scope="col">{t('usageReport.columns.flavor')}</th>
									<th scope="col">vCPU</th>
									<th scope="col">RAM(GB)</th>
									<th scope="col">{t('usageReport.columns.usageHours')}</th>
									<th scope="col">vCPU·h</th>
									<th scope="col">{t('usageReport.columns.vmCount')}</th>
								</tr>
							</thead>
							<tbody class="motion-stagger">
								{#each sortedFlavors as f (f.flavor)}
									<tr>
										<td>
											<div class="flex items-center gap-2">
												<span class="font-mono text-ink-0">{f.flavor}</span>
												{#if f.gpu_count > 0}
													<Pill tone="accent">{t('usageReport.flavors.gpuCount', { count: formatValue(f.gpu_count) })}</Pill>
												{/if}
											</div>
										</td>
										<td class="tabular-nums text-ink-2">{formatValue(f.vcpus)}</td>
										<td class="tabular-nums text-ink-2">{formatValue(Math.round(f.ram_mb / 1024))}</td>
										<td class="font-medium tabular-nums text-ink-0">{formatValue(f.usage_hours, 1)}</td>
										<td class="tabular-nums text-ink-2">{formatValue(f.vcpu_hours, 1)}</td>
										<td class="tabular-nums text-ink-2">{formatValue(f.instance_count)}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</TableShell>
				{/if}
			</Card>

			<Card padding="lg" class="flex min-w-0 flex-col gap-4">
				<SectionHeader title={t('usageReport.forecast.title')} meta={t('usageReport.forecast.window', { days: data.forecast.window_days })} />

				<div class="space-y-3">
					<SectionLabel>{t('usageReport.resources.compute')}</SectionLabel>
					{#if data.quota.compute_available === false}
						<p class="text-xs text-ink-2">{t('usageReport.forecast.computeFailed')}</p>
					{:else}
						{#each computeRows as row (row.label)}
							{@render forecastRow(row, data.forecast.horizon_days)}
						{/each}
					{/if}
				</div>

				<div class="space-y-3">
					<SectionLabel>GPU</SectionLabel>
					{#if data.quota.gpu_available === false}
						<p class="text-xs text-ink-2">{t('usageReport.forecast.gpuFailed')}</p>
					{:else if gpuRows.length === 0}
						<p class="text-xs text-ink-2">{t('usageReport.forecast.noGpuQuota')}</p>
					{:else}
						{#each gpuRows as row (row.label)}
							{@render forecastRow(row, data.forecast.horizon_days)}
						{/each}
					{/if}
				</div>

				<div class="space-y-3">
					<SectionLabel>{t('usageReport.resources.blockStorage')}</SectionLabel>
					{#if data.quota.storage_available === false}
						<p class="text-xs text-ink-2">{t('usageReport.forecast.storageFailed')}</p>
					{:else}
						{#each storageRows as row (row.label)}
							{@render forecastRow(row, data.forecast.horizon_days)}
						{/each}
					{/if}
				</div>

				<p class="mt-auto text-xs text-ink-2">
					{t('usageReport.forecast.description', { window: formatValue(data.forecast.window_days), horizon: formatValue(data.forecast.horizon_days) })}
				</p>
			</Card>
		</div>

		<Card padding="lg">
			<SectionHeader title={t('usageReport.instances.title')} meta={t('usageReport.instances.top', { count: formatValue(data.instance_usage.length) })} />
			{#if data.instance_usage.length === 0}
				<div class="mt-6 py-6 text-center text-sm text-ink-2">{t('usageReport.noData')}</div>
			{:else}
				<TableShell density="compact" class="mt-4">
					<table>
						<thead>
							<tr>
								<th scope="col">{t('usageReport.resources.instance')}</th>
								<th scope="col">{t('usageReport.columns.flavor')}</th>
								<th scope="col">{t('usageReport.columns.status')}</th>
								<th scope="col">{t('usageReport.columns.started')}</th>
								<th scope="col">{t('usageReport.columns.usageHours')}</th>
								<th scope="col">vCPU</th>
								<th scope="col">GPU</th>
							</tr>
						</thead>
						<tbody class="motion-stagger">
							{#each data.instance_usage as row (row.instance_id)}
								<tr>
									<td>
										<div class="text-ink-0">{row.name || t('usageReport.missingValue')}</div>
										<div class="font-mono text-xs text-ink-2">{row.instance_id.slice(0, 8)}</div>
									</td>
									<td class="font-mono text-ink-2">{row.flavor}</td>
									<td>
										<div class="flex items-center gap-1.5">
											<StatusChip status={row.state} />
											{#if row.ended_at}
												<Pill tone="neutral">{t('usageReport.instances.deleted')}</Pill>
											{/if}
										</div>
									</td>
									<td class="tabular-nums text-ink-2">{row.started_at ? formatDate(row.started_at) : t('usageReport.missingValue')}</td>
									<td class="font-medium tabular-nums text-ink-0">{formatValue(row.hours, 1)}</td>
									<td class="tabular-nums text-ink-2">{formatValue(row.vcpus)}</td>
									<td class="tabular-nums text-ink-2">{row.gpu_count ? formatValue(row.gpu_count) : t('usageReport.missingValue')}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</TableShell>
			{/if}
		</Card>

		<Card padding="lg">
			<SectionHeader title={t('usageReport.inventory.title')} meta={t('usageReport.inventory.meta')} />
			<div class="mt-4">
				{#if inventoryState === 'loading'}
					<LoadingSkeleton variant="table" rows={4} />
				{:else if inventoryState === 'error'}
					<Alert tone="warning">{t('usageReport.inventory.loadFailed')}</Alert>
				{:else}
					<div class="grid grid-cols-1 gap-3.5 md:grid-cols-2 lg:grid-cols-3">
						{#each inventoryGroups as group (group.id)}
							<section class="space-y-2.5" aria-label={group.title}>
								<SectionLabel>{group.title}</SectionLabel>
								{#each group.rows as row (row.label)}
									<CapacityBar label={row.label} used={row.item.in_use} total={row.item.limit} unit={row.unit} size="xs" />
								{/each}
								{#if group.id === 'compute' && data.quota.compute_available !== false && isQuotaItem(inventory?.compute.key_pairs)}
									<StatTile label={t('usageReport.inventory.keyPairLimit')} value={inventory.compute.key_pairs.limit === -1 ? t('usageReport.forecast.unlimited') : formatValue(inventory.compute.key_pairs.limit)} accent="blue" flat />
								{/if}
							</section>
						{/each}
						{#if objectStorage}
							<section class="space-y-2.5" aria-label={t('usageReport.resources.objectStorage')}>
								<SectionLabel>{t('usageReport.resources.objectStorage')}</SectionLabel>
								<div class="grid gap-px overflow-hidden rounded-lg border border-line bg-line">
									<StatTile label={t('usageReport.resources.container')} value={objectStorage.container_count.toLocaleString(intlLocale())} accent="blue" flat />
									<StatTile label={t('usageReport.resources.object')} value={objectStorage.object_count.toLocaleString(intlLocale())} accent="cyan" flat />
									<StatTile label={t('usageReport.resources.usage')} value={objectStorage.bytes_used > 0 ? formatSize(objectStorage.bytes_used) : `${formatValue(0)} B`} accent="violet" flat />
								</div>
							</section>
						{/if}
						{#if database}
							<section class="space-y-2.5" aria-label={t('usageReport.resources.database')}>
								<SectionLabel>{t('usageReport.resources.database')}</SectionLabel>
								<div class="overflow-hidden rounded-lg border border-line">
									<StatTile label={t('usageReport.resources.dbInstance')} value={formatValue(database.instances_count)} accent="emerald" flat />
								</div>
							</section>
						{/if}
					</div>
				{/if}
			</div>
		</Card>

		<!-- LLM 채팅 사용량 (빌트인) -->
		{#if chatUsage?.found}
			<Card padding="lg">
				<SectionHeader title={t('usageReport.chat.title')} meta={t('usageReport.chat.meta')} />
				<div class="grid grid-cols-2 lg:grid-cols-3 gap-3.5 mt-4">
					<StatTile
						label={t('usageReport.chat.monthTokens')}
						value={(chatUsage.month_prompt_tokens + chatUsage.month_completion_tokens).toLocaleString(intlLocale())}
						accent="blue"
					>
						{#snippet icon()}
							<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
								<path d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
							</svg>
						{/snippet}
					</StatTile>
					<StatTile label={t('usageReport.chat.inputTokens')} value={chatUsage.month_prompt_tokens.toLocaleString(intlLocale())} accent="blue" />
					<StatTile label={t('usageReport.chat.outputTokens')} value={chatUsage.month_completion_tokens.toLocaleString(intlLocale())} accent="cyan" />
					<StatTile
						label={t('usageReport.chat.monthCredits')}
						value={chatUsage.month_credited_cost.toLocaleString(intlLocale())}
						accent="violet"
					>
						{#snippet icon()}
							<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
								<circle cx="12" cy="12" r="10"/>
							</svg>
						{/snippet}
					</StatTile>
					<StatTile
						label={t('usageReport.chat.monthRequests')}
						value={formatValue(chatUsage.month_request_count)}
						accent="cyan"
					>
						{#snippet icon()}
							<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
								<rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
							</svg>
						{/snippet}
					</StatTile>
					<StatTile label={t('usageReport.chat.monthQuota')} value={t('usageReport.chat.quotaValue', { used: chatUsage.quota_used.toLocaleString(intlLocale()), max: chatUsage.quota_max.toLocaleString(intlLocale()) })} accent="amber" />
				</div>
			</Card>
		{/if}
	{:else}
		<EmptyState headline={t('usageReport.empty.title')} description={t('usageReport.empty.description')} />
	{/if}
</PageShell>
