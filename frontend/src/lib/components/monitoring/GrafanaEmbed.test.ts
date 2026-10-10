import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/svelte';

vi.mock('$lib/stores/auth', () => ({
	auth: {
		subscribe(run: (value: { token: string; projectId: string }) => void) {
			run({ token: 'test-token', projectId: 'test-project' });
			return () => {};
		},
	},
}));

vi.mock('$lib/stores/grafana', () => ({
	loadGrafanaContext: vi.fn().mockResolvedValue({
		grafanaUrl: 'https://grafana.example.com',
		dashboards: { node: 'node-dashboard' },
	}),
}));

import GrafanaEmbed from './GrafanaEmbed.svelte';

describe('Grafana iframe presentation contract', () => {
	it.each([
		{ panelId: undefined, path: '/d/node-dashboard/_' },
		{ panelId: 7, path: '/d-solo/node-dashboard/_' },
	])('suppresses branding without changing the dashboard/panel query: $path', async ({ panelId, path }) => {
		render(GrafanaEmbed, {
			dashboardKey: 'node',
			panelId,
			vars: { project_id: 'project & team/one' },
			range: 'now-3h',
		});
		await waitFor(() => expect(screen.getByTitle('node')).toBeInstanceOf(HTMLIFrameElement));
		const iframe = screen.getByTitle('node') as HTMLIFrameElement;
		const url = new URL(iframe.src);
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
});
