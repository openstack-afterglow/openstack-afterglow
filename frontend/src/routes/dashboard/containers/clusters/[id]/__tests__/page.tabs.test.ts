import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import type { Cluster, StackResource } from '$lib/types/cluster';
import { t as tc } from '$lib/i18n/ns/common';

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));

vi.mock('$app/stores', () => ({
	page: writable({ params: { id: 'cluster-1' }, data: {} }),
}));
vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token', projectId: 'project' }),
}));
vi.mock('$lib/api/client', () => ({
	api: { get: mockGet, delete: vi.fn() },
	ApiError: class ApiError extends Error { status = 500; },
}));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({
		active: false,
		intervalSeconds: 10,
		intervalOptions: [10, 15, 30, 60],
	}),
}));

import Page from '../+page.svelte';

const cluster: Cluster = {
	id: 'cluster-1',
	name: 'cluster',
	status: 'CREATE_COMPLETE',
	status_reason: null,
	cluster_template_id: 'template-1',
	master_count: 1,
	node_count: 2,
	api_address: null,
	coe_version: null,
	keypair: null,
	create_timeout: null,
	created_at: '2026-01-01T00:00:00Z',
	updated_at: null,
	stack_id: 'stack-1',
};

describe('K3s cluster detail tabs', () => {
	it('defers hidden tabs and remembers a successfully loaded empty tab', async () => {
		const resources = Promise.withResolvers<[]>();
		mockGet.mockImplementation((path: string) => {
			if (path === '/api/v1/clusters/cluster-1') return Promise.resolve(cluster);
			if (path.endsWith('/stack/resources')) return resources.promise;
			throw new Error(`unexpected GET ${path}`);
		});

		render(Page);
		const resourcesTab = await screen.findByRole('tab', { name: '스택 리소스' });
		expect(mockGet).toHaveBeenCalledOnce();

		await fireEvent.focus(resourcesTab);
		await fireEvent.click(resourcesTab);
		expect(mockGet).toHaveBeenCalledTimes(2);
		resources.resolve([]);
		await vi.waitFor(() => expect(screen.getByText('스택 리소스 정보를 불러올 수 없습니다')).toBeTruthy());

		await fireEvent.blur(resourcesTab);
		await fireEvent.focus(resourcesTab);
		expect(mockGet).toHaveBeenCalledTimes(2);
	});

  it('retains resource regex, filters and sort across refresh, tab unmounts and unavailable values', async () => {
    const resource = (name: string, status = 'CREATE_COMPLETE'): StackResource => ({
      resource_name: name, resource_status: status, resource_type: 'OS::Nova::Server',
      physical_resource_id: `physical-${name}`, resource_status_reason: null, created_at: '2026-01-01T00:00:00Z',
    });
    let rows = [resource('alpha'), resource('zeta'), resource('failed', 'CREATE_FAILED')];
    mockGet.mockImplementation((path: string) => {
      if (path === '/api/v1/clusters/cluster-1') return Promise.resolve(cluster);
      if (path.endsWith('/stack/resources')) return Promise.resolve(rows);
      throw new Error(`unexpected GET ${path}`);
    });
    const rendered = render(Page);
    await fireEvent.click(await screen.findByRole('tab', { name: '스택 리소스' }));
    await screen.findByText('alpha');
    const search = rendered.container.querySelector('#legacy-cluster-resources-search') as HTMLInputElement;
    await fireEvent.input(search, { target: { value: '^(alpha|zeta|failed)$' } });
    let headings = within(rendered.container.querySelector('thead')!);
    await fireEvent.click(headings.getByRole('button', { name: tc('table.filterColumn', { column: '상태' }) }));
    const menu = screen.getByRole('dialog', { name: tc('table.filterColumn', { column: '상태' }) });
    await fireEvent.click(within(menu).getByLabelText('CREATE_FAILED'));
    await fireEvent.keyDown(menu, { key: 'Escape' });
    for (const direction of ['none', 'ascending'] as const) {
      await fireEvent.click(headings.getByRole('button', { name: tc('table.sortColumn', { column: '리소스 이름', direction: tc(`table.${direction}`) }) }));
    }
    rows = [resource('alpha'), resource('zeta'), resource('beta')];
    await fireEvent.click(screen.getByRole('button', { name: '새로고침' }));
    await vi.waitFor(() => expect([...rendered.container.querySelectorAll('tbody tr')].map(row => row.firstElementChild?.textContent)).toEqual(['zeta', 'alpha']));
    expect(search.value).toBe('^(alpha|zeta|failed)$');

    await fireEvent.click(screen.getByRole('tab', { name: '상세' }));
    await fireEvent.click(screen.getByRole('tab', { name: '스택 리소스' }));
    expect((rendered.container.querySelector('#legacy-cluster-resources-search') as HTMLInputElement).value).toBe('^(alpha|zeta|failed)$');
    expect(rendered.container.querySelector('th[aria-sort="descending"]')).toBeTruthy();
    headings = within(rendered.container.querySelector('thead')!);
    rows = [resource('alpha', 'CREATE_FAILED')];
    await fireEvent.click(screen.getByRole('button', { name: '새로고침' }));
    await vi.waitFor(() => expect(rendered.container.querySelectorAll('tbody tr')).toHaveLength(0));
    expect(headings.getByRole('button', { name: tc('table.filterColumn', { column: '상태' }) })).toBeTruthy();
    await fireEvent.click(headings.getByRole('button', { name: tc('table.filterColumn', { column: '상태' }) }));
    expect(screen.getByLabelText('CREATE_COMPLETE')).toBeTruthy();
    await fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    await fireEvent.input(rendered.container.querySelector('#legacy-cluster-resources-search')!, { target: { value: '[' } });
    expect(screen.getByText(tc('table.regexError'))).toBeTruthy();
    expect(rendered.container.querySelectorAll('tbody tr')).toHaveLength(0);
  });
});
