<script lang="ts" generics="Row">
	import { getContext } from 'svelte';
	import { t } from '$lib/i18n/ns/common';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { TABLE_MISSING_VALUE, TABLE_VIEW_VISIBILITY, type TableColumn, type TableSort, type TableView } from '$lib/utils/tableView.svelte';
	import { compileRegexSearch, matchesRegexSearch } from '$lib/utils/regexSearch';
	import Button from './Button.svelte';
	import Field from './Field.svelte';
	import RegexSearch from './RegexSearch.svelte';
	import SelectInput from './SelectInput.svelte';
	import SelectionCheckbox from './SelectionCheckbox.svelte';
	import SlideOver from './SlideOver.svelte';
	import TextInput from './TextInput.svelte';

	/**
	 * Mobile card-mode replacement for the per-column control row: one trigger opens a full-width
	 * sheet whose sort/filter choices stay local until the explicit apply action.
	 */
	let { view }: { view: TableView<Row> } = $props();

	type Range = { min: string; max: string };
	type Draft = { sort: TableSort | null; filters: Record<string, string[] | null>; ranges: Record<string, Range> };

	const uid = $props.id();
	const ownerVisible = getContext<(() => boolean) | undefined>(TABLE_VIEW_VISIBILITY);
	const SEARCH_THRESHOLD = 8;
	let open = $state(false);
	let draft = $state<Draft>({ sort: null, filters: {}, ranges: {} });
	let baseline = $state.raw<Draft>({ sort: null, filters: {}, ranges: {} });
	let queries = $state<Record<string, string>>({});

	const sortColumns = $derived(view.columns.filter((column) => column.sortable !== false));
	const filterColumns = $derived(view.columns.filter((column) => column.filterable !== false));
	const nativeScope = $derived(filterColumns.some((column) => column.onFilterChange || column.rangeFilter));
	const activeCount = $derived(filterColumns.filter((column) => Object.hasOwn(view.filters, column.key)
		|| Boolean(column.rangeFilter && (column.rangeFilter.min() || column.rangeFilter.max()))).length);
	const triggerLabel = $derived(activeCount ? t('table.filtersActive', { count: activeCount.toLocaleString(intlLocale()) }) : t('table.filters'));

	function snapshot(): Draft {
		const filters: Draft['filters'] = {};
		const ranges: Draft['ranges'] = {};
		for (const column of filterColumns) {
			filters[column.key] = Object.hasOwn(view.filters, column.key) ? [...view.selected(column.key)] : null;
			if (column.rangeFilter) ranges[column.key] = { min: column.rangeFilter.min(), max: column.rangeFilter.max() };
		}
		return { sort: view.sort ? { ...view.sort } : null, filters, ranges };
	}

	function openSheet() {
		baseline = snapshot();
		draft = snapshot();
		queries = Object.fromEntries(filterColumns.map((column) => [column.key, '']));
		open = true;
	}

	function closeSheet() {
		open = false;
	}

	function resetDraft() {
		draft = {
			sort: null,
			filters: Object.fromEntries(filterColumns.map((column) => [column.key, null])),
			ranges: Object.fromEntries(filterColumns.filter((column) => column.rangeFilter).map((column) => [column.key, { min: '', max: '' }])),
		};
	}

	function sameValues(left: readonly string[] | null, right: readonly string[] | null): boolean {
		if (left === null || right === null) return left === right;
		return left.length === right.length && left.every((value) => right.includes(value));
	}

	/** Commit only what the user changed in this sheet, through the table's own setters. */
	function apply() {
		const next = $state.snapshot(draft) as Draft;
		for (const column of filterColumns) {
			const selected = next.filters[column.key] ?? null;
			if (!sameValues(selected, baseline.filters[column.key] ?? null)) {
				if (selected === null) view.clearFilter(column.key);
				else view.setFilter(column.key, selected);
			}
			const range = column.rangeFilter;
			const draftRange = next.ranges[column.key];
			const baseRange = baseline.ranges[column.key];
			if (range && draftRange && baseRange && (draftRange.min !== baseRange.min || draftRange.max !== baseRange.max)) {
				range.onchange(draftRange.min, draftRange.max);
			}
		}
		const sort = next.sort;
		if (sort?.key !== baseline.sort?.key || sort?.direction !== baseline.sort?.direction) view.setSort(sort);
		open = false;
	}

	function optionLabel(option: { value: string; label: string }): string {
		return option.value === TABLE_MISSING_VALUE ? t('table.missing') : option.label || t('table.emptyValue');
	}

	function isChecked(column: TableColumn<Row>, value: string): boolean {
		const selected = draft.filters[column.key] ?? null;
		if (column.filterMode === 'single') return selected?.includes(value) ?? false;
		return selected === null || selected.includes(value);
	}

	function toggleValue(column: TableColumn<Row>, value: string) {
		const selected = draft.filters[column.key] ?? null;
		if (column.filterMode === 'single') {
			draft.filters[column.key] = selected?.includes(value) ? null : [value];
			return;
		}
		const current = selected ?? view.options(column.key).map((option) => option.value);
		draft.filters[column.key] = current.includes(value) ? current.filter((item) => item !== value) : [...current, value];
	}

	function freeValue(column: TableColumn<Row>): string {
		const value = draft.filters[column.key]?.[0] ?? '';
		return value.startsWith('\u0000') ? '' : value;
	}

	function draftCount(column: TableColumn<Row>): number {
		const range = draft.ranges[column.key];
		return (draft.filters[column.key]?.length ?? 0) + (range && (range.min || range.max) ? 1 : 0);
	}

	function draftActive(column: TableColumn<Row>): boolean {
		const range = draft.ranges[column.key];
		return draft.filters[column.key] != null || Boolean(range && (range.min || range.max));
	}

	function visibleOptions(column: TableColumn<Row>) {
		const options = view.options(column.key);
		const compiled = compileRegexSearch(queries[column.key] ?? '');
		return options.filter((option) => matchesRegexSearch(compiled, optionLabel(option)));
	}

	function portal(node: HTMLElement) {
		document.body.appendChild(node);
		return { destroy: () => node.remove() };
	}

	$effect(() => {
		if (open && ownerVisible && !ownerVisible()) closeSheet();
	});
</script>

<Button variant="secondary" size="sm" ariaLabel={triggerLabel} title={triggerLabel} ariaExpanded={open} class="table-filter-trigger" onclick={openSheet}>
	<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" aria-hidden="true"><path d="M2 3h12L9.5 8v4l-3 1V8L2 3Z" /></svg>
	<span>{t('table.filters')}</span>
	{#if activeCount}<span class="filter-badge" aria-hidden="true">{activeCount.toLocaleString(intlLocale())}</span>{/if}
</Button>

{#if open}
	<div use:portal class="table-filter-sheet-host">
		<SlideOver open={true} title={t('table.filtersTitle')} onClose={closeSheet}>
			{#if sortColumns.length}
				<section class="sheet-section" aria-labelledby={`${uid}-sort-heading`}>
					<h3 id={`${uid}-sort-heading`} class="sheet-heading">{t('table.sortOrder')}</h3>
					<Field label={t('table.sortBy')} for={`${uid}-sort-key`}>
						<SelectInput id={`${uid}-sort-key`} value={draft.sort?.key ?? ''} onchange={(event) => { const key = (event.currentTarget as HTMLSelectElement).value; draft.sort = key ? { key, direction: draft.sort?.direction ?? 'asc' } : null; }}>
							<option value="">{t('table.none')}</option>
							{#each sortColumns as column (column.key)}<option value={column.key}>{column.label}</option>{/each}
						</SelectInput>
					</Field>
					{#if draft.sort}
						<div class="sort-direction" role="group" aria-label={t('table.sortOrder')}>
							<Button variant="ghost" size="sm" ariaPressed={draft.sort.direction === 'asc'} onclick={() => { if (draft.sort) draft.sort = { ...draft.sort, direction: 'asc' }; }}>{t('table.ascending')}</Button>
							<Button variant="ghost" size="sm" ariaPressed={draft.sort.direction === 'desc'} onclick={() => { if (draft.sort) draft.sort = { ...draft.sort, direction: 'desc' }; }}>{t('table.descending')}</Button>
						</div>
					{/if}
				</section>
			{/if}
			{#if nativeScope}<p class="sheet-note">{t('table.nativeFilterScope')}</p>{/if}
			{#each filterColumns as column, columnIndex (column.key)}
				{@const options = visibleOptions(column)}
				{@const allCount = view.options(column.key).length}
				<!-- Initial disclosure follows the applied condition; editing never collapses the section. -->
				<details class="filter-section" open={baseline.filters[column.key] != null || Boolean(baseline.ranges[column.key]?.min || baseline.ranges[column.key]?.max)}>
					<summary>
						<span class="filter-section-label">{t('table.filterColumn', { column: column.label })}</span>
						{#if draftActive(column)}<span class="filter-badge">{draftCount(column).toLocaleString(intlLocale())}</span>{/if}
					</summary>
					<div class="filter-section-body">
						{#if column.filterFreeValue}
							<Field label={t('table.filterValue')} for={`${uid}-${columnIndex}-free`}>
								<TextInput id={`${uid}-${columnIndex}-free`} value={freeValue(column)} oninput={(event) => { const value = (event.currentTarget as HTMLInputElement).value; draft.filters[column.key] = value ? [value] : null; }} />
							</Field>
						{/if}
						{#if column.rangeFilter && draft.ranges[column.key]}
							<div class="filter-range">
								<Field label={t('table.minimum')} for={`${uid}-${columnIndex}-min`}><TextInput id={`${uid}-${columnIndex}-min`} inputmode="numeric" bind:value={draft.ranges[column.key].min} /></Field>
								<Field label={t('table.maximum')} for={`${uid}-${columnIndex}-max`}><TextInput id={`${uid}-${columnIndex}-max`} inputmode="numeric" bind:value={draft.ranges[column.key].max} /></Field>
								<p class="sheet-note">{t('table.rangeHelp')}</p>
							</div>
						{/if}
						{#if allCount > SEARCH_THRESHOLD}
							<RegexSearch id={`${uid}-${columnIndex}-search`} bind:value={queries[column.key]} label={t('table.searchValues')} />
						{/if}
						{#if allCount}
							<div class="filter-actions">
								<Button variant="ghost" size="xs" onclick={() => { draft.filters[column.key] = null; }}>{t('table.selectAll')}</Button>
								{#if column.filterMode !== 'single'}<Button variant="ghost" size="xs" onclick={() => { draft.filters[column.key] = []; }}>{t('table.selectNone')}</Button>{/if}
							</div>
							<div class="filter-values" role="group" aria-label={t('table.filterColumn', { column: column.label })}>
								{#each options as option, index (option.value)}
									<div class="filter-value">
										<SelectionCheckbox id={`${uid}-${columnIndex}-value-${index}`} checked={isChecked(column, option.value)} ariaLabel={optionLabel(option)} onclick={() => toggleValue(column, option.value)} />
										<label for={`${uid}-${columnIndex}-value-${index}`} class="value-label"><span>{optionLabel(option)}</span>{#if option.count !== null}<span class="value-count">{option.count.toLocaleString(intlLocale())}</span>{/if}</label>
									</div>
								{:else}<p class="sheet-note">{t('search.noMatch')}</p>{/each}
							</div>
						{/if}
					</div>
				</details>
			{/each}
			{#snippet footer()}
				<Button variant="ghost" size="md" onclick={resetDraft}>{t('table.resetView')}</Button>
				<Button variant="secondary" size="md" onclick={closeSheet}>{t('actions.cancel')}</Button>
				<Button variant="primary" size="md" onclick={apply}>{t('table.applyQuery')}</Button>
			{/snippet}
		</SlideOver>
	</div>
{/if}

<style>
	.filter-badge { display: inline-flex; align-items: center; justify-content: center; min-width: 1.25rem; padding: 0 0.375rem; border-radius: 9999px; background: var(--color-surface-selected); color: var(--color-ink-0); font-size: var(--type-support); font-variant-numeric: tabular-nums; line-height: 1.25rem; }
	.sheet-section { display: flex; flex-direction: column; gap: 0.5rem; }
	.sheet-heading { margin: 0; font-size: var(--type-body); font-weight: 600; color: var(--color-ink-0); }
	.sort-direction, .filter-actions { display: flex; flex-wrap: wrap; gap: 0.25rem; }
	.sheet-note { margin: 0; color: var(--color-ink-2); font-size: var(--type-support); line-height: 1.4; }
	.filter-section { border: 1px solid var(--color-line); border-radius: var(--radius-lg); background: var(--color-surface-raised); }
	.filter-section summary { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; min-height: var(--control-touch-height); padding: 0.5rem 0.75rem; cursor: pointer; color: var(--color-ink-1); font-weight: 500; }
	.filter-section summary:focus-visible { outline: none; box-shadow: var(--focus-ring); border-radius: var(--radius-lg); }
	.filter-section-label { min-width: 0; overflow-wrap: anywhere; }
	.filter-section-body { display: flex; flex-direction: column; gap: 0.5rem; padding: 0 0.75rem 0.75rem; }
	.filter-range { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 0.5rem; }
	.filter-range .sheet-note { grid-column: 1 / -1; }
	.filter-values { display: flex; flex-direction: column; border-top: 1px solid var(--color-line); }
	.filter-value { display: flex; align-items: center; gap: 0.5rem; min-height: var(--control-touch-height); }
	.value-label { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; align-self: stretch; flex: 1; min-width: 0; overflow-wrap: anywhere; cursor: pointer; }
	.value-count { font-variant-numeric: tabular-nums; color: var(--color-ink-2); }
	@media (forced-colors: active) { .filter-section summary:focus-visible { outline: 2px solid CanvasText; } }
</style>
