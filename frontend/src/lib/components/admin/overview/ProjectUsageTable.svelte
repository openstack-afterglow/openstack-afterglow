<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-ops';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import type { ProjectUsage } from '$lib/types/adminOverview';
	import UsageBar from '$lib/components/ui/UsageBar.svelte';

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
	<div class="text-ink-0 text-[15px] font-semibold mb-3.5">{t('overview.projects.title')}</div>
	{#if loading}
		<div class="space-y-2" role="status" aria-busy="true" aria-label={t('overview.projects.loading')}>
			{#each Array(4) as _}
				<div class="h-9 motion-skeleton rounded"></div>
			{/each}
		</div>
	{:else if projects.length > 0}
		<div class="overflow-x-auto" aria-label={t('overview.projects.tableLabel')}>
		<!-- 테이블 헤더 -->
		<div class="grid min-w-[760px] grid-cols-[2fr_80px_120px_120px_120px_50px] gap-x-3 rounded-t-lg border border-b-0 border-line bg-surface-sunken px-3.5 py-2 text-xs font-medium tracking-tight text-ink-2">
			<div>{t('overview.projects.project')}</div><div class="text-right">VM</div><div>CPU</div><div>RAM</div><div>{t('overview.projects.disk')}</div><div class="text-right">GPU</div>
		</div>
		<div class="min-w-[760px] overflow-hidden rounded-b-lg border border-line">
			{#each projects.filter(p => p.instances.used > 0 || p.cpu.used > 0 || p.disk_gb.used > 0) as p, i}
				<button
					class="grid w-full grid-cols-[2fr_80px_120px_120px_120px_50px] items-center gap-x-3 px-3.5 py-2.5 text-left text-[13px] transition-colors hover:bg-surface-selected {i < projects.filter(p => p.instances.used > 0 || p.cpu.used > 0 || p.disk_gb.used > 0).length - 1 ? 'border-b border-line' : ''}"
					onclick={() => { onSelectProject(p); }}
				>
					<div class="min-w-0">
						<span class="block break-words text-ink-0 font-medium">{p.project_name}</span>
						<span class="block break-all text-xs text-ink-2">{p.project_id.slice(0, 8)}</span>
					</div>
					<div class="min-w-0 break-all text-right text-ink-2 font-mono text-xs">{p.instances.used.toLocaleString(intlLocale(), { useGrouping: false })}/{p.instances.quota === -1 ? '∞' : p.instances.quota.toLocaleString(intlLocale(), { useGrouping: false })}</div>
					<div class="flex min-w-0 items-center gap-1.5">
						<UsageBar value={p.cpu.used} max={p.cpu.quota} size="sm" showValue={false} class="w-14 shrink-0" />
						<span class="min-w-0 break-all text-ink-2 font-mono text-xs">{p.cpu.used.toLocaleString(intlLocale(), { useGrouping: false })}</span>
					</div>
					<div class="flex min-w-0 items-center gap-1.5">
						<UsageBar value={p.ram_mb.used} max={p.ram_mb.quota} size="sm" showValue={false} class="w-14 shrink-0" />
						<span class="min-w-0 break-all text-ink-2 font-mono text-xs">{Math.round(p.ram_mb.used/1024).toLocaleString(intlLocale(), { useGrouping: false })}G</span>
					</div>
					<div class="flex min-w-0 items-center gap-1.5">
						<UsageBar value={p.disk_gb.used} max={p.disk_gb.quota} size="sm" showValue={false} class="w-14 shrink-0" />
						<span class="min-w-0 break-all text-ink-2 font-mono text-xs">{Math.round(p.disk_gb.used).toLocaleString(intlLocale(), { useGrouping: false })}G</span>
					</div>
					<div class="text-right">
						{#if p.gpu_instances > 0}
							<span class="text-violet-400 font-mono text-xs">{p.gpu_instances.toLocaleString(intlLocale(), { useGrouping: false })}</span>
						{:else}
							<span class="text-ink-2 text-xs">—</span>
						{/if}
					</div>
				</button>
			{/each}
		</div>
		</div>
	{:else}
		<div class="text-ink-2 text-sm py-6 text-center">{t('overview.projects.empty')}</div>
	{/if}
</div>
