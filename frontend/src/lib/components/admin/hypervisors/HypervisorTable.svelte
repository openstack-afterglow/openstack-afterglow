<script lang="ts">
	import { formatNumber } from '$lib/utils/format';
	import HypervisorUsageBar from './HypervisorUsageBar.svelte';
	import { t } from '$lib/i18n/ns/admin-compute';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import TableColumnHeader from '$lib/components/ui/TableColumnHeader.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import { createTableView, type TableColumn } from '$lib/utils/tableView.svelte';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { t as tc } from '$lib/i18n/ns/common';

	export interface HypervisorRow {
		id: string;
		name: string;
		state: string;
		status: string;
		vcpus: number;
		vcpus_used: number;
		vcpus_allowed: number;
		memory_size_mb: number;
		memory_used_mb: number;
		memory_allowed_mb: number;
		local_disk_gb: number;
		local_disk_used_gb: number;
		running_vms: number;
		gpu_total?: number;
		gpu_used?: number;
		gpu_model?: string | null;
		gpu_models?: readonly string[];
		cpu_model?: string | null;
	}

	let {
		hypervisors,
		selectedId,
		onSelect,
	}: {
		hypervisors: HypervisorRow[];
		selectedId: string | null;
		onSelect: (id: string) => void;
	} = $props();

	const columns = $derived<TableColumn<HypervisorRow>[]>([
		{ key: 'name', label: t('hypervisors.table.hostname'), value: (row) => row.name },
		{ key: 'state', label: t('hypervisors.connection.label'), value: (row) => t(row.state === 'up' ? 'hypervisors.connection.up' : 'hypervisors.connection.down') },
		{ key: 'status', label: t('hypervisors.scheduling.label'), value: (row) => t(row.status === 'enabled' ? 'hypervisors.scheduling.enabled' : 'hypervisors.scheduling.disabled') },
		{ key: 'running_vms', label: t('hypervisors.table.vmCount'), value: (row) => row.running_vms, format: (_value, row) => formatNumber(row.running_vms) },
		{ key: 'cpu_model', label: t('hypervisors.cpuModel'), value: (row) => row.cpu_model },
		{ key: 'vcpus_used', label: 'vCPU', value: (row) => row.vcpus_used, format: (_value, row) => formatNumber(row.vcpus_used) },
		{ key: 'memory_used_mb', label: t('hypervisors.table.ram'), value: (row) => row.memory_used_mb, format: (value) => typeof value === 'number' ? `${formatNumber(Math.round(value / 1024))} GB` : '—' },
		{ key: 'gpu_model', label: t('hypervisors.table.gpuModel'), value: (row) => row.gpu_model, filterValues: (row) => row.gpu_models ?? (row.gpu_model ? [row.gpu_model] : []) },
		{ key: 'gpu_used', label: t('hypervisors.table.gpuCount'), value: (row) => (row.gpu_total ?? 0) > 0 ? row.gpu_used ?? 0 : null, format: (value) => typeof value === 'number' ? formatNumber(value) : '—' },
	]);
	const view = createTableView<HypervisorRow>({ rows: () => hypervisors, columns: () => columns, locale: intlLocale });
</script>

<TableViewControls {view} />
{#if view.rows.length === 0}<p class="py-4 text-sm text-ink-2">{hypervisors.length ? tc('table.noMatches') : t('hypervisors.page.empty')}</p>{/if}
<ResponsiveTable>
	{#snippet cards()}
		{#each view.rows as h (h.id)}
			<CompactResourceCard selected={selectedId === h.id}>
				<button type="button" class="min-h-11 break-all text-left font-mono font-medium text-ink-0" onclick={() => onSelect(h.id)}>{h.name}</button>
				<div class="flex flex-wrap gap-2 text-xs"><span class={h.state === 'up' ? 'text-state-success-text' : 'text-state-danger-text'}>{t(h.state === 'up' ? 'hypervisors.connection.up' : 'hypervisors.connection.down')}</span><span class={h.status === 'enabled' ? 'text-state-success-text' : 'text-state-warning-text'}>{t(h.status === 'enabled' ? 'hypervisors.scheduling.enabled' : 'hypervisors.scheduling.disabled')}</span></div>
				<div class="space-y-1 text-xs text-ink-2"><p>{t('hypervisors.table.vmCount')}: {formatNumber(h.running_vms)}</p><p>vCPU: {formatNumber(h.vcpus_used)}/{formatNumber(h.vcpus_allowed || h.vcpus)}</p><p>{t('hypervisors.table.ram')}: {formatNumber(Math.round(h.memory_used_mb / 1024))}/{formatNumber(Math.round((h.memory_allowed_mb || h.memory_size_mb) / 1024))} GB</p></div>
				{#snippet details()}<div class="space-y-2 break-all text-xs text-ink-2"><p class="font-mono">{h.id}</p><p>{t('hypervisors.cpuModel')}: {h.cpu_model ?? '-'}</p><p>{t('hypervisors.table.gpuModel')}: {h.gpu_model ?? '-'}</p><p>{t('hypervisors.table.gpuCount')}: {(h.gpu_total ?? 0) > 0 ? `${formatNumber(h.gpu_used ?? 0)}/${formatNumber(h.gpu_total ?? 0)}` : '-'}</p></div>{/snippet}
			</CompactResourceCard>
		{/each}
	{/snippet}
<div class="overflow-x-auto">
	<table class="w-full text-sm">
		<thead>
			<tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
				{#each columns as column (column.key)}<TableColumnHeader {view} columnKey={column.key} />{/each}
			</tr>
		</thead>
		<tbody>
			{#each view.rows as h (h.id)}
				<tr
					class="border-b border-line/50 text-xs transition-colors {selectedId === h.id ? 'bg-surface-sunken/70' : ''}"
				>
					<td class="p-0">
						<button type="button" onclick={() => onSelect(h.id)} class="block w-full py-2 pr-4 font-mono text-ink-0 hover:text-warm-text-hover transition-colors text-left" title={h.name}>{h.name}</button>
					</td>
					<td class="py-2 pr-4"><span class={h.state === 'up' ? 'text-[var(--color-state-success-text)]' : 'text-[var(--color-state-danger-text)]'}>{t(h.state === 'up' ? 'hypervisors.connection.up' : 'hypervisors.connection.down')}</span></td>
					<td class="py-2 pr-4"><span class={h.status === 'enabled' ? 'text-[var(--color-state-success-text)]' : 'text-[var(--color-state-warning-text)]'}>{t(h.status === 'enabled' ? 'hypervisors.scheduling.enabled' : 'hypervisors.scheduling.disabled')}</span></td>
					<td class="py-2 pr-4 text-ink-2">{formatNumber(h.running_vms)}</td>
					<td class="py-2 pr-4 text-ink-2 font-mono text-xs max-lg:hidden">{h.cpu_model ?? '-'}</td>
					<td class="py-2 pr-4">
						<HypervisorUsageBar
							used={h.vcpus_used}
							total={h.vcpus_allowed || h.vcpus}
							label="{formatNumber(h.vcpus_used)}/{formatNumber(h.vcpus_allowed || h.vcpus)}"
						/>
					</td>
					<td class="py-2 pr-4">
						<HypervisorUsageBar
							used={h.memory_used_mb}
							total={h.memory_allowed_mb || h.memory_size_mb}
							label="{formatNumber(Math.round(h.memory_used_mb/1024))}/{formatNumber(Math.round((h.memory_allowed_mb || h.memory_size_mb)/1024))}"
						/>
					</td>
					<td class="py-2 pr-4 text-xs {h.gpu_model ? 'text-ink-2 font-mono' : 'text-ink-2'}">{h.gpu_model ?? '-'}</td>
					<td class="py-2">
						{#if (h.gpu_total ?? 0) > 0}
							<HypervisorUsageBar
								used={h.gpu_used ?? 0}
								total={h.gpu_total ?? 0}
								label="{formatNumber(h.gpu_used ?? 0)}/{formatNumber(h.gpu_total ?? 0)}"
							/>
						{:else}
							<span class="text-ink-2">-</span>
						{/if}
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>
</ResponsiveTable>
