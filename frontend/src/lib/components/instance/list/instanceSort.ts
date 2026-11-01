import type { Instance } from '$lib/types/compute';
import { sortResources } from '$lib/utils/resourceSort';
import { consumerInstanceFlavorLabel } from '$lib/utils/flavorDisplay';
import { intlLocale } from '$lib/i18n/runtime.svelte';

export type InstanceSortKey = 'name' | 'status' | 'image' | 'ip' | 'library' | 'strategy';
/** `null` keeps the default newest-first order. */
export type InstanceSort = { key: InstanceSortKey; direction: 'asc' | 'desc' } | null;


/** Header click cycle: ascending → descending → default newest-first. */
export function nextInstanceSort(current: InstanceSort, key: InstanceSortKey): InstanceSort {
	if (current?.key !== key) return { key, direction: 'asc' };
	return current.direction === 'asc' ? { key, direction: 'desc' } : null;
}

/**
 * Sort by a visible column. Rows are first ordered newest-first, so equal values keep that order
 * (Array.prototype.sort is stable). Empty values stay last in both directions.
 */
export function sortInstances(
	rows: readonly Instance[],
	sort: InstanceSort,
	statusLabel: (status: string) => string,
	strategyLabel: (strategy: string) => string,
): Instance[] {
	const newest = sortResources(rows, 'created_desc');
	if (!sort) return newest;
	const collator = new Intl.Collator(intlLocale(), { numeric: true, sensitivity: 'base' });
	const value = (row: Instance): string => {
		switch (sort.key) {
			case 'name': return row.name ?? '';
			case 'status': return row.status ? statusLabel(row.status) : '';
			case 'image': return [row.image_name, consumerInstanceFlavorLabel(row)].filter(Boolean).join(' ');
			case 'ip': return (row.ip_addresses.find((ip) => ip.type === 'fixed') ?? row.ip_addresses[0])?.addr ?? '';
			case 'library': return row.union_libraries.filter(Boolean).join(', ');
			case 'strategy': return row.union_strategy ? strategyLabel(row.union_strategy) : '';
		}
	};
	const direction = sort.direction === 'asc' ? 1 : -1;
	return newest.map((row) => ({ row, key: value(row) }))
		.sort((a, b) => {
			if (!a.key || !b.key) return Number(!a.key) - Number(!b.key);
			return direction * collator.compare(a.key, b.key);
		})
		.map(({ row }) => row);
}
