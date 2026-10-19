<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-ops';
	import RichText from '$lib/i18n/RichText.svelte';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import QuotaBar from '$lib/components/ui/QuotaBar.svelte';
	import SummaryStatCard from './SummaryStatCard.svelte';
	import BklitChart from '$lib/components/charts/BklitChart.svelte';
	import type { ChartSpec } from '$lib/components/charts/types';
	import Pill from '$lib/components/ui/Pill.svelte';
	import { intlLocale } from '$lib/i18n/runtime.svelte';

	export type TelemetryStatus = 'available' | 'partial' | 'not_configured' | 'forbidden' | 'unavailable' | 'not_collected';
	export interface NativeMeter {
		series: { ts: number; value: number | null }[];
		source: 'gnocchi' | null;
		unit: string;
		status: TelemetryStatus;
		error: string | null;
	}
	export interface SystemTelemetry {
		source: 'gnocchi' | null;
		status: TelemetryStatus;
		error: string | null;
		truncated: boolean;
		resources: { id: string; name: string; type: string; metrics: Record<string, NativeMeter> }[];
	}

	export interface MonitoringSummary {
		telemetry?: SystemTelemetry;
		compute: {
			hypervisors_total: number;
			hypervisors_up: number;
			vcpus_used: number;
			vcpus_total: number;
			memory_used_mb: number;
			memory_total_mb: number;
			running_vms: number;
			gpu_instances: number;
			instance_stats: { total: number; active: number; shutoff: number; error: number; other: number };
		};
		storage: {
			volume_count: number;
			volume_by_status: Record<string, number>;
			total_gb: number;
			file_storage_count: number;
			volume_snapshot_count?: number;
			volume_backup_count?: number;
			share_snapshot_count?: number;
			image_count?: number;
		};
		network: {
			network_count: number;
			router_count: number;
			router_active: number;
			floatingip_count: number;
			floatingip_active: number;
			port_count: number;
			subnet_count?: number;
			security_group_count?: number;
			load_balancer_count?: number;
			load_balancer_active?: number;
		};
		containers: {
			zun_count: number;
			k3s_count: number;
			k3s_active?: number;
			k3s_available?: boolean;
		};
		data_services?: {
			database_instance_count: number;
		};
		identity?: {
			user_count: number;
			project_count: number;
		};
	}

	let {
		summary,
		loading,
		refreshing,
	}: {
		summary: MonitoringSummary | null;
		loading: boolean;
		refreshing: boolean;
	} = $props();

	// Keep DOM/chart work bounded even when the native provider returns many resources.
	const RESOURCE_LIMIT = 12;
	const METER_LIMIT = 12;
	let historyOpen = $state<Record<string, boolean>>({});
	const telemetry = $derived(summary?.telemetry);
	const resources = $derived((telemetry?.resources ?? []).slice(0, RESOURCE_LIMIT).map(resource => ({
		...resource,
		meters: Object.entries(resource.metrics).slice(0, METER_LIMIT).map(([name, meter]) => {
			const samples = meter.series.filter(point => Number.isFinite(point.ts)).map(point => ({
				ts: point.ts,
				value: typeof point.value === 'number' && Number.isFinite(point.value) ? point.value : null,
			})).sort((a, b) => a.ts - b.ts);
			return { name, ...meter, samples, latest: samples.at(-1), hasSamples: samples.some(point => point.value !== null) };
		}),
	})));
	const limited = $derived(telemetry?.truncated || (telemetry?.resources.length ?? 0) > RESOURCE_LIMIT || resources.some(resource => Object.keys(resource.metrics).length > METER_LIMIT));
	function statusLabel(status: TelemetryStatus) {
		const keys = {
			available: 'monitoring.telemetry.available', partial: 'monitoring.telemetry.partial',
			not_configured: 'monitoring.telemetry.notConfigured', forbidden: 'monitoring.telemetry.forbidden',
			unavailable: 'monitoring.telemetry.unavailable', not_collected: 'monitoring.telemetry.notCollected',
		} as const;
		return t(keys[status] ?? keys.unavailable);
	}
	function valueWithUnit(value: number | null | undefined, unit: string) {
		return value == null ? '—' : `${value.toLocaleString(intlLocale(), { maximumFractionDigits: 3 })} ${unit || t('monitoring.telemetry.unknownUnit')}`;
	}
	function time(ts: number) { return new Date(ts * 1000).toLocaleString(intlLocale()); }
	function historySpec(name: string, meter: NativeMeter, samples: NativeMeter['series']): ChartSpec {
		return {
			kind: 'time-series',
			data: samples.map(point => ({ time: point.ts * 1000, value: point.value })),
			xKey: 'time',
			series: [{ key: 'value', label: `${name} (${meter.unit || t('monitoring.telemetry.unknownUnit')})`, color: 'var(--color-chart-1)' }],
			formatValue: value => valueWithUnit(value, meter.unit),
		};
	}
	function gb(mb: number) { return Math.round(mb / 1024); }
</script>

{#if loading}
	<LoadingSkeleton variant="table" rows={6} />
{:else if !summary}
	<div class="text-red-400 text-sm">{t('monitoring.summary.loadFailed')}</div>
{:else}
	<div class="motion-stagger grid grid-cols-1 lg:grid-cols-2 gap-6" data-tour="admin-monitoring-summary">
		<span class="sr-only" data-tour="admin-monitoring-summary-ready">{t('monitoring.summary.ready')}</span>
		<section class="native-telemetry min-w-0 bg-surface-base border border-line rounded-xl p-5 lg:col-span-2" aria-labelledby="native-telemetry-title" aria-busy={refreshing}>
			<div class="flex min-w-0 flex-wrap items-center justify-between gap-3 mb-3">
				<h2 id="native-telemetry-title" class="text-sm font-semibold text-ink-0">{t('monitoring.telemetry.title')}</h2>
				<Pill class="telemetry-status" tone={telemetry?.status === 'available' ? 'success' : 'neutral'}>{statusLabel(telemetry?.status ?? 'unavailable')}</Pill>
			</div>
			<p class="text-xs text-ink-2 mb-2">{t('monitoring.telemetry.description')}</p>
			<p class="text-xs text-ink-2 mb-3">{t('monitoring.telemetry.policyCoverage')}</p>
			<p class="text-xs text-ink-2 mb-3">{t('monitoring.telemetry.source', { source: telemetry?.source === 'gnocchi' ? 'Gnocchi' : t('monitoring.telemetry.noSource') })}</p>
			{#if limited}<p class="text-xs text-state-warning-text mb-3" role="status">{t('monitoring.telemetry.limited')}</p>{/if}
			{#if resources.length === 0}
				<p class="text-sm text-ink-2" role="status">{t('monitoring.telemetry.noSamples')}</p>
			{:else}
				<div class="space-y-4">
					{#each resources as resource (`${resource.type}:${resource.id}`)}
						<section class="min-w-0 border-t border-line pt-4" aria-label={`${resource.name || resource.id} (${resource.type})`}>
							<h3 class="text-sm font-medium text-ink-1 break-all">{resource.name || resource.id}</h3>
							<p class="text-xs text-ink-2 break-all mb-3">{resource.type} · {resource.id}</p>
							<div class="grid min-w-0 grid-cols-1 md:grid-cols-2 gap-3">
								{#each resource.meters as meter (meter.name)}
									{@const historyKey = JSON.stringify([resource.type, resource.id, meter.name])}
									<div class="min-w-0 rounded-lg bg-surface-sunken p-3" role="group" aria-label={meter.name}>
										<div class="flex min-w-0 flex-wrap items-start justify-between gap-2">
											<h4 class="text-xs font-medium text-ink-1 break-all">{meter.name}</h4>
											<Pill class="telemetry-status" tone={meter.status === 'available' ? 'success' : 'neutral'}>{statusLabel(meter.status)}</Pill>
										</div>
										<p class="mt-2 text-sm text-ink-0 tabular-nums break-all">{t('monitoring.telemetry.latest')}: {valueWithUnit(meter.latest?.value, meter.unit)}</p>
										<p class="mt-1 text-xs text-ink-2 break-words">{t('monitoring.telemetry.source', { source: meter.source === 'gnocchi' ? 'Gnocchi' : t('monitoring.telemetry.noSource') })} · {t('monitoring.telemetry.unit', { unit: meter.unit || t('monitoring.telemetry.unknownUnit') })}</p>
										{#if meter.latest}<p class="mt-1 text-xs text-ink-2 break-words">{t('monitoring.telemetry.observedAt', { time: time(meter.latest.ts) })}</p>{/if}
										{#if meter.hasSamples}
											<details class="mt-2" bind:open={historyOpen[historyKey]}>
												<summary class="min-h-11 cursor-pointer py-3 text-xs text-ink-1 focus-visible:outline focus-visible:outline-accent">{t('monitoring.telemetry.history')}</summary>
												{#if historyOpen[historyKey]}<BklitChart spec={historySpec(meter.name, meter, meter.samples)} height={160} label={`${resource.name || resource.id} · ${meter.name} (${meter.unit})`} />{/if}
											</details>
										{:else}
											<p class="mt-2 text-xs text-ink-2">{t('monitoring.telemetry.noSamples')}</p>
										{/if}
									</div>
								{:else}
									<p class="text-xs text-ink-2">{t('monitoring.telemetry.noSamples')}</p>
								{/each}
							</div>
						</section>
					{/each}
				</div>
			{/if}
		</section>
		<!-- Compute -->
		<div class="bg-surface-base border border-line rounded-xl p-5">
			<div class="flex flex-wrap items-center justify-between gap-2 mb-4">
				<h2 class="text-sm font-semibold text-ink-0">{t('monitoring.summary.compute')}</h2>
				<span class="text-xs text-ink-2">
					{#snippet upCount(text: string)}<span class="text-green-400">{text}</span>{/snippet}
					<RichText segments={t.rich('monitoring.summary.hypervisors', { up: summary.compute.hypervisors_up, total: summary.compute.hypervisors_total })} tags={{ up: upCount }} />
				</span>
			</div>

			<p class="text-xs text-ink-2 mb-3">{t('monitoring.summary.allocationNotice')}</p>
			<div class="mb-4">
				<QuotaBar label={t('monitoring.summary.vcpuAllocation')} used={summary.compute.vcpus_used} limit={summary.compute.vcpus_total} size="md" />
			</div>
			<div class="mb-4">
				<QuotaBar label={t('monitoring.summary.ramAllocation')} used={gb(summary.compute.memory_used_mb)} limit={gb(summary.compute.memory_total_mb)} size="md" />
			</div>

			<div class="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-2">
				<SummaryStatCard value={summary.compute.instance_stats?.active ?? 0} label={t('monitoring.summary.activeStatus')} valueClass="text-green-400" size="sm" />
				<SummaryStatCard value={summary.compute.instance_stats?.shutoff ?? 0} label={t('monitoring.summary.shutoffStatus')} valueClass="text-ink-2" size="sm" />
				<SummaryStatCard value={summary.compute.instance_stats?.error ?? 0} label={t('monitoring.summary.errorStatus')} valueClass="text-red-400" size="sm" />
				<SummaryStatCard value={summary.compute.gpu_instances} label={t('monitoring.summary.gpuVm')} valueClass="text-purple-400" size="sm" />
			</div>

			<div class="mt-3 text-xs text-ink-2 text-right">
				{t('monitoring.summary.instanceTotal', { count: summary.compute.instance_stats?.total ?? 0 })}
			</div>
		</div>

		<!-- Storage -->
		<div class="bg-surface-base border border-line rounded-xl p-5">
			<h2 class="text-sm font-semibold text-ink-0 mb-4">{t('monitoring.summary.storage')}</h2>

			<div class="grid grid-cols-2 gap-3 mb-4">
				<SummaryStatCard value={summary.storage.volume_count} label={t('monitoring.summary.volumes')} />
				<SummaryStatCard
					value={summary.storage.total_gb >= 1024
						? (summary.storage.total_gb / 1024).toFixed(1) + ' TB'
						: summary.storage.total_gb + ' GB'}
					label={t('monitoring.summary.totalCapacity')}
				/>
			</div>

			{#if Object.keys(summary.storage.volume_by_status).length > 0}
				<div class="space-y-1.5">
					{#each Object.entries(summary.storage.volume_by_status) as [status, count]}
						<div class="flex justify-between text-xs">
							<span class="{status === 'available' ? 'text-green-400' : status === 'in-use' ? 'text-warm-text' : status === 'error' ? 'text-red-400' : 'text-ink-2'}">{status}</span>
							<span class="text-ink-2">{t('monitoring.summary.count', { count })}</span>
						</div>
					{/each}
				</div>
			{/if}

			<div class="mt-4 pt-4 border-t border-line space-y-1.5 text-xs">
				<div class="flex items-center justify-between">
					<span class="text-ink-2">{t('monitoring.summary.fileStorage')}</span>
					<span class="text-ink-2">{t('monitoring.summary.count', { count: summary.storage.file_storage_count })}</span>
				</div>
				<div class="flex items-center justify-between">
					<span class="text-ink-2">{t('monitoring.summary.volumeSnapshots')}</span>
					<span class="text-ink-2">{t('monitoring.summary.count', { count: summary.storage.volume_snapshot_count ?? 0 })}</span>
				</div>
				<div class="flex items-center justify-between">
					<span class="text-ink-2">{t('monitoring.summary.volumeBackups')}</span>
					<span class="text-ink-2">{t('monitoring.summary.count', { count: summary.storage.volume_backup_count ?? 0 })}</span>
				</div>
				<div class="flex items-center justify-between">
					<span class="text-ink-2">{t('monitoring.summary.fileSnapshots')}</span>
					<span class="text-ink-2">{t('monitoring.summary.count', { count: summary.storage.share_snapshot_count ?? 0 })}</span>
				</div>
				<div class="flex items-center justify-between">
					<span class="text-ink-2">{t('monitoring.summary.images')}</span>
					<span class="text-ink-2">{t('monitoring.summary.count', { count: summary.storage.image_count ?? 0 })}</span>
				</div>
			</div>
		</div>

		<!-- Network -->
		<div class="bg-surface-base border border-line rounded-xl p-5">
			<h2 class="text-sm font-semibold text-ink-0 mb-4">{t('monitoring.summary.network')}</h2>

			<div class="grid grid-cols-2 gap-3 mb-3">
				<SummaryStatCard value={summary.network.network_count} label={t('monitoring.summary.network')} />
				<SummaryStatCard value={summary.network.router_count} label={t('monitoring.summary.routers')}>
					{#snippet labelExtra()}
						<span class="text-green-400">{t('monitoring.summary.activeCount', { count: summary.network.router_active })}</span>
					{/snippet}
				</SummaryStatCard>
				<SummaryStatCard value={summary.network.floatingip_count} label={t('monitoring.summary.floatingIps')}>
					{#snippet labelExtra()}
						<span class="text-green-400">{t('monitoring.summary.activeCount', { count: summary.network.floatingip_active })}</span>
					{/snippet}
				</SummaryStatCard>
				<SummaryStatCard value={summary.network.port_count} label={t('monitoring.summary.ports')} />
			</div>

			<div class="mt-3 pt-4 border-t border-line space-y-1.5 text-xs">
				<div class="flex items-center justify-between">
					<span class="text-ink-2">{t('monitoring.summary.subnets')}</span>
					<span class="text-ink-2">{t('monitoring.summary.count', { count: summary.network.subnet_count ?? 0 })}</span>
				</div>
				<div class="flex items-center justify-between">
					<span class="text-ink-2">{t('monitoring.summary.securityGroups')}</span>
					<span class="text-ink-2">{t('monitoring.summary.count', { count: summary.network.security_group_count ?? 0 })}</span>
				</div>
				<div class="flex items-center justify-between">
					<span class="text-ink-2">{t('monitoring.summary.loadBalancers')}</span>
					<span class="text-ink-2">
						{t('monitoring.summary.count', { count: summary.network.load_balancer_count ?? 0 })}
						{#if (summary.network.load_balancer_count ?? 0) > 0}
							<span class="text-green-400">{t('monitoring.summary.activeCount', { count: summary.network.load_balancer_active ?? 0 })}</span>
						{/if}
					</span>
				</div>
			</div>
		</div>

		<!-- Containers -->
		<div class="bg-surface-base border border-line rounded-xl p-5">
			<h2 class="text-sm font-semibold text-ink-0 mb-4">{t('monitoring.summary.containers')}</h2>

			<div class="grid grid-cols-2 gap-3">
				<SummaryStatCard value={summary.containers.zun_count} label={t('monitoring.summary.zunContainers')} size="lg" />
				<SummaryStatCard
					value={summary.containers.k3s_available === false ? t('monitoring.summary.unavailable') : summary.containers.k3s_count}
					label={t('monitoring.summary.droverClusters')}
					size="lg"
				>
					{#snippet labelExtra()}
						{#if summary.containers.k3s_available !== false && (summary.containers.k3s_count ?? 0) > 0}
							<span class="text-green-400">{t('monitoring.summary.activeCount', { count: summary.containers.k3s_active ?? 0 })}</span>
						{/if}
					{/snippet}
				</SummaryStatCard>
			</div>

			<div class="mt-4 pt-4 border-t border-line grid grid-cols-2 gap-2">
				<a href="/admin/containers" class="flex items-center justify-center gap-1.5 text-xs text-warm-text hover:text-warm-text-hover transition-colors bg-surface-sunken rounded-lg py-2">
					{t('monitoring.summary.containerList')}
				</a>
				<a href="/admin/drover" class="flex items-center justify-center gap-1.5 text-xs text-warm-text hover:text-warm-text-hover transition-colors bg-surface-sunken rounded-lg py-2">
					{t('monitoring.summary.droverLink')}
				</a>
			</div>
		</div>

		<!-- 데이터 서비스 -->
		<div class="bg-surface-base border border-line rounded-xl p-5">
			<h2 class="text-sm font-semibold text-ink-0 mb-4">{t('monitoring.summary.dataServices')}</h2>
			<div class="grid grid-cols-1 gap-3">
				<SummaryStatCard value={summary.data_services?.database_instance_count ?? 0} label={t('monitoring.summary.databaseInstances')} size="lg" />
			</div>
			<div class="mt-4 pt-4 border-t border-line">
				<a href="/admin/database-instances" class="flex items-center justify-center gap-1.5 text-xs text-warm-text hover:text-warm-text-hover transition-colors bg-surface-sunken rounded-lg py-2">
					{t('monitoring.summary.databaseLink')}
				</a>
			</div>
		</div>

		<!-- Identity -->
		<div class="bg-surface-base border border-line rounded-xl p-5">
			<h2 class="text-sm font-semibold text-ink-0 mb-4">{t('monitoring.summary.identity')}</h2>
			<div class="grid grid-cols-2 gap-3">
				<SummaryStatCard value={summary.identity?.user_count ?? 0} label={t('monitoring.summary.users')} size="lg" />
				<SummaryStatCard value={summary.identity?.project_count ?? 0} label={t('monitoring.summary.projects')} size="lg" />
			</div>
			<div class="mt-4 pt-4 border-t border-line grid grid-cols-2 gap-2">
				<a href="/admin/users" class="flex items-center justify-center gap-1.5 text-xs text-warm-text hover:text-warm-text-hover transition-colors bg-surface-sunken rounded-lg py-2">
					{t('monitoring.summary.usersLink')}
				</a>
				<a href="/admin/projects" class="flex items-center justify-center gap-1.5 text-xs text-warm-text hover:text-warm-text-hover transition-colors bg-surface-sunken rounded-lg py-2">
					{t('monitoring.summary.projectsLink')}
				</a>
			</div>
		</div>
	</div>
{/if}

<style>
	.native-telemetry :global(.telemetry-status) {
		max-width: 100%;
		white-space: normal;
		overflow-wrap: anywhere;
		font-size: 0.75rem;
		color: var(--color-ink-1);
	}
</style>
