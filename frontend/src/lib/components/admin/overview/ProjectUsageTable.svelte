<script lang="ts">
	import type { ProjectUsage } from '$lib/types/adminOverview';
	import { usageBar, usageGrad, formatQuota } from '$lib/utils/usageBar';

	let {
		projects,
		loading,
		onSelectProject,
	}: {
		projects: ProjectUsage[];
		loading: boolean;
		onSelectProject: (p: ProjectUsage) => void;
	} = $props();
</script>

<div class="bg-surface-base border border-line rounded-lg p-5">
	<div class="text-ink-0 text-[15px] font-semibold mb-3.5">프로젝트별 리소스</div>
	{#if loading}
		<div class="space-y-2">
			{#each Array(4) as _}
				<div class="h-9 bg-surface-sunken rounded animate-pulse"></div>
			{/each}
		</div>
	{:else if projects.length > 0}
		<div class="overflow-x-auto" aria-label="프로젝트별 리소스 표">
		<!-- 테이블 헤더 -->
		<div class="grid min-w-[760px] grid-cols-[2fr_80px_120px_120px_120px_50px] rounded-t-lg border border-b-0 border-line bg-surface-sunken px-3.5 py-2 text-xs font-medium tracking-tight text-ink-2">
			<div>프로젝트</div><div class="text-right">VM</div><div>CPU</div><div>RAM</div><div>Disk</div><div class="text-right">GPU</div>
		</div>
		<div class="min-w-[760px] overflow-hidden rounded-b-lg border border-line">
			{#each projects.filter(p => p.instances.used > 0 || p.cpu.used > 0 || p.disk_gb.used > 0) as p, i}
				<button
					class="grid w-full grid-cols-[2fr_80px_120px_120px_120px_50px] items-center px-3.5 py-2.5 text-left text-[13px] transition-colors hover:bg-surface-selected {i < projects.filter(p => p.instances.used > 0 || p.cpu.used > 0 || p.disk_gb.used > 0).length - 1 ? 'border-b border-line' : ''}"
					onclick={() => { onSelectProject(p); }}
				>
					<div class="min-w-0">
						<span class="block break-words text-ink-0 font-medium">{p.project_name}</span>
						<span class="block break-all text-xs text-ink-2">{p.project_id.slice(0, 8)}</span>
					</div>
					<div class="text-right text-ink-2 font-mono text-xs">{formatQuota(p.instances.used, p.instances.quota)}</div>
					<div class="flex items-center gap-1.5">
						<div class="w-14 h-1.5 bg-surface-selected rounded-full overflow-hidden shrink-0">
							<div class="h-full rounded-full transition-all" style="width: {usageBar(p.cpu.used, p.cpu.quota)}%; background: {usageGrad(p.cpu.used, p.cpu.quota)}"></div>
						</div>
						<span class="text-ink-2 font-mono text-[11px] min-w-[24px]">{p.cpu.used}</span>
					</div>
					<div class="flex items-center gap-1.5">
						<div class="w-14 h-1.5 bg-surface-selected rounded-full overflow-hidden shrink-0">
							<div class="h-full rounded-full transition-all" style="width: {usageBar(p.ram_mb.used, p.ram_mb.quota)}%; background: {usageGrad(p.ram_mb.used, p.ram_mb.quota)}"></div>
						</div>
						<span class="text-ink-2 font-mono text-[11px] min-w-[28px]">{Math.round(p.ram_mb.used/1024)}G</span>
					</div>
					<div class="flex items-center gap-1.5">
						<div class="w-14 h-1.5 bg-surface-selected rounded-full overflow-hidden shrink-0">
							<div class="h-full rounded-full transition-all" style="width: {usageBar(p.disk_gb.used, p.disk_gb.quota)}%; background: {usageGrad(p.disk_gb.used, p.disk_gb.quota)}"></div>
						</div>
						<span class="text-ink-2 font-mono text-[11px] min-w-[28px]">{Math.round(p.disk_gb.used)}G</span>
					</div>
					<div class="text-right">
						{#if p.gpu_instances > 0}
							<span class="text-violet-400 font-mono text-xs">{p.gpu_instances}</span>
						{:else}
							<span class="text-ink-2 text-xs">—</span>
						{/if}
					</div>
				</button>
			{/each}
		</div>
		</div>
	{:else}
		<div class="text-ink-2 text-sm py-6 text-center">데이터가 없습니다</div>
	{/if}
</div>
