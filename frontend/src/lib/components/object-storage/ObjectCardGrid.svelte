<script lang="ts">
	import { t } from '$lib/i18n/ns/object-storage';
	import { untrack } from 'svelte';
	import { useObjectBrowser } from '$lib/stores/objectBrowser.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { EmptyState, SelectionCheckbox } from '$lib/components/ui';
	import ObjectFileCard from './ObjectFileCard.svelte';
	import ObjectFolderCard from './ObjectFolderCard.svelte';
	import { createArrivals } from './arrivals';
 import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';

	const s = useObjectBrowser();
	const folders = $derived(s.gridRows.filter((row) => row.isDir));
	const files = $derived(s.gridRows.filter((row) => !row.isDir));
	const searching = $derived(s.filterText.length > 0);

	// Keep the route-owned history through tab/view changes and loading skeleton swaps.
	// Opacity only: cards hold fixed-position action menus.
	let { arrivals = createArrivals() }: { arrivals?: ReturnType<typeof createArrivals> } = $props();
	let arrivalContainer = untrack(() => s.containerName);
	$effect.pre(() => {
		const name = s.containerName;
		if (name === arrivalContainer) return;
		arrivalContainer = name;
		arrivals.reset();
	});

	// Retain a settled directory only while refreshing that exact listing.
	let completedListing = $state<string | null>(null);
	let completedObjects = $state.raw<typeof s.objects | null>(null);
	let pendingListing = '';
	let listingWasLoading = true;
	$effect.pre(() => {
		const owner = JSON.stringify([s.containerName, s.prefix]);
		if (s.loading) pendingListing = owner;
		else if (listingWasLoading) {
			completedListing = pendingListing || owner;
			completedObjects = s.objects;
		}
		listingWasLoading = s.loading;
	});
	const retainedListing = $derived(completedObjects === s.objects && completedListing === JSON.stringify([s.containerName, s.prefix]));
</script>

{#if s.loading && retainedListing}<LoadingState variant="inline" />{/if}
{#if s.loading && !retainedListing}
	<LoadingState variant="surface" />
{:else if s.gridRows.length === 0}
	<EmptyState
		icon="M2 6a2 2 0 012-2h4l2 2h6a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z"
		headline={searching ? t('views.cardGrid.noResults') : t('views.cardGrid.noObjects')}
		description={searching
			? t('views.cardGrid.searchHint')
			: t('views.cardGrid.emptyHint')}
	/>
{:else}
 <ResponsiveTable>
  {#snippet cards()}
   <div class="responsive-card-toolbar flex flex-wrap items-center gap-2 text-xs"><SelectionCheckbox checked={s.visibleSelectedCount > 0 && s.visibleSelectedCount === s.visibleObjectCount} indeterminate={s.visibleSelectedCount > 0 && s.visibleSelectedCount < s.visibleObjectCount} disabled={s.bulkDeleting || s.bulkMoving} ariaLabel={t('views.cardGrid.selectAllVisible')} onclick={s.toggleSelectAll} /><span>{t('views.cardGrid.objectCount', { count: s.visibleObjectCount })}</span></div>
   {#each s.gridRows as row (row.obj.name)}{#if row.isDir}<ObjectFolderCard obj={row.obj} />{:else}<ObjectFileCard obj={row.obj} fullPath={row.fullPath} compact />{/if}{/each}
  {/snippet}
	<div class="space-y-4">
		<div class="flex items-center gap-2.5 border-b border-line pb-2">
			<SelectionCheckbox
				checked={s.visibleSelectedCount > 0 && s.visibleSelectedCount === s.visibleObjectCount}
				indeterminate={s.visibleSelectedCount > 0 && s.visibleSelectedCount < s.visibleObjectCount}
				disabled={s.bulkDeleting || s.bulkMoving}
				ariaLabel={t('views.cardGrid.selectAllVisible')}
				onclick={s.toggleSelectAll}
			/>
			<span class="text-xs text-ink-2">{t('views.cardGrid.objectCount', { count: s.visibleObjectCount })}</span>
		</div>

		{#if folders.length}
			<section class="space-y-2">
				<h3 class="text-xs font-medium uppercase tracking-wider text-ink-2">{t('views.cardGrid.folders')}</h3>
				<div class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
					{#each folders as row (row.obj.name)}
						{@const order = arrivals.next(row.obj.name)}
						<div class="grid grid-cols-1" class:motion-fade={order !== null} style:--motion-index={order}>
							<ObjectFolderCard obj={row.obj} />
						</div>
					{/each}
				</div>
			</section>
		{/if}

		{#if files.length}
			<section class="space-y-2">
				<h3 class="text-xs font-medium uppercase tracking-wider text-ink-2">{t('views.cardGrid.files')}</h3>
				<div class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
					{#each files as row (row.obj.name)}
						{@const order = arrivals.next(row.obj.name)}
						<div class="grid grid-cols-1" class:motion-fade={order !== null} style:--motion-index={order}>
							<ObjectFileCard obj={row.obj} fullPath={row.fullPath} />
						</div>
					{/each}
				</div>
			</section>
		{/if}
	</div>
 </ResponsiveTable>
{/if}
