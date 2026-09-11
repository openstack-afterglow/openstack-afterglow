<script lang="ts">
	import type { ProjectData } from '$lib/types/userDashboard';

	interface Props {
		projects: ProjectData[];
	}

	let { projects }: Props = $props();

	function formatRam(mb: number): string {
		if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
		return `${mb} MB`;
	}
</script>

{#if projects.length > 0}
	<div class="hidden sm:block bg-surface-base border border-line rounded-lg p-5 mb-5">
		<div class="text-ink-0 text-[15px] font-semibold mb-3.5">프로젝트별 사용량</div>
		<div class="bg-[#0B1220] border border-line rounded-lg overflow-hidden">
			<div class="grid grid-cols-[1.5fr_80px_80px_90px_80px_90px] px-4 py-2.5 border-b border-line text-[11px] uppercase tracking-wider text-ink-3 font-medium">
				<div>프로젝트</div>
				<div class="text-right">인스턴스</div>
				<div class="text-right">볼륨</div>
				<div class="text-right">스토리지</div>
				<div class="text-right">vCPU</div>
				<div class="text-right">RAM</div>
			</div>
			{#each projects as p}
				<div class="grid grid-cols-[1.5fr_80px_80px_90px_80px_90px] px-4 py-3 text-[13px] items-center border-b border-line last:border-b-0 hover:bg-surface-sunken/20 transition-colors">
					<div class="min-w-0">
						<div class="text-ink-0 font-medium truncate">{p.project_name}</div>
						{#if p.error}
							<span class="text-[10px] text-red-400">조회 실패</span>
						{/if}
					</div>
					<div class="text-right">
						{#if p.instance_count > 0}
							<span class="text-action-warm font-mono text-xs font-medium">{p.instance_count}</span>
						{:else}
							<span class="text-ink-3 text-xs">—</span>
						{/if}
					</div>
					<div class="text-right">
						{#if p.volume_count > 0}
							<span class="text-cyan-400 font-mono text-xs font-medium">{p.volume_count}</span>
						{:else}
							<span class="text-ink-3 text-xs">—</span>
						{/if}
					</div>
					<div class="text-right">
						{#if p.storage_gb > 0}
							<span class="text-violet-400 font-mono text-xs">{p.storage_gb} GB</span>
						{:else}
							<span class="text-ink-3 text-xs">—</span>
						{/if}
					</div>
					<div class="text-right">
						{#if p.vcpus > 0}
							<span class="text-emerald-400 font-mono text-xs">{p.vcpus}</span>
						{:else}
							<span class="text-ink-3 text-xs">—</span>
						{/if}
					</div>
					<div class="text-right">
						{#if p.ram_mb > 0}
							<span class="text-action-warm font-mono text-xs">{formatRam(p.ram_mb)}</span>
						{:else}
							<span class="text-ink-3 text-xs">—</span>
						{/if}
					</div>
				</div>
			{/each}
		</div>
	</div>
{/if}
