// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { buildServiceFilters, createServiceListState, filterAndSortRows, serviceTimestamp, type ServiceListField } from '../serviceList';

interface Row { id: string; updated: string | null; host: string | null }
const fields: ServiceListField<Row>[] = [
	{ key: 'updated', label: 'Updated', value: row => row.updated, sortValue: row => serviceTimestamp(row.updated) },
	{ key: 'host', label: 'Host', value: row => row.host, filter: true },
];

describe('service list ordering boundaries', () => {
	it('orders real instants across timezones and leaves missing or invalid timestamps last in both directions', () => {
		const rows: Row[] = [
			{ id: 'later', updated: '2026-09-14T08:00:00Z', host: 'host10' },
			{ id: 'missing', updated: null, host: null },
			{ id: 'earlier', updated: '2026-09-14T10:00:00+09:00', host: 'host2' },
			{ id: 'invalid', updated: 'not-a-date', host: null },
			{ id: 'middle', updated: '2026-09-14 04:00:00', host: 'host3' },
		];
		const view = createServiceListState('updated');
		expect(filterAndSortRows(rows, fields, view).map(row => row.id)).toEqual(['earlier', 'middle', 'later', 'missing', 'invalid']);
		view.sortDirection = 'desc';
		expect(filterAndSortRows(rows, fields, view).map(row => row.id)).toEqual(['later', 'middle', 'earlier', 'missing', 'invalid']);
		expect(rows.map(row => row.id)).toEqual(['later', 'missing', 'earlier', 'invalid', 'middle']);
	});

	it('keeps a literal unknown-looking host distinct from a missing host', () => {
		const rows: Row[] = [
			{ id: 'literal', host: 'missing', updated: null },
			{ id: 'absent', host: null, updated: null },
		];
		const options = buildServiceFilters(rows, fields)[0].options;
		const view = createServiceListState();
		view.filters.host = options.find(option => option.label === '미확인')!.value;
		expect(filterAndSortRows(rows, fields, view).map(row => row.id)).toEqual(['absent']);
		view.filters.host = options.find(option => option.label === 'missing')!.value;
		expect(filterAndSortRows(rows, fields, view).map(row => row.id)).toEqual(['literal']);
	});
});
