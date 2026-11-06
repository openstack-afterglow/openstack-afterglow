import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import type { ZunContainer } from '$lib/types/zunContainer';
import { t as tc } from '$lib/i18n/ns/common';
import { t } from '$lib/i18n/ns/containers-shell';

const { goto, api } = vi.hoisted(() => ({
	goto: vi.fn(),
	api: {
		get: vi.fn(),
		post: vi.fn(),
		delete: vi.fn(),
	},
}));

vi.mock('$app/navigation', () => ({ goto }));
vi.mock('$lib/api/client', () => ({
	api,
	ApiError: class ApiError extends Error { status = 500; },
}));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token', projectId: 'project' }),
}));

import Page from '../+page.svelte';

const container: ZunContainer = {
	uuid: 'running-1',
	name: 'running',
	status: 'Running',
	status_reason: null,
	image: 'alpine',
	command: null,
	cpu: 1,
	memory: '512M',
	created_at: '2026-01-01T00:00:00Z',
};

describe('container instances page', () => {
	beforeEach(() => {
		goto.mockReset();
		api.get.mockReset().mockResolvedValue({ items: [container], service_available: true, message: '' });
	});

	it.each([
		[],
		{ items: null, service_available: true, message: '' },
		{ items: [null], service_available: true, message: '' },
		{ items: [], service_available: 'true', message: '' },
	])('reports malformed list transport without publishing an empty success: %j', async malformed => {
		api.get.mockResolvedValue(malformed);
		render(Page);
		expect(await screen.findByRole('alert')).toHaveProperty('textContent', t('instances.errors.server'));
		expect(screen.queryByText(t('instances.empty.title'))).toBeNull();
		expect(screen.queryByRole('button', { name: 'running' })).toBeNull();
	});

	it('keeps its last successful rows and regex when a refresh returns the wrong response shape', async () => {
		render(Page);
		await screen.findByRole('button', { name: 'running' });
		const search = screen.getByRole('searchbox');
		await fireEvent.input(search, { target: { value: '^running$' } });
		api.get.mockResolvedValue([]);
		await fireEvent.click(screen.getByRole('button', { name: tc('autoRefresh.refreshNow') }));
		expect(await screen.findByRole('alert')).toHaveProperty('textContent', t('instances.errors.server'));
		expect(screen.getByRole('button', { name: 'running' })).toBeTruthy();
		expect((search as HTMLInputElement).value).toBe('^running$');
		expect(screen.queryByText(t('instances.empty.title'))).toBeNull();
	});

	it('wires a container name to its detail route', async () => {
		render(Page);

		await fireEvent.click(await screen.findByRole('button', { name: 'running' }));
		expect(goto).toHaveBeenCalledWith('/dashboard/containers/instances/running-1');
	});

  it('preserves regex, exact column filtering and descending order through refresh and empty results', async () => {
    const rows = [
      { ...container, uuid: 'a', name: 'alpha' },
      { ...container, uuid: 'z', name: 'zeta' },
      { ...container, uuid: 's', name: 'stopped', status: 'Stopped' },
    ];
    api.get.mockResolvedValue({ items: rows, service_available: true, message: '' });
    const rendered = render(Page);
    await screen.findByRole('button', { name: 'alpha' });
    const search = rendered.container.querySelector('#zun-container-search') as HTMLInputElement;
    await fireEvent.input(search, { target: { value: '^(alpha|zeta|stopped)$' } });
    const headings = within(rendered.container.querySelector('thead')!);
    await fireEvent.click(headings.getByRole('button', { name: tc('table.filterColumn', { column: '상태' }) }));
    const menu = screen.getByRole('dialog', { name: tc('table.filterColumn', { column: '상태' }) });
    await fireEvent.click(within(menu).getByLabelText('Stopped'));
    await fireEvent.keyDown(menu, { key: 'Escape' });
    for (const direction of ['none', 'ascending'] as const) {
      await fireEvent.click(headings.getByRole('button', { name: tc('table.sortColumn', { column: '이름', direction: tc(`table.${direction}`) }) }));
    }
    api.get.mockResolvedValue({ items: [...rows, { ...container, uuid: 'b', name: 'beta' }], service_available: true, message: '' });
    await fireEvent.click(screen.getByRole('button', { name: tc('autoRefresh.refreshNow') }));
    await vi.waitFor(() => expect(api.get).toHaveBeenLastCalledWith('/api/v1/containers', 'token', 'project', { refresh: true }));
    await vi.waitFor(() => expect([...rendered.container.querySelectorAll('tbody tr')].map(row => row.querySelector('td:nth-child(2) button')?.textContent)).toEqual(['zeta', 'alpha']));
    expect(search.value).toBe('^(alpha|zeta|stopped)$');
    expect(rendered.container.querySelector('th[aria-sort="descending"]')).toBeTruthy();

    await fireEvent.input(search, { target: { value: '[' } });
    expect(rendered.container.querySelectorAll('tbody tr')).toHaveLength(0);
    expect(screen.getByText(tc('table.regexError'))).toBeTruthy();
    expect(headings.getByRole('button', { name: tc('table.filterColumn', { column: '상태' }) })).toBeTruthy();
    await fireEvent.input(search, { target: { value: '^alpha$' } });
    expect(await screen.findByRole('button', { name: 'alpha' })).toBeTruthy();
  });
});
