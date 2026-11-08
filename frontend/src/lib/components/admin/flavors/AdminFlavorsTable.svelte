<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-compute';
	import { t as poolText } from '$lib/i18n/ns/compute-pools';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import type { Flavor } from '$lib/types/flavor';
	import Pagination from '$lib/components/ui/Pagination.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import { isManagedFlavor } from '$lib/api/computePools';
	import TableColumnHeader from '$lib/components/ui/TableColumnHeader.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import type { createTableView } from '$lib/utils/tableView.svelte';

	let {
		flavors,
		view,
		search = '',
		totalUnfiltered,
		pageSize,
		refreshing,
		deletingId = null,
		onManage,
		onDelete,
		tourDeleteId = null,
	}: {
		flavors: Flavor[];
		view: ReturnType<typeof createTableView<Flavor>>;
		search?: string;
		totalUnfiltered: number;
		pageSize: number;
		refreshing: boolean;
		deletingId?: string | null;
		onManage: (f: Flavor) => void;
		onDelete: (id: string) => Promise<void>;
		tourDeleteId?: string | null;
	} = $props();

	let currentPage = $state(0);

	function formatRam(mb: number): string {
		if (mb >= 1024) return `${(mb / 1024).toFixed(mb % 1024 === 0 ? 0 : 1)} GB`;
		return `${mb} MB`;
	}


	let totalPages = $derived(Math.max(1, Math.ceil(flavors.length / pageSize)));

	let pagedFlavors = $derived(
		flavors.slice(currentPage * pageSize, (currentPage + 1) * pageSize),
	);

	// View criteria reset paging; refreshed arrays only clamp a now-missing page.
	$effect(() => {
		void pageSize;
		void search;
		void view.sort;
		void view.filters;
		currentPage = 0;
	});
	$effect(() => { if (currentPage >= totalPages) currentPage = totalPages - 1; });
</script>

<TableViewControls {view} />
<ResponsiveTable>
	{#snippet cards()}
		{#each pagedFlavors as f (f.id)}
			<CompactResourceCard>
				<div class="flex flex-wrap items-start justify-between gap-2"><h3 class="break-all font-medium text-ink-0">{f.display_name ?? f.name}</h3><Pill tone="neutral" size="xs">{f.is_public ? t('flavors.visibility.public') : t('flavors.visibility.private')}</Pill>{#if f.gpu_count === null || f.is_gpu === null}<Pill tone="neutral" size="xs">GPU · {poolText('unknown')}</Pill>{:else if f.is_gpu}<Pill tone="accent" size="xs">GPU ×{f.gpu_count}</Pill>{/if}</div>
				{#if f.display_name}<p class="break-all text-xs text-ink-2">{f.name} · <span class="font-mono">{f.id}</span></p>{/if}
				<p class="text-xs text-ink-2">{f.vcpus} vCPU · {formatRam(f.ram)} · {f.disk} GB</p>
				{#snippet actions()}<Button variant="secondary" size="sm" onclick={() => onManage(f)}>{t('flavors.manage.action')}</Button><Button variant="danger" size="sm" disabled={deletingId === f.id || isManagedFlavor(f)} onclick={() => onDelete(f.id)} dataTour={f.id === tourDeleteId ? 'admin-flavors-delete' : undefined}>{#if deletingId === f.id}<LoadingState variant="control" label="" aria-hidden="true" />{/if}{deletingId === f.id ? t('flavors.delete.pending') : t('flavors.delete.action')}</Button>{/snippet}
				{#snippet details()}<div class="space-y-2 break-all text-xs text-ink-2"><p class="font-mono">{f.id}</p>{#if f.description}<p>{f.description}</p>{/if}</div>{/snippet}
			</CompactResourceCard>
		{/each}
	{/snippet}
	<div class="overflow-x-auto">
		<table class="w-full text-sm">
			<thead>
				<tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
					{#each view.columns as column (column.key)}
						<TableColumnHeader {view} columnKey={column.key} />
					{/each}
					<th class="text-right py-2">{t('flavors.table.actions')}</th>
				</tr>
			</thead>
			<tbody>
				{#each pagedFlavors as f (f.id)}
					<tr class="border-b border-line/50 text-xs hover:bg-surface-sunken/50 transition-colors">
						<td class="py-2 pr-4">
							<div class="min-w-0">
								<span class="text-ink-0 max-md:block max-md:max-w-[66vw] max-md:truncate" title={f.name}>{f.display_name ?? f.name}</span>
								<p class="break-all text-xs text-ink-2">{#if f.display_name && f.display_name !== f.name}{f.name} · {/if}<span class="font-mono">{f.id}</span></p>
								{#if f.description}
									<div class="text-ink-2 text-xs mt-0.5">{f.description}</div>
								{/if}
							</div>
						</td>
						<td class="py-2 pr-4 text-ink-2">{f.vcpus}</td>
						<td class="py-2 pr-4 text-ink-2">{formatRam(f.ram)}</td>
						<td class="py-2 pr-4 text-ink-2">{f.disk} GB</td>
						<td class="py-2 pr-4">
							<div class="flex flex-wrap items-center gap-1">
								<span
									class="px-1.5 py-0.5 rounded text-xs font-medium {f.is_public
										? 'bg-green-900/30 text-green-400'
										: 'bg-yellow-900/30 text-yellow-400'}"
								>{f.is_public ? t('flavors.visibility.public') : t('flavors.visibility.private')}</span>
							</div>
						</td>
						<td class="py-2 pr-4 text-ink-2">
							{#if f.gpu_count === null || f.is_gpu === null}
								<span>GPU · {poolText('unknown')}</span>
							{:else if f.is_gpu}
								<span class="text-purple-400">GPU ×{f.gpu_count}</span>
							{:else}
								-
							{/if}
						</td>
						<td class="py-2 text-right">
							<div class="flex items-center justify-end gap-2">
								<button
									onclick={() => onManage(f)}
									class="text-warm-text hover:text-warm-text-hover text-xs"
								>{t('flavors.manage.action')}</button>
								<button
									onclick={() => onDelete(f.id)}
									data-tour={f.id === tourDeleteId ? 'admin-flavors-delete' : undefined}
									disabled={deletingId === f.id || isManagedFlavor(f)}
									class="text-state-danger-text hover:text-state-danger-text/90 text-xs"
								>
									{#if deletingId === f.id}
										<span class="inline-flex items-center gap-2" role="status"><LoadingState variant="control" label="" aria-hidden="true" /><span>{t('flavors.delete.pending')}</span></span>
									{:else}{t('flavors.delete.action')}{/if}
								</button>
							</div>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
</ResponsiveTable>
	<Pagination
		page={currentPage + 1}
		{totalPages}
		total={flavors.length}
		{pageSize}
		hasPrev={currentPage > 0}
		hasNext={currentPage < totalPages - 1}
		onPrev={() => { currentPage -= 1; }}
		onNext={() => { currentPage += 1; }}
		note={flavors.length < totalUnfiltered ? t('flavors.table.filteredNote', { count: totalUnfiltered }) : null}
	/>
