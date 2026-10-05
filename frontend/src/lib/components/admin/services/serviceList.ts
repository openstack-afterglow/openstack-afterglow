import { t } from '$lib/i18n/ns/admin-ops';
import { intlLocale } from '$lib/i18n/runtime.svelte';

export interface ServiceListState {
	search: string;
	filters: Record<string, string>;
	sortKey: string;
	sortDirection: 'asc' | 'desc';
}

type ListValue = string | number | null | undefined;

export interface ServiceListField<T> {
	key: string;
	label: string;
	value: (row: T) => ListValue;
	filter?: boolean;
	search?: boolean;
	sortValue?: (row: T) => ListValue;
}

export interface ServiceFilter {
	key: string;
	label: string;
	options: { value: string; label: string }[];
}

let collatorLocale = '';
let collator: Intl.Collator;

function serviceCollator(): Intl.Collator {
	const locale = intlLocale();
	if (locale !== collatorLocale) {
		collator = new Intl.Collator(locale, { numeric: true, sensitivity: 'base' });
		collatorLocale = locale;
	}
	return collator;
}

export function createServiceListState(defaultSortKey = ''): ServiceListState {
	return { search: '', filters: {}, sortKey: defaultSortKey, sortDirection: 'asc' };
}

function isMissing(value: ListValue): boolean {
	return value == null || (typeof value === 'string' && !value.trim())
		|| (typeof value === 'number' && !Number.isFinite(value));
}

function filterValue(value: ListValue): string {
	return isMissing(value) ? 'missing' : `value:${value}`;
}

export function serviceFilterLabel(value: string, fieldKey?: string): string {
	if (value === 'missing') return t('services.state.unknown');
	const code = value.slice('value:'.length);
	if (fieldKey === 'status' && (code === 'enabled' || code === 'disabled')) {
		return t(`services.state.${code}`);
	}
	if ((fieldKey === 'state' || fieldKey === 'alive') && (code === 'up' || code === 'down' || code === 'alive')) {
		return t(`services.state.${code}`);
	}
	if (fieldKey === 'admin_state' && (code === 'UP' || code === 'DOWN')) {
		return code === 'UP' ? t('services.state.adminUp') : t('services.state.adminDown');
	}
	return code;
}

export function buildServiceFilters<T>(rows: readonly T[], fields: readonly ServiceListField<T>[]): ServiceFilter[] {
	const collator = serviceCollator();
	return fields.filter(field => field.filter).map(field => {
		const values = new Set(rows.map(row => filterValue(field.value(row))));
		const options = [...values].map(value => ({ value, label: serviceFilterLabel(value, field.key) }));
		options.sort((a, b) => {
			if (a.value === 'missing') return b.value === 'missing' ? 0 : 1;
			if (b.value === 'missing') return -1;
			return collator.compare(a.value, b.value);
		});
		return { key: field.key, label: field.label, options };
	});
}

export function filterAndSortRows<T>(rows: readonly T[], fields: readonly ServiceListField<T>[], view: ServiceListState): readonly T[] {
	const terms = view.search.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
	const activeFilters = fields.filter(field => field.filter && view.filters[field.key]);
	const searchFields = fields.filter(field => field.search !== false);
	let result = rows;
	if (terms.length || activeFilters.length) {
		result = rows.filter(row => {
			if (!activeFilters.every(field => filterValue(field.value(row)) === view.filters[field.key])) return false;
			return terms.every(term => searchFields.some(field => {
				const value = field.value(row);
				return value != null && String(value).toLocaleLowerCase().includes(term);
			}));
		});
	}
	const sortField = fields.find(field => field.key === view.sortKey);
	if (!sortField) return result;
	const collator = serviceCollator();
	const direction = view.sortDirection === 'asc' ? 1 : -1;
	const getValue = sortField.sortValue ?? sortField.value;
	// Compute each sort value once, including timestamp parsing, without mutating API arrays.
	return result.map(row => ({ row, value: getValue(row) })).sort((a, b) => {
		const aMissing = isMissing(a.value);
		const bMissing = isMissing(b.value);
		if (aMissing || bMissing) return aMissing === bMissing ? 0 : aMissing ? 1 : -1;
		const comparison = typeof a.value === 'number' && typeof b.value === 'number'
			? a.value - b.value
			: collator.compare(String(a.value), String(b.value));
		return direction * comparison;
	}).map(entry => entry.row);
}

export function serviceTimestamp(value: string | null | undefined): number | null {
	if (!value) return null;
	const normalized = value.replace(' ', 'T');
	// OpenStack timestamps without an explicit offset are UTC, not browser-local time.
	const timestamp = Date.parse(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(normalized) ? normalized : `${normalized}Z`);
	return Number.isFinite(timestamp) ? timestamp : null;
}
