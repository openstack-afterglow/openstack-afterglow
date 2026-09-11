import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import TabsFixture from './TabsFixture.svelte';

describe('Tabs', () => {
	it('links the selected tab to its caller-owned panel', () => {
		render(TabsFixture);
		const tab = screen.getByRole('tab', { name: '개요' });
		const panel = screen.getByRole('tabpanel', { name: '개요' });

		expect(tab.getAttribute('aria-selected')).toBe('true');
		expect(tab.getAttribute('aria-controls')).toBe(panel.id);
		expect(panel.getAttribute('aria-labelledby')).toBe(tab.id);
	});

	it('moves focus with arrows, skips disabled tabs, and activates manually', async () => {
		render(TabsFixture);
		const overview = screen.getByRole('tab', { name: '개요' });
		const activity = screen.getByRole('tab', { name: '활동' });
		overview.focus();

		await fireEvent.keyDown(overview, { key: 'ArrowRight' });
		await Promise.resolve();
		expect(document.activeElement).toBe(activity);
		expect(screen.getByRole('tabpanel', { name: '개요' })).toBeTruthy();
		expect(activity.getAttribute('aria-selected')).toBe('false');

		await fireEvent.keyDown(activity, { key: 'Enter' });
		expect(activity.getAttribute('aria-selected')).toBe('true');
		expect(screen.getByRole('tabpanel', { name: '활동' })).toBeTruthy();
	});

	it('wraps with arrows and supports Home and End', async () => {
		render(TabsFixture);
		const overview = screen.getByRole('tab', { name: '개요' });
		const activity = screen.getByRole('tab', { name: '활동' });
		overview.focus();

		await fireEvent.keyDown(overview, { key: 'ArrowLeft' });
		await Promise.resolve();
		expect(document.activeElement).toBe(activity);
		await fireEvent.keyDown(activity, { key: 'Home' });
		await Promise.resolve();
		expect(document.activeElement).toBe(overview);
		await fireEvent.keyDown(overview, { key: 'End' });
		await Promise.resolve();
		expect(document.activeElement).toBe(activity);
	});
});
