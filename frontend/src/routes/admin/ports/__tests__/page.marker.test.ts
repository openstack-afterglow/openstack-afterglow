import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import { writable } from 'svelte/store';

const { mockGet, mockPrefetch } = vi.hoisted(() => ({ mockGet: vi.fn(), mockPrefetch: vi.fn() }));

vi.mock('$lib/api/client', () => ({
	api: { get: mockGet, prefetch: mockPrefetch, put: vi.fn(), post: vi.fn(), delete: vi.fn() },
	ApiError: class ApiError extends Error { status = 500; },
}));
vi.mock('$lib/tutorial/engine', async () => {
	const actual = await vi.importActual<Record<string, unknown>>('$lib/tutorial/engine');
	return { ...actual, isTourActive: () => false };
});
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'token', projectId: 'project' }) }));
vi.mock('$lib/stores/projectNames', async () => {
	const names = writable(new Map<string, string>());
	return { projectNames: Object.assign(names, { load: vi.fn().mockResolvedValue(new Map<string, string>()) }) };
});
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({ active: false, intervalSeconds: 30, intervalOptions: [15, 30, 60] }),
}));
vi.mock('$lib/components/admin/ports/PortsTable.svelte', async () => ({
	default: (await import('./_PortsTableProbe.svelte')).default,
}));

import Page from '../+page.svelte';

describe('admin port marker generation', () => {
	beforeEach(() => {
		vi.useFakeTimers();
		vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
		mockGet.mockReset();
		mockPrefetch.mockReset().mockResolvedValue(undefined);
	});

	afterEach(() => {
		vi.useRealTimers();
		vi.unstubAllGlobals();
	});

	it('keeps the latest page-size result and schedules only its marker', async () => {
		const oldRequest = Promise.withResolvers<{ items: Array<Record<string, unknown>>; next_marker: string }>();
		const newRequest = Promise.withResolvers<{ items: Array<Record<string, unknown>>; next_marker: string }>();
		const pending = [oldRequest, newRequest];
		mockGet.mockImplementation((path: string) => path.startsWith('/api/v1/admin/all-ports')
			? pending.shift()!.promise
			: Promise.resolve([]));
		render(Page);
		await vi.waitFor(() => expect(mockGet.mock.calls.some((call) => String(call[0]).includes('limit=20'))).toBe(true));
		await fireEvent.click(screen.getByRole('button', { name: '10' }));
		await vi.waitFor(() => expect(mockGet.mock.calls.some((call) => String(call[0]).includes('limit=10'))).toBe(true));

		newRequest.resolve({
			items: [{ id: 'new-port', name: 'Newest port', fixed_ips: [], device_owner: '', project_id: '' }],
			next_marker: 'new-marker',
		});
		expect(await screen.findByText('Newest port')).toBeTruthy();
		oldRequest.resolve({
			items: [{ id: 'old-port', name: 'Stale port', fixed_ips: [], device_owner: '', project_id: '' }],
			next_marker: 'old-marker',
		});
		await vi.advanceTimersByTimeAsync(200);

		expect(screen.queryByText('Stale port')).toBeNull();
		expect(mockPrefetch).toHaveBeenCalledOnce();
		expect(mockPrefetch.mock.calls[0][0]).toBe('/api/v1/admin/all-ports?limit=10&marker=new-marker');
	});
	it('does not advance or rewind markers again while the next page is pending', async () => {
		const next = Promise.withResolvers<{ items: Array<Record<string, unknown>>; next_marker: string | null }>();
		mockGet.mockImplementation((path: string) => {
			if (!path.startsWith('/api/v1/admin/all-ports')) return Promise.resolve([]);
			if (path.includes('marker=next-marker')) return next.promise;
			return Promise.resolve({ items: [{ id: 'first', name: 'First port' }], next_marker: 'next-marker' });
		});
		render(Page);
		await screen.findByText('First port');
		await fireEvent.click(screen.getByRole('button', { name: 'Next ports' }));
		expect(screen.getByRole('button', { name: 'Next ports' })).toHaveProperty('disabled', true);
		expect(screen.getByRole('button', { name: 'Previous ports' })).toHaveProperty('disabled', true);
		await fireEvent.click(screen.getByRole('button', { name: 'Next ports' }));
		await fireEvent.click(screen.getByRole('button', { name: 'Previous ports' }));
		expect(mockGet.mock.calls.filter(([path]) => String(path).startsWith('/api/v1/admin/all-ports'))).toHaveLength(2);
		expect(screen.getByTestId('marker-depth').textContent).toBe('1');
		next.resolve({ items: [{ id: 'second', name: 'Second port' }], next_marker: null });
		await screen.findByText('Second port');
		await fireEvent.click(screen.getByRole('button', { name: 'Previous ports' }));
		await screen.findByText('First port');
		expect(screen.getByTestId('marker-depth').textContent).toBe('0');
	});
});
