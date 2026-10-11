import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { writable, type Writable } from 'svelte/store';
import type { AdminNetworkDetail } from '$lib/types/networks';

const mocks = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: { get: mocks.get }, ApiError: class extends Error {} }));
vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token-a', userId: 'user-a', projectId: 'scope-a' }),
	isMockAuthActive: () => false,
	getMockupProfile: () => null,
}));
vi.mock('$app/stores', () => ({ page: writable({ params: { id: 'net-a' }, url: new URL('https://example.test/admin/networks/net-a') }) }));

import { auth } from '$lib/stores/auth';
import { projectNames } from '$lib/stores/projectNames';
import { tick } from 'svelte';
import { page } from '$app/stores';
import Page from '../+page.svelte';
const routePage = page as unknown as Writable<{ params: { id: string }; url: URL }>;

function network(id: string): AdminNetworkDetail {
	return { id, name: `name-${id}`, status: 'ACTIVE', subnets: [], subnet_details: [], routers: [], is_external: false, is_shared: false, project_id: 'owner-full-id', provider_network_type: null, provider_segmentation_id: null, provider_physical_network: null };
}
function deferred<T>() {
	let resolve!: (value: T) => void;
	const promise = new Promise<T>((done) => { resolve = done; });
	return { promise, resolve };
}
function target(id: string) {
	routePage.set({ params: { id }, url: new URL(`https://example.test/admin/networks/${id}`) });
}

beforeEach(() => {
	cleanup();
	projectNames.invalidate();
	mocks.get.mockReset();
	auth.set({ token: 'token-a', userId: 'user-a', projectId: 'scope-a' } as never);
	target('net-a');
});

describe('admin network detail request scopes', () => {
	it('keeps the exact owner ID when its directory fails', async () => {
		mocks.get.mockImplementation((path: string) => path.endsWith('/names') ? Promise.reject(new Error('directory unavailable')) : Promise.resolve(network('net-a')));
		render(Page);
		expect(await screen.findByText('owner-full-id')).toBeTruthy();
		expect(await screen.findByRole('status')).toBeTruthy();
		expect(screen.getByText('name-net-a')).toBeTruthy();
	});

	it('does not publish an old target after navigation', async () => {
		const oldNetwork = deferred<AdminNetworkDetail>();
		mocks.get.mockImplementation((path: string) => {
			if (path.endsWith('/names')) return Promise.resolve([{ id: 'owner-full-id', name: 'current-owner' }]);
			return path.endsWith('/net-a') ? oldNetwork.promise : Promise.resolve(network('net-b'));
		});
		render(Page);
		await tick();
		target('net-b');
		expect(await screen.findByText('name-net-b')).toBeTruthy();
		oldNetwork.resolve(network('net-a'));
		await oldNetwork.promise;
		await waitFor(() => {
			expect(screen.queryByText('name-net-a')).toBeNull();
			expect(screen.getByText('current-owner')).toBeTruthy();
		});
	});

	it('fences old authentication responses and offers a real retry after failure', async () => {
		const oldNetwork = deferred<AdminNetworkDetail>();
		const oldNames = deferred<{ id: string; name: string }[]>();
		mocks.get.mockImplementation((path: string, token: string) => {
			if (path.endsWith('/names')) return token === 'token-a' ? oldNames.promise : Promise.resolve([{ id: 'owner-full-id', name: 'current-owner' }]);
			if (token === 'token-a') return oldNetwork.promise;
			return Promise.reject(new Error('inventory unavailable'));
		});
		render(Page);
		await tick();
		auth.set({ token: 'token-b', userId: 'user-b', projectId: 'scope-b' } as never);
		const alert = await screen.findByRole('alert');
		oldNetwork.resolve(network('net-a'));
		oldNames.resolve([{ id: 'owner-full-id', name: 'obsolete-owner' }]);
		await oldNetwork.promise;
		await oldNames.promise;
		await waitFor(() => expect(screen.queryByText('name-net-a')).toBeNull());
		mocks.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/names') ? [] : network('net-a')));
		await fireEvent.click(alert.querySelector('button')!);
		expect(await screen.findByText('name-net-a')).toBeTruthy();
		expect(screen.getByText('current-owner')).toBeTruthy();
		expect(screen.queryByText('obsolete-owner')).toBeNull();
	});
});
