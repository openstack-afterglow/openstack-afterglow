<script lang="ts" generics="Row">
	import { getContext, tick } from 'svelte';
	import { t } from '$lib/i18n/ns/common';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { TABLE_MISSING_VALUE, TABLE_VIEW_VISIBILITY, type TableView } from '$lib/utils/tableView.svelte';
	import { compileRegexSearch, matchesRegexSearch } from '$lib/utils/regexSearch';
	import Button from './Button.svelte';
	import RegexSearch from './RegexSearch.svelte';
	import SelectionCheckbox from './SelectionCheckbox.svelte';
	import Field from './Field.svelte';
	import TextInput from './TextInput.svelte';
	import { dialogFocus } from '$lib/utils/dialogFocus';

	let { view, columnKey, class: className = '' }: { view: TableView<Row>; columnKey: string; class?: string } = $props();
	const uid = $props.id();
	const ownerVisible = getContext<(() => boolean) | undefined>(TABLE_VIEW_VISIBILITY);
	const column = $derived(view.columns.find((item) => item.key === columnKey));
	const sortOrders = ['ascending', 'descending', 'none'] as const;
	const direction = $derived(view.direction(columnKey));
	const active = $derived(Object.hasOwn(view.filters, columnKey));
	const selected = $derived(view.selected(columnKey));
	const rangeActive = $derived(Boolean(column?.rangeFilter && (column.rangeFilter.min() || column.rangeFilter.max())));
	const filterActive = $derived(active || rangeActive);
	let freeValue = $state('');
	let rangeMin = $state('');
	let rangeMax = $state('');
	let open = $state(false);
	let modalHost = $state(false);
	let query = $state('');
	let trigger = $state<HTMLButtonElement | null>(null);
	let popover = $state<HTMLDivElement | null>(null);
	let style = $state('');
	const options = $derived(view.options(columnKey));
	const compiled = $derived(compileRegexSearch(query));
	const visibleOptions = $derived(options.filter((option) => matchesRegexSearch(compiled,
		option.value === TABLE_MISSING_VALUE ? t('table.missing') : option.label || t('table.emptyValue'))));

	function portal(node: HTMLElement) {
		document.body.appendChild(node);
		return { destroy: () => node.remove() };
	}

	function position(event?: Event) {
		if (!trigger || !popover) return;
		const rect = trigger.getBoundingClientRect();
		const padding = 12;
		const gap = 4;
		const viewport = window.visualViewport;
		const viewportTop = viewport?.offsetTop ?? 0;
		const viewportLeft = viewport?.offsetLeft ?? 0;
		const viewportHeight = viewport?.height ?? window.innerHeight;
		const viewportWidth = viewport?.width ?? window.innerWidth;
		const ownsFocus = popover.contains(document.activeElement);
		if (event?.type === 'scroll' && event.target !== viewport && !ownsFocus
			&& rect.height > 0 && (rect.bottom <= 0 || rect.top >= window.innerHeight)) {
			closeMenu();
			return;
		}
		// Keep editing reachable when a soft keyboard shrinks or pans the visual viewport.
		const viewportBottom = viewportTop + viewportHeight;
		const anchorTop = Math.max(viewportTop + padding, Math.min(rect.top, viewportBottom - padding));
		const anchorBottom = Math.max(viewportTop + padding, Math.min(rect.bottom, viewportBottom - padding));
		const below = viewportBottom - anchorBottom - padding - gap;
		const above = anchorTop - viewportTop - padding - gap;
		const upward = below < 420 && above > below;
		const height = Math.max(0, Math.min(420, upward ? above : below));
		const width = Math.max(0, Math.min(320, viewportWidth - padding * 2));
		const left = Math.min(Math.max(viewportLeft + padding, rect.left), viewportLeft + viewportWidth - padding - width);
		const vertical = upward
			? `bottom:${window.innerHeight - anchorTop + gap}px;`
			: `top:${anchorBottom + gap}px;`;
		style = `left:${left}px;${vertical}width:${width}px;max-height:${height}px;`;
	}

	async function openMenu() {
		query = '';
		syncNativeDrafts();
		modalHost = Boolean(trigger?.closest('[aria-modal="true"]'));
		trigger?.focus();
		open = true;
		await tick();
		if (!open) return;
		position();
		popover?.querySelector<HTMLInputElement>('input')?.focus();
	}

	function closeMenu(restore = false) {
		open = false;
		if (restore) trigger?.focus();
	}

	function toggleValue(value: string) {
		if (column?.filterMode === 'single') {
			const wasSelected = selected.includes(value);
			if (wasSelected) view.clearFilter(columnKey);
			else view.setFilter(columnKey, [value]);
			syncNativeDrafts();
			return;
		}
		const current = active ? selected : options.map((option) => option.value);
		view.setFilter(columnKey, current.includes(value) ? current.filter((item) => item !== value) : [...current, value]);
	}

	function chooseSort(next: 'ascending' | 'descending' | 'none') {
		view.setSort(next === 'none' ? null : { key: columnKey, direction: next === 'ascending' ? 'asc' : 'desc' });
	}
	function syncNativeDrafts() {
		freeValue = view.selected(columnKey)[0] ?? '';
		rangeMin = column?.rangeFilter?.min() ?? '';
		rangeMax = column?.rangeFilter?.max() ?? '';
	}

	function applyNativeValue() {
		if (freeValue) view.setFilter(columnKey, [freeValue]);
		else view.clearFilter(columnKey);
		syncNativeDrafts();
	}

	function resetColumnFilter() {
		view.clearFilter(columnKey);
		syncNativeDrafts();
	}


	function applyRange() {
		const range = column?.rangeFilter;
		if (range && (rangeMin !== range.min() || rangeMax !== range.max())) range.onchange(rangeMin, rangeMax);
		syncNativeDrafts();
	}

	function resetRange() {
		rangeMin = '';
		rangeMax = '';
		const range = column?.rangeFilter;
		if (range && (range.min() || range.max())) range.onchange('', '');
		syncNativeDrafts();
	}

	function handleKeydown(event: KeyboardEvent) {
		if (event.key === 'Escape') {
			event.preventDefault();
			event.stopPropagation();
			closeMenu(true);
			return;
		}
		const focusable = [...(popover?.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled)') ?? [])];
		if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
			const current = focusable.indexOf(document.activeElement as HTMLElement);
			const next = current + (event.key === 'ArrowDown' ? 1 : -1);
			if (focusable.length) {
				event.preventDefault();
				focusable[(next + focusable.length) % focusable.length]?.focus();
			}
		}
		if (event.key === 'Tab' && ((event.shiftKey && document.activeElement === focusable[0]) || (!event.shiftKey && document.activeElement === focusable.at(-1)))) {
			closeMenu(true);
			if (event.shiftKey) event.preventDefault();
		}
	}
	$effect(() => {
		if (open && ownerVisible && !ownerVisible()) closeMenu();
	});


	$effect(() => {
		if (!open) return;
		const outside = (event: PointerEvent) => {
			const target = event.target as Node;
			if (!popover?.contains(target) && !trigger?.contains(target)) closeMenu();
		};
		const focusOutside = (event: FocusEvent) => {
			const target = event.target as Node;
			if (!popover?.contains(target) && !trigger?.contains(target)) closeMenu();
		};
		const viewport = window.visualViewport;
		document.addEventListener('pointerdown', outside);
		document.addEventListener('focusin', focusOutside);
		window.addEventListener('resize', position);
		window.addEventListener('scroll', position, true);
		viewport?.addEventListener('resize', position);
		viewport?.addEventListener('scroll', position);
		return () => {
			document.removeEventListener('pointerdown', outside);
			document.removeEventListener('focusin', focusOutside);
			window.removeEventListener('resize', position);
			window.removeEventListener('scroll', position, true);
			viewport?.removeEventListener('resize', position);
			viewport?.removeEventListener('scroll', position);
		};
	});
</script>

{#if column}
	<span class="table-column-control {className}">
		{#if column.sortable !== false}
			<Button variant="ghost" size="xs" onclick={() => view.toggleSort(columnKey)} ariaLabel={t('table.sortColumn', { column: column.label, direction: t(`table.${direction}`) })} title={t('table.sortCycle')}>
				<span class="column-label">{column.label}</span>
				<svg width="12" height="14" viewBox="0 0 12 14" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
					{#if direction !== 'descending'}<path d="M3 11V3M.5 5.5 3 3l2.5 2.5" />{/if}
					{#if direction !== 'ascending'}<path d="M9 3v8m-2.5-2.5L9 11l2.5-2.5" />{/if}
				</svg>
			</Button>
		{:else}<span class="column-label">{column.label}</span>{/if}
		{#if column.filterable !== false}
			<button bind:this={trigger} type="button" class="column-filter" class:active={filterActive} aria-label={t('table.filterColumn', { column: column.label })} aria-describedby={filterActive ? `${uid}-filter-state` : undefined} aria-haspopup="dialog" aria-expanded={open} aria-controls={open ? `${uid}-popover` : undefined} title={t('table.filterColumn', { column: column.label })} onclick={() => open ? closeMenu() : void openMenu()}>
				<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" aria-hidden="true"><path d="M2 3h12L9.5 8v4l-3 1V8L2 3Z" /></svg>
				{#if filterActive}<span class="filter-count">{(selected.length + (rangeActive ? 1 : 0)).toLocaleString(intlLocale())}</span>{/if}
			</button>
			{#if filterActive}<span hidden id={`${uid}-filter-state`}>{t('selection.count', { count: selected.length + (rangeActive ? 1 : 0) })}</span>{/if}
		{/if}
	</span>
	{#if open}
		<div use:portal use:dialogFocus={{ enabled: modalHost, onEscape: () => closeMenu(true), initialFocus: 'input' }} bind:this={popover} id={`${uid}-popover`} role="dialog" aria-label={t('table.filterColumn', { column: column.label })} tabindex="-1" class="table-column-popover" {style} onkeydown={handleKeydown}>
			<div class="popover-heading"><strong>{column.label}</strong><Button variant="ghost" size="xs" ariaLabel={t('actions.close')} onclick={() => closeMenu(true)}><svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="m4 4 8 8m0-8-8 8" /></svg></Button></div>
			{#if column.sortable !== false}
				<div class="sort-options" role="group" aria-label={t('table.sortOrder')}>
					{#each sortOrders as order}
						<Button variant="ghost" size="xs" ariaPressed={direction === order} onclick={() => chooseSort(order)}>{t(`table.${order}`)}</Button>
					{/each}
				</div>
			{/if}
			{#if column.onFilterChange || column.rangeFilter}<p class="native-scope">{t('table.nativeFilterScope')}</p>{/if}
			{#if column.filterFreeValue}
				<div class="native-input">
					<Field label={t('table.filterValue')} for={`${uid}-native-value`}>
						<TextInput id={`${uid}-native-value`} bind:value={freeValue} onkeydown={(event) => { if (event.key === 'Enter') { event.preventDefault(); applyNativeValue(); } }} />
					</Field>
					<Button variant="secondary" size="xs" onclick={applyNativeValue}>{t('table.apply')}</Button>
				</div>
			{/if}
			{#if column.rangeFilter}
				<div class="native-range">
					<Field label={t('table.minimum')} for={`${uid}-minimum`}><TextInput id={`${uid}-minimum`} inputmode="numeric" bind:value={rangeMin} /></Field>
					<Field label={t('table.maximum')} for={`${uid}-maximum`}><TextInput id={`${uid}-maximum`} inputmode="numeric" bind:value={rangeMax} /></Field>
					<p class="range-help">{t('table.rangeHelp')}</p>
					<div class="filter-actions"><Button variant="secondary" size="xs" onclick={applyRange}>{t('table.apply')}</Button><Button variant="ghost" size="xs" onclick={resetRange}>{t('table.resetFilter')}</Button></div>
				</div>
			{/if}
			<div class="value-search"><RegexSearch id={`${uid}-search`} bind:value={query} label={t('table.searchValues')} /></div>
			<div class="filter-actions">
				<Button variant="ghost" size="xs" onclick={() => { if (column.filterMode === 'single') resetColumnFilter(); else view.setFilter(columnKey, options.map((option) => option.value)); }}>{t('table.selectAll')}</Button>
				{#if column.filterMode !== 'single'}<Button variant="ghost" size="xs" onclick={() => view.setFilter(columnKey, [])}>{t('table.selectNone')}</Button>{/if}
				<Button variant="ghost" size="xs" onclick={resetColumnFilter}>{t('table.resetFilter')}</Button>
			</div>
			<div class="filter-values" role="group" aria-label={t('table.filterColumn', { column: column.label })}>
				{#each visibleOptions as option, index (option.value)}
					<div class="filter-value">
						<SelectionCheckbox id={`${uid}-value-${index}`} checked={column.filterMode === 'single' ? selected.includes(option.value) : !active || selected.includes(option.value)} ariaLabel={option.value === TABLE_MISSING_VALUE ? t('table.missing') : option.label || t('table.emptyValue')} onclick={() => toggleValue(option.value)} />
						<label for={`${uid}-value-${index}`} class="value-label"><span>{option.value === TABLE_MISSING_VALUE ? t('table.missing') : option.label || t('table.emptyValue')}</span>{#if option.count !== null}<span class="value-count">{option.count.toLocaleString(intlLocale())}</span>{/if}</label>
					</div>
				{:else}<p class="no-values">{t('search.noMatch')}</p>{/each}
			</div>
		</div>
	{/if}
{/if}

<style>
	.table-column-control { display: inline-flex; align-items: center; gap: 0.125rem; min-width: 0; max-width: 100%; }
	.column-label { min-width: min-content; white-space: normal; word-break: keep-all; overflow-wrap: normal; }
	.column-filter { display: inline-flex; align-items: center; justify-content: center; gap: 0.125rem; flex: 0 0 auto; min-width: var(--control-height); min-height: var(--control-height); padding: 0.25rem; border: 1px solid transparent; border-radius: var(--radius-md); background: transparent; color: var(--color-ink-2); cursor: pointer; }
	.column-filter:hover, .column-filter.active { background: var(--color-surface-selected); color: var(--color-ink-0); }
	.column-filter:focus-visible { outline: none; box-shadow: var(--focus-ring); }
	.filter-count { font-size: var(--type-support); font-variant-numeric: tabular-nums; }
	.table-column-popover { position: fixed; z-index: var(--z-popover); display: flex; flex-direction: column; overflow: auto; border: 1px solid var(--color-line-2); border-radius: var(--radius-lg); background: var(--color-surface-raised); box-shadow: var(--shadow-popover); color: var(--color-ink-1); font-size: var(--type-body); font-weight: 400; text-align: start; }
	.popover-heading { display: flex; justify-content: space-between; align-items: center; gap: 0.5rem; padding: 0.375rem 0.75rem; }
	.popover-heading strong { min-width: 0; overflow-wrap: anywhere; }
	.sort-options, .filter-actions { display: flex; flex-wrap: wrap; gap: 0.25rem; padding: 0.25rem 0.5rem; }
	.sort-options { border-block: 1px solid var(--color-line); }
	.value-search { padding: 0.5rem 0.75rem; }
	.filter-values { min-height: 0; overflow-y: auto; flex: 1 0 5rem; border-top: 1px solid var(--color-line); }
	.filter-value { display: flex; align-items: center; gap: 0.5rem; min-height: var(--control-height); padding: 0.375rem 0.75rem; }
	.filter-value:hover { background: var(--color-surface-selected); }
	.value-label { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; align-self: stretch; flex: 1; min-width: 0; overflow-wrap: anywhere; cursor: pointer; }
	.value-count { font-variant-numeric: tabular-nums; color: var(--color-ink-2); }
	.no-values { margin: 0; padding: 0.75rem; color: var(--color-ink-2); }
	.native-scope, .range-help { margin: 0; color: var(--color-ink-2); font-size: var(--type-support); line-height: 1.4; }
	.native-scope { padding: 0.5rem 0.75rem 0; }
	.native-input { display: flex; align-items: flex-end; gap: 0.5rem; padding: 0.5rem 0.75rem; }
	.native-input :global(.field) { flex: 1; min-width: 0; }
	.native-range { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 0.5rem; padding: 0.5rem 0.75rem; border-bottom: 1px solid var(--color-line); }
	.native-range .range-help, .native-range .filter-actions { grid-column: 1 / -1; }
	@media (max-width: 767px), (pointer: coarse) { .column-filter, .filter-value { min-height: var(--control-touch-height); } .column-filter { min-width: var(--control-touch-height); } }
	@media (forced-colors: active) { .column-filter:focus-visible { outline: 2px solid CanvasText; } .column-filter.active { border-color: Highlight; } }
</style>
