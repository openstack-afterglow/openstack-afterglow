import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import { get } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('$app/environment', () => ({ browser: true }));
vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$app/stores', async () => {
	// Hoisted mock factories run before static imports initialize; load the real store here.
	const { readable } = await import('svelte/store');
	return { page: readable({ url: new URL('http://localhost/dashboard'), data: {} }) };
});
vi.mock('$lib/api/client', () => ({ api: { get: vi.fn().mockResolvedValue([]) } }));

import { goto } from '$app/navigation';
import CmdPalette from '$lib/components/CmdPalette.svelte';
import { auth } from '$lib/stores/auth';
import { palette } from '$lib/stores/palette';
import { siteConfig, initSiteConfig } from '$lib/config/site';
import { initLocale } from '$lib/i18n/runtime.svelte';

const initialAuth = get(auth);
const initialSiteConfig = get(siteConfig);

beforeEach(() => {
	vi.clearAllMocks();
	initLocale('ko');
	palette.close();
	initSiteConfig({ services: { chat: false, waygate: false } });
});

afterEach(() => {
	cleanup();
	palette.close();
	auth.set(initialAuth);
	siteConfig.set(initialSiteConfig);
	initLocale('ko');
});

describe('command palette service visibility', () => {
	it.each([
		[false, 'chat', 'Lumen', '/dashboard/chat'],
		[true, 'chat', 'Lumen', '/admin/chat'],
		[false, 'waygate', 'Waygate', '/dashboard/network/waygate'],
		[true, 'waygate', 'Waygate', '/admin/waygate'],
	] as const)('updates %s mode %s destinations when capability changes', async (admin, service, label, href) => {
		auth.set({ ...initialAuth, isSystemAdmin: admin, roles: admin ? ['admin'] : [] });
		render(CmdPalette);
		palette.open();
		await tick();
		const search = screen.getByRole('combobox');
		await fireEvent.input(search, { target: { value: label } });
		const accessibleName = new RegExp(`^${label} `);
		expect(screen.queryByRole('option', { name: accessibleName })).toBeNull();

		initSiteConfig({ services: { [service]: true } });
		await tick();
		const destination = screen.getByRole('option', { name: accessibleName });
		initSiteConfig({ services: { [service]: false } });
		await tick();
		expect(screen.queryByRole('option', { name: accessibleName })).toBeNull();
		expect(destination.isConnected).toBe(false);

		initSiteConfig({ services: { [service]: true } });
		await tick();
		await fireEvent.click(screen.getByRole('option', { name: accessibleName }));
		expect(goto).toHaveBeenCalledWith(href);
		expect(get(palette)).toBe(false);
	});
});
