import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import { tick } from 'svelte';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/dashboard-home';
import type { Instance } from '$lib/types/compute';

const mocks = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: { get: mocks.get, withExperience: () => ({ get: mocks.get }) } }));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token-a' as string | null, projectId: 'project-a' as string | null, userId: 'user-a', sessionId: 'session-a', isSystemAdmin: false }),
	authReady: writable(true),
	projectSwitching: writable(false),
}));
vi.mock('$lib/stores/servicePermissions', () => ({
	observedProjectPermissions: writable({ loading: false, error: null, permissions: null }),
}));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({ active: false, intervalSeconds: 30, intervalOptions: [15, 30, 60] }),
}));
vi.mock('$lib/components/charts/runtime', () => ({
	mountChart: () => ({ update: vi.fn(), destroy: vi.fn() }),
}));

import { auth, authReady, projectSwitching } from '$lib/stores/auth';
import Page from '../+page.svelte';

const instance = (id: string, project_id: string | null = 'project-a'): Instance => ({
	id, name: id, project_id, status: 'ACTIVE', image_name: null, flavor_name: 'small',
	ip_addresses: [], created_at: null, union_libraries: [], union_strategy: null,
});
const batch = { metrics: { cpu: {
	series: [{ ts: 60, value: 0 }, { ts: 120, value: 5 }], source: 'gnocchi',
	unit: '%', status: 'available', native_status: 'available', error: null,
} } };
function metricsResponse(path: string) {
	return path.includes('/metrics-summary') ? { monitoring_available: true, stats: {} } : batch;
}

beforeEach(() => {
	initLocale('ko');
	auth.update(state => ({ ...state, token: 'token-a', projectId: 'project-a', userId: 'user-a', sessionId: 'session-a', isSystemAdmin: false }));
	authReady.set(true);
	projectSwitching.set(false);
	mocks.get.mockReset().mockImplementation((path: string) => Promise.resolve(path === '/api/v1/instances'
		? [instance('own-vm'), instance('foreign-vm', 'project-b'), instance('unknown-owner', null)] : metricsResponse(path)));
});
afterEach(cleanup);

describe('project VM observability', () => {
	it('requires current project and makes no inventory or metrics request without it', async () => {
		auth.update(state => ({ ...state, projectId: null }));
		render(Page);
		expect(screen.getByText(t('observability.selectProject'))).toBeTruthy();
		await tick();
		expect(mocks.get).not.toHaveBeenCalled();
	});

	it.each([false, true])('selects only current-project Nova instances and uses real instance charts in user mode (admin=%s)', async (isSystemAdmin) => {
		auth.update(state => ({ ...state, isSystemAdmin }));
		const view = render(Page);
		await fireEvent.click(await screen.findByRole('button', { name: /own-vm/ }));
		expect(screen.queryByRole('button', { name: /foreign-vm|unknown-owner/ })).toBeNull();
		expect(await screen.findByText(/gnocchi · 사용 가능/)).toBeTruthy();
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/instances', 'token-a', 'project-a', { refresh: false });
		expect(mocks.get.mock.calls.some(([path, token, project]) => path.startsWith('/api/v1/instances/own-vm/metrics-batch?') && token === 'token-a' && project === 'project-a')).toBe(true);
		expect(mocks.get.mock.calls.every(([path]) => !path.includes('grafana') && !path.includes('/admin/'))).toBe(true);
		expect(screen.queryByRole('button', { name: 'Grafana' })).toBeNull();
		expect(view.container.querySelector('iframe')).toBeNull();
	});

	it('clears measurements when search hides the selected instance', async () => {
		render(Page);
		await fireEvent.click(await screen.findByRole('button', { name: /own-vm/ }));
		await screen.findByText(/gnocchi · 사용 가능/);
		await fireEvent.input(screen.getByRole('searchbox'), { target: { value: 'unmatched' } });
		expect(screen.queryByText(/gnocchi · 사용 가능/)).toBeNull();
		expect(screen.getByText(t('observability.noResults'))).toBeTruthy();
	});

	it('distinguishes failed lookup from verified empty inventory and permits explicit recovery', async () => {
		mocks.get.mockRejectedValueOnce(new Error('provider offline')).mockResolvedValue([]);
		render(Page);
		expect((await screen.findByRole('alert')).textContent).toContain(t('observability.loadFailed'));
		expect(screen.queryByText(t('observability.empty'))).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: t('observability.refresh') }));
		expect(await screen.findByText(t('observability.empty'))).toBeTruthy();
		expect(mocks.get).toHaveBeenLastCalledWith('/api/v1/instances', 'token-a', 'project-a', { refresh: true });
	});

	it.each(['project', 'identity', 'projectAba'] as const)('discards late inventory after %s change', async (transition) => {
		const stale = Promise.withResolvers<Instance[]>();
		mocks.get.mockReturnValueOnce(stale.promise).mockImplementation((path: string) => Promise.resolve(path === '/api/v1/instances'
			? [instance('fresh-vm', transition === 'project' ? 'project-b' : 'project-a')] : metricsResponse(path)));
		render(Page);
		await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(1));
		if (transition === 'project' || transition === 'projectAba') {
			auth.update(state => ({ ...state, projectId: 'project-b' }));
			if (transition === 'projectAba') auth.update(state => ({ ...state, projectId: 'project-a' }));
		} else if (transition === 'identity') auth.update(state => ({ ...state, userId: 'user-b', sessionId: 'session-b' }));
		await screen.findByRole('button', { name: /fresh-vm/ });
		stale.resolve([instance('stale-private-vm')]);
		await stale.promise;
		await tick();
		expect(screen.queryByRole('button', { name: /stale-private-vm/ })).toBeNull();
		expect(mocks.get.mock.calls.some(([path]) => path.includes('/metrics-'))).toBe(false);
	});

	it('waits for verified auth readiness before inventory dispatch', async () => {
		authReady.set(false);
		render(Page);
		await tick();
		expect(mocks.get).not.toHaveBeenCalled();
		authReady.set(true);
		await screen.findByRole('button', { name: /own-vm/ });
		expect(mocks.get).toHaveBeenCalledTimes(1);
	});

	it('preserves picker selection and inventory across normal same-owner token rotation', async () => {
		render(Page);
		await fireEvent.click(await screen.findByRole('button', { name: /own-vm/ }));
		await screen.findByText(/gnocchi · 사용 가능/);
		auth.update(state => ({ ...state, token: 'rotated-token' }));
		await tick();
		expect(screen.getByRole('button', { name: /own-vm/ }).getAttribute('aria-pressed')).toBe('true');
		expect(mocks.get.mock.calls.filter(([path]) => path === '/api/v1/instances')).toHaveLength(1);
	});

	it('accepts an in-flight same-owner inventory during verified token rotation', async () => {
		const pending = Promise.withResolvers<Instance[]>();
		mocks.get.mockReturnValueOnce(pending.promise);
		render(Page);
		await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(1));
		auth.update(state => ({ ...state, token: 'rotated-token' }));
		pending.resolve([instance('current-vm')]);
		await screen.findByRole('button', { name: /current-vm/ });
		expect(mocks.get).toHaveBeenCalledTimes(1);
	});
});
