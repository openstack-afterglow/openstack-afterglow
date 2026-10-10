import { render } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import LinkedStatTileFixture from './StatTileLinkedFixture.svelte';
import StatTile from '../StatTile.svelte';


describe('StatTile', () => {

	it('keeps the tone class on a linked stat tile direct child', () => {
		const { container } = render(LinkedStatTileFixture);

		const linkedTile = container.querySelector('a[href="/admin/users"] > .stat-tile.tile-warning');
		expect(linkedTile).toBeTruthy();
		expect(linkedTile?.textContent).toContain('사용자');
		expect(linkedTile?.textContent).toContain('4');
		expect(linkedTile?.textContent).toContain('명');
	});

	it('preserves numeric precision and literal string values', async () => {
		const view = render(StatTile, { label: '사용률', value: 12.5 });
		expect(view.container.querySelector('.stat-value')?.textContent).toBe('12.5');
		await view.rerender({ label: '사용률', value: '무제한' });
		expect(view.container.querySelector('.stat-value')?.textContent).toBe('무제한');
	});

	it.each([[-1, 0], [25, 0.25], [120, 1]])('clamps visible progress for %s', (value, scale) => {
		const view = render(StatTile, { label: 'CPU', value, progress: { value, max: 100 } });
		expect((view.container.querySelector('.progress-bar') as HTMLElement).style.transform).toBe(`scaleX(${scale})`);
	});
});
