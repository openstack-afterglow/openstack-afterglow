<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-network';
	import type { AdminNetwork } from '$lib/types/networks';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';

	let {
		networks,
		ownerNames,
		emptyMessage,
		onRowClick,
		onEdit,
		onDelete,
	}: {
		networks: AdminNetwork[];
		ownerNames: ReadonlyMap<string, string>;
		emptyMessage: string;
		onRowClick: (id: string) => void;
		onEdit: (n: AdminNetwork) => void;
		onDelete: (n: AdminNetwork) => void;
	} = $props();
</script>

<ResponsiveTable>
	{#snippet cards()}
		{#each networks as n (n.id)}
			<CompactResourceCard>
				<div class="flex items-start justify-between gap-2"><button type="button" class="min-h-11 break-all text-left font-medium text-ink-0" onclick={() => onRowClick(n.id)}>{n.name || n.id.slice(0, 8)}</button><StatusChip status={n.status} /></div>
				<div class="space-y-1 text-xs text-ink-2"><p>{t('adminNetworkTable.owner')}: {n.project_id ? (ownerNames.get(n.project_id) ?? n.project_name ?? n.project_id.slice(0, 8)) : '-'}</p><p>{n.is_external ? t('adminNetworkTable.external') : t('adminNetworkTable.internal')}{n.is_shared ? ` · ${t('adminNetworkTable.shared')}` : ''} · {t('adminNetworkTable.subnetCount', { count: n.subnets.length })}</p></div>
				{#snippet actions()}<Button variant="secondary" size="sm" onclick={() => onEdit(n)}>{t('adminNetworkTable.edit')}</Button><Button variant="danger" size="sm" onclick={() => onDelete(n)}>{t('adminNetworkTable.delete')}</Button>{/snippet}
				{#snippet details()}<div class="space-y-2 break-all font-mono text-xs text-ink-2"><p>{n.id}</p><p>{n.project_id ?? '-'}</p>{#each n.subnets as subnet}<p>{subnet}</p>{/each}</div>{/snippet}
			</CompactResourceCard>
		{/each}
		{#if networks.length === 0 && emptyMessage}<p class="col-span-full py-6 text-center text-sm text-ink-2">{emptyMessage}</p>{/if}
	{/snippet}
<div class="overflow-x-auto">
	<table class="w-full text-sm">
		<thead>
			<tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
				<th class="text-left py-2 pr-4">{t('adminNetworkTable.name')}</th>
				<th class="text-left py-2 pr-4">{t('adminNetworkTable.owner')}</th>
				<th class="text-left py-2 pr-4">{t('adminNetworkTable.status')}</th>
				<th class="text-left py-2 pr-4">{t('adminNetworkTable.type')}</th>
				<th class="text-left py-2 pr-4">{t('adminNetworkTable.subnets')}</th>
				<th class="text-left py-2">{t('adminNetworkTable.actions')}</th>
			</tr>
		</thead>
		<tbody>
			{#each networks as n (n.id)}
				<tr
					class="border-b border-line/50 text-xs transition-colors"
				>
					<td class="p-0">
						<button type="button" onclick={() => onRowClick(n.id)} class="block w-full py-2 pr-4 font-medium text-ink-0 hover:text-warm-text-hover transition-colors text-left" title={n.name || n.id}><span class="max-md:block max-md:max-w-[66vw] max-md:truncate">{n.name || n.id.slice(0, 8)}</span></button>
					</td>
					<td class="py-2 pr-4">
						{#if n.project_id}
							{#if ownerNames.get(n.project_id) ?? n.project_name}<div class="text-ink-1">{ownerNames.get(n.project_id) ?? n.project_name}</div>{/if}
							<div class="font-mono text-ink-2 break-all">{n.project_id}</div>
						{:else}<span class="text-ink-2">-</span>{/if}
					</td>
					<td class="py-2 pr-4 {n.status === 'ACTIVE' ? 'text-green-400' : 'text-ink-2'}">{n.status}</td>
					<td class="py-2 pr-4">
						{#if n.is_external}<span class="px-1.5 py-0.5 bg-orange-900/30 text-orange-300 rounded text-xs mr-1">{t('adminNetworkTable.external')}</span>{/if}
						{#if n.is_shared}<span class="px-1.5 py-0.5 bg-surface-selected/30 text-warm-text rounded text-xs">{t('adminNetworkTable.shared')}</span>{/if}
						{#if !n.is_external && !n.is_shared}<span class="text-ink-2">{t('adminNetworkTable.internal')}</span>{/if}
					</td>
					<td class="py-2 pr-4 text-ink-2">{t('adminNetworkTable.subnetCount', { count: n.subnets.length })}</td>
					<td class="py-2" onclick={(e) => e.stopPropagation()}>
						<div class="flex items-center gap-1">
							<button
								onclick={() => onEdit(n)}
								class="px-2 py-0.5 text-xs bg-surface-selected hover:bg-surface-selected text-ink-2 rounded"
							>{t('adminNetworkTable.edit')}</button>
							<button
								onclick={() => onDelete(n)}
								class="px-2 py-0.5 text-xs bg-red-900/30 hover:bg-red-900/50 text-red-400 rounded"
							>{t('adminNetworkTable.delete')}</button>
						</div>
					</td>
				</tr>
			{/each}
			{#if networks.length === 0 && emptyMessage}
				<tr><td colspan="6" class="py-6 text-center text-ink-2">{emptyMessage}</td></tr>
			{/if}
		</tbody>
	</table>
</div>
</ResponsiveTable>
