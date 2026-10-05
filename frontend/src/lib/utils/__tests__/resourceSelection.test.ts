import { describe, expect, it } from 'vitest';
import { createResourceSelection } from '../resourceSelection.svelte';

describe('createResourceSelection', () => {
	it('replaces the current visible selection and clears it when all IDs are selected', () => {
		const selection = createResourceSelection();
		selection.toggle('stale');
		selection.toggleAll(['volume-1', 'volume-2']);
		expect([...selection.ids]).toEqual(['volume-1', 'volume-2']);

		selection.toggleAll(['volume-1', 'volume-2']);
		expect(selection.count).toBe(0);
	});

	it('retains only refreshed IDs', () => {
		const selection = createResourceSelection();
		selection.toggleAll(['image-1', 'image-2']);
		selection.retain(['image-2', 'image-3']);
		expect([...selection.ids]).toEqual(['image-2']);
	});

	it('prunes on project or list changes and removes only successful IDs', () => {
		const selection = createResourceSelection();
		selection.toggleAll(['network-1', 'network-2', 'network-3']);
		selection.remove(['network-1', 'network-3']);
		expect([...selection.ids]).toEqual(['network-2']);

		selection.retain([]);
		expect(selection.count).toBe(0);
	});
});
