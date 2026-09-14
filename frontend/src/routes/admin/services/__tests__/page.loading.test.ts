import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import { writable } from 'svelte/store';

const { mockGet, autoRefreshCallback } = vi.hoisted(() => ({
	mockGet: vi.fn(),
	autoRefreshCallback: { current: null as (() => Promise<void>) | null },
}));

vi.mock('$lib/api/client', () => ({ api: { get: mockGet } }));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token', userId: 'user-a', projectId: 'project-a' }),
}));
vi.mock('$lib/config/site', () => ({
	siteConfig: writable({
		services: { magnum: true, manila: true, zun: true },
	}),
}));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: (callback: () => Promise<void>) => {
		autoRefreshCallback.current = callback;
		return {
			active: false,
			intervalSeconds: 15,
			intervalOptions: [10, 15, 30, 60],
		};
	},
}));

import Page from '../+page.svelte';
import { auth } from '$lib/stores/auth';
import type { Service } from '$lib/types/adminServices';

beforeEach(() => {
	mockGet.mockReset();
	auth.update((current) => ({ ...current, token: 'token', userId: 'user-a', projectId: 'project-a' }));
});
afterEach(cleanup);

const services: Service[] = [
	{ id: 'a', binary: 'nova-compute', host: 'host10', status: 'enabled', state: 'down', zone: 'nova', updated_at: null, disabled_reason: null },
	{ id: 'b', binary: 'nova-compute', host: 'host2', status: 'disabled', state: 'up', zone: 'nova', updated_at: null, disabled_reason: 'maintenance' },
	{ id: 'c', binary: 'nova-scheduler', host: 'host1', status: 'enabled', state: 'up', zone: 'nova', updated_at: null, disabled_reason: null },
];

function rowHosts(): string[] {
	return screen.getAllByRole('row').slice(1).map(row => row.querySelectorAll('td')[1].textContent?.trim() ?? '');
}

describe('admin services loading graph', () => {
	it('loads only the active category and starts an idle tab on intent', async () => {
		const compute = Promise.withResolvers<Record<string, unknown>>();
		const network = Promise.withResolvers<Record<string, unknown>>();
		let networkCalls = 0;
		mockGet.mockImplementation((path: string) => {
			if (path.endsWith('category=compute')) return compute.promise;
			if (path.endsWith('category=network')) {
				networkCalls += 1;
				return networkCalls === 1 ? network.promise : Promise.resolve({ network: [] });
			}
			throw new Error(`unexpected GET ${path}`);
		});

		render(Page);
		await vi.waitFor(() => expect(mockGet).toHaveBeenCalledOnce());
		expect(mockGet.mock.calls[0][0]).toBe('/api/v1/admin/services?category=compute');

		await fireEvent.pointerEnter(screen.getByRole('button', { name: /Network/ }));
		expect(mockGet).toHaveBeenCalledTimes(2);
		expect(mockGet.mock.calls[1][0]).toBe('/api/v1/admin/services?category=network');

		compute.resolve({ compute: [] });
		network.resolve({ network: [] });
		await tick();

		await fireEvent.click(screen.getByRole('button', { name: /Network/ }));
		expect(mockGet).toHaveBeenCalledTimes(2);

		await autoRefreshCallback.current?.();
		expect(mockGet).toHaveBeenCalledTimes(3);
		expect(mockGet.mock.calls[2][0]).toBe('/api/v1/admin/services?category=network');
		expect(mockGet.mock.calls[2][3]).toEqual({ refresh: true });

		await fireEvent.click(screen.getByRole('button', { name: '새로고침' }));
		await vi.waitFor(() => expect(mockGet).toHaveBeenCalledTimes(4));
		expect(mockGet.mock.calls[3][0]).toBe('/api/v1/admin/services?category=network');
	});

	it('keeps each tab\'s filters and sorting when switching between service categories', async () => {
		mockGet.mockImplementation((path: string) => Promise.resolve(
			path.endsWith('category=compute') ? { compute: services } : { block_storage: services }
		));
		render(Page);
		await screen.findByRole('cell', { name: 'host10' });
		await fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'value:enabled' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Host 정렬' }));
		expect(rowHosts()).toEqual(['host1', 'host10']);

		await fireEvent.click(screen.getByRole('button', { name: /Block Storage/ }));
		await screen.findByRole('cell', { name: 'host2' });
		await fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'value:disabled' } });
		expect(rowHosts()).toEqual(['host2']);
		await fireEvent.click(screen.getByRole('button', { name: /Compute/ }));
		expect(rowHosts()).toEqual(['host1', 'host10']);
		await fireEvent.click(screen.getByRole('button', { name: /Block Storage/ }));
		expect(rowHosts()).toEqual(['host2']);
	});

	it('keeps filtered rows interactive during refresh and applies fresh data without losing the selection', async () => {
		const refreshed = Promise.withResolvers<Record<string, unknown>>();
		mockGet.mockResolvedValueOnce({ compute: services }).mockReturnValueOnce(refreshed.promise);
		render(Page);
		await screen.findByRole('cell', { name: 'host10' });
		await fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'value:enabled' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Host 정렬' }));
		const refresh = autoRefreshCallback.current?.();
		await tick();
		expect(rowHosts()).toEqual(['host1', 'host10']);
		await fireEvent.click(screen.getByRole('button', { name: 'Host 정렬' }));
		expect(rowHosts()).toEqual(['host10', 'host1']);

		refreshed.resolve({ compute: services.map(service => ({ ...service, status: 'disabled' })) });
		await refresh;
		await vi.waitFor(() => expect(screen.queryByRole('table')).toBeNull());
		expect(screen.getByRole('option', { name: /^enabled/, selected: true })).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: '필터·정렬 초기화' }));
		expect(rowHosts()).toEqual(['host10', 'host2', 'host1']);
	});

	it('retains same-scope rows across in-flight token rotation without leaking rows to another project', async () => {
		const projectARefresh = Promise.withResolvers<Record<string, unknown>>();
		const rotated = Promise.withResolvers<Record<string, unknown>>();
		const projectB = Promise.withResolvers<Record<string, unknown>>();
		mockGet.mockResolvedValueOnce({ compute: services }).mockImplementation((_path: string, requestToken: string, requestProjectId: string) => {
			if (requestProjectId === 'project-b') return projectB.promise;
			if (requestToken === 'rotated-token') return rotated.promise;
			return projectARefresh.promise;
		});

		render(Page);
		await screen.findByRole('cell', { name: 'host10' });
		const refresh = autoRefreshCallback.current?.();
		await tick();
		expect((screen.getByRole('button', { name: '필터·정렬 초기화' }) as HTMLButtonElement).disabled).toBe(false);

		auth.update((current) => ({ ...current, token: 'rotated-token' }));
		await tick();
		expect(screen.getByRole('cell', { name: 'host10' })).toBeTruthy();
		rotated.resolve({ compute: [{ ...services[0], host: 'host-rotated' }] });
		await screen.findByRole('cell', { name: 'host-rotated' });
		projectARefresh.resolve({ compute: [{ ...services[0], host: 'stale-host' }] });
		await refresh;
		expect(screen.queryByRole('cell', { name: 'stale-host' })).toBeNull();

		auth.update((current) => ({ ...current, token: 'project-b-token', projectId: 'project-b' }));
		await tick();
		expect(screen.queryByRole('cell', { name: 'host-rotated' })).toBeNull();
		projectB.resolve({ compute: [{ ...services[0], host: 'host-project-b' }] });
		await screen.findByRole('cell', { name: 'host-project-b' });
	});
});
