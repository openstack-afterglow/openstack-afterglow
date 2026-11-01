import { describe, expect, it } from 'vitest';
import { sortResources, type ResourceSort } from '../resourceSort';

const rows = [
	{ id: 'old', name: 'alpha', created_at: '2026-10-26T23:00:00Z' },
	{ id: 'missing', name: 'Zulu', created_at: null },
	{ id: 'same-b', name: 'ALPHA', created_at: '2026-10-28T00:00:00+09:00' },
	{ id: 'new', name: 'Alpha', created_at: '2026-10-28T01:00:00' },
	{ id: 'invalid', name: 'omega', created_at: 'not-a-date' },
	{ id: 'same-a', name: 'beta', created_at: '2026-10-27T15:00:00Z' },
];

describe('resource list ordering', () => {
	it.each<[ResourceSort, string[]]>([
		['created_desc', ['new', 'same-a', 'same-b', 'old', 'invalid', 'missing']],
		['created_asc', ['old', 'same-a', 'same-b', 'new', 'invalid', 'missing']],
		['name_asc', ['new', 'old', 'same-b', 'same-a', 'invalid', 'missing']],
		['name_desc', ['missing', 'invalid', 'same-a', 'new', 'old', 'same-b']],
	])('%s uses full timestamps, UTC for unzoned native dates, and stable IDs', (sort, expected) => {
		const before = rows.map((row) => ({ ...row }));
		expect(sortResources(rows, sort).map((row) => row.id)).toEqual(expected);
		expect(rows).toEqual(before);
	});

	it('keeps epoch timestamps ahead of unknown dates in either date direction', () => {
		const values = [{ id: 'unknown' }, { id: 'epoch', created_at: '1970-01-01T00:00:00Z' }];
		for (const sort of ['created_desc', 'created_asc'] as const) {
			expect(sortResources(values, sort).map((row) => row.id)).toEqual(['epoch', 'unknown']);
		}
	});
});
