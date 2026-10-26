// @vitest-environment node
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createSwr } from '../swr.svelte';

afterEach(() => vi.useRealTimers());
describe('controller-local display snapshots', () => {
	it('never exposes another mounted actor controller cache even in the same project', () => {
		const first = createSwr(() => 'project');
		first.swrSet('/volumes', [{ id: 'private-volume' }]);
		expect(first.swrGet('/volumes')).toEqual([{ id: 'private-volume' }]);
		expect(createSwr(() => 'project').swrGet('/volumes')).toBeNull();
	});
	it('expires without extending the lifetime on reads', () => {
		vi.useFakeTimers();
		const cache = createSwr(() => 'project');
		cache.swrSet('/volumes', [1]);
		vi.advanceTimersByTime(29_000);
		expect(cache.swrGet('/volumes')).toEqual([1]);
		vi.advanceTimersByTime(1_000);
		expect(cache.swrGet('/volumes')).toBeNull();
	});
	it('discards old values when the controller observes a scope change', () => {
		let project = 'a';
		const cache = createSwr(() => project);
		cache.swrSet('/networks', ['a']);
		project = 'b';
		expect(cache.swrGet('/networks')).toBeNull();
		cache.swrSet('/networks', ['b']);
		project = 'a';
		expect(cache.swrGet('/networks')).toBeNull();
	});
});
