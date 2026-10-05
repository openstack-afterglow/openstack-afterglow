<script lang="ts">
	import { t } from '$lib/i18n/ns/network-pages';
	let {
		visibleNetworkCount,
		projectRouterCount,
		instanceCount,
		projectFipCount,
		projectLbCount,
	}: {
		visibleNetworkCount: number;
		projectRouterCount: number;
		instanceCount: number;
		projectFipCount: number;
		projectLbCount: number;
	} = $props();
</script>

<div class="mt-4 flex gap-6 text-xs text-ink-2 px-1">
	<span>{t('topologySummary.networks', { count: visibleNetworkCount })}</span>
	<span>{t('topologySummary.routers', { count: projectRouterCount })}</span>
	<span>{t('topologySummary.instances', { count: instanceCount })}</span>
	<span>{t('topologySummary.floatingIps', { count: projectFipCount })}</span>
	<span>{t('topologySummary.loadBalancers', { count: projectLbCount })}</span>
</div>
