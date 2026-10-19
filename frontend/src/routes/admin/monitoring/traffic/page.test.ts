import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import Page from './+page.svelte';
import { auth, authReady, projectSwitching } from '$lib/stores/auth';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/traffic-analytics';
import { observations } from '$lib/components/admin/traffic/__tests__/observations';
import type { TrafficSnapshot } from '$lib/types/trafficAnalytics';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: { get } }));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'token-a', userId: 'user-a', projectId: 'project-a', isSystemAdmin: true }), authReady: writable(true), projectSwitching: writable(false) }));
const actor = { token: 'token-a', userId: 'user-a', projectId: 'project-a', isSystemAdmin: true };
beforeEach(() => { get.mockReset(); initLocale('en'); auth.set(actor as never); authReady.set(true); projectSwitching.set(false); });
afterEach(() => { cleanup(); initLocale('ko'); });

describe('traffic API to UI', () => {
	it('loads the admin aggregate with source/range and current credentials, and renders real observed categories', async () => {
		get.mockResolvedValue(observations()); render(Page);
		await screen.findByText('/admin');
		expect(get).toHaveBeenCalledExactlyOnceWith('/api/v1/admin/monitoring/traffic?range=24h&source=backend&origin=all', actor.token, actor.projectId, { refresh: true });
		expect(screen.getByRole('link', { name: t('routes.topology') }).getAttribute('href')).toBe('/admin/infrastructure-topology');
		expect(screen.getByText(t('routes.note'))).toBeTruthy(); expect(screen.getByText(t('coverage.partial'), { exact: false })).toBeTruthy();
	});
	it('separates source snapshots and ignores a late previous-source response', async () => {
		const pending = Promise.withResolvers<TrafficSnapshot>();
		get.mockImplementationOnce(() => pending.promise).mockResolvedValue(observations({ source: 'frontend', routes: [{ ...observations().routes[0], route: '/frontend-observed' }] }));
		render(Page); await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
		await fireEvent.change(screen.getByLabelText(t('controls.source')), { target: { value: 'frontend' } });
		await screen.findByText('/frontend-observed'); pending.resolve(observations({ routes: [{ ...observations().routes[0], route: '/old-backend' }] }));
		await waitFor(() => expect(screen.queryByText('/old-backend')).toBeNull());
		expect(screen.getByText(t('coverage.frontend'))).toBeTruthy();
	});
	it('changes range without mixing prior totals and refreshes the selected source', async () => {
		get.mockResolvedValueOnce(observations()).mockResolvedValueOnce(observations({ range: '7d', routes: [{ ...observations().routes[0], route: '/week-observed' }] })).mockResolvedValue(observations({ range: '7d', routes: [{ ...observations().routes[0], route: '/fresh-observed' }] })); render(Page); await screen.findByText('/admin');
		await fireEvent.change(screen.getByLabelText(t('controls.range')), { target: { value: '7d' } });
		await screen.findByText('/week-observed'); expect(screen.queryByText('/admin')).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: t('controls.refresh') }));
		await screen.findByText('/fresh-observed'); expect(screen.queryByText('/week-observed')).toBeNull();
	});
	it('keeps origin filters, totals and route breakdowns together and ignores a late all-origin result', async () => {
		const pending = Promise.withResolvers<TrafficSnapshot>();
		const origins = { internal: 0, external: 10, unknown: 0, legacy_unclassified: 0 };
		get.mockImplementationOnce(() => pending.promise).mockResolvedValue(observations({ origin: 'external', origins,
			routes: [{ ...observations().routes[0], route: '/external-observed', origins }] }));
		render(Page); await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
		await fireEvent.change(screen.getByLabelText(t('controls.origin')), { target: { value: 'external' } });
		await screen.findByText('/external-observed');
		expect(get).toHaveBeenLastCalledWith('/api/v1/admin/monitoring/traffic?range=24h&source=backend&origin=external', actor.token, actor.projectId, { refresh: true });
		const breakdown = within(screen.getByText(t('origins.external'), { selector: 'dt' }).closest('dl')!);
		expect(breakdown.getByText(t('origins.external'), { selector: 'dt' }).nextElementSibling?.textContent).toBe('10');
		expect(breakdown.getByText(t('origins.internal'), { selector: 'dt' }).nextElementSibling?.textContent).toBe('0');
		const row = screen.getByText('/external-observed').closest('tr')!;
		expect(within(row).getAllByRole('cell').slice(1, 6).map(cell => cell.textContent)).toEqual(['10', '0', '10', '0', '0']);
		pending.resolve(observations({ routes: [{ ...observations().routes[0], route: '/old-all-origins' }] }));
		await waitFor(() => expect(screen.queryByText('/old-all-origins')).toBeNull());
		expect(screen.getByText('/external-observed')).toBeTruthy();
	});
	it('rejects a same-shape response for a different origin instead of showing its counts', async () => {
		get.mockResolvedValue(observations()); render(Page); await screen.findByText('/admin');
		await fireEvent.change(screen.getByLabelText(t('controls.origin')), { target: { value: 'external' } });
		await screen.findByText(t('loadFailed')); expect(screen.queryByText('/admin')).toBeNull();
	});
	it('does not present a schema/source mismatch as available observations and offers refresh', async () => {
		get.mockResolvedValueOnce(observations({ source: 'frontend' })).mockResolvedValue(observations()); render(Page);
		await screen.findByText(t('loadFailed')); expect(screen.queryByText('/admin')).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: t('controls.refresh') })); await screen.findByText('/admin');
	});
	it('does not retain old counts as current after transport failure', async () => {
		get.mockResolvedValueOnce(observations()).mockRejectedValue(new Error('network failed')); render(Page); await screen.findByText('/admin');
		await fireEvent.click(screen.getByRole('button', { name: t('controls.refresh') })); await screen.findByText(t('loadFailed'));
		expect(screen.queryByText('/admin')).toBeNull(); expect(screen.getByText(t('coverage.proxy'))).toBeTruthy();
	});
	it.each(['disabled', 'unavailable', 'partial'] as const)('renders %s without fake zero totals or countries', async (state) => {
		get.mockResolvedValue(observations({ state, totals: null, origins: null, countries: [], routes: [], series: [] })); render(Page);
		await screen.findByText(t(`states.${state}`), { exact: false });
		expect(screen.queryByText('/admin')).toBeNull();
		const origins = within(screen.getByText(t('origins.internal'), { selector: 'dt' }).closest('dl')!);
		for (const origin of ['internal', 'external', 'unknown', 'legacy_unclassified'] as const) {
			expect(origins.getByText(t(`origins.${origin}`), { selector: 'dt' }).nextElementSibling?.textContent).toBe(t('unknown'));
		}
		await screen.findByText(t('empty'));
		expect(screen.getAllByText(t('unknown')).length).toBeGreaterThan(0);
	});
	it('masks old authority immediately and drops delayed results across an A→B→A actor transition', async () => {
		const pending = Promise.withResolvers<TrafficSnapshot>();
		get.mockImplementationOnce(() => pending.promise).mockResolvedValue(observations({ routes: [{ ...observations().routes[0], route: '/new-actor' }] }));
		render(Page); await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
		auth.set({ ...actor, token: 'token-b', userId: 'user-b' } as never); await screen.findByText('/new-actor');
		auth.set(actor as never); await waitFor(() => expect(get).toHaveBeenCalledTimes(3)); await screen.findByText('/new-actor');
		pending.resolve(observations({ routes: [{ ...observations().routes[0], route: '/old-private' }] })); await waitFor(() => expect(screen.queryByText('/old-private')).toBeNull());
	});
	it('fences changes of owner even when the token and project stay the same', async () => {
		const pending = Promise.withResolvers<TrafficSnapshot>();
		get.mockImplementationOnce(() => pending.promise).mockResolvedValue(observations({ routes: [{ ...observations().routes[0], route: '/current-owner' }] }));
		render(Page); await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
		auth.set({ ...actor, userId: 'user-b' } as never); await screen.findByText('/current-owner');
		pending.resolve(observations({ routes: [{ ...observations().routes[0], route: '/previous-owner' }] }));
		await waitFor(() => expect(screen.queryByText('/previous-owner')).toBeNull());
		expect(screen.getByText('/current-owner')).toBeTruthy();
	});
	it.each(['unverified', 'switching'] as const)('hides data during %s authority transitions and discards delayed observations', async (transition) => {
		const pending = Promise.withResolvers<TrafficSnapshot>();
		get.mockResolvedValueOnce(observations()).mockImplementationOnce(() => pending.promise).mockResolvedValue(observations({ routes: [{ ...observations().routes[0], route: '/after-transition' }] }));
		render(Page); await screen.findByText('/admin');
		await fireEvent.click(screen.getByRole('button', { name: t('controls.refresh') }));
		await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
		if (transition === 'unverified') authReady.set(false); else projectSwitching.set(true);
		await waitFor(() => expect(screen.getByRole('button', { name: t('controls.refresh') }).hasAttribute('disabled')).toBe(true));
		expect(screen.queryByText('/admin')).toBeNull(); expect(get).toHaveBeenCalledTimes(2);
		pending.resolve(observations({ routes: [{ ...observations().routes[0], route: '/during-transition' }] }));
		await waitFor(() => expect(screen.queryByText('/during-transition')).toBeNull());
		authReady.set(true); projectSwitching.set(false); await screen.findByText('/after-transition');
		expect(screen.queryByText('/during-transition')).toBeNull();
	});
	it('removes observed data on authority loss and never fetches when authority is absent', async () => {
		get.mockResolvedValue(observations()); render(Page); await screen.findByText('/admin');
		auth.set({ ...actor, isSystemAdmin: false } as never); await screen.findByText(t('adminRequired'));
		expect(screen.queryByText('/admin')).toBeNull(); expect(get).toHaveBeenCalledTimes(1);
	});
});
