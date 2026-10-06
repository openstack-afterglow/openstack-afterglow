import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/svelte';
import type { UserDashboardSummary } from '$lib/types/userDashboard';

const mocks = vi.hoisted(() => ({
	apiGet: vi.fn(),
	refresh: null as (() => void | Promise<void>) | null,
}));
vi.mock('$lib/stores/auth', () => ({
	auth: { subscribe: (run: (value: unknown) => void) => {
		run({ token: 'token', projectId: 'project' });
		return () => {};
	} },
}));
vi.mock('$lib/api/client', () => ({ api: { get: mocks.apiGet }, ApiError: class extends Error {} }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: (callback: () => void | Promise<void>) => {
		mocks.refresh = callback;
		return { active: false, intervalSeconds: 30, intervalOptions: [10, 30, 60] };
	},
}));

import Page from '../+page.svelte';

function summary(reverse = false): UserDashboardSummary {
	const instances = ['first', 'second'].map((id) => ({ id, name: id, status: 'ACTIVE', flavor_name: 'small', created_at: '' }));
	return {
		current_project_id: 'project',
		projects: [{
			project_id: 'project', project_name: 'Project', instances: reverse ? instances.reverse() : instances,
			volumes: [{ id: 'volume', name: 'data volume', status: 'available', size: reverse ? 20 : 10, volume_type: 'ssd', created_at: '' }],
			instance_count: 2, volume_count: 1, storage_gb: reverse ? 20 : 10, vcpus: 2, ram_mb: 1024, network_count: 1, fip_count: 1,
		}],
		totals: { instances: 2, volumes: 1, storage_gb: reverse ? 20 : 10, vcpus: 2, ram_mb: 1024, networks: 1, floating_ips: 1 },
	};
}

beforeEach(() => { mocks.apiGet.mockReset(); mocks.refresh = null; });
afterEach(() => cleanup());

describe('my resources refresh', () => {
	it('retains existing resource rows while refreshing and reordering data', async () => {
		mocks.apiGet.mockResolvedValueOnce(summary());
		render(Page);
		const first = await screen.findByText('first');
		const volume = screen.getByText('data volume');
		const project = screen.getByText('Project');
		let resolve!: (value: UserDashboardSummary) => void;
		mocks.apiGet.mockImplementationOnce(() => new Promise<UserDashboardSummary>((done) => { resolve = done; }));
		const pending = mocks.refresh!();
		expect(screen.getByText('first')).toBe(first);
		expect(screen.getByText('data volume')).toBe(volume);
		resolve(summary(true));
		await pending;
		await waitFor(() => expect(screen.getByText('20 GB · ssd')).toBeTruthy());
		expect(screen.getByText('first')).toBe(first);
		expect(screen.getByText('data volume')).toBe(volume);
		expect(screen.getByText('Project')).toBe(project);
	});
});
