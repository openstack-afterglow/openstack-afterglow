import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
import { theme } from '$lib/stores/theme';
import { t } from '$lib/i18n/ns/shell';
import english from '$lib/i18n/messages/en/shell.json';
import { getLocale } from '$lib/i18n/runtime.svelte';
import ThemeSelect from '../ThemeSelect.svelte';
vi.mock('$app/environment', () => ({ browser: true }));

afterEach(() => { theme.set('system'); });

describe('explicit theme choice', () => {
	it('selects a specific mode without cycling and restores trigger focus', async () => {
		theme.set('light');
		const { container } = render(ThemeSelect, { id: 'theme-trigger' });
		const trigger = container.querySelector('summary')!;
		await fireEvent.click(trigger);
		await fireEvent.click(screen.getByRole('menuitemradio', { name: t('theme.dark') }));
		expect(get(theme)).toBe('dark');
		expect(localStorage.getItem('afterglow_theme')).toBe('dark');
		expect(container.querySelector('details')!.open).toBe(false);
		expect(document.activeElement).toBe(trigger);
	});

	it('opens by keyboard, traverses all choices, and Escape leaves the preference unchanged', async () => {
		theme.set('light');
		const { container } = render(ThemeSelect, { id: 'theme-keyboard' });
		const trigger = container.querySelector('summary')!;
		await fireEvent.keyDown(trigger, { key: 'ArrowDown' });
		await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('menuitemradio', { name: t('theme.light') })));
		await fireEvent.keyDown(document.activeElement!, { key: 'End' });
		await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('menuitemradio', { name: t('theme.system') })));
		await fireEvent.keyDown(document.activeElement!, { key: 'Escape' });
		expect(get(theme)).toBe('light');
		expect(container.querySelector('details')!.open).toBe(false);
		expect(document.activeElement).toBe(trigger);
	});
});

it('honors an explicit document locale without changing the interface preference', async () => {
	theme.set('system');
	const originalLocale = getLocale();
	const { container } = render(ThemeSelect, { id: 'document-theme', locale: 'en' });
	await fireEvent.click(container.querySelector('summary')!);
	expect(screen.getByRole('menuitemradio', { name: english['theme.light'] })).toBeTruthy();
	expect(screen.getByRole('menuitemradio', { name: english['theme.dark'] })).toBeTruthy();
	expect(getLocale()).toBe(originalLocale);
});
