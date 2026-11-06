import { compileRegexSearch, matchesRegexSearch } from './regexSearch';
import { getContext, setContext } from 'svelte';

/** Retained presentation owners can explicitly dismiss their portaled controls when hidden. */
export const TABLE_VIEW_VISIBILITY = Symbol('tableViewVisibility');

/** Call during component initialization; a nested owner cannot unmask its hidden parent. */
export function provideTableViewVisibility(visible: () => boolean): void {
	const inherited = getContext<(() => boolean) | undefined>(TABLE_VIEW_VISIBILITY);
	setContext(TABLE_VIEW_VISIBILITY, () => (inherited?.() ?? true) && visible());
}

export type TableValue = string | number | boolean | null | undefined;
export type TableColumn<Row> = {
	key: string;
	label: string;
	value: (row: Row) => TableValue;
	/** Optional set-valued membership; display/search/sort still use value. */
	filterValues?: (row: Row) => readonly TableValue[];
	format?: (value: TableValue, row: Row) => string;
	sortable?: boolean;
	filterable?: boolean;
	filterOptions?: () => TableOption[];
	filterSelection?: () => readonly string[] | null;
	onFilterChange?: (values: string[] | null) => void;
	filterMode?: 'single' | 'multiple';
	filterFreeValue?: boolean;
	rangeFilter?: { min: () => string; max: () => string; onchange: (min: string, max: string) => void };
};
export type TableSort = { key: string; direction: 'asc' | 'desc' };
export type TableOption = { value: string; label: string; count: number | null };
export interface TableViewState {
	sort: TableSort | null;
	filters: Record<string, string[]>;
}
export interface TableView<Row> {
	setSort(sort: TableSort | null): void;
	readonly rows: Row[];
	readonly columns: TableColumn<Row>[];
	readonly error: boolean;
	readonly sort: TableSort | null;
	readonly filters: Record<string, string[]>;
	toggleSort(key: string): void;
	setFilter(key: string, values: string[]): void;
	clearFilter(key: string): void;
	reset(): void;
	orderRows(rows: readonly Row[]): Row[];
	options(key: string): TableOption[];
	direction(key: string): 'ascending' | 'descending' | 'none';
	selected(key: string): string[];
}

export const TABLE_MISSING_VALUE = '\u0000missing';
const VALUE_ESCAPE = '\u0000value:';
const isMissing = (value: TableValue) => value == null || (typeof value === 'number' && !Number.isFinite(value));

/** Preserve ordinary raw values while making the reserved missing identity collision-proof. */
export function tableFacetValue(value: TableValue): string {
	if (isMissing(value)) return TABLE_MISSING_VALUE;
	const text = String(value);
	return text.startsWith('\u0000') ? VALUE_ESCAPE + text : text;
}

function facetLabel(value: string): string {
	return value.startsWith(VALUE_ESCAPE) ? value.slice(VALUE_ESCAPE.length) : value;
}

export function createTableView<Row>({
	rows: source,
	columns: columnSource,
	search = () => '',
	searchable,
	locale = () => 'en',
	state: externalState,
	onSortChange,
}: {
	rows: () => readonly Row[];
	columns: () => TableColumn<Row>[];
	search?: () => string;
	searchable?: (row: Row) => string | readonly string[];
	locale?: () => string;
	state?: TableViewState;
	onSortChange?: (sort: TableSort | null) => void;
}): TableView<Row> {
	const ownedState = $state<TableViewState>({ sort: null, filters: {} });
	const state = externalState ?? ownedState;
	const columns = $derived(columnSource());
	const compiled = $derived(compileRegexSearch(search()));
	const collator = $derived(new Intl.Collator(locale(), { numeric: true, sensitivity: 'base' }));
	const activeFilters = $derived.by(() => {
		const merged = { ...state.filters };
		for (const column of columns) {
			if (!column.onFilterChange) continue;
			const selected = column.filterSelection?.() ?? null;
			if (selected === null) delete merged[column.key];
			else merged[column.key] = [...selected];
		}
		return merged;
	});
	const searchRows = $derived.by(() => {
		const incoming = source();
		if (!compiled.regex && !compiled.error) return incoming;
		return incoming.filter((row) => matchesRegexSearch(compiled, searchable
			? searchable(row)
			: columns.map((column) => {
				const value = column.value(row);
				return isMissing(value) ? '' : column.format?.(value, row) ?? String(value);
			})));
	});

	function facetValues(column: TableColumn<Row>, row: Row): readonly TableValue[] {
		const values = column.filterValues?.(row);
		return values ? values.length ? values : [null] : [column.value(row)];
	}

	function matchesFilters(row: Row, except?: string): boolean {
		return columns.every((column) => column.key === except || column.filterable === false || column.onFilterChange
			|| !Object.hasOwn(state.filters, column.key)
			|| facetValues(column, row).some((value) => state.filters[column.key].includes(tableFacetValue(value))));
	}

	function sortRows(result: Row[]): Row[] {
		const sort = state.sort;
		const column = sort && columns.find((item) => item.key === sort.key && item.sortable !== false);
		if (!column || !sort) return result;
		const factor = sort.direction === 'asc' ? 1 : -1;
		return result.sort((a, b) => {
			const left = column.value(a);
			const right = column.value(b);
			const leftMissing = isMissing(left);
			const rightMissing = isMissing(right);
			if (leftMissing || rightMissing) return leftMissing === rightMissing ? 0 : leftMissing ? 1 : -1;
			const comparison = typeof left === 'number' && typeof right === 'number'
				? left - right
				: typeof left === 'boolean' && typeof right === 'boolean'
					? Number(left) - Number(right)
					: collator.compare(String(left), String(right));
			return comparison * factor;
		});
	}
	const projected = $derived(sortRows(searchRows.filter((row) => matchesFilters(row))));
	function setSort(next: TableSort | null) {
		if (next && !columns.some((column) => column.key === next.key && column.sortable !== false)) return;
		if (state.sort?.key === next?.key && state.sort?.direction === next?.direction) return;
		state.sort = next;
		onSortChange?.(next);
	}


	return {
		get rows() { return projected; },
		orderRows(rows) { return sortRows([...rows]); },
		get columns() { return columns; },
		get error() { return compiled.error; },
		get sort() { return state.sort; },
		get filters() { return activeFilters; },
		setSort,
		toggleSort(key) {
			if (!columns.some((column) => column.key === key && column.sortable !== false)) return;
			setSort(state.sort?.key !== key ? { key, direction: 'asc' }
				: state.sort.direction === 'asc' ? { key, direction: 'desc' } : null);
		},
		setFilter(key, values) {
			const column = columns.find((item) => item.key === key && item.filterable !== false);
			if (!column) return;
			const selected = [...new Set(values)];
			if (column.filterMode === 'single' && selected.length > 1) return;
			if (column.onFilterChange) {
				const current = column.filterSelection?.() ?? null;
				if (current && current.length === selected.length && current.every((value, index) => value === selected[index])) return;
				column.onFilterChange(selected);
			} else state.filters = { ...state.filters, [key]: selected };
		},
		clearFilter(key) {
			const column = columns.find((item) => item.key === key);
			if (column?.filterSelection?.() != null) column.onFilterChange?.(null);
			const remaining = { ...state.filters };
			delete remaining[key];
			state.filters = remaining;
		},
		reset() {
			setSort(null);
			state.filters = {};
			for (const column of columns) {
				if (column.filterSelection?.() != null) column.onFilterChange?.(null);
				const range = column.rangeFilter;
				if (range && (range.min() || range.max())) range.onchange('', '');
			}
		},
		options(key) {
			const column = columns.find((item) => item.key === key);
			if (!column) return [];
			const options = new Map<string, TableOption>((column.filterOptions?.() ?? []).map((option) => [option.value, { ...option }]));
			for (const row of column.onFilterChange ? [] : searchRows) {
				if (!matchesFilters(row, key)) continue;
				const seen = new Set<string>();
				for (const raw of facetValues(column, row)) {
					const value = tableFacetValue(raw);
					if (seen.has(value)) continue;
					seen.add(value);
					const previous = options.get(value);
					if (previous) previous.count = (previous.count ?? 0) + 1;
					else options.set(value, {
						value,
						label: isMissing(raw) ? '' : column.format?.(raw, row) ?? String(raw),
						count: 1,
					});
				}
			}
			for (const value of Object.hasOwn(activeFilters, key) ? activeFilters[key] : []) {
				if (!options.has(value)) options.set(value, { value, label: value === TABLE_MISSING_VALUE ? '' : facetLabel(value), count: column.onFilterChange ? null : 0 });
			}
			return [...options.values()].sort((a, b) => {
				if (a.value === TABLE_MISSING_VALUE || b.value === TABLE_MISSING_VALUE) return a.value === b.value ? 0 : a.value === TABLE_MISSING_VALUE ? 1 : -1;
				return collator.compare(a.label, b.label);
			});
		},
		direction(key) { return state.sort?.key === key ? state.sort.direction === 'asc' ? 'ascending' : 'descending' : 'none'; },
		selected(key) { return Object.hasOwn(activeFilters, key) ? activeFilters[key] : []; },
	};
}
