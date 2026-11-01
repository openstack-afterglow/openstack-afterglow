<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-ops';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import type { Overview } from '$lib/types/adminOverview';
	let { overview }: { overview: Overview } = $props();
	const rows = $derived([
		{ label: t('overview.kpi.hypervisors'), value: overview.hypervisor_count, href: '/admin/hypervisors' },
		{ label: t('overview.kpi.totalVms'), value: overview.instance_stats?.total ?? null, href: '/admin/instances' },
		{ label: t('overview.kpi.gpuVms'), value: overview.gpu_instances, href: '/admin/instances' },
	]);
</script>

<div class="grid grid-cols-1 gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-3">
	{#each rows as row}
		<a href={row.href} class="flex items-baseline justify-between gap-3 bg-surface-base px-4 py-3 text-sm transition-colors hover:bg-surface-selected">
			<span class="text-ink-2">{row.label}</span><span class="font-semibold tabular-nums text-ink-0">{row.value == null ? '—' : row.value.toLocaleString(intlLocale())}</span>
		</a>
	{/each}
</div>
