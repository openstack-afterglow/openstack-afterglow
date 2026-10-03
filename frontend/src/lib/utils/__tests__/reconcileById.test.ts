import { describe, expect, it } from 'vitest';
import { reconcileById } from '../reconcileById';

describe('Waygate response reconciliation', () => {
	it('does not publish an unchanged empty or populated result', () => {
		const empty: { id: string }[] = [];
		expect(reconcileById(empty, [])).toBe(empty);
		const rows = [{ id: 'a', name: 'laptop', allowed_ips: ['10.0.0.0/24'] }];
		expect(reconcileById(rows, [{ id: 'a', name: 'laptop', allowed_ips: ['10.0.0.0/24'] }])).toBe(rows);
	});

	it('updates only changed IDs while retaining unchanged peers across additions, reorders and removals', () => {
		const first = { id: 'a', name: 'laptop', allowed_ips: ['10.0.0.0/24'] };
		const second = { id: 'b', name: 'phone', allowed_ips: ['10.0.0.0/24'] };
		const initial = [first, second];
		const updated = reconcileById(initial, [
			{ id: 'a', name: 'laptop', allowed_ips: ['10.0.0.0/24'] },
			{ id: 'b', name: 'phone', allowed_ips: ['10.1.0.0/24'] },
			{ id: 'c', name: 'tablet', allowed_ips: [] },
		]);
		expect(updated).not.toBe(initial);
		expect(updated[0]).toBe(first);
		expect(updated[1]).not.toBe(second);
		expect(updated[1].allowed_ips).toEqual(['10.1.0.0/24']);
		const reordered = reconcileById(updated, [
			{ id: 'c', name: 'tablet', allowed_ips: [] },
			{ id: 'a', name: 'laptop', allowed_ips: ['10.0.0.0/24'] },
		]);
		expect(reordered[0]).toBe(updated[2]);
		expect(reordered[1]).toBe(first);
		expect(reordered).toHaveLength(2);
	});
});
