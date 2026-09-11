<script lang="ts">
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
	<div class="text-red-400 text-sm">모니터링 데이터를 불러올 수 없습니다.</div>
{:else}
	<div class="grid grid-cols-1 lg:grid-cols-2 gap-6" data-tour="admin-monitoring-summary">
		<span class="sr-only" data-tour="admin-monitoring-summary-ready">모니터링 요약 준비됨</span>
		<!-- Compute -->
		<div class="bg-surface-base border border-line rounded-xl p-5">
			<div class="flex items-center justify-between mb-4">
				<h2 class="text-sm font-semibold text-ink-0">Compute</h2>
				<span class="text-xs text-ink-3">
					하이퍼바이저 <span class="text-green-400">{summary.compute.hypervisors_up}</span>/{summary.compute.hypervisors_total} up
				</span>
			</div>

			<div class="mb-4">
				<QuotaBar label="vCPU" used={summary.compute.vcpus_used} limit={summary.compute.vcpus_total} size="md" />
			</div>
			<div class="mb-4">
				<QuotaBar label="RAM (GB)" used={gb(summary.compute.memory_used_mb)} limit={gb(summary.compute.memory_total_mb)} size="md" />
			</div>

			<div class="mt-4 grid grid-cols-4 gap-2">
				<SummaryStatCard value={summary.compute.instance_stats?.active ?? 0} label="ACTIVE" valueClass="text-green-400" size="sm" />
				<SummaryStatCard value={summary.compute.instance_stats?.shutoff ?? 0} label="SHUTOFF" valueClass="text-ink-2" size="sm" />
				<SummaryStatCard value={summary.compute.instance_stats?.error ?? 0} label="ERROR" valueClass="text-red-400" size="sm" />
				<SummaryStatCard value={summary.compute.gpu_instances} label="GPU VM" valueClass="text-purple-400" size="sm" />
			</div>

			<div class="mt-3 text-xs text-ink-3 text-right">
				총 {summary.compute.instance_stats?.total ?? 0}개 인스턴스
			</div>
		</div>

		<!-- Storage -->
		<div class="bg-surface-base border border-line rounded-xl p-5">
			<h2 class="text-sm font-semibold text-ink-0 mb-4">스토리지</h2>

			<div class="grid grid-cols-2 gap-3 mb-4">
				<SummaryStatCard value={summary.storage.volume_count} label="볼륨" />
				<SummaryStatCard
					value={summary.storage.total_gb >= 1024
						? (summary.storage.total_gb / 1024).toFixed(1) + ' TB'
						: summary.storage.total_gb + ' GB'}
					label="총 용량"
				/>
			</div>

			{#if Object.keys(summary.storage.volume_by_status).length > 0}
				<div class="space-y-1.5">
					{#each Object.entries(summary.storage.volume_by_status) as [status, count]}
						<div class="flex justify-between text-xs">
							<span class="{status === 'available' ? 'text-green-400' : status === 'in-use' ? 'text-action-warm' : status === 'error' ? 'text-red-400' : 'text-ink-2'}">{status}</span>
							<span class="text-ink-2">{count}개</span>
						</div>
					{/each}
				</div>
			{/if}

			<div class="mt-4 pt-4 border-t border-line space-y-1.5 text-xs">
				<div class="flex items-center justify-between">
					<span class="text-ink-3">파일 스토리지</span>
					<span class="text-ink-2">{summary.storage.file_storage_count}개</span>
				</div>
				<div class="flex items-center justify-between">
					<span class="text-ink-3">볼륨 스냅샷</span>
					<span class="text-ink-2">{summary.storage.volume_snapshot_count ?? 0}개</span>
				</div>
				<div class="flex items-center justify-between">
					<span class="text-ink-3">볼륨 백업</span>
					<span class="text-ink-2">{summary.storage.volume_backup_count ?? 0}개</span>
				</div>
				<div class="flex items-center justify-between">
					<span class="text-ink-3">파일 스냅샷</span>
					<span class="text-ink-2">{summary.storage.share_snapshot_count ?? 0}개</span>
				</div>
				<div class="flex items-center justify-between">
					<span class="text-ink-3">이미지</span>
					<span class="text-ink-2">{summary.storage.image_count ?? 0}개</span>
				</div>
			</div>
		</div>

		<!-- Network -->
		<div class="bg-surface-base border border-line rounded-xl p-5">
			<h2 class="text-sm font-semibold text-ink-0 mb-4">네트워크</h2>

			<div class="grid grid-cols-2 gap-3 mb-3">
				<SummaryStatCard value={summary.network.network_count} label="네트워크" />
				<SummaryStatCard value={summary.network.router_count} label="라우터">
					{#snippet labelExtra()}
						<span class="text-green-400">({summary.network.router_active} active)</span>
					{/snippet}
				</SummaryStatCard>
				<SummaryStatCard value={summary.network.floatingip_count} label="Floating IP">
					{#snippet labelExtra()}
						<span class="text-green-400">({summary.network.floatingip_active} active)</span>
					{/snippet}
				</SummaryStatCard>
				<SummaryStatCard value={summary.network.port_count} label="포트" />
			</div>

			<div class="mt-3 pt-4 border-t border-line space-y-1.5 text-xs">
				<div class="flex items-center justify-between">
					<span class="text-ink-3">서브넷</span>
					<span class="text-ink-2">{summary.network.subnet_count ?? 0}개</span>
				</div>
				<div class="flex items-center justify-between">
					<span class="text-ink-3">Security Group</span>
					<span class="text-ink-2">{summary.network.security_group_count ?? 0}개</span>
				</div>
				<div class="flex items-center justify-between">
					<span class="text-ink-3">Load Balancer</span>
					<span class="text-ink-2">
						{summary.network.load_balancer_count ?? 0}개
						{#if (summary.network.load_balancer_count ?? 0) > 0}
							<span class="text-green-400">({summary.network.load_balancer_active ?? 0} active)</span>
						{/if}
					</span>
				</div>
			</div>
		</div>

		<!-- Containers -->
		<div class="bg-surface-base border border-line rounded-xl p-5">
			<h2 class="text-sm font-semibold text-ink-0 mb-4">컨테이너</h2>

			<div class="grid grid-cols-2 gap-3">
				<SummaryStatCard value={summary.containers.zun_count} label="Zun 컨테이너" size="lg" />
				<SummaryStatCard
					value={summary.containers.k3s_available === false ? '사용할 수 없음' : summary.containers.k3s_count}
					label="Drover 클러스터"
					size="lg"
				>
					{#snippet labelExtra()}
						{#if summary.containers.k3s_available !== false && (summary.containers.k3s_count ?? 0) > 0}
							<span class="text-green-400">({summary.containers.k3s_active ?? 0} active)</span>
						{/if}
					{/snippet}
				</SummaryStatCard>
			</div>

			<div class="mt-4 pt-4 border-t border-line grid grid-cols-2 gap-2">
				<a href="/admin/containers" class="flex items-center justify-center gap-1.5 text-xs text-action-warm hover:text-action-warm-hover transition-colors bg-surface-sunken rounded-lg py-2">
					컨테이너 목록 →
				</a>
				<a href="/admin/drover" class="flex items-center justify-center gap-1.5 text-xs text-action-warm hover:text-action-warm-hover transition-colors bg-surface-sunken rounded-lg py-2">
					Drover 클러스터 →
				</a>
			</div>
		</div>

		<!-- 데이터 서비스 -->
		<div class="bg-surface-base border border-line rounded-xl p-5">
			<h2 class="text-sm font-semibold text-ink-0 mb-4">데이터 서비스</h2>
			<div class="grid grid-cols-1 gap-3">
				<SummaryStatCard value={summary.data_services?.database_instance_count ?? 0} label="DB 인스턴스 (Trove)" size="lg" />
			</div>
			<div class="mt-4 pt-4 border-t border-line">
				<a href="/admin/database-instances" class="flex items-center justify-center gap-1.5 text-xs text-action-warm hover:text-action-warm-hover transition-colors bg-surface-sunken rounded-lg py-2">
					DB 인스턴스 →
				</a>
			</div>
		</div>

		<!-- Identity -->
		<div class="bg-surface-base border border-line rounded-xl p-5">
			<h2 class="text-sm font-semibold text-ink-0 mb-4">Identity</h2>
			<div class="grid grid-cols-2 gap-3">
				<SummaryStatCard value={summary.identity?.user_count ?? 0} label="사용자" size="lg" />
				<SummaryStatCard value={summary.identity?.project_count ?? 0} label="프로젝트" size="lg" />
			</div>
			<div class="mt-4 pt-4 border-t border-line grid grid-cols-2 gap-2">
				<a href="/admin/users" class="flex items-center justify-center gap-1.5 text-xs text-action-warm hover:text-action-warm-hover transition-colors bg-surface-sunken rounded-lg py-2">
					사용자 →
				</a>
				<a href="/admin/projects" class="flex items-center justify-center gap-1.5 text-xs text-action-warm hover:text-action-warm-hover transition-colors bg-surface-sunken rounded-lg py-2">
					프로젝트 →
				</a>
			</div>
		</div>
	</div>
{/if}
