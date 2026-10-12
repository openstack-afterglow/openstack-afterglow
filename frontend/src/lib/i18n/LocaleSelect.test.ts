import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import LocaleSelect from './LocaleSelect.svelte';
import { getLocale, initLocale } from './runtime.svelte';

beforeEach(() => {
	initLocale('ko');
	document.documentElement.lang = 'ko';
	document.cookie = 'afterglow_locale=; path=/; max-age=0';
	sessionStorage.removeItem('afterglow.i18n.refocus');
});
afterEach(() => {
	cleanup();
	initLocale('ko');
	document.documentElement.lang = 'ko';
	document.cookie = 'afterglow_locale=; path=/; max-age=0';
	sessionStorage.removeItem('afterglow.i18n.refocus');
});

async function openMenu() {
	const { container } = render(LocaleSelect, { id: 'locale-test' });
	const trigger = container.querySelector('summary')!;
	trigger.focus();
	await fireEvent.keyDown(trigger, { key: 'ArrowDown' });
	await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('button', { name: '한국어' })));
	return { trigger, details: container.querySelector('details')! };
}

describe('themed language disclosure', () => {
	it('changes the app language and cookie while restoring trigger focus', async () => {
		const { trigger, details } = await openMenu();
		await fireEvent.keyDown(document.activeElement!, { key: 'ArrowDown' });
		const english = screen.getByRole('button', { name: 'English' });
		expect(document.activeElement).toBe(english);
		await fireEvent.click(english);
		await waitFor(() => expect(document.activeElement).toBe(trigger));
		expect(getLocale()).toBe('en');
		expect(document.documentElement.lang).toBe('en');
		expect(document.cookie).toContain('afterglow_locale=en');
		expect(details.open).toBe(false);
	});

	it('dismisses with Escape and returns focus from the last choice', async () => {
		const { trigger, details } = await openMenu();
		await fireEvent.keyDown(document.activeElement!, { key: 'End' });
		expect(document.activeElement).toBe(screen.getByRole('button', { name: '简体中文' }));
		await fireEvent.keyDown(document.activeElement!, { key: 'Escape' });
		expect(details.open).toBe(false);
		expect(document.activeElement).toBe(trigger);
		expect(getLocale()).toBe('ko');
	});

	it('dismisses immediately after mouse opening, before the native toggle notification', async () => {
		const { container } = render(LocaleSelect, { id: 'locale-immediate' });
		const trigger = container.querySelector('summary')!;
		const details = container.querySelector('details')!;
		trigger.focus();
		trigger.click();
		expect(details.open).toBe(true);
		await fireEvent.keyDown(trigger, { key: 'Escape' });
		expect(details.open).toBe(false);
		expect(document.activeElement).toBe(trigger);
	});

	it('wraps arrow navigation and keeps Home and End inside the choices', async () => {
		await openMenu();
		for (const [key, name] of [['End', '简体中文'], ['ArrowDown', '한국어'], ['ArrowUp', '简体中文'], ['Home', '한국어']] as const) {
			await fireEvent.keyDown(document.activeElement!, { key });
			expect(document.activeElement).toBe(screen.getByRole('button', { name }));
		}
		expect(getLocale()).toBe('ko');
	});

	it('allows focus within the menu and dismisses outside without stealing focus', async () => {
		const { trigger, details } = await openMenu();
		const english = screen.getByRole('button', { name: 'English' });
		english.focus();
		expect(details.open).toBe(true);
		const outside = document.createElement('button');
		document.body.append(outside);
		try {
			outside.focus();
			await waitFor(() => expect(details.open).toBe(false));
			expect(document.activeElement).toBe(outside);
			trigger.focus();
			await fireEvent.keyDown(trigger, { key: 'ArrowDown' });
			await fireEvent.click(outside);
			expect(details.open).toBe(false);
			expect(document.activeElement).not.toBe(trigger);
		} finally {
			outside.remove();
		}
	});
});
