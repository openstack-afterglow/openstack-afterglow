import { describe, expect, it } from 'vitest';
import { pinCreatedPort } from './pinCreatedPort';

const items = [{ id: 'a' }, { id: 'b' }];
const created = { id: 'new' };

describe('pinCreatedPort', () => {
	it('leaves the listing order alone when no tour is running', () => {
		expect(pinCreatedPort(items, created, { tourActive: false, firstPage: true, scoped: false })).toBe(items);
	});

	it('pins the created port first during a tour when it is not on the page', () => {
		expect(pinCreatedPort(items, created, { tourActive: true, firstPage: true, scoped: false }).map((p) => p.id)).toEqual(['new', 'a', 'b']);
	});

	it('does not duplicate a port that is already listed, nor pin on later or scoped pages', () => {
		const listed = [...items, created];
		expect(pinCreatedPort(listed, created, { tourActive: true, firstPage: true, scoped: false })).toBe(listed);
		expect(pinCreatedPort(items, created, { tourActive: true, firstPage: false, scoped: false })).toBe(items);
		expect(pinCreatedPort(items, created, { tourActive: true, firstPage: true, scoped: true })).toBe(items);
		expect(pinCreatedPort(items, null, { tourActive: true, firstPage: true, scoped: false })).toBe(items);
	});
});
