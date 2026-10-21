<script lang="ts">
	import { projectNames } from '$lib/stores/projectNames';
	import type { PortInfo } from '$lib/types/networks';
	import Pagination from '$lib/components/ui/Pagination.svelte';
	import { t } from '$lib/i18n/ns/admin-network';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';

	let {
		ports,
		markerStack,
		nextMarker,
		onEdit,
		onDelete,
		onPrev,
		onNext,
		onintent,
	}: {
		ports: PortInfo[];
		markerStack: string[];
		nextMarker: string | null;
		onEdit: (port: PortInfo) => void;
		onDelete: (port: PortInfo) => void;
		onPrev: () => void;
		onNext: () => void;
		onintent?: () => void;
	} = $props();
</script>

<ResponsiveTable>
	{#snippet cards()}
		{#each ports as p (p.id)}
			<CompactResourceCard>
				<div class="flex items-start justify-between gap-2"><h3 class="break-all font-medium text-ink-0">{p.name || p.id.slice(0, 12)}</h3><StatusChip status={p.status} /></div>
				<div class="space-y-1 break-all text-xs text-ink-2"><p>{t('portsTable.ipAddress')}: {p.fixed_ips[0]?.ip_address ?? '-'}{p.fixed_ips.length > 1 ? ` (+${p.fixed_ips.length - 1})` : ''}</p><p>{t('portsTable.deviceOwner')}: {p.device_owner || '-'}</p><p>{t('portsTable.project')}: {p.project_id ? ($projectNames.get(p.project_id) ?? p.project_id.slice(0, 8)) : '-'}</p></div>
				{#snippet actions()}{#if !p.device_owner}<Button variant="secondary" size="sm" onclick={() => onEdit(p)}>{t('portsTable.edit')}</Button><Button variant="danger" size="sm" onclick={() => onDelete(p)}>{t('portsTable.delete')}</Button>{/if}{/snippet}
				{#snippet details()}<div class="space-y-2 break-all font-mono text-xs text-ink-2"><p>{p.id}</p><p>{p.project_id ?? '-'}</p>{#each p.fixed_ips as ip}<p>{ip.ip_address}</p>{/each}</div>{/snippet}
			</CompactResourceCard>
		{/each}
	{/snippet}
<div class="overflow-x-auto">
	<table class="w-full text-sm">
		<thead>
			<tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
				<th class="text-left py-2 pr-4">{t('portsTable.nameId')}</th>
				<th class="text-left py-2 pr-4">{t('portsTable.status')}</th>
				<th class="text-left py-2 pr-4">{t('portsTable.deviceOwner')}</th>
				<th class="text-left py-2 pr-4">{t('portsTable.ipAddress')}</th>
				<th class="text-left py-2 pr-4">{t('portsTable.project')}</th>
				<th class="text-left py-2">{t('portsTable.actions')}</th>
			</tr>
		</thead>
		<tbody>
			{#each ports as p (p.id)}
				<tr class="border-b border-line/50 text-xs hover:bg-surface-sunken/30 transition-colors">
					<td class="py-2 pr-4">
						<div class="text-ink-0 max-md:max-w-[66vw] max-md:truncate" title={p.name || ''}>{p.name || '-'}</div>
						<div class="text-ink-2 font-mono">{p.id.slice(0, 12)}...</div>
					</td>
					<td class="py-2 pr-4 {p.status === 'ACTIVE' ? 'text-green-400' : 'text-ink-2'}">{p.status}</td>
					<td class="py-2 pr-4 text-ink-2 text-xs break-all max-w-[160px]">{p.device_owner || '-'}</td>
					<td class="py-2 pr-4 font-mono text-ink-2">
						{#each p.fixed_ips as ip}
							<div>{ip.ip_address}</div>
						{/each}
						{#if p.fixed_ips.length === 0}-{/if}
					</td>
					<td class="py-2 pr-4 text-ink-2">{p.project_id ? ($projectNames.get(p.project_id) ?? p.project_id.slice(0, 8)) : '-'}</td>
					<td class="py-2">
						{#if !p.device_owner || p.device_owner === ''}
							<div class="flex items-center gap-1">
								<button
									onclick={() => onEdit(p)}
									class="px-2 py-0.5 text-xs bg-surface-selected hover:bg-surface-selected text-ink-2 rounded"
								>{t('portsTable.edit')}</button>
								<button
									onclick={() => onDelete(p)}
									class="px-2 py-0.5 text-xs bg-red-900/30 hover:bg-red-900/50 text-red-400 rounded"
								>{t('portsTable.delete')}</button>
							</div>
						{/if}
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>
</ResponsiveTable>
<Pagination
	page={markerStack.length + 1}
	hasPrev={markerStack.length > 0}
	hasNext={!!nextMarker}
	note={t('portsTable.count', { count: ports.length })}
	{onPrev}
	{onNext}
	{onintent}
/>
