import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { writable, type Writable } from 'svelte/store';
import type { Cluster } from '$lib/types/cluster';
import { t as tc } from '$lib/i18n/ns/common';

const { mockGet, mockPrefetch } = vi.hoisted(() => ({ mockGet: vi.fn(), mockPrefetch: vi.fn() }));

vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$lib/api/client', () => ({
	api: { get: mockGet, prefetch: mockPrefetch, post: vi.fn(), delete: vi.fn() },
	ApiError: class ApiError extends Error { status = 500; },
}));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'token', projectId: 'project' }), canWrite: writable(true) }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
  createAutoRefresh: (refresh: (force: boolean) => Promise<void>) => ({ active: false, intervalSeconds: 30, intervalOptions: [10, 15, 30, 60], refresh: () => refresh(true) }),
}));

import { canWrite } from '$lib/stores/auth';
import Page from '../+page.svelte';

describe('cluster create catalog intent', () => {
	beforeEach(() => { vi.clearAllMocks(); (canWrite as Writable<boolean>).set(true); });
	it('keeps templates deferred until intent and uses the same path on click', async () => {
		mockGet.mockImplementation((path: string) => {
			if (path === '/api/v1/clusters') return Promise.resolve([]);
			if (path === '/api/v1/clusters/templates') return Promise.resolve([]);
			throw new Error(`unexpected GET ${path}`);
		});
		mockPrefetch.mockResolvedValue(undefined);

		render(Page);
		const create = await screen.findByRole('button', { name: '+ 클러스터 생성' });
		expect(mockGet).toHaveBeenCalledOnce();

		await fireEvent.pointerEnter(create);
		expect(mockPrefetch).toHaveBeenCalledWith('/api/v1/clusters/templates', 'token', 'project');
		expect(mockGet).toHaveBeenCalledOnce();

		await fireEvent.click(create);
		await vi.waitFor(() => expect(mockGet).toHaveBeenCalledTimes(2));
		expect(mockGet.mock.calls[1][0]).toBe('/api/v1/clusters/templates');
	});
	it('denies ordinary cluster writes with canWrite=false rather than substituting a service role', async () => {
		(canWrite as Writable<boolean>).set(false);
		mockGet.mockResolvedValue([]);
		render(Page);
		const create = await screen.findByRole('button', { name: '+ 클러스터 생성' }) as HTMLButtonElement;
		expect(create.disabled).toBe(true);
		await fireEvent.pointerEnter(create);
		await fireEvent.click(create);
		expect(mockPrefetch).not.toHaveBeenCalled();
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(mockGet.mock.calls.map(call => call[0])).toEqual(['/api/v1/clusters']);
	});

  it('retains regex and descending column order when the legacy inventory refreshes', async () => {
    const cluster: Cluster = {
      id: 'cluster-a', name: 'alpha', status: 'CREATE_COMPLETE', status_reason: null,
      cluster_template_id: null, master_count: 1, node_count: 2, api_address: null,
      coe_version: null, keypair: null, create_timeout: null,
      created_at: '2026-01-01T00:00:00Z', updated_at: null, stack_id: null,
    };
    let rows = [cluster, { ...cluster, id: 'cluster-z', name: 'zeta' }];
    mockGet.mockResolvedValue(rows);
    const rendered = render(Page);
    await screen.findByRole('button', { name: 'alpha' });
    const search = rendered.container.querySelector('#legacy-cluster-search') as HTMLInputElement;
    await fireEvent.input(search, { target: { value: '^(alpha|zeta)$' } });
    const headings = within(rendered.container.querySelector('thead')!);
    for (const direction of ['none', 'ascending'] as const) {
      await fireEvent.click(headings.getByRole('button', { name: tc('table.sortColumn', { column: '이름', direction: tc(`table.${direction}`) }) }));
    }
    rows = [...rows, { ...cluster, id: 'cluster-b', name: 'beta' }];
    mockGet.mockResolvedValue(rows);
    await fireEvent.click(screen.getByRole('button', { name: tc('autoRefresh.refreshNow') }));
    await vi.waitFor(() => expect(mockGet).toHaveBeenLastCalledWith('/api/v1/clusters', 'token', 'project', { refresh: true }));
    await vi.waitFor(() => expect([...rendered.container.querySelectorAll('tbody tr')].map(row => row.querySelector('td:nth-child(2) button')?.textContent)).toEqual(['zeta', 'alpha']));
    expect(search.value).toBe('^(alpha|zeta)$');
    expect(rendered.container.querySelector('th[aria-sort="descending"]')).toBeTruthy();
    await fireEvent.input(search, { target: { value: '[' } });
    expect(screen.getByText(tc('table.regexError'))).toBeTruthy();
    expect(rendered.container.querySelectorAll('tbody tr')).toHaveLength(0);
    expect(headings.getByRole('button', { name: tc('table.filterColumn', { column: '이름' }) })).toBeTruthy();
  });
});
