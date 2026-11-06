<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-network';
	import type { AdminNetwork } from '$lib/types/networks';
	import { ActionMenu, Button, ResourceIdentifier, StatusChip } from '$lib/components/ui';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import TableColumnHeader from '$lib/components/ui/TableColumnHeader.svelte';
	import type { createTableView } from '$lib/utils/tableView.svelte';

	let { networks, view, ownerNames, ownerDomains = new Map<string, string>(), emptyMessage, onRowClick, onEdit, onDelete }: {
		networks: AdminNetwork[];
		view: ReturnType<typeof createTableView<AdminNetwork>>;
		ownerNames: ReadonlyMap<string, string>;
		ownerDomains?: ReadonlyMap<string, string>;
		emptyMessage: string;
		onRowClick: (id: string) => void;
		onEdit: (network: AdminNetwork) => void;
		onDelete: (network: AdminNetwork) => void;
	} = $props();
	let openMenu = $state<string | null>(null);
</script>

{#snippet networkActions(network: AdminNetwork, surface: string)}
	<ActionMenu open={openMenu === `${surface}:${network.id}`} ariaLabel={t('list.actionsFor', { name: network.name || network.id })} onopen={() => openMenu = `${surface}:${network.id}`} onclose={() => openMenu = null}>
		<Button variant="ghost" class="w-full justify-start" onclick={() => { openMenu = null; onRowClick(network.id); }}>{t('list.details')}</Button>
		<Button variant="ghost" class="w-full justify-start" onclick={() => { openMenu = null; onEdit(network); }}>{t('adminNetworkTable.edit')}</Button>
		<Button variant="danger" class="w-full justify-start" onclick={() => { openMenu = null; onDelete(network); }}>{t('adminNetworkTable.delete')}</Button>
	</ActionMenu>
{/snippet}

{#snippet owner(network: AdminNetwork)}
	{#if network.project_id}
		{#if ownerNames.get(network.project_id) ?? network.project_name}<div class="text-ink-1">{ownerNames.get(network.project_id) ?? network.project_name}</div>{/if}
		{#if ownerDomains.get(network.project_id)}<ResourceIdentifier id={ownerDomains.get(network.project_id)} /><span class="mx-1 text-ink-3">/</span>{/if}
		<ResourceIdentifier id={network.project_id} />
	{:else}<span class="text-ink-2">—</span>{/if}
{/snippet}

<ResponsiveTable>
	{#snippet cards()}
		{#each networks as network (network.id)}
			<CompactResourceCard>
				<div class="flex items-center justify-between gap-2"><button type="button" class="min-h-11 min-w-0 break-all text-left font-medium text-ink-0 hover:text-warm-text" onclick={() => onRowClick(network.id)}>{network.name || network.id.slice(0, 8)}</button><StatusChip status={network.status} /></div>
				<ResourceIdentifier id={network.id} />
				<div class="text-sm text-ink-2">{@render owner(network)}</div>
				<div class="flex flex-wrap gap-2 text-sm text-ink-2"><span>{network.is_external ? t('adminNetworkTable.external') : t('adminNetworkTable.internal')}{network.is_shared ? ` · ${t('adminNetworkTable.shared')}` : ''}</span><span class="tabular-nums">{t('adminNetworkTable.subnetCount', { count: network.subnets.length })}</span></div>
				{#snippet actions()}{@render networkActions(network, 'card')}{/snippet}
			</CompactResourceCard>
		{/each}
		{#if networks.length === 0 && emptyMessage}<p class="col-span-full py-6 text-center text-sm text-ink-2">{emptyMessage}</p>{/if}
	{/snippet}
	<div class="overflow-x-auto rounded-lg border border-line bg-surface-base">
		<table class="w-full text-sm">
			<thead><tr class="border-b border-line text-left text-[13px] text-ink-2">
				{#each view.columns as column (column.key)}<TableColumnHeader {view} columnKey={column.key} />{/each}<th class="px-4 py-2 text-right font-medium">{t('adminNetworkTable.actions')}</th>
			</tr></thead>
			<tbody>
				{#each networks as network (network.id)}
					<tr class="border-b border-line last:border-b-0">
						<td class="px-4 py-2"><button type="button" onclick={() => onRowClick(network.id)} class="font-medium text-left text-ink-0 hover:text-warm-text" title={network.name || network.id}>{network.name || network.id.slice(0, 8)}</button><ResourceIdentifier id={network.id} /></td>
						<td class="px-4 py-2">{@render owner(network)}</td>
						<td class="px-4 py-2"><StatusChip status={network.status} /></td>
						<td class="px-4 py-2 text-ink-2">{network.is_external ? t('adminNetworkTable.external') : t('adminNetworkTable.internal')}{network.is_shared ? ` · ${t('adminNetworkTable.shared')}` : ''}</td>
						<td class="px-4 py-2 text-right tabular-nums text-ink-2">{network.subnets.length}</td>
						<td class="px-4 py-2"><div class="flex justify-end">{@render networkActions(network, 'row')}</div></td>
					</tr>
				{/each}
				{#if networks.length === 0 && emptyMessage}<tr><td colspan="6" class="px-4 py-6 text-center text-ink-2">{emptyMessage}</td></tr>{/if}
			</tbody>
		</table>
	</div>
</ResponsiveTable>
