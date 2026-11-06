<script lang="ts">
	import { t } from '$lib/i18n/ns/network-pages';
	import type { TopologyLoadBalancer } from '$lib/types/topology';
	import { t as tc } from '$lib/i18n/ns/common';
	import { t as tr } from '$lib/i18n/ns/network-resources';
	import { createTableView, type TableColumn } from '$lib/utils/tableView.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import { untrack } from 'svelte';

	let {
		lb,
		onClose,
	}: {
		lb: TopologyLoadBalancer;
		onClose: () => void;
	} = $props();
	const listenerColumns = (): TableColumn<TopologyLoadBalancer['listeners'][number]>[] => [
		{ key: 'name', label: tc('table.name'), value: row => row.name || row.id },
		{ key: 'protocol', label: tr('securityGroup.rules.protocol'), value: row => row.protocol },
		{ key: 'port', label: tr('lb.form.port'), value: row => row.protocol_port },
	];
	const memberColumns = (): TableColumn<TopologyLoadBalancer['members'][number]>[] => [
		{ key: 'address', label: tr('lb.form.ipAddress'), value: row => row.address },
		{ key: 'port', label: tr('lb.form.port'), value: row => row.protocol_port },
		{ key: 'status', label: tc('table.status'), value: row => row.status },
	];
	const listenerView = createTableView({ rows: () => lb.listeners, columns: listenerColumns });
	const memberView = createTableView({ rows: () => lb.members, columns: memberColumns });
	const loadBalancerId = $derived(lb.id);
	$effect(() => { loadBalancerId; untrack(() => { listenerView.reset(); memberView.reset(); }); });
</script>

<div class="p-6 space-y-5">
	<div class="flex items-start justify-between">
		<div>
			<h2 class="text-lg font-semibold text-ink-0">{lb.name || t('topologyLoadBalancer.title')}</h2>
			<p class="text-xs text-ink-2 mt-0.5 font-mono">{lb.id}</p>
		</div>
		<!-- 닫기 버튼은 SlidePanel 이 제공한다(`[data-slide-panel-close]`) -->
	</div>
	<div class="grid grid-cols-2 gap-3 text-sm">
		<div class="bg-surface-sunken rounded-lg p-3">
			<p class="text-ink-2 text-xs mb-1">{t('topologyLoadBalancer.vipAddress')}</p>
			<p class="text-ink-0 font-mono">{lb.vip_address ?? '-'}</p>
		</div>
		<div class="bg-surface-sunken rounded-lg p-3">
			<p class="text-ink-2 text-xs mb-1">{t('topologyLoadBalancer.provisioningStatus')}</p>
			<p class="font-medium" style="color:{lb.provisioning_status === 'ACTIVE' ? '#22c55e' : '#f59e0b'}">{lb.provisioning_status}</p>
		</div>
		<div class="bg-surface-sunken rounded-lg p-3">
			<p class="text-ink-2 text-xs mb-1">{t('topologyLoadBalancer.operatingStatus')}</p>
			<p class="font-medium" style="color:{lb.operating_status === 'ONLINE' ? '#22c55e' : '#94a3b8'}">{lb.operating_status}</p>
		</div>
	</div>
	{#if lb.listeners.length > 0 || Object.keys(listenerView.filters).length || listenerView.sort}
		<div>
			<h3 class="text-sm font-medium text-ink-2 mb-2">{t('topologyLoadBalancer.listeners')}</h3>
			<TableViewControls view={listenerView} class="" />
			{#if lb.listeners.length > 0 && listenerView.rows.length === 0}<p class="text-sm text-ink-2">{tc('table.noMatches')}</p>{/if}
			<div class="space-y-1.5">
				{#each listenerView.rows as li (li.id)}
					<div class="bg-surface-sunken rounded-lg px-3 py-2 text-sm flex items-center gap-3">
						<span class="text-cyan-400 font-mono text-xs">{li.protocol}:{li.protocol_port}</span>
						<span class="text-ink-2 truncate">{li.name || li.id}</span>
					</div>
				{/each}
			</div>
		</div>
	{/if}
	{#if lb.members.length > 0 || Object.keys(memberView.filters).length || memberView.sort}
		<div>
			<h3 class="text-sm font-medium text-ink-2 mb-2">{t('topologyLoadBalancer.members', { count: lb.members.length })}</h3>
			<TableViewControls view={memberView} class="" />
			{#if lb.members.length > 0 && memberView.rows.length === 0}<p class="text-sm text-ink-2">{tc('table.noMatches')}</p>{/if}
			<div class="space-y-1.5">
				{#each memberView.rows as m (m.id)}
					<div class="bg-surface-sunken rounded-lg px-3 py-2 text-sm flex items-center gap-3">
						<span class="w-2 h-2 rounded-full flex-shrink-0" style="background:{m.status === 'ACTIVE' ? '#22c55e' : m.status === 'ERROR' ? '#ef4444' : '#64748b'}"></span>
						<span class="text-ink-0 font-mono text-xs">{m.address}:{m.protocol_port}</span>
						<span class="text-ink-2 text-xs">{m.status}</span>
						{#if !m.server_id}
							<span class="text-xs text-yellow-600">{t('topologyLoadBalancer.externalHost')}</span>
						{/if}
					</div>
				{/each}
			</div>
		</div>
	{/if}
</div>
