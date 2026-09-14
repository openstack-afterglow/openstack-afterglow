import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import type { Writable } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('$app/environment', () => ({ browser: true }));
vi.mock('$app/stores', async () => {
	const { writable } = await import('svelte/store');
	return { page: writable({ url: new URL('http://localhost/dashboard'), data: {} }) };
});

import { page } from '$app/stores';
import { initSiteConfig, siteConfig } from '$lib/config/site';
import Sidebar from '../Sidebar.svelte';

// The SvelteKit readable is replaced with a writable store by the mock above.
const mockPage = page as unknown as Writable<{ url: URL; data: Record<string, never> }>;

function navigate(pathname: string) {
	mockPage.set({
		url: new URL(pathname, 'http://localhost'), data: {}
	});
	return tick();
}

beforeEach(async () => {
	await navigate('/dashboard');
});

afterEach(() => {
	cleanup();
	siteConfig.update((current) => ({ ...current, services: { ...current.services, k3s: false } }));
});

describe('Sidebar navigation ownership', () => {
	it('opens topology directly without expanding or activating the network group', async () => {
		await navigate('/dashboard/network/topology');
		render(Sidebar);

		expect(screen.getByRole('link', { name: '토폴로지' }).getAttribute('aria-current')).toBe('page');
		expect(screen.queryByRole('link', { name: '네트워크' })).toBeNull();
		expect(screen.getByRole('button', { name: /네트워크/ }).classList.contains('text-ink-0')).toBe(false);
	});

	it('preserves manual network expansion and collapse when navigating to topology', async () => {
		render(Sidebar);
		const network = screen.getByRole('button', { name: /네트워크/ });
		await fireEvent.click(network);
		await navigate('/dashboard/network/topology');
		expect(screen.getByRole('link', { name: '네트워크' })).toBeTruthy();

		await fireEvent.click(network);
		await navigate('/dashboard');
		await navigate('/dashboard/network/topology');
		expect(screen.queryByRole('link', { name: '네트워크' })).toBeNull();
	});

	it('automatically expands the network group for a nested resource route', async () => {
		render(Sidebar);
		await navigate('/dashboard/network/topology');
		await navigate('/dashboard/network/networks/network-1');

		expect(screen.getByRole('link', { name: '네트워크' }).getAttribute('aria-current')).toBe('page');
		expect(screen.getByRole('link', { name: '토폴로지' }).getAttribute('aria-current')).toBeNull();
	});

	it('expands the container group for its Drover entry outside the container URL prefix', async () => {
		initSiteConfig({ services: { k3s: true } });
		await navigate('/dashboard/drover/cluster-1');
		render(Sidebar);

		expect(screen.getByRole('link', { name: 'Drover' }).getAttribute('aria-current')).toBe('page');
	});
});
