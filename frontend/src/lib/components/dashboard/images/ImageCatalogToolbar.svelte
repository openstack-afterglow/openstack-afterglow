<script lang="ts">
	import { Button, Card, Pill, SelectInput, TextInput } from '$lib/components/ui';
	import type { CatalogOption, CatalogSortMode, VerificationFilter } from '$lib/stores/imageCatalog.svelte';
	import { t } from '$lib/i18n/ns/images-keys';

	export type CatalogViewMode = 'repositories' | 'tags';

	let {
		searchQuery = $bindable(''),
		repositoryFilter = $bindable('all'),
		tagFilter = $bindable('all'),
		verificationFilter = $bindable<VerificationFilter>('all'),
		sortMode = $bindable<CatalogSortMode>('newest'),
		viewMode = 'repositories',
		repositoryOptions = [],
		tagOptions = [],
		resultCount = 0,
		totalCount = 0,
		repositoryCount = 0,
		onClear,
		onViewModeChange,
	}: {
		searchQuery?: string;
		repositoryFilter?: string;
		tagFilter?: string;
		verificationFilter?: VerificationFilter;
		sortMode?: CatalogSortMode;
		viewMode?: CatalogViewMode;
		repositoryOptions?: CatalogOption[];
		tagOptions?: CatalogOption[];
		resultCount?: number;
		totalCount?: number;
		repositoryCount?: number;
		onClear?: () => void;
		onViewModeChange?: (mode: CatalogViewMode) => void;
	} = $props();

	const hasFilters = $derived(Boolean(searchQuery.trim() || repositoryFilter !== 'all' || tagFilter !== 'all' || verificationFilter !== 'all'));
</script>

<Card surface="subtle" padding="lg" class="catalog-toolbar">
	<div class="toolbar-heading">
		<div>
			<p class="toolbar-kicker">{t('catalogToolbar.kicker')}</p>
			<h2>{t('catalogToolbar.title')}</h2>
			<p class="toolbar-copy">{t('catalogToolbar.description')}</p>
		</div>
		<div class="heading-actions">
			<div class="view-toggle" role="group" aria-label={t('catalogToolbar.viewMode')}>
				<Button variant={viewMode === 'repositories' ? 'accent' : 'ghost'} size="xs" onclick={() => onViewModeChange?.('repositories')}>{t('catalogToolbar.repositoryView')}</Button>
				<Button variant={viewMode === 'tags' ? 'accent' : 'ghost'} size="xs" onclick={() => onViewModeChange?.('tags')}>{t('catalogToolbar.tagsView')}</Button>
			</div>
			<Pill tone="info" dot>{t('catalogToolbar.repositoryCount', { count: repositoryCount })}</Pill>
		</div>
	</div>

	<div class="search-row">
		<label for="image-catalog-search" class="sr-only">{t('catalogToolbar.searchLabel')}</label>
		<div class="search-field">
			<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor">
				<circle cx="11" cy="11" r="7" stroke-width="1.8" />
				<path d="m20 20-4-4" stroke-linecap="round" stroke-width="1.8" />
			</svg>
			<TextInput
				id="image-catalog-search"
				type="search"
				bind:value={searchQuery}
				placeholder={t('catalogToolbar.searchPlaceholder')}
				class="search-input"
			/>
			{#if searchQuery}
				<button type="button" class="clear-search" onclick={() => searchQuery = ''} aria-label={t('catalogToolbar.clearSearch')}>×</button>
			{/if}
		</div>
		{#if hasFilters}
			<Button variant="ghost" size="sm" onclick={onClear}>{t('catalogToolbar.clearFilters')}</Button>
		{/if}
	</div>

	<div class="filter-row">
		<div class="filter-control">
			<label for="image-repository-filter">{t('catalogToolbar.repositoryLabel')}</label>
			<SelectInput id="image-repository-filter" bind:value={repositoryFilter}>
				<option value="all">{t('catalogToolbar.allRepositories')}</option>
				{#each repositoryOptions as option}
					<option value={option.value}>{option.label}{option.count ? ` (${option.count})` : ''}</option>
				{/each}
			</SelectInput>
		</div>
		<div class="filter-control">
			<label for="image-tag-filter">{t('catalogToolbar.tagLabel')}</label>
			<SelectInput id="image-tag-filter" bind:value={tagFilter}>
				<option value="all">{t('catalogToolbar.allTags')}</option>
				{#each tagOptions as option}
					<option value={option.value}>{option.label}{option.count ? ` (${option.count})` : ''}</option>
				{/each}
			</SelectInput>
		</div>
		<div class="filter-control">
			<label for="image-verification-filter">{t('catalogToolbar.trustLabel')}</label>
			<SelectInput id="image-verification-filter" bind:value={verificationFilter}>
				<option value="all">{t('catalogToolbar.allTrust')}</option>
				<option value="verified">{t('catalogToolbar.verified')}</option>
				<option value="unverified">{t('catalogToolbar.unverified')}</option>
				<option value="unavailable">{t('catalogToolbar.unavailable')}</option>
			</SelectInput>
		</div>
		<div class="filter-control sort-control">
			<label for="image-sort-mode">{t('catalogToolbar.sortLabel')}</label>
			<SelectInput id="image-sort-mode" bind:value={sortMode}>
				<option value="relevance">{t('catalogToolbar.relevance')}</option>
				<option value="newest">{t('catalogToolbar.newest')}</option>
				<option value="oldest">{t('catalogToolbar.oldest')}</option>
				<option value="name">{t('catalogToolbar.name')}</option>
			</SelectInput>
		</div>
	</div>

	<div class="toolbar-footer">
		<span>{t('catalogToolbar.resultSummary', { imageCount: resultCount, repositoryCount })}</span>
		{#if totalCount !== resultCount}<span class="footer-muted">{t('catalogToolbar.filteredSummary', { count: totalCount })}</span>{/if}
	</div>
</Card>

<style>
	:global(.catalog-toolbar) {
		display: grid;
		gap: 1rem;
		margin-bottom: 1.25rem;
	}
	.toolbar-heading,
	.search-row,
	.filter-row,
	.toolbar-footer,
	.heading-actions,
	.view-toggle {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}
	.toolbar-heading { justify-content: space-between; gap: 1rem; flex-wrap: wrap; }
	.heading-actions { gap: 0.85rem; flex-wrap: wrap; }
	.view-toggle { gap: 0.2rem; padding: 0.2rem; border: 1px solid var(--color-line); border-radius: 0.5rem; background: var(--color-surface-sunken); }
	.toolbar-kicker {
		margin: 0 0 0.25rem;
		color: var(--color-warm-text);
		font-size: 0.625rem;
		font-weight: 700;
		letter-spacing: 0.14em;
	}
	h2 { margin: 0; color: var(--color-ink-0); font-size: 1.05rem; font-weight: 650; }
	.toolbar-copy { margin: 0.35rem 0 0; color: var(--color-ink-2); font-size: 0.75rem; }
	.search-row { align-items: stretch; }
	.search-field { position: relative; display: flex; align-items: center; flex: 1; min-width: 0; }
	.search-field :global(.text-input) { padding-left: 2.35rem; padding-right: 2.25rem; }
	.search-field svg { position: absolute; z-index: 1; left: 0.75rem; width: 1rem; height: 1rem; color: var(--color-ink-2); pointer-events: none; }
	.clear-search {
		position: absolute;
		right: 0.65rem;
		width: 1.5rem;
		height: 1.5rem;
		border: 0;
		border-radius: 999px;
		background: var(--color-surface-raised);
		color: var(--color-ink-2);
		font-size: 1rem;
		line-height: 1;
		cursor: pointer;
	}
	.clear-search:hover { color: var(--color-ink-0); background: var(--color-surface-sunken); }
	.filter-row { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); align-items: end; }
	.filter-control { display: grid; gap: 0.3rem; min-width: 0; }
	.filter-control label { color: var(--color-ink-2); font-size: 0.6875rem; font-weight: 600; }
	@media (min-width: 80rem) {
		.filter-row { grid-template-columns: repeat(4, minmax(0, 1fr)); }
	}
	.toolbar-footer { color: var(--color-ink-1); font-size: 0.75rem; }
	.footer-muted { color: var(--color-ink-2); }
	@media (max-width: 767px) {
		.toolbar-heading, .search-row { align-items: stretch; flex-direction: column; }
		.filter-row { grid-template-columns: minmax(0, 1fr); }
		.toolbar-heading { gap: 0.75rem; }
		.heading-actions { justify-content: space-between; }
		.filter-control, .sort-control { max-width: none; min-width: 0; }
		.search-row :global(.btn) { align-self: flex-start; }
	}
</style>
