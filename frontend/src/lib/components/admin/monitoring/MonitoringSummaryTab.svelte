<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-ops';
	import RichText from '$lib/i18n/RichText.svelte';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import QuotaBar from '$lib/components/ui/QuotaBar.svelte';
	import SummaryStatCard from './SummaryStatCard.svelte';

	export interface MonitoringSummary {
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

	function pct(used: number, total: number) {
		if (!total) return 0;
		return Math.min(100, Math.round((used / total) * 100));
	}
	function gb(mb: number) { return Math.round(mb / 1024); }
</script>

{#if loading}
	<LoadingSkeleton variant="table" rows={6} />
{:else if !summary}
	<div class="text-red-400 text-sm">{t('monitoring.summary.loadFailed')}</div>
{:else}
	<div class="grid grid-cols-1 lg:grid-cols-2 gap-6" data-tour="admin-monitoring-summary">
		<span class="sr-only" data-tour="admin-monitoring-summary-ready">{t('monitoring.summary.ready')}</span>
		<!-- Compute -->
		<div class="bg-surface-base border border-line rounded-xl p-5">
			<div class="flex items-center justify-between mb-4">
				<h2 class="text-sm font-semibold text-ink-0">{t('monitoring.summary.compute')}</h2>
				<span class="text-xs text-ink-2">
					{#snippet upCount(text: string)}<span class="text-green-400">{text}</span>{/snippet}
					<RichText segments={t.rich('monitoring.summary.hypervisors', { up: summary.compute.hypervisors_up, total: summary.compute.hypervisors_total })} tags={{ up: upCount }} />
				</span>
			</div>

			<div class="mb-4">
				<QuotaBar label="vCPU" used={summary.compute.vcpus_used} limit={summary.compute.vcpus_total} size="md" />
			</div>
			<div class="mb-4">
				<QuotaBar label="RAM (GB)" used={gb(summary.compute.memory_used_mb)} limit={gb(summary.compute.memory_total_mb)} size="md" />
			</div>

			<div class="mt-4 grid grid-cols-4 gap-2">
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
