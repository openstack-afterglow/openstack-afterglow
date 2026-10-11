<script lang="ts">
	import { t } from '$lib/i18n/ns/dashboard-home';
	import { Card, Pill } from '$lib/components/ui';
	import type { ResourceCategory, UserDashboardSummary } from '$lib/types/userDashboard';

	let { totals }: { totals: UserDashboardSummary['totals'] } = $props();
	const groups: { id: 'infrastructure' | 'network' | 'logical' | 'storage'; categories: ResourceCategory[] }[] = [
		{ id: 'infrastructure', categories: ['instances', 'volumes', 'images', 'keypairs', 'volume_snapshots', 'volume_backups'] },
		{ id: 'network', categories: ['floating_ips', 'networks', 'subnets', 'routers', 'security_groups', 'load_balancers'] },
		{ id: 'logical', categories: ['database_instances', 'database_backups', 'k3s_clusters', 'waygate_gateways', 'containers', 'magnum_clusters'] },
		{ id: 'storage', categories: ['shares', 'share_snapshots', 'share_networks', 'security_services', 'buckets', 'packages', 'secrets'] },
	];
	const metrics = ['vcpus', 'ram_mb', 'storage_gb'] as const;
</script>

<section data-resource-summary class="space-y-3 mb-5" aria-label={t('myResources.summaryTitle')}>
	<p class="text-xs text-ink-2">{t('myResources.countingHelp')}</p>
	<div class="grid grid-cols-1 lg:grid-cols-2 gap-3">
		{#each groups as group (group.id)}
			<Card surface="base">
				<h2 class="text-sm font-semibold mb-3">{t(`myResources.group.${group.id}`)}</h2>
				<dl class="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2">
					{#each group.categories as category (category)}
						{@const total = totals.resources[category]}
						<div data-total-category={category} data-total-state={total.state} class="flex flex-wrap items-center justify-between gap-2 text-xs border-b border-line pb-2">
							<dt class="text-ink-1">{t(`myResources.category.${category}`)}</dt>
							<dd class="flex items-center gap-2 tabular-nums">
								<span data-total-count>{total.state !== 'ready' || total.count === null ? t('myResources.unknown') : total.count}</span>
								{#if total.state !== 'ready'}
									<Pill tone={total.state === 'failed' ? 'danger' : total.state === 'denied' || total.state === 'partial' ? 'warning' : 'neutral'}>{t(`myResources.state.${total.state}`)}</Pill>
								{/if}
								{#if total.state === 'partial'}
									<span data-known-count class="text-ink-2">{t('myResources.knownCount', { count: total.known_count })}</span>
								{/if}
							</dd>
						</div>
					{/each}
				</dl>
			</Card>
		{/each}
	</div>
	<Card surface="base">
		<dl class="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
			{#each metrics as metric}
				{@const value = totals.usage[metric]}
				<div data-total-usage={metric} class="flex justify-between gap-2">
					<dt class="text-ink-2">{t(`myResources.usage.${metric}`)}</dt>
					<dd class="tabular-nums">{value === null ? t('myResources.unknown') : value}</dd>
				</div>
			{/each}
		</dl>
		<p class="text-xs text-ink-2 mt-2">{t('myResources.usageHelp')}</p>
	</Card>
</section>
