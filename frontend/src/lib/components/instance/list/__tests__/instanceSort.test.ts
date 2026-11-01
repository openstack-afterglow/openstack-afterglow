import { describe, expect, it } from 'vitest';
import type { Instance } from '$lib/types/compute';
import { nextInstanceSort, sortInstances, type InstanceSortKey } from '../instanceSort';

const row = (id: string, values: Partial<Instance> = {}): Instance => ({
	id, name: id, status: '', image_name: null, flavor_name: '', ip_addresses: [],
	created_at: '2026-01-01T00:00:00Z', union_libraries: [], union_strategy: null, ...values,
});
const status = (value: string) => ({ ACTIVE: 'Alpha', SHUTOFF: 'Zulu' }[value] ?? value);
const strategy = (value: string) => ({ prebuilt: 'Alpha', dynamic: 'Zulu' }[value] ?? value);
const sort = (rows: Instance[], key: InstanceSortKey, direction: 'asc' | 'desc' = 'asc') =>
	sortInstances(rows, { key, direction }, status, strategy).map(({ id }) => id);

describe('instance column sorting', () => {
	it('cycles ascending, descending, default and switches columns independently', () => {
		expect(nextInstanceSort(null, 'name')).toEqual({ key: 'name', direction: 'asc' });
		expect(nextInstanceSort({ key: 'name', direction: 'asc' }, 'name')).toEqual({ key: 'name', direction: 'desc' });
		expect(nextInstanceSort({ key: 'name', direction: 'desc' }, 'name')).toBeNull();
		expect(nextInstanceSort({ key: 'name', direction: 'desc' }, 'ip')).toEqual({ key: 'ip', direction: 'asc' });
	});
	it('keeps newest-first as default and tie order without mutating source', () => {
		const rows = [row('old', { name: 'same' }), row('new', { name: 'same', created_at: '2026-02-01T00:00:00Z' })];
		expect(sortInstances(rows, null, status, strategy).map(({ id }) => id)).toEqual(['new', 'old']);
		expect(sort(rows, 'name')).toEqual(['new', 'old']);
		expect(rows.map(({ id }) => id)).toEqual(['old', 'new']);
	});
	it.each([
		['name', { name: 'vm-2' }, { name: 'vm-10' }],
		['status', { status: 'ACTIVE' }, { status: 'SHUTOFF' }],
		['image', { image_name: 'Alpha', flavor_name: 'small' }, { image_name: 'Zulu', flavor_name: 'small' }],
		['ip', { ip_addresses: [{ addr: '10.0.0.2', type: 'fixed', network_name: 'net' }] }, { ip_addresses: [{ addr: '10.0.0.10', type: 'fixed', network_name: 'net' }] }],
		['library', { union_libraries: ['alpha'] }, { union_libraries: ['zulu'] }],
		['strategy', { union_strategy: 'prebuilt' }, { union_strategy: 'dynamic' }],
	] satisfies [InstanceSortKey, Partial<Instance>, Partial<Instance>][])('sorts the %s visible projection in both directions', (key, a, b) => {
		const rows = [row('b', b), row('a', a)];
		expect(sort(rows, key)).toEqual(['a', 'b']);
		expect(sort(rows, key, 'desc')).toEqual(['b', 'a']);
	});
	it.each(['name', 'status', 'ip', 'library', 'strategy'] as const)('keeps missing %s last in either direction', key => {
		const rows = [row('missing', { name: '' }), row('present', { name: 'name', status: 'ACTIVE', union_strategy: 'prebuilt', union_libraries: ['lib'], ip_addresses: [{ addr: '::1', type: 'fixed', network_name: 'net' }] })];
		expect(sort(rows, key)).toEqual(['present', 'missing']);
		expect(sort(rows, key, 'desc')).toEqual(['present', 'missing']);
	});
});
