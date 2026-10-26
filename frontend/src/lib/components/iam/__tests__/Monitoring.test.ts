import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { setTimeout as nextTurn } from 'node:timers/promises';
import { writable } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { DomainBudgets, DomainForecast, IamResourceWorkspace } from '$lib/api/workspaceIam';

const { api } = vi.hoisted(() => ({ api: { get: vi.fn(), put: vi.fn() } }));
vi.mock('$lib/api/client', () => ({ api, ApiError: class ApiError extends Error { constructor(public status: number, message: string) { super(message); } } }));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token', userId: 'actor', domainId: 'domain-a', isDomainManager: true }),
	authReady: writable(true), projectSwitching: writable(false)
}));
import { auth } from '$lib/stores/auth';
import { ApiError } from '$lib/api/client';
import { t } from '$lib/i18n/ns/workspace-iam';
import DomainIamConsole from '../DomainIamConsole.svelte';
import IamResources from '../IamResources.svelte';
import IamQuotas from '../IamQuotas.svelte';
import IamForecast from '../IamForecast.svelte';

const session = { token: () => 'token', userId: 'actor', domainId: 'domain-a', isCurrent: () => true, canSubmit: () => true };
const metric = { service: 'nova', metric: 'instances', kind: 'count' as const, unit: 'count', value: 7, status: 'ready' as const };
const quota = { project_id: 'project-a', compute: { instances: { limit: 12, in_use: 7 } }, volume: null, network: null, file_storage: null, availability: { compute: true }, errors: {} };
const resources: IamResourceWorkspace = {
	domain: { id: 'domain-a', name: 'Domain A', enabled: true },
	projects: [{ id: 'project-a', name: 'Project A', enabled: true, resources: [{ ...metric, value: 3 }], quotas: quota }],
	users: [{ id: 'user-a', name: 'Alice', domain_id: 'account-home', enabled: true, project_ids: ['project-a'], membership_state: 'ready', resources: [{ ...metric, value: 1 }] }],
	resources: [metric, { ...metric, metric: 'keypairs', value: null, status: 'unavailable', error: 'domain_aggregate_unsupported' }],
	inventory: [{ category: 'instances', id: 'vm-a', name: 'Domain VM', project_id: 'project-a', user_id: 'user-a', status: 'ACTIVE' }],
	coverage: { observed_at: '2026-10-26T00:00:00Z', partial: true, notes: ['keypairs:unsupported'] }
};
const budgets: DomainBudgets = { domain_id: 'domain-a', revision: 1, ceilings: {}, defaults: {}, enforcement_scope: 'afterglow_project_allocations', defaults_future_only: true, drift: false, allocations: {}, projects: [{ id: 'project-a', name: 'Project A', enabled: true }], operations: [], allocation_blocked: false, blocking_operation_id: null };
const forecast: DomainForecast = { domain_id: 'domain-a', observed_at: '2026-10-26T00:00:00Z', window_days: 7, horizon_days: 30, source: 'nova_simple_tenant_usage', entries: [{ metric: 'vcpus', unit: 'vcpu', status: 'unavailable', error: 'history_unavailable', current: null, limit: null, trend: null }] };
function fixture(path: string) {
	if (path.endsWith('/context')) return { domain_id: 'domain-a', domain_name: 'Domain A', is_domain_manager: true };
	if (path.endsWith('/users')) return { items: [] };
	if (path.endsWith('/monitoring/forecast')) return forecast;
	if (path.endsWith('/monitoring')) return resources;
	if (path.endsWith('/projects/project-a/quotas')) return quota;
	if (path.endsWith('/quotas')) return budgets;
	throw new Error(`Unexpected path: ${path}`);
}
beforeEach(() => {
	vi.resetAllMocks();
	auth.set({ token: 'token', userId: 'actor', domainId: 'domain-a', isDomainManager: true } as never);
	api.get.mockImplementation((path: string) => Promise.resolve(fixture(path)));
});
afterEach(cleanup);

describe('unified current-domain monitoring', () => {
	it('replaces the duplicate tabs and publishes resources while other sections fail or remain pending', async () => {
		const pending = Promise.withResolvers<DomainBudgets>();
		api.get.mockImplementation((path: string) => path.endsWith('/monitoring/forecast') ? Promise.reject(new Error('history failed')) : path.endsWith('/quotas') ? pending.promise : Promise.resolve(fixture(path)));
		render(DomainIamConsole);
		await fireEvent.click(await screen.findByRole('button', { name: t('monitoringTitle') }));
		await waitFor(() => expect(within(document.getElementById('iam-monitoring-forecast')!).getByRole('alert')).toBeTruthy());
		expect(screen.queryByRole('button', { name: t('quotas') })).toBeNull();
		expect(screen.queryByRole('button', { name: t('resources') })).toBeNull();
		const overview = document.getElementById('iam-monitoring-overview')!;
		expect(within(overview).getByRole('heading', { name: t('monitoringOverview') })).toBeTruthy();
		expect(within(overview).getAllByText('7 count').length).toBeGreaterThan(0);
		pending.reject(new Error('policy storage failed'));
		await waitFor(() => expect(within(document.getElementById('iam-monitoring-allocation')!).getByRole('alert')).toBeTruthy());
		expect(within(overview).getAllByText('7 count').length).toBeGreaterThan(0);
	});
	it('keeps full service coverage, inventory and per-project/user attribution reachable', async () => {
		render(IamResources, { session, onDenied: vi.fn() });
		await screen.findByText(t('monitoringAllMetrics'));
		expect(screen.getByText('domain_aggregate_unsupported')).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: t('scope.project') }));
		expect(screen.getByRole('combobox', { name: t('project') })).toBeTruthy();
		expect(screen.getByText('3 count')).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: t('scope.user') }));
		expect(screen.getByText('account-home')).toBeTruthy();
		expect(screen.getByText('1 count')).toBeTruthy();
		expect(screen.getByText('Domain VM')).toBeTruthy();
	});
	it('loads project quota editing and future defaults within the allocation section', async () => {
		render(IamQuotas, { session, onDenied: vi.fn() });
		await fireEvent.click(await screen.findByRole('button', { name: t('editProject') }));
		await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/v1/iam/projects/project-a/quotas', 'token', undefined, { cache: 'no-store' }));
		await screen.findByText(t('projectHelp'));
		await fireEvent.click(screen.getByRole('button', { name: t('editDefaults') }));
		expect(screen.getByText(t('defaultsHelp'))).toBeTruthy();
	});
	it.each([IamResources, IamQuotas, IamForecast])('starts a deferred initial load after authority revalidation releases it', async component => {
		const onDenied = vi.fn();
		const view = render(component, { session, blocked: true, onDenied });
		expect(api.get).not.toHaveBeenCalled();
		await view.rerender({ session, blocked: false, onDenied });
		await waitFor(() => expect(api.get).toHaveBeenCalledOnce());
		await waitFor(() => expect((screen.getByRole('button', { name: t('reload') }) as HTMLButtonElement).disabled).toBe(false));
	});
	it('shows unavailable history explicitly without projecting missing inputs', async () => {
		render(IamForecast, { session, onDenied: vi.fn() });
		await screen.findByText(t('monitoringForecastUnavailable'));
		expect(screen.getByText('history_unavailable')).toBeTruthy();
		expect(screen.queryByText('0%')).toBeNull();
		expect(screen.queryByText(t('monitoringDailyChange'))).toBeNull();
	});
	it('fences delayed monitoring data after unmount', async () => {
		const old = Promise.withResolvers<IamResourceWorkspace>();
		let reads = 0;
		api.get.mockImplementation((path: string) => path.endsWith('/monitoring') && ++reads === 1 ? old.promise : Promise.resolve(fixture(path)));
		const first = render(IamResources, { session, onDenied: vi.fn() });
		await waitFor(() => expect(reads).toBe(1));
		first.unmount();
		render(IamResources, { session, onDenied: vi.fn() });
		await screen.findByText(t('monitoringAllMetrics'));
		old.resolve({ ...resources, inventory: [{ ...resources.inventory[0], name: 'Obsolete VM' }] });
		await nextTurn(); await tick();
		expect(screen.queryByText('Obsolete VM')).toBeNull();
		expect(reads).toBe(2);
	});
	it('rechecks manager authority on a native section denial without hiding good sections', async () => {
		api.get.mockImplementation((path: string) => path.endsWith('/monitoring/forecast') ? Promise.reject(new ApiError(403, 'domain_monitoring_native_denied')) : Promise.resolve(fixture(path)));
		render(DomainIamConsole);
		await fireEvent.click(await screen.findByRole('button', { name: t('monitoringTitle') }));
		await screen.findByText('domain_monitoring_native_denied');
		await waitFor(() => expect(api.get.mock.calls.filter(([path]) => path.endsWith('/context'))).toHaveLength(2));
		expect(document.getElementById('iam-monitoring-overview')).toBeTruthy();
		expect(document.getElementById('iam-monitoring-allocation')).toBeTruthy();
		expect(screen.getAllByText('7 count').length).toBeGreaterThan(0);
		expect(screen.getByRole('button', { name: t('editDefaults') })).toBeTruthy();
	});
	it('retires original monitoring and forecast payloads across real domain A→B→A transitions', async () => {
		const oldResources = Promise.withResolvers<IamResourceWorkspace>();
		const oldForecast = Promise.withResolvers<DomainForecast>();
		let resourcesReads = 0; let forecastReads = 0;
		api.get.mockImplementation((path: string) => {
			if (path.endsWith('/monitoring') && ++resourcesReads === 1) return oldResources.promise;
			if (path.endsWith('/monitoring/forecast') && ++forecastReads === 1) return oldForecast.promise;
			return Promise.resolve(fixture(path));
		});
		render(DomainIamConsole);
		await fireEvent.click(await screen.findByRole('button', { name: t('monitoringTitle') }));
		await waitFor(() => expect(forecastReads).toBe(1));
		auth.update(state => ({ ...state, domainId: 'domain-b' }));
		auth.update(state => ({ ...state, domainId: 'domain-a' }));
		await waitFor(() => expect(resourcesReads).toBe(2));
		await screen.findByText(t('monitoringAllMetrics'));
		await screen.findByText('Domain VM');
		await screen.findByText('nova_simple_tenant_usage');
		oldResources.resolve({ ...resources, inventory: [{ ...resources.inventory[0], name: 'Obsolete VM' }] });
		oldForecast.resolve({ ...forecast, source: 'obsolete-forecast' });
		await nextTurn(); await tick();
		expect(screen.queryByText('Obsolete VM')).toBeNull();
		expect(screen.queryByText('obsolete-forecast')).toBeNull();
		expect(forecastReads).toBe(2);
		expect(screen.getByText('Domain VM')).toBeTruthy();
		expect(screen.getByText('nova_simple_tenant_usage')).toBeTruthy();
	});
	it('rejects a forecast for a different domain', async () => {
		api.get.mockResolvedValue({ ...forecast, domain_id: 'foreign', source: 'foreign-history' });
		render(IamForecast, { session, onDenied: vi.fn() });
		await screen.findByText(t('scopeMismatch'));
		expect(screen.queryByText('foreign-history')).toBeNull();
	});
	it('does not publish forecast success or denial after unmount', async () => {
		for (const denied of [false, true]) {
			const pending = Promise.withResolvers<DomainForecast>();
			const onDenied = vi.fn();
			api.get.mockReturnValue(pending.promise);
			const previousCalls = api.get.mock.calls.length;
			const view = render(IamForecast, { session, onDenied });
			await waitFor(() => expect(api.get.mock.calls.length).toBe(previousCalls + 1));
			view.unmount();
			if (denied) pending.reject(new ApiError(403, 'stale-denial')); else pending.resolve({ ...forecast, source: 'stale-history' });
			await nextTurn(); await tick();
			expect(onDenied).not.toHaveBeenCalled();
			expect(screen.queryByText('stale-history')).toBeNull();
		}
	});
	it('formats a real negative daily slope separately from unlimited quota sentinels', async () => {
		api.get.mockResolvedValue({ ...forecast, entries: [{ ...forecast.entries[0], status: 'ready', error: null, current: 4, limit: 20, trend: { current_pct: 20, slope_per_day: -1, projected_pct: 0, days_to_limit: null, trend_available: true, series: [10, 9, 8, 7, 6, 5, 4] } }] });
		render(IamForecast, { session, onDenied: vi.fn() });
		await screen.findByText(`${t('monitoringDailyChange')}: -1 vcpu`);
		expect(screen.queryByText(t('unlimited'))).toBeNull();
	});
});
