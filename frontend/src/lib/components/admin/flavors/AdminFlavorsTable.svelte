<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-compute';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import type { Flavor } from '$lib/types/flavor';
	import Pagination from '$lib/components/ui/Pagination.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import Button from '$lib/components/ui/Button.svelte';

	let {
		flavors,
		totalUnfiltered,
		pageSize,
		refreshing,
		deletingId = null,
		onManage,
		onDelete,
	}: {
		flavors: Flavor[];
		totalUnfiltered: number;
		pageSize: number;
		refreshing: boolean;
		deletingId?: string | null;
		onManage: (f: Flavor) => void;
		onDelete: (id: string) => Promise<void>;
	} = $props();

	let sortColumn = $state('');
	let sortAsc = $state(true);
	let currentPage = $state(0);

	function toggleSort(col: string) {
		if (sortColumn === col) {
			sortAsc = !sortAsc;
		} else {
			sortColumn = col;
			sortAsc = true;
		}
	}

	function sortIcon(col: string): string {
		if (sortColumn !== col) return '↕';
		return sortAsc ? '↑' : '↓';
	}

	function formatRam(mb: number): string {
		if (mb >= 1024) return `${(mb / 1024).toFixed(mb % 1024 === 0 ? 0 : 1)} GB`;
		return `${mb} MB`;
	}

	function isQuotaManaged(flavor: Flavor): boolean {
		return flavor.extra_specs?.['afterglow:access_mode'] === 'gpu_quota';
	}

	let sortedFlavors = $derived(
		flavors.toSorted((a, b) => {
			if (!sortColumn) return 0;
			let va: string | number, vb: string | number;
			if (sortColumn === 'is_public') {
				va = a.is_public ? 1 : 0;
				vb = b.is_public ? 1 : 0;
			} else {
				va = (a as unknown as Record<string, unknown>)[sortColumn] as string | number;
				vb = (b as unknown as Record<string, unknown>)[sortColumn] as string | number;
			}
			const cmp =
				typeof va === 'string' ? va.localeCompare(vb as string) : (va as number) - (vb as number);
			return sortAsc ? cmp : -cmp;
		}),
	);

	let totalPages = $derived(Math.max(1, Math.ceil(flavors.length / pageSize)));

	let pagedFlavors = $derived(
		sortedFlavors.slice(currentPage * pageSize, (currentPage + 1) * pageSize),
	);

	// Reset to page 0 when flavors list or pageSize changes
	$effect(() => {
		flavors;
		pageSize;
		currentPage = 0;
	});
</script>

<ResponsiveTable>
	{#snippet cards()}
		<div class="responsive-card-toolbar">
			<Button variant="ghost" size="sm" onclick={() => toggleSort('name')}>{t('flavors.fields.name')} {sortIcon('name')}</Button><Button variant="ghost" size="sm" onclick={() => toggleSort('vcpus')}>{t('flavors.fields.vcpu')} {sortIcon('vcpus')}</Button><Button variant="ghost" size="sm" onclick={() => toggleSort('ram')}>{t('flavors.fields.ram')} {sortIcon('ram')}</Button><Button variant="ghost" size="sm" onclick={() => toggleSort('disk')}>{t('flavors.fields.disk')} {sortIcon('disk')}</Button><Button variant="ghost" size="sm" onclick={() => toggleSort('is_public')}>{t('flavors.fields.public')} {sortIcon('is_public')}</Button>
		</div>
		{#each pagedFlavors as f (f.id)}
			<CompactResourceCard>
				<div class="flex flex-wrap items-start justify-between gap-2"><h3 class="break-all font-medium text-ink-0">{f.name}</h3><Pill tone="neutral" size="xs">{f.is_public ? t('flavors.visibility.public') : t('flavors.visibility.private')}</Pill>{#if f.is_gpu}<Pill tone="accent" size="xs">GPU ×{f.gpu_count}</Pill>{/if}</div>
				<p class="text-xs text-ink-2">{f.vcpus} vCPU · {formatRam(f.ram)} · {f.disk} GB</p>
				{#snippet actions()}<Button variant="secondary" size="sm" onclick={() => onManage(f)}>{t('flavors.manage.action')}</Button><Button variant="danger" size="sm" disabled={deletingId === f.id} onclick={() => onDelete(f.id)}>{deletingId === f.id ? t('flavors.delete.pending') : t('flavors.delete.action')}</Button>{/snippet}
				{#snippet details()}<div class="space-y-2 break-all text-xs text-ink-2"><p class="font-mono">{f.id}</p>{#if f.description}<p>{f.description}</p>{/if}{#if !f.is_public && f.is_gpu}<p>{isQuotaManaged(f) ? t('flavors.access.quotaPolicyTitle') : t('flavors.access.manualPolicyTitle')}</p>{/if}</div>{/snippet}
			</CompactResourceCard>
		{/each}
	{/snippet}
	<div class="overflow-x-auto">
		<table class="w-full text-sm">
			<thead>
				<tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
					<th
						class="text-left py-2 pr-4 cursor-pointer select-none hover:text-ink-1"
						onclick={() => toggleSort('name')}
					>{t('flavors.fields.name')} <span class="text-ink-2">{sortIcon('name')}</span></th>
					<th
						class="text-left py-2 pr-4 cursor-pointer select-none hover:text-ink-1"
						onclick={() => toggleSort('vcpus')}
					>{t('flavors.fields.vcpu')} <span class="text-ink-2">{sortIcon('vcpus')}</span></th>
					<th
						class="text-left py-2 pr-4 cursor-pointer select-none hover:text-ink-1"
						onclick={() => toggleSort('ram')}
					>{t('flavors.fields.ram')} <span class="text-ink-2">{sortIcon('ram')}</span></th>
					<th
						class="text-left py-2 pr-4 cursor-pointer select-none hover:text-ink-1"
						onclick={() => toggleSort('disk')}
					>{t('flavors.fields.disk')} <span class="text-ink-2">{sortIcon('disk')}</span></th>
					<th
						class="text-left py-2 pr-4 cursor-pointer select-none hover:text-ink-1"
						onclick={() => toggleSort('is_public')}
					>{t('flavors.fields.public')} <span class="text-ink-2">{sortIcon('is_public')}</span></th>
					<th class="text-left py-2 pr-4">{t('flavors.fields.gpu')}</th>
					<th class="text-right py-2">{t('flavors.table.actions')}</th>
				</tr>
			</thead>
			<tbody>
				{#each pagedFlavors as f (f.id)}
					<tr class="border-b border-line/50 text-xs hover:bg-surface-sunken/50 transition-colors">
						<td class="py-2 pr-4">
							<div class="min-w-0">
								<span class="text-ink-0 max-md:block max-md:max-w-[66vw] max-md:truncate" title={f.name}>{f.name}</span>
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
								{#if !f.is_public && f.is_gpu}
									<span title={isQuotaManaged(f) ? t('flavors.access.quotaPolicyTitle') : t('flavors.access.manualPolicyTitle')}>
										<Pill tone={isQuotaManaged(f) ? 'accent' : 'neutral'} size="xs">
											{isQuotaManaged(f) ? t('flavors.access.quotaLinked') : t('flavors.access.manual')}
										</Pill>
									</span>
								{/if}
							</div>
						</td>
						<td class="py-2 pr-4 text-ink-2">
							{#if f.is_gpu}
								<span class="text-purple-400">GPU{f.gpu_count > 1 ? ` x${f.gpu_count}` : ''}</span>
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
									disabled={deletingId === f.id}
									class="text-state-danger-text hover:text-state-danger-text/90 text-xs"
								>
									{#if deletingId === f.id}
										<span class="inline-flex items-center gap-2" role="status"><ActivityIndicator size="xs" tone="ink" /><span>{t('flavors.delete.pending')}</span></span>
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
