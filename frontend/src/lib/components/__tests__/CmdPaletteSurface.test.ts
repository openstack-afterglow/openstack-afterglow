import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { get, type Writable } from 'svelte/store';
import { tick } from 'svelte';

vi.mock('$app/environment', () => ({ browser: true }));
vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$app/stores', async () => {
	// vi.mock is hoisted before static imports initialize; resolve the real store inside its factory.
	const { writable } = await import('svelte/store');
	return { page: writable({ url: new URL('http://localhost/dashboard'), data: {} }) };
});
vi.mock('$lib/api/client', () => ({ api: { get: vi.fn().mockResolvedValue([]) } }));

import { page } from '$app/stores';
import { auth } from '$lib/stores/auth';
import { palette } from '$lib/stores/palette';
import { initLocale } from '$lib/i18n/runtime.svelte';
import CmdPalette from '../CmdPalette.svelte';

const route = page as unknown as Writable<{ url: URL; data: Record<string, unknown> }>;
const originalAuth = get(auth);

beforeEach(() => {
	initLocale('ko');
	auth.set({ ...originalAuth, token: 'verified', isSystemAdmin: true });
	route.set({ url: new URL('http://localhost/dashboard'), data: {} });
	palette.close();
});
afterEach(() => { cleanup(); palette.close(); auth.set(originalAuth); });

it('does not offer global administrator destinations until the administrator surface is entered', async () => {
	render(CmdPalette);
	palette.open();
	const input = await screen.findByRole('combobox');
	await fireEvent.input(input, { target: { value: '시스템 관리자' } });
	await tick();
	expect(screen.queryByRole('option', { name: /시스템 관리자/ })).toBeNull();
	route.set({ url: new URL('http://localhost/admin'), data: {} });
	await waitFor(() => expect(screen.getByRole('option', { name: /시스템 관리자/ })).toBeTruthy());
});
