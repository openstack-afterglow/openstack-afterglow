<script lang="ts" module>
	export type CatalogViewMode = 'repositories' | 'tags';
</script>

<script lang="ts" generics="T extends ImageInfo">
	import { AnimatedNumber, Button, Card, Pill } from '$lib/components/ui';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import type { createImageCatalog } from '$lib/stores/imageCatalog.svelte';
	import type { ImageInfo } from '$lib/types/compute';
	import { t } from '$lib/i18n/ns/images-keys';

	let { catalog, viewMode = 'repositories', namespace = 'image-catalog', tourPrefix = 'images', columnControls = 'all', onViewModeChange }: {
		catalog: ReturnType<typeof createImageCatalog<T>>;
		viewMode?: CatalogViewMode;
		namespace?: string;
		tourPrefix?: string;
		columnControls?: 'all' | 'compact' | 'none';
		onViewModeChange?: (mode: CatalogViewMode) => void;
	} = $props();
</script>

<div data-tour={`${tourPrefix}-controls`}>
<Card surface="subtle" padding="lg" class="mb-5 space-y-4">
	<div class="flex flex-wrap items-center justify-between gap-3">
		<div><h2 class="font-semibold">{t('catalogToolbar.title')}</h2><p class="text-xs text-ink-2">{t('catalogToolbar.description')}</p></div>
		<div class="flex flex-wrap items-center gap-2">
			<div class="flex flex-wrap gap-1" role="group" aria-label={t('catalogToolbar.viewMode')}>
				<Button variant={viewMode === 'repositories' ? 'accent' : 'ghost'} size="xs" onclick={() => onViewModeChange?.('repositories')}>{t('catalogToolbar.repositoryView')}</Button>
				<Button variant={viewMode === 'tags' ? 'accent' : 'ghost'} size="xs" onclick={() => onViewModeChange?.('tags')}>{t('catalogToolbar.tagsView')}</Button>
			</div>
			<Pill tone="info" dot><AnimatedNumber value={catalog.visibleRepositoryCount} format={value => t('catalogToolbar.repositoryCount', { count: Math.round(value) })} /></Pill>
		</div>
	</div>
	<RegexSearch id={`${namespace}-search`} bind:value={catalog.searchQuery} label={t('catalogToolbar.searchLabel')} placeholder={t('catalogToolbar.searchPlaceholder')} />
	{#if columnControls !== 'none'}<TableViewControls view={catalog.view} class={columnControls === 'all' ? '' : 'lg:hidden'} />{/if}
	<Button variant="ghost" size="sm" onclick={catalog.clearFilters}>{t('catalogToolbar.clearFilters')}</Button>
	<p class="text-xs text-ink-2">{t('catalogToolbar.resultSummary', { imageCount: catalog.filteredImages.length, repositoryCount: catalog.visibleRepositoryCount })}</p>
</Card>
</div>
