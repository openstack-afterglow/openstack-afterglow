import { createTableView, type TableColumn, type TableView, type TableOption } from '$lib/utils/tableView.svelte';
import { intlLocale } from '$lib/i18n/runtime.svelte';

export interface ObservationView<Row> {
	search: string;
	view: TableView<Row>;
	readonly sourceCount: number;
}

/** The feature component owns this model, including while loading/disclosing its table. */
export function createObservationView<Row>(
	rows: () => readonly Row[],
	columns: () => TableColumn<Row>[],
	searchable?: (row: Row) => string | readonly string[],
): ObservationView<Row> {
	let search = $state('');
	const view = createTableView({ rows, columns, searchable, search: () => search, locale: intlLocale });
	return { get search() { return search; }, set search(value) { search = value; }, get sourceCount() { return rows().length; }, view };
}

/** Native scalar predicates retain upstream cursor/statistics semantics in the header. */
export function nativeObservationFilter(
	selection: () => string,
	onchange: (value: string) => void,
	options: () => TableOption[],
	freeValue = true,
) {
	return {
		filterMode: 'single' as const,
		filterFreeValue: freeValue,
		filterSelection: () => selection() ? [selection()] : null,
		filterOptions: options,
		onFilterChange: (values: string[] | null) => {
			if (values && values.length > 1) throw new RangeError('Native observation filter requires one value');
			onchange(values?.[0] ?? '');
		},
	};
}

/** Loaded values are suggestions, never a claimed complete provider facet inventory. */
export function observationOptions(values: readonly (string | null | undefined)[]): TableOption[] {
	return [...new Set(values.filter((value): value is string => typeof value === 'string' && value !== ''))]
		.map(value => ({ value, label: value, count: null }));
}
