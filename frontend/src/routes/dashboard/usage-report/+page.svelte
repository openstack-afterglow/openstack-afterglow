<script lang="ts">
	import { untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api } from '$lib/api/client';
	import { siteConfig } from '$lib/config/site';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import { formatDate, formatSize } from '$lib/utils/format';
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

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	async function fetchData() {
		if (!token || !projectId) return;
		const serial = ++requestSerial;
		loading = !data;
		error = null;
		const [report, quotas] = await Promise.allSettled([
			api.get<UsageReport>(`/api/v1/dashboard/usage-report?range=${period}`, token, projectId),
			api.get<DashboardQuotas>('/api/v1/dashboard/quotas', token, projectId),
		]);
		if (serial !== requestSerial) return;
		if (report.status === 'fulfilled') {
			data = report.value;
		} else {
			error = report.reason instanceof Error ? report.reason.message : '데이터 로딩 실패';
		}
		if (quotas.status === 'fulfilled') {
			inventory = quotas.value;
			inventoryState = 'ready';
		} else {
			inventoryState = 'error';
		}
		loading = false;
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
			['블록 스토리지', forecast.volume_gb],
			...Object.entries(forecast.gpu).map(([type, entry]): [string, ForecastEntry] => [`GPU ${type}`, entry]),
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
				used: Math.round(quota.ram_mb.in_use / 1024),
				total: quota.ram_mb.limit === -1 ? -1 : Math.round(quota.ram_mb.limit / 1024),
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
			label: `GPU ${row.gpu_type}`,
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
			{ label: '용량', used: quota.volume_gb.in_use, total: quota.volume_gb.limit, unit: 'GB', limit: quota.volume_gb.limit, entry: forecast.volume_gb, scale: 1 },
			{ label: '볼륨 수', used: quota.volumes.in_use, total: quota.volumes.limit, unit: '', limit: quota.volumes.limit, entry: null, scale: 1 },
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
				title: '네트워크',
				rows: quotaRows([
					['Floating IP', network?.floatingip],
					['네트워크', network?.network],
					['서브넷', network?.subnet],
					['포트', network?.port],
					['라우터', network?.router],
					['보안 그룹', network?.security_group],
					['보안 그룹 규칙', network?.security_group_rule],
				]),
			},
			{
				title: '블록 스토리지',
				rows: quotaRows([
					['볼륨', storage?.volumes],
					['스냅샷', storage?.snapshots],
					['백업', storage?.backups],
					['백업 용량', storage?.backup_gigabytes, 'GB'],
				]),
			},
			{
				title: '컴퓨트 한도',
				rows: quotaRows([
					['인스턴스', compute?.instances],
					['서버 그룹', compute?.server_groups],
				]),
			},
		];
		// Disabled Manila returns a flat sentinel instead of per-resource entries.
		if ($siteConfig.services.manila && typeof files?.shares === 'object') {
			groups.push({
				title: '파일 스토리지',
				rows: quotaRows([
					['공유', files.shares],
					['용량', files.gigabytes, 'GB'],
					['공유 네트워크', files.share_networks],
					['스냅샷 용량', files.snapshot_gigabytes, 'GB'],
				]),
			});
		}
		return groups.filter((group) => group.rows.length > 0);
	});

	const objectStorage = $derived($siteConfig.services.swift ? (inventory?.object_storage ?? null) : null);
	const database = $derived($siteConfig.services.trove ? (inventory?.database ?? null) : null);

	function formatAmount(value: number, scale = 1): string {
		return (value / scale).toLocaleString(undefined, { maximumFractionDigits: 2 });
	}

	function forecastText(row: ForecastRow, horizon: number): string {
		const entry = row.entry;
		if (!entry) return '';
		if (row.limit === -1) return '무제한';
		if (!entry.trend_available || entry.slope_per_day == null) return '추세 데이터 없음';
		const parts: string[] = [];
		if (entry.projected_pct != null) parts.push(`${horizon}일 후 예상 ${entry.projected_pct}%`);
		parts.push(`일 ${entry.slope_per_day >= 0 ? '+' : ''}${formatAmount(entry.slope_per_day, row.scale)}${row.unit}`);
		if (entry.days_to_limit === 0) parts.push('한도 도달');
		else if (entry.days_to_limit != null) parts.push(`약 ${entry.days_to_limit}일 후 한도 도달`);
		return parts.join(' · ');
	}
</script>

{#snippet forecastRow(row: ForecastRow, horizon: number)}
	<div class="space-y-1.5">
		<CapacityBar label={row.label} used={row.used} total={row.total} unit={row.unit} size="sm" />
		{#if row.entry}
			<p class="text-xs text-ink-2 tabular-nums">{forecastText(row, horizon)}</p>
			{#if row.entry.series.length >= 2}
				<div class="space-y-1">
					<Spark data={row.entry.series} height={24} class="w-full" />
					<p class="text-xs text-ink-2 tabular-nums">
						최소 {formatAmount(Math.min(...row.entry.series), row.scale)}{row.unit} · 최대 {formatAmount(Math.max(...row.entry.series), row.scale)}{row.unit}
					</p>
				</div>
			{/if}
		{/if}
	</div>
{/snippet}

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
		<div class="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line md:grid-cols-3">
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
				unit="/ {data.stats.total_instances} 기간 내"
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
				label="RAM 시간"
				value={data.stats.ram_gb_hours.toFixed(1)}
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
				label="GPU 시간"
				value={data.stats.gpu_hours.toFixed(1)}
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
			<Alert tone="warning" title="쿼터 임박">
				{attention.join(', ')} 사용률이 80% 이상이거나 {data.forecast.horizon_days}일 내 한도 도달이 예상됩니다. 사용량이 낮은 인스턴스를 확인하세요.
			</Alert>
		{/if}

		<div class="grid grid-cols-1 gap-3.5 lg:grid-cols-[2fr_1fr]">
			<Card padding="lg" class="min-w-0">
				<SectionHeader title="플레이버별 사용 시간" meta="{sortedFlavors.length}종" />
				{#if sortedFlavors.length === 0}
					<div class="mt-6 py-6 text-center text-sm text-ink-2">데이터 없음</div>
				{:else}
					<TableShell density="compact" class="mt-4">
						<table>
							<thead>
								<tr>
									<th scope="col">Flavor</th>
									<th scope="col">vCPU</th>
									<th scope="col">RAM(GB)</th>
									<th scope="col">사용 시간(h)</th>
									<th scope="col">vCPU·h</th>
									<th scope="col">VM 수</th>
								</tr>
							</thead>
							<tbody>
								{#each sortedFlavors as f (f.flavor)}
									<tr>
										<td>
											<div class="flex items-center gap-2">
												<span class="font-mono text-ink-0">{f.flavor}</span>
												{#if f.gpu_count > 0}
													<Pill tone="accent">GPU ×{f.gpu_count}</Pill>
												{/if}
											</div>
										</td>
										<td class="tabular-nums text-ink-2">{f.vcpus}</td>
										<td class="tabular-nums text-ink-2">{Math.round(f.ram_mb / 1024)}</td>
										<td class="font-medium tabular-nums text-ink-0">{f.usage_hours.toFixed(1)}</td>
										<td class="tabular-nums text-ink-2">{f.vcpu_hours.toFixed(1)}</td>
										<td class="tabular-nums text-ink-2">{f.instance_count}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</TableShell>
				{/if}
			</Card>

			<Card padding="lg" class="flex min-w-0 flex-col gap-4">
				<SectionHeader title="쿼터 예측" meta="{data.forecast.window_days}일 추세" />

				<div class="space-y-3">
					<SectionLabel>컴퓨트</SectionLabel>
					{#if data.quota.compute_available === false}
						<p class="text-xs text-ink-2">컴퓨트 쿼터를 불러오지 못했습니다</p>
					{:else}
						{#each computeRows as row (row.label)}
							{@render forecastRow(row, data.forecast.horizon_days)}
						{/each}
					{/if}
				</div>

				<div class="space-y-3">
					<SectionLabel>GPU</SectionLabel>
					{#if data.quota.gpu_available === false}
						<p class="text-xs text-ink-2">GPU 쿼터를 불러오지 못했습니다</p>
					{:else if gpuRows.length === 0}
						<p class="text-xs text-ink-2">할당된 GPU 쿼터 없음</p>
					{:else}
						{#each gpuRows as row (row.label)}
							{@render forecastRow(row, data.forecast.horizon_days)}
						{/each}
					{/if}
				</div>

				<div class="space-y-3">
					<SectionLabel>블록 스토리지</SectionLabel>
					{#if data.quota.storage_available === false}
						<p class="text-xs text-ink-2">블록 스토리지 쿼터를 불러오지 못했습니다</p>
					{:else}
						{#each storageRows as row (row.label)}
							{@render forecastRow(row, data.forecast.horizon_days)}
						{/each}
					{/if}
				</div>

				<p class="mt-auto text-xs text-ink-2">
					최근 {data.forecast.window_days}일 일별 할당량의 선형 추세를 {data.forecast.horizon_days}일 뒤로 연장한 값입니다. 블록 스토리지는 사용 이력 API가 없어 현재 사용량만 표시합니다.
				</p>
			</Card>
		</div>

		<Card padding="lg">
			<SectionHeader title="인스턴스별 사용 시간" meta="상위 {data.instance_usage.length}" />
			{#if data.instance_usage.length === 0}
				<div class="mt-6 py-6 text-center text-sm text-ink-2">데이터 없음</div>
			{:else}
				<TableShell density="compact" class="mt-4">
					<table>
						<thead>
							<tr>
								<th scope="col">인스턴스</th>
								<th scope="col">Flavor</th>
								<th scope="col">상태</th>
								<th scope="col">시작</th>
								<th scope="col">사용 시간(h)</th>
								<th scope="col">vCPU</th>
								<th scope="col">GPU</th>
							</tr>
						</thead>
						<tbody>
							{#each data.instance_usage as row (row.instance_id)}
								<tr>
									<td>
										<div class="text-ink-0">{row.name || '-'}</div>
										<div class="font-mono text-xs text-ink-2">{row.instance_id.slice(0, 8)}</div>
									</td>
									<td class="font-mono text-ink-2">{row.flavor}</td>
									<td>
										<div class="flex items-center gap-1.5">
											<StatusChip status={row.state} />
											{#if row.ended_at}
												<Pill tone="neutral">삭제됨</Pill>
											{/if}
										</div>
									</td>
									<td class="tabular-nums text-ink-2">{row.started_at ? formatDate(row.started_at) : '-'}</td>
									<td class="font-medium tabular-nums text-ink-0">{row.hours.toFixed(1)}</td>
									<td class="tabular-nums text-ink-2">{row.vcpus}</td>
									<td class="tabular-nums text-ink-2">{row.gpu_count || '-'}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</TableShell>
			{/if}
		</Card>

		<Card padding="lg">
			<SectionHeader title="프로젝트 리소스 현황" meta="현재 할당/한도" />
			<div class="mt-4">
				{#if inventoryState === 'loading'}
					<LoadingSkeleton variant="table" rows={4} />
				{:else if inventoryState === 'error'}
					<Alert tone="warning">프로젝트 리소스 현황을 불러오지 못했습니다. 새로고침으로 다시 시도하세요.</Alert>
				{:else}
					<div class="grid grid-cols-1 gap-3.5 md:grid-cols-2 lg:grid-cols-3">
						{#each inventoryGroups as group (group.title)}
							<section class="space-y-2.5" aria-label={group.title}>
								<SectionLabel>{group.title}</SectionLabel>
								{#each group.rows as row (row.label)}
									<CapacityBar label={row.label} used={row.item.in_use} total={row.item.limit} unit={row.unit} size="xs" />
								{/each}
								{#if group.title === '컴퓨트 한도' && isQuotaItem(inventory?.compute.key_pairs)}
									<StatTile label="키페어 한도 (사용자별)" value={inventory.compute.key_pairs.limit === -1 ? '무제한' : inventory.compute.key_pairs.limit} accent="blue" flat />
								{/if}
							</section>
						{/each}
						{#if objectStorage}
							<section class="space-y-2.5" aria-label="오브젝트 스토리지">
								<SectionLabel>오브젝트 스토리지</SectionLabel>
								<div class="grid gap-px overflow-hidden rounded-lg border border-line bg-line">
									<StatTile label="컨테이너" value={objectStorage.container_count.toLocaleString()} accent="blue" flat />
									<StatTile label="오브젝트" value={objectStorage.object_count.toLocaleString()} accent="cyan" flat />
									<StatTile label="사용량" value={objectStorage.bytes_used > 0 ? formatSize(objectStorage.bytes_used) : '0 B'} accent="violet" flat />
								</div>
							</section>
						{/if}
						{#if database}
							<section class="space-y-2.5" aria-label="데이터베이스">
								<SectionLabel>데이터베이스</SectionLabel>
								<div class="overflow-hidden rounded-lg border border-line">
									<StatTile label="DB 인스턴스" value={database.instances_count} accent="emerald" flat />
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
