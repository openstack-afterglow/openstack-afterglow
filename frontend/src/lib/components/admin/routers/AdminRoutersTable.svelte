<script lang="ts">
	import type { AdminRouter } from '$lib/types/networks';
	import { t } from '$lib/i18n/ns/admin-network';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';

	let {
		routers,
		onEdit,
		onDelete,
	}: {
		routers: AdminRouter[];
		onEdit: (router: AdminRouter) => void;
		onDelete: (router: AdminRouter) => void;
	} = $props();
</script>

<ResponsiveTable>
	{#snippet cards()}
		{#each routers as r (r.id)}
			<CompactResourceCard>
				<div class="flex items-start justify-between gap-2"><h3 class="break-all font-medium text-ink-0">{r.name || r.id.slice(0, 8)}</h3><StatusChip status={r.status} /></div>
				<div class="space-y-1 text-xs text-ink-2"><p>{t('adminRoutersTable.subnetCount', { count: r.connected_subnet_ids.length })}</p><p>{t('adminRoutersTable.externalGateway')}: {r.external_gateway_network_id?.slice(0, 8) ?? '-'}</p><p>{t('adminRoutersTable.project')}: {r.project_id?.slice(0, 8) ?? '-'}</p></div>
				{#snippet actions()}<Button variant="secondary" size="sm" onclick={() => onEdit(r)}>{t('adminRoutersTable.edit')}</Button><Button variant="danger" size="sm" onclick={() => onDelete(r)}>{t('adminRoutersTable.delete')}</Button>{/snippet}
				{#snippet details()}<div class="space-y-2 break-all font-mono text-xs text-ink-2"><p>{r.id}</p><p>{r.project_id ?? '-'}</p><p>{r.external_gateway_network_id ?? '-'}</p>{#each r.connected_subnet_ids as id}<p>{id}</p>{/each}</div>{/snippet}
			</CompactResourceCard>
		{/each}
	{/snippet}
<div class="overflow-x-auto">
	<table class="w-full text-sm">
		<thead>
			<tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
				<th class="text-left py-2 pr-4">{t('adminRoutersTable.name')}</th>
				<th class="text-left py-2 pr-4">{t('adminRoutersTable.status')}</th>
				<th class="text-left py-2 pr-4">{t('adminRoutersTable.externalGateway')}</th>
				<th class="text-left py-2 pr-4">{t('adminRoutersTable.connectedSubnets')}</th>
				<th class="text-left py-2 pr-4">{t('adminRoutersTable.project')}</th>
				<th class="text-left py-2">{t('adminRoutersTable.actions')}</th>
			</tr>
		</thead>
		<tbody>
			{#each routers as r (r.id)}
				<tr class="border-b border-line/50 text-xs hover:bg-surface-sunken/30 transition-colors">
					<td class="py-2 pr-4 text-ink-0"><span class="max-md:block max-md:max-w-[66vw] max-md:truncate" title={r.name || r.id}>{r.name || r.id.slice(0, 8)}</span></td>
					<td class="py-2 pr-4 {r.status === 'ACTIVE' ? 'text-green-400' : 'text-ink-2'}">{r.status}</td>
					<td class="py-2 pr-4 text-ink-2 font-mono">
						{r.external_gateway_network_id ? r.external_gateway_network_id.slice(0, 8) + '...' : '-'}
					</td>
					<td class="py-2 pr-4 text-ink-2">{t('adminRoutersTable.subnetCount', { count: r.connected_subnet_ids.length })}</td>
					<td class="py-2 pr-4 text-ink-2 font-mono">{r.project_id?.slice(0, 8) ?? '-'}</td>
					<td class="py-2">
						<div class="flex items-center gap-1">
							<button onclick={() => onEdit(r)}
								class="px-2 py-0.5 text-xs bg-surface-selected hover:bg-surface-selected text-ink-2 rounded">{t('adminRoutersTable.edit')}</button>
							<button onclick={() => onDelete(r)}
								class="px-2 py-0.5 text-xs bg-red-900/30 hover:bg-red-900/50 text-red-400 rounded">{t('adminRoutersTable.delete')}</button>
						</div>
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>
</ResponsiveTable>
