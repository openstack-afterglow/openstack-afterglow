import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import { get, type Writable } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('$app/environment', () => ({ browser: true }));
vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$app/stores', async () => {
	// Hoisted mock factories run before static imports initialize; load the real store here.
	const { writable } = await import('svelte/store');
	return { page: writable({ url: new URL('http://localhost/dashboard'), data: {} }) };
});
vi.mock('$lib/api/client', () => ({ api: { get: vi.fn().mockResolvedValue([]) } }));

import { goto } from '$app/navigation';
import { page } from '$app/stores';
import CmdPalette from '$lib/components/CmdPalette.svelte';
import { auth } from '$lib/stores/auth';
import { palette } from '$lib/stores/palette';
import { siteConfig, initSiteConfig } from '$lib/config/site';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { allNavItems } from '$lib/config/nav';
import { DEFAULT_BETA_FEATURES } from '$lib/stores/betaFeatures';

const initialAuth = get(auth);
const initialSiteConfig = get(siteConfig);

const route = page as unknown as Writable<{ url: URL; data: Record<string, unknown> }>;
beforeEach(() => {
	vi.clearAllMocks();
	initLocale('ko');
	palette.close();
	initSiteConfig({ services: { chat: false, waygate: false } });
	route.set({ url: new URL('http://localhost/dashboard'), data: {} });
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
		[false, 'chat', '/dashboard/chat'],
		[true, 'chat', '/admin/chat'],
		[false, 'waygate', '/dashboard/network/waygate'],
		[true, 'waygate', '/admin/waygate'],
	] as const)('updates %s mode %s destinations when capability changes', async (admin, service, href) => {
		auth.set({ ...initialAuth, isSystemAdmin: admin, roles: admin ? ['admin'] : [] });
		route.set({ url: new URL(admin ? 'http://localhost/admin' : 'http://localhost/dashboard'), data: {} });
		render(CmdPalette);
		palette.open();
		await tick();
		const search = screen.getByRole('combobox');
		const label = allNavItems(admin, DEFAULT_BETA_FEATURES).find(item => item.href === href)!.label;
		await fireEvent.input(search, { target: { value: label } });
		const resultId = `command-palette-result-${`route:${href}`.replace(/[^a-zA-Z0-9_-]/g, '-')}`;
		expect(document.getElementById(resultId)).toBeNull();

		initSiteConfig({ services: { [service]: true } });
		await tick();
		const destination = document.getElementById(resultId)!;
		expect(destination.getAttribute('role')).toBe('option');
		initSiteConfig({ services: { [service]: false } });
		await tick();
		expect(document.getElementById(resultId)).toBeNull();
		expect(destination.isConnected).toBe(false);

		initSiteConfig({ services: { [service]: true } });
		await tick();
		await fireEvent.click(document.getElementById(resultId)!);
		expect(goto).toHaveBeenCalledWith(href);
		expect(get(palette)).toBe(false);
	});
});
