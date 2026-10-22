import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/svelte';
import { tick } from 'svelte';
import { get } from 'svelte/store';
import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { ApiError } from '$lib/api/errors';
import type { DomainUsage } from '$lib/types/adminOverview';

const mocks = vi.hoisted(() => ({ get: vi.fn(), goto: vi.fn(), refresh: undefined as (() => void) | undefined }));
// Mock factories run before static imports; resolve the real error class inside that hoisted boundary.
vi.mock('$lib/api/client', async () => ({ api: { get: mocks.get }, ApiError: (await import('$lib/api/errors')).ApiError }));
vi.mock('$app/navigation', () => ({ goto: mocks.goto }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({ createAutoRefresh: (callback: () => void) => { mocks.refresh = callback; return {}; } }));
vi.mock('$lib/components/admin/overview/ResourceDonutsCard.svelte', () => ({ default: () => ({}) }));
vi.mock('$lib/components/admin/overview/KpiCardRow.svelte', () => ({ default: () => ({}) }));
vi.mock('$lib/components/admin/overview/ServiceCountCards.svelte', () => ({ default: () => ({}) }));
vi.mock('$lib/components/admin/overview/VersionInfoPanel.svelte', () => ({ default: () => ({}) }));
import Page from './+page.svelte';
const initial = get(auth);
const row = (name: string): DomainUsage => ({ domain_id: 'owned-domain', domain_name: name, owner_status: 'known', project_ids: ['owned-project'], project_count: 1, instances: 1, vcpus: 2, ram_mb: 4096, gpu_instances: 0, volumes: 1, volume_gb: 1024, attached_volumes: 1, attached_gb: 1024, available_volumes: 0, available_gb: 0 });
function serve(domains: unknown = [row('Current domain')]) {
	mocks.get.mockImplementation((path: string) => {
		if (path === '/api/v1/admin/overview/domains') return domains;
		if (path === '/api/v1/admin/overview') return Promise.resolve({});
		if (path === '/api/v1/admin/notifications') return Promise.resolve([]);
		return Promise.resolve(null);
	});
}
async function flush() { await tick(); await Promise.resolve(); await tick(); }
beforeEach(() => {
	initLocale('en'); mocks.get.mockReset(); mocks.goto.mockReset();
	auth.set({ ...initial, token: 'admin-token', userId: 'admin', sessionId: 'session-a', projectId: 'workspace', isSystemAdmin: true });
	authReady.set(true); logoutInProgress.set(false); projectSwitching.set(false);
	vi.stubGlobal('matchMedia', vi.fn((query: string) => ({ matches: true, media: query, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
});
afterEach(() => { cleanup(); auth.set(initial); authReady.set(false); logoutInProgress.set(false); projectSwitching.set(false); initLocale('ko'); vi.unstubAllGlobals(); });

describe('administrator overview response ownership', () => {
	it('loads domain totals and never requests the old project quota monitor', async () => {
		serve(Promise.resolve([row('Current domain')])); render(Page);
		expect(await screen.findByText('Current domain')).toBeTruthy();
		expect(mocks.get.mock.calls.some(([path]) => path === '/api/v1/admin/overview/projects')).toBe(false);
		expect(screen.getByRole('link', { name: 'View instances' }).getAttribute('href')).toBe('/admin/instances?domain_id=owned-domain');
	});

	it('discards a same-tick auth ABA response and publishes only the current request', async () => {
		const old = Promise.withResolvers<DomainUsage[]>(); const current = Promise.withResolvers<DomainUsage[]>();
		serve(old.promise); render(Page);
		await waitFor(() => expect(mocks.get).toHaveBeenCalledWith('/api/v1/admin/overview/domains', 'admin-token', 'workspace'));
		const original = get(auth);
		serve(current.promise);
		auth.set({ ...original, projectId: 'other' }); auth.set(original);
		await flush(); old.resolve([row('STALE domain')]); await flush();
		expect(screen.queryByText('STALE domain')).toBeNull();
		expect(get(authReady)).toBe(false);
		expect(mocks.get.mock.calls.filter(([path]) => path === '/api/v1/admin/overview/domains')).toHaveLength(1);
		// The fixture accepts verification of the current epoch before allowing fresh reads.
		authReady.set(true);
		await waitFor(() => expect(mocks.get.mock.calls.filter(([path]) => path === '/api/v1/admin/overview/domains')).toHaveLength(2));
		current.resolve([row('Fresh domain')]);
		expect(await screen.findByText('Fresh domain')).toBeTruthy();
	});

	it.each(['logout', 'unverified', 'switching', 'revoked'] as const)('clears private results and suppresses late promises after %s', async kind => {
		serve(Promise.resolve([row('Private domain')])); render(Page);
		await screen.findByText('Private domain');
		const old = Promise.withResolvers<DomainUsage[]>(); serve(old.promise); mocks.refresh?.();
		if (kind === 'logout') logoutInProgress.set(true);
		else if (kind === 'unverified') authReady.set(false);
		else if (kind === 'switching') projectSwitching.set(true);
		else auth.update(state => ({ ...state, isSystemAdmin: false }));
		await flush(); old.resolve([row('STALE domain')]); await flush();
		expect(screen.queryByText('Private domain')).toBeNull(); expect(screen.queryByText('STALE domain')).toBeNull();
	});

	it('ignores a stale overview 403 instead of navigating the replacement session', async () => {
		const old = Promise.withResolvers<unknown>(); serve(Promise.resolve([]));
		const implementation = mocks.get.getMockImplementation()!;
		mocks.get.mockImplementation((path: string) => path === '/api/v1/admin/overview' ? old.promise : implementation(path));
		render(Page); await waitFor(() => expect(mocks.get).toHaveBeenCalled());
		serve(Promise.resolve([row('Replacement session')]));
		auth.update(state => ({ ...state, sessionId: 'session-b' })); await flush();
		old.reject(new ApiError(403, 'Old authority revoked')); await flush();
		expect(mocks.goto).not.toHaveBeenCalled();
		expect(get(authReady)).toBe(false);
		expect(screen.queryByText('Replacement session')).toBeNull();
		expect(mocks.get.mock.calls.filter(([path]) => path === '/api/v1/admin/overview/domains')).toHaveLength(1);
		authReady.set(true);
		await waitFor(() => expect(mocks.get.mock.calls.filter(([path]) => path === '/api/v1/admin/overview/domains')).toHaveLength(2));
		expect(await screen.findByText('Replacement session')).toBeTruthy();
	});

	it('rejects stale notification and identity snapshots after a new logical login with the same token', async () => {
		const notifications = Promise.withResolvers<unknown>(); const identity = Promise.withResolvers<unknown>();
		serve(Promise.resolve([row('Old session domain')]));
		const implementation = mocks.get.getMockImplementation()!;
		mocks.get.mockImplementation((path: string) => path.endsWith('/notifications') ? notifications.promise
			: path.endsWith('/identity/summary') ? identity.promise : implementation(path));
		render(Page); await screen.findByText('Old session domain');
		serve(Promise.resolve([row('Current session domain')]));
		auth.update(state => ({ ...state, sessionId: 'new-logical-login' }));
		await flush();
		expect(get(authReady)).toBe(false);
		expect(screen.queryByText('Old session domain')).toBeNull();
		expect(screen.queryByText('Current session domain')).toBeNull();
		expect(mocks.get.mock.calls.filter(([path]) => path === '/api/v1/admin/overview/domains')).toHaveLength(1);
		authReady.set(true);
		await waitFor(() => expect(mocks.get.mock.calls.filter(([path]) => path === '/api/v1/admin/overview/domains')).toHaveLength(2));
		await screen.findByText('Current session domain');
		notifications.resolve([{ severity: 'critical', message: 'private', href: '/admin/users', target: 'old-user' }]);
		identity.resolve({ user_count: 9876, project_count: 8765, role_count: 7654, group_count: 6543 });
		await flush();
		expect(screen.queryByRole('alert')).toBeNull();
		expect(screen.queryByRole('link', { name: /Users/ })).toBeNull();
		expect(screen.queryByText('9,876')).toBeNull();
	});

	it('prevents an older refresh from replacing a newer summary and retains the last result on refresh failure', async () => {
		serve(Promise.resolve([row('Initial domain')])); render(Page); await screen.findByText('Initial domain');
		const old = Promise.withResolvers<DomainUsage[]>(); const current = Promise.withResolvers<DomainUsage[]>();
		serve(old.promise); mocks.refresh?.(); serve(current.promise); mocks.refresh?.();
		current.resolve([row('Latest domain')]); await screen.findByText('Latest domain');
		old.resolve([row('STALE domain')]); await flush(); expect(screen.queryByText('STALE domain')).toBeNull();
		serve(Promise.reject(new Error('inventory unavailable'))); mocks.refresh?.();
		expect(await screen.findByRole('alert')).toBeTruthy(); expect(screen.getByText('Latest domain')).toBeTruthy();
	});

	it('does not let an unmounted page publish or redirect after navigation', async () => {
		const old = Promise.withResolvers<unknown>(); serve(Promise.resolve([]));
		const implementation = mocks.get.getMockImplementation()!;
		mocks.get.mockImplementation((path: string) => path === '/api/v1/admin/overview' ? old.promise : implementation(path));
		const first = render(Page); await waitFor(() => expect(mocks.get).toHaveBeenCalled()); first.unmount();
		serve(Promise.resolve([row('New page')])); render(Page); await screen.findByText('New page');
		old.reject(new ApiError(403, 'Old page denied')); await flush();
		expect(mocks.goto).not.toHaveBeenCalled(); expect(screen.getByText('New page')).toBeTruthy();
	});
});
