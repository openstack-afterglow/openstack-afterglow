import { render } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import LinkedStatTileFixture from './StatTileLinkedFixture.svelte';


describe('StatTile', () => {

	it('keeps the tone class on a linked stat tile direct child', () => {
		const { container } = render(LinkedStatTileFixture);

		const linkedTile = container.querySelector('a[href="/admin/users"] > .stat-tile.tile-warning');
		expect(linkedTile).toBeTruthy();
		expect(linkedTile?.textContent).toContain('사용자');
		expect(linkedTile?.textContent).toContain('4');
		expect(linkedTile?.textContent).toContain('명');
	});
});
