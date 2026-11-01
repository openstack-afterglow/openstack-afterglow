import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import { tick } from 'svelte';

const mocks = vi.hoisted(() => ({ load: vi.fn() }));
vi.mock('$lib/stores/auth', () => {
	const auth = writable({ token: 'test-token' as string | null, projectId: 'test-project', userId: 'admin-a', isSystemAdmin: true });
	let epoch = 0;
	auth.subscribe(() => { epoch += 1; });
	return { auth, getAuthVerificationEpoch: () => epoch };
});
vi.mock('$lib/stores/theme', () => {
	const theme = writable<'dark' | 'light'>('dark');
	return { resolvedTheme: theme, theme };
});
vi.mock('$lib/api/client', () => ({ api: { get: mocks.load } }));
vi.mock('$lib/mockup/transport', () => ({ getActiveMockupProfile: () => null }));
vi.mock('$lib/mockup/state', () => ({ getMockupRevision: () => 0, onMockupRevisionChange: () => () => {} }));

import { auth } from '$lib/stores/auth';
import { theme } from '$lib/stores/theme';
import GrafanaEmbed from './GrafanaEmbed.svelte';
import { invalidateGrafanaContext } from '$lib/stores/grafana';

const context = { grafana_url: 'https://grafana.example.com', dashboards: { node: 'node-dashboard' } };
beforeEach(() => {
	auth.update(state => ({ ...state, token: 'test-token', projectId: 'test-project', userId: 'admin-a', isSystemAdmin: true }));
	theme.set('dark');
	invalidateGrafanaContext();
	mocks.load.mockReset().mockResolvedValue(context);
});

describe('administrator Grafana iframe presentation contract', () => {
	it.each([
		{ panelId: undefined, path: '/d/node-dashboard/_' },
		{ panelId: 7, path: '/d-solo/node-dashboard/_' },
	])('suppresses branding without changing the dashboard/panel query: $path', async ({ panelId, path }) => {
		render(GrafanaEmbed, {
			dashboardKey: 'node', panelId,
			vars: { project_id: 'project & team/one' }, range: 'now-3h',
		});
		await waitFor(() => expect(screen.getByTitle('node')).toBeInstanceOf(HTMLIFrameElement));
		const url = new URL((screen.getByTitle('node') as HTMLIFrameElement).src);
		expect(url.origin).toBe('https://grafana.example.com');
		expect(url.pathname).toBe(path);
		expect(url.searchParams.getAll('hideLogo')).toEqual(['1']);
		expect(url.searchParams.has('kiosk')).toBe(true);
		expect(url.searchParams.get('orgId')).toBe('1');
		expect(url.searchParams.get('theme')).toBe('dark');
		expect(url.searchParams.get('from')).toBe('now-3h');
		expect(url.searchParams.get('to')).toBe('now');
		expect(url.searchParams.get('var-project_id')).toBe('project & team/one');
		expect(url.searchParams.get('panelId')).toBe(panelId === undefined ? null : '7');
	});

	it('keeps the same dashboard and query while tracking both console themes', async () => {
		render(GrafanaEmbed, { dashboardKey: 'node' });
		await screen.findByTitle('node');
		theme.set('light');
		await waitFor(() => expect(new URL((screen.getByTitle('node') as HTMLIFrameElement).src).searchParams.get('theme')).toBe('light'));
		expect(mocks.load).toHaveBeenCalledTimes(1);
	});

	it('does not render or load infrastructure embeds for a member', async () => {
		auth.update(state => ({ ...state, isSystemAdmin: false }));
		const view = render(GrafanaEmbed, { dashboardKey: 'node' });
		await tick();
		expect(mocks.load).not.toHaveBeenCalled();
		expect(view.container.querySelector('iframe')).toBeNull();
	});

	it('reloads through the real catalog cache after auth A → B → A retires an API read', async () => {
		const pending = Promise.withResolvers<typeof context>();
		mocks.load.mockReturnValueOnce(pending.promise).mockResolvedValue({ ...context, grafana_url: 'https://fresh.example.com' });
		render(GrafanaEmbed, { dashboardKey: 'node' });
		await waitFor(() => expect(mocks.load).toHaveBeenCalledTimes(1));
		auth.update(state => ({ ...state, projectId: 'project-b' }));
		auth.update(state => ({ ...state, projectId: 'test-project' }));
		await screen.findByTitle('node');
		pending.reject(new DOMException('Retired API auth epoch', 'AbortError'));
		await tick();
		await tick();
		expect(new URL((screen.getByTitle('node') as HTMLIFrameElement).src).origin).toBe('https://fresh.example.com');
	});

	it('removes the iframe immediately when authority is lost', async () => {
		const view = render(GrafanaEmbed, { dashboardKey: 'node' });
		await screen.findByTitle('node');
		auth.update(state => ({ ...state, isSystemAdmin: false }));
		await tick();
		expect(view.container.querySelector('iframe')).toBeNull();
	});
});
