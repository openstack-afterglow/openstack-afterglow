import { afterEach, describe, expect, it, vi } from 'vitest';
import { createTableView, TABLE_MISSING_VALUE, tableFacetValue, type TableColumn, type TableView, type TableViewState } from './tableView.svelte';

type Row = { id: string; name: string; status: string; size?: number | null; zone: string };
const columns: TableColumn<Row>[] = [
	{ key: 'name', label: 'Name', value: (row) => row.name },
	{ key: 'status', label: 'Status', value: (row) => row.status },
	{ key: 'size', label: 'Size', value: (row) => row.size },
	{ key: 'zone', label: 'Zone', value: (row) => row.zone },
];
const initial: Row[] = [
	{ id: 'a', name: 'host10', status: 'active', size: 10, zone: 'east' },
	{ id: 'b', name: 'host2', status: 'paused', size: 2, zone: 'east' },
	{ id: 'c', name: 'host2', status: 'active', size: null, zone: 'west' },
	{ id: 'd', name: 'host1', status: 'error', zone: 'east' },
];
const cleanups: (() => void)[] = [];
afterEach(() => { for (const cleanup of cleanups.splice(0)) cleanup(); });

function setup() {
	const state = $state({ rows: initial.map((row) => ({ ...row })), search: '', locale: 'en' });
	let view!: TableView<Row>;
	cleanups.push($effect.root(() => {
		view = createTableView({ rows: () => state.rows, columns: () => columns, search: () => state.search, searchable: (row) => row.name, locale: () => state.locale });
	}));
	return { state, view };
}

describe('createTableView', () => {
	it('cycles natural ascending, descending and stable incoming default order without mutating source', () => {
		const { state, view } = setup();
		view.toggleSort('name');
		expect(view.direction('name')).toBe('ascending');
		expect(view.rows.map((row) => row.id)).toEqual(['d', 'b', 'c', 'a']);
		view.toggleSort('name');
		expect(view.rows.map((row) => row.id)).toEqual(['a', 'b', 'c', 'd']);
		view.toggleSort('name');
		expect(view.sort).toBeNull();
		expect(view.rows.map((row) => row.id)).toEqual(['a', 'b', 'c', 'd']);
		expect(state.rows.map((row) => row.id)).toEqual(['a', 'b', 'c', 'd']);
	});

	it('sorts numbers numerically and keeps null, undefined and nonfinite unknowns last in both directions', () => {
		const { state, view } = setup();
		state.rows = [...state.rows, { id: 'e', name: 'host0', status: 'active', size: Number.NaN, zone: 'east' }];
		view.toggleSort('size');
		expect(view.rows.map((row) => row.id)).toEqual(['b', 'a', 'c', 'd', 'e']);
		view.toggleSort('size');
		expect(view.rows.map((row) => row.id)).toEqual(['a', 'b', 'c', 'd', 'e']);
	});

	it('combines OR within a facet and AND across facets before caller pagination', () => {
		const { view } = setup();
		view.setFilter('status', ['active', 'paused']);
		view.setFilter('zone', ['east']);
		view.toggleSort('size');
		expect(view.rows.map((row) => row.id)).toEqual(['b', 'a']);
		expect(view.rows.slice(0, 1).map((row) => row.id)).toEqual(['b']);
		view.setFilter('status', []);
		expect(view.rows).toEqual([]);
		view.clearFilter('status');
		expect(view.rows.map((row) => row.id)).toEqual(['b', 'a', 'd']);
	});

	it('retains query, sort and absent selected values across refresh, including zero-count options', () => {
		const { state, view } = setup();
		state.search = '^host';
		view.setFilter('status', ['paused']);
		view.toggleSort('name');
		view.toggleSort('name');
		state.rows = [{ id: 'z', name: 'host99', status: 'active', size: 99, zone: 'east' }];
		expect(view.rows).toEqual([]);
		expect(view.sort).toEqual({ key: 'name', direction: 'desc' });
		expect(view.selected('status')).toEqual(['paused']);
		expect(view.options('status')).toContainEqual({ value: 'paused', label: 'paused', count: 0 });
		state.rows = [...state.rows, { id: 'y', name: 'HOST42', status: 'paused', size: 42, zone: 'west' }];
		expect(view.rows.map((row) => row.id)).toEqual(['y']);
	});

	it('shows faceted counts constrained by search and other columns, but not its own selection', () => {
		const { state, view } = setup();
		state.search = '^host(2|10)$';
		view.setFilter('zone', ['east']);
		view.setFilter('status', ['active']);
		expect(view.options('status')).toEqual([
			{ value: 'active', label: 'active', count: 1 },
			{ value: 'paused', label: 'paused', count: 1 },
		]);
	});

	it('keeps missing distinct from empty, false, zero and reserved-looking actual strings', () => {
		expect(tableFacetValue(null)).toBe(TABLE_MISSING_VALUE);
		expect(tableFacetValue(undefined)).toBe(TABLE_MISSING_VALUE);
		expect(tableFacetValue(Number.POSITIVE_INFINITY)).toBe(TABLE_MISSING_VALUE);
		expect(new Set([tableFacetValue(null), tableFacetValue(''), tableFacetValue(false), tableFacetValue(0), tableFacetValue(TABLE_MISSING_VALUE)]).size).toBe(5);
		const { view } = setup();
		view.setFilter('size', [TABLE_MISSING_VALUE]);
		expect(view.rows.map((row) => row.id)).toEqual(['c', 'd']);
	});

	it('invalid expressions hide rows and reset never rewrites the caller search', () => {
		const { state, view } = setup();
		state.search = '[';
		view.setFilter('status', ['active']);
		view.toggleSort('name');
		expect(view.error).toBe(true);
		expect(view.rows).toEqual([]);
		view.reset();
		expect(view.filters).toEqual({});
		expect(view.sort).toBeNull();
		expect(state.search).toBe('[');
		expect(view.rows).toEqual([]);
		state.search = '^HOST2$';
		expect(view.error).toBe(false);
		expect(view.rows.map((row) => row.id)).toEqual(['b', 'c']);
	});

	it('matches anchored regex independently against default declared fields', () => {
		const view = createTableView({ rows: () => initial, columns: () => columns, search: () => '^host2$' });
		expect(view.rows.map((row) => row.id)).toEqual(['b', 'c']);
		const explicit = createTableView({ rows: () => initial, columns: () => columns, search: () => '^b$', searchable: (row) => [row.id, row.name] });
		expect(explicit.rows.map((row) => row.id)).toEqual(['b']);
	});

	it('preserves set-valued membership and counts each row once per facet', () => {
		const rows = [
			{ models: ['A10', 'A100', 'A10'] },
			{ models: ['A100'] },
			{ models: [] },
		];
		const view = createTableView({
			rows: () => rows,
			columns: () => [{ key: 'models', label: 'Models', value: (row) => row.models.join(', '), filterValues: (row) => row.models }],
		});
		view.setFilter('models', ['A10']);
		expect(view.rows).toEqual([rows[0]]);
		expect(view.options('models')).toEqual([
			{ value: 'A10', label: 'A10', count: 1 },
			{ value: 'A100', label: 'A100', count: 2 },
			{ value: TABLE_MISSING_VALUE, label: '', count: 1 },
		]);
		view.setFilter('models', [TABLE_MISSING_VALUE]);
		expect(view.rows).toEqual([rows[2]]);
	});

	it('can retain only explicit view conditions in a reactive parent across child remounts', () => {
		const state = $state<TableViewState>({ sort: null, filters: {} });
		const first = createTableView({ rows: () => initial, columns: () => columns, state });
		first.toggleSort('name');
		first.setFilter('status', ['paused']);
		const remounted = createTableView({ rows: () => initial, columns: () => columns, state });
		expect(remounted.direction('name')).toBe('ascending');
		expect(remounted.rows.map((row) => row.id)).toEqual(['b']);
		state.filters = {};
		state.sort = null;
		expect(remounted.rows.map((row) => row.id)).toEqual(['a', 'b', 'c', 'd']);
	});

	it('delegates external facets to native query state without narrowing the loaded provider page', () => {
		const native = $state<{ selection: string[] | null }>({ selection: null });
		const change = vi.fn((values: string[] | null) => { native.selection = values; });
		const view = createTableView({
			rows: () => initial,
			columns: () => [{
				key: 'status', label: 'Status', value: (row: Row) => row.status,
				filterMode: 'single',
				filterOptions: () => [{ value: 'active', label: 'Active', count: 120 }, { value: 'paused', label: 'Paused', count: null }],
				filterSelection: () => native.selection,
				onFilterChange: change,
			}],
		});
		view.setFilter('status', ['paused']);
		expect(change).toHaveBeenLastCalledWith(['paused']);
		expect(view.filters).toEqual({ status: ['paused'] });
		expect(view.selected('status')).toEqual(['paused']);
		expect(view.rows).toHaveLength(initial.length);
		expect(view.options('status')).toContainEqual({ value: 'active', label: 'Active', count: 120 });
		view.setFilter('status', ['active', 'paused']);
		expect(change).toHaveBeenCalledTimes(1);
		native.selection = ['provider-only'];
		expect(view.options('status')).toContainEqual({ value: 'provider-only', label: 'provider-only', count: null });
		view.clearFilter('status');
		expect(change).toHaveBeenLastCalledWith(null);
		expect(view.filters).toEqual({});
	});

	it('does not fan reset callbacks out to inactive native columns or unchanged sorting', () => {
		const native = $state<{ selection: string[] | null; min: string; max: string }>({ selection: null, min: '', max: '' });
		const change = vi.fn((values: string[] | null) => { native.selection = values; });
		const rangeChange = vi.fn((min: string, max: string) => { native.min = min; native.max = max; });
		const sortChange = vi.fn();
		const view = createTableView({
			rows: () => initial,
			columns: () => [
				{ key: 'status', label: 'Status', value: (row: Row) => row.status, filterSelection: () => native.selection, onFilterChange: change },
				{ key: 'size', label: 'Size', value: (row: Row) => row.size, rangeFilter: { min: () => native.min, max: () => native.max, onchange: rangeChange } },
			],
			onSortChange: sortChange,
		});
		view.reset();
		expect(change).not.toHaveBeenCalled();
		expect(rangeChange).not.toHaveBeenCalled();
		expect(sortChange).not.toHaveBeenCalled();
		view.setSort({ key: 'size', direction: 'desc' });
		expect(sortChange).toHaveBeenCalledTimes(1);
		view.setSort({ key: 'size', direction: 'desc' });
		expect(sortChange).toHaveBeenCalledTimes(1);
		view.setFilter('status', ['active']);
		native.min = '10';
		native.max = '99';
		view.reset();
		expect(change).toHaveBeenCalledTimes(2);
		expect(rangeChange).toHaveBeenCalledTimes(1);
		expect(rangeChange).toHaveBeenLastCalledWith('', '');
		expect(sortChange).toHaveBeenLastCalledWith(null);
		view.reset();
		expect(change).toHaveBeenCalledTimes(2);
		expect(rangeChange).toHaveBeenCalledTimes(1);
		expect(sortChange).toHaveBeenCalledTimes(2);
	});

	it('orders retained contextual rows without applying regex or facets and never mutates their supplied default order', () => {
		const { state, view } = setup();
		state.search = '^host2$';
		view.setFilter('status', ['paused']);
		expect(view.rows.map((row) => row.id)).toEqual(['b']);
		const contextual = [initial[0], initial[3], initial[2]];
		expect(view.orderRows(contextual).map((row) => row.id)).toEqual(['a', 'd', 'c']);
		view.setSort({ key: 'name', direction: 'desc' });
		expect(view.orderRows(contextual).map((row) => row.id)).toEqual(['a', 'c', 'd']);
		expect(view.rows.map((row) => row.id)).toEqual(['b']);
		expect(contextual.map((row) => row.id)).toEqual(['a', 'd', 'c']);
		view.setSort({ key: 'size', direction: 'desc' });
		expect(view.orderRows(contextual).map((row) => row.id)).toEqual(['a', 'd', 'c']);
	});

	it('does not permit controls on explicitly disabled or unknown columns', () => {
		const view = createTableView({ rows: () => initial, columns: () => [{ key: 'name', label: 'Name', value: (row: Row) => row.name, sortable: false, filterable: false }] });
		view.toggleSort('name');
		view.toggleSort('missing');
		view.setFilter('name', []);
		view.setFilter('missing', []);
		expect(view.sort).toBeNull();
		expect(view.filters).toEqual({});
		expect(view.options('missing')).toEqual([]);
	});
});
