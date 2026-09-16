<script lang="ts">
	import { Button, Card, Pill, SelectInput, TextInput } from '$lib/components/ui';

	export interface CatalogOption {
		value: string;
		label: string;
		count?: number;
	}
	export type CatalogViewMode = 'repositories' | 'tags';

	let {
		searchQuery = $bindable(''),
		repositoryFilter = $bindable('all'),
		tagFilter = $bindable('all'),
		sortMode = $bindable<'relevance' | 'updated' | 'name'>('relevance'),
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
		sortMode?: 'relevance' | 'updated' | 'name';
		viewMode?: CatalogViewMode;
		repositoryOptions?: CatalogOption[];
		tagOptions?: CatalogOption[];
		resultCount?: number;
		totalCount?: number;
		repositoryCount?: number;
		onClear?: () => void;
		onViewModeChange?: (mode: CatalogViewMode) => void;
	} = $props();

	const hasFilters = $derived(Boolean(searchQuery.trim() || repositoryFilter !== 'all' || tagFilter !== 'all'));
</script>

<Card surface="subtle" padding="lg" class="catalog-toolbar">
	<div class="toolbar-heading">
		<div>
			<p class="toolbar-kicker">IMAGE CATALOG</p>
			<h2>Repository와 tag로 이미지 찾기</h2>
			<p class="toolbar-copy">Docker Hub처럼 이름을 검색하고, 같은 repository의 버전을 tag로 고르세요.</p>
		</div>
		<div class="heading-actions">
			<div class="view-toggle" role="group" aria-label="이미지 보기 방식">
				<Button variant={viewMode === 'repositories' ? 'accent' : 'ghost'} size="xs" onclick={() => onViewModeChange?.('repositories')}>Repository</Button>
				<Button variant={viewMode === 'tags' ? 'accent' : 'ghost'} size="xs" onclick={() => onViewModeChange?.('tags')}>Tags</Button>
			</div>
			<Pill tone="info" dot>{repositoryCount} repositories</Pill>
		</div>
	</div>

	<div class="search-row">
		<label for="image-catalog-search" class="sr-only">이미지 repository 또는 tag 검색</label>
		<div class="search-field">
			<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor">
				<circle cx="11" cy="11" r="7" stroke-width="1.8" />
				<path d="m20 20-4-4" stroke-linecap="round" stroke-width="1.8" />
			</svg>
			<TextInput
				id="image-catalog-search"
				type="search"
				bind:value={searchQuery}
				placeholder="ubuntu, ubuntu:24.04, registry.example/ubuntu"
				class="search-input"
			/>
			{#if searchQuery}
				<button type="button" class="clear-search" onclick={() => searchQuery = ''} aria-label="검색어 지우기">×</button>
			{/if}
		</div>
		{#if hasFilters}
			<Button variant="ghost" size="sm" onclick={onClear}>필터 초기화</Button>
		{/if}
	</div>

	<div class="filter-row">
		<div class="filter-control">
			<label for="image-repository-filter">Repository</label>
			<SelectInput id="image-repository-filter" bind:value={repositoryFilter}>
				<option value="all">모든 repository</option>
				{#each repositoryOptions as option}
					<option value={option.value}>{option.label}{option.count ? ` (${option.count})` : ''}</option>
				{/each}
			</SelectInput>
		</div>
		<div class="filter-control">
			<label for="image-tag-filter">Tag</label>
			<SelectInput id="image-tag-filter" bind:value={tagFilter}>
				<option value="all">모든 tag</option>
				{#each tagOptions as option}
					<option value={option.value}>{option.label}{option.count ? ` (${option.count})` : ''}</option>
				{/each}
			</SelectInput>
		</div>
		<div class="filter-control sort-control">
			<label for="image-sort-mode">정렬</label>
			<SelectInput id="image-sort-mode" bind:value={sortMode}>
				<option value="relevance">관련도순</option>
				<option value="updated">최근 업데이트순</option>
				<option value="name">이름순</option>
			</SelectInput>
		</div>
	</div>

	<div class="toolbar-footer">
		<span>{resultCount}개 이미지 · {repositoryCount}개 repository</span>
		{#if totalCount !== resultCount}<span class="footer-muted">전체 {totalCount}개에서 필터링됨</span>{/if}
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
	.toolbar-heading { justify-content: space-between; gap: 1rem; }
	.heading-actions { gap: 0.85rem; }
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
	.filter-row { align-items: end; }
	.filter-control { display: grid; gap: 0.3rem; min-width: 10rem; flex: 1; }
	.filter-control label { color: var(--color-ink-2); font-size: 0.6875rem; font-weight: 600; }
	.sort-control { max-width: 13rem; }
	.toolbar-footer { color: var(--color-ink-1); font-size: 0.75rem; }
	.footer-muted { color: var(--color-ink-2); }
	@media (max-width: 42rem) {
		.toolbar-heading, .search-row, .filter-row { align-items: stretch; flex-direction: column; }
		.toolbar-heading { gap: 0.75rem; }
		.heading-actions { justify-content: space-between; }
		.filter-control, .sort-control { max-width: none; min-width: 0; }
		.search-row :global(.btn) { align-self: flex-start; }
	}
</style>
