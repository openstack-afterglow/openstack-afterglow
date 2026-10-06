<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-ops';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { formatNumber } from '$lib/utils/format';
	import { AnimatedNumber } from '$lib/components/ui';
	import type { Overview } from '$lib/types/adminOverview';

	let { overview }: { overview: Overview } = $props();
	const count = (n: number) => formatNumber(Math.round(n));
</script>

<div class="motion-enter grid grid-cols-1 gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-3">
	<!-- 하이퍼바이저 -->
	<a href="/admin/hypervisors" class="flex items-center gap-3 bg-surface-base p-4 transition-colors hover:bg-surface-selected">
		<div class="flex size-8 shrink-0 items-center justify-center text-warm-text">
			<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2"/></svg>
		</div>
		<div class="flex-1 min-w-0">
			<div class="text-xs font-medium tracking-tight text-ink-2">{t('overview.kpi.hypervisors')}</div>
			<div class="flex items-baseline gap-2 mt-0.5">
				<div class="text-[28px] font-bold text-ink-0 leading-none"><AnimatedNumber value={overview.hypervisor_count} format={count} /></div>
				<span class="ml-auto text-xs text-warm-text">{t('overview.kpi.details')}</span>
			</div>
		</div>
	</a>

	<!-- 총 VM -->
	<a href="/admin/instances" class="flex items-center gap-3 bg-surface-base p-4 transition-colors hover:bg-surface-selected">
		<div class="flex size-8 shrink-0 items-center justify-center text-emerald-400">
			<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18"/></svg>
		</div>
		<div class="flex-1 min-w-0">
			<div class="text-xs font-medium tracking-tight text-ink-2">{t('overview.kpi.totalVms')}</div>
			<div class="flex items-baseline gap-2 mt-0.5 flex-wrap">
				<div class="text-[28px] font-bold text-ink-0 leading-none"><AnimatedNumber value={overview.running_vms} format={count} /></div>
				{#if overview.instance_stats}
					<div class="flex gap-2 text-xs ml-auto flex-wrap">
						<span class="text-emerald-400">● {overview.instance_stats.active.toLocaleString(intlLocale(), { useGrouping: false })}</span>
						<span class="text-red-400">{t('overview.kpi.errorCount', { count: overview.instance_stats.error })}</span>
					</div>
				{/if}
			</div>
			<span class="text-xs text-warm-text">{t('overview.kpi.viewAll')}</span>
		</div>
	</a>

	<!-- GPU VM -->
	<a href="/admin/instances" class="flex items-center gap-3 bg-surface-base p-4 transition-colors hover:bg-surface-selected">
		<div class="flex size-8 shrink-0 items-center justify-center text-violet-400">
			<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>
		</div>
		<div class="flex-1 min-w-0">
			<div class="text-xs font-medium tracking-tight text-ink-2">GPU VM</div>
			<div class="flex items-baseline gap-2 mt-0.5">
				<div class="text-[28px] font-bold {overview.gpu_instances > 0 ? 'text-violet-300' : 'text-ink-0'} leading-none"><AnimatedNumber value={overview.gpu_instances} format={count} /></div>
				<div class="text-ink-2 text-xs">{t('overview.kpi.instances')}</div>
			</div>
		</div>
	</a>
</div>
