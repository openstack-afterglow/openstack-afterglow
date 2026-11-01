export type ResourceSort = 'created_desc' | 'created_asc' | 'name_asc' | 'name_desc';

interface SortableResource {
	id: string;
	name?: string | null;
	created_at?: string | null;
}

function creationTime(value: string | null | undefined): number | null {
	if (!value) return null;
	// Native Cinder timestamps can omit a zone; those timestamps are UTC.
	const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}Z`;
	const time = Date.parse(normalized);
	return Number.isFinite(time) ? time : null;
}


/** Sort a complete project list without changing its authority/selection snapshot. */
export function sortResources<T extends SortableResource>(rows: readonly T[], sort: ResourceSort): T[] {
	const direction = sort.endsWith('_desc') ? -1 : 1;
	const byName = sort.startsWith('name_');
	return rows.map((row) => ({ row, time: byName ? null : creationTime(row.created_at) }))
		.sort((a, b) => {
			let order: number;
			if (byName) {
				const aName = (a.row.name ?? '').toLowerCase();
				const bName = (b.row.name ?? '').toLowerCase();
				order = direction * (aName < bName ? -1 : aName > bName ? 1 : 0);
			}
			else if (a.time === null || b.time === null) order = Number(a.time === null) - Number(b.time === null);
			else order = direction * (a.time - b.time);
			return order || (a.row.id < b.row.id ? -1 : a.row.id > b.row.id ? 1 : 0);
		})
		.map(({ row }) => row);
}
