import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { get } from 'svelte/store';
import { acceptAuthVerification, auth, authReady, getAuthVerificationEpoch, logoutInProgress, projectSwitching, setAuth } from '$lib/stores/auth';
import { initLocale } from '$lib/i18n/runtime.svelte';
import type { ServiceVersions, VersionInfo } from '$lib/types/adminOverview';
import { ApiError } from '$lib/api/errors';
import { refreshAuthState } from '$lib/utils/authSession';

const mocks = vi.hoisted(() => ({ get: vi.fn(), servicesGet: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: { get: (path: string, ...args: unknown[]) =>
	(path === '/api/v1/admin/service-versions' ? mocks.servicesGet : mocks.get)(path, ...args) } }));
import Page from './+page.svelte';

const initial = get(auth);
const snapshot = (version = 'backend-version'): VersionInfo => ({
	platform: { backend_version: version },
	runtime: { python_version: '3.12.13', uptime_seconds: 3661 },
	dependencies: { fastapi: '0.136.3', optional: null },
	git: { commit: '0123456789abcdef0123456789abcdef01234567', tag: '1.32.6', branch: 'dev' },
});
const services = (version = '2.1'): ServiceVersions => ({ services: [
	{ service: 'nova', status: 'available', version, version_kind: 'api' },
	{ service: 'neutron', status: 'available', version: '2.0', version_kind: 'api' },
	{ service: 'lumen', status: 'available', version: '0.6.12', version_kind: 'product' },
	{ service: 'drover', status: 'available', version: null, version_kind: null },
	{ service: 'palimpsest', status: 'unavailable', version: null, version_kind: null },
	{ service: 'waygate', status: 'disabled', version: null, version_kind: null },
] });
async function flush() { await tick(); await Promise.resolve(); await tick(); }
beforeEach(() => {
	initLocale('en');
	vi.stubGlobal('__APP_VERSION__', 'frontend-test-version');
	mocks.get.mockReset();
	mocks.servicesGet.mockReset().mockResolvedValue(services());
	auth.set({ ...initial, token: 'admin-token', userId: 'admin', sessionId: 'session-a', projectId: 'workspace', domainId: 'home', identityDomainId: 'home', isSystemAdmin: true });
	expect(acceptAuthVerification(getAuthVerificationEpoch(), {})).toBe(true);
	logoutInProgress.set(false); projectSwitching.set(false);
});
afterEach(() => {
	cleanup(); auth.set(initial); authReady.set(false); logoutInProgress.set(false); projectSwitching.set(false); initLocale('ko');
	vi.unstubAllGlobals();
});

describe('administrator system information', () => {
	it('shows every existing version group immediately and requests only the protected information endpoints', async () => {
		mocks.get.mockResolvedValue(snapshot()); render(Page);
		expect(await screen.findByText('backend-version')).toBeTruthy();
		expect(screen.getByRole('heading', { level: 1, name: 'System information' })).toBeTruthy();
		for (const name of ['Platform', 'Runtime', 'Dependencies', 'Git']) expect(screen.getByRole('heading', { name })).toBeTruthy();
		for (const text of ['Frontend version', '3.12.13', 'fastapi', '0.136.3', 'optional', '—', '0123456789abcdef0123456789abcdef01234567', '1.32.6', 'dev']) expect(screen.getAllByText(text).length).toBeGreaterThan(0);
		expect(screen.getByText('frontend-test-version')).toBeTruthy();
		expect(mocks.get.mock.calls).toEqual([['/api/v1/admin/version', 'admin-token', 'workspace', { refresh: false }]]);
		expect(mocks.servicesGet.mock.calls).toEqual([['/api/v1/admin/service-versions', 'admin-token', 'workspace', { refresh: false }]]);
	});

	it('keeps a failed read distinct from absent data and explicitly retries with forced freshness', async () => {
		mocks.get.mockRejectedValueOnce(new Error('unavailable')).mockResolvedValueOnce(snapshot()); render(Page);
		expect((await screen.findByRole('alert')).textContent).toContain('Could not load system information');
		expect(screen.queryByText('Backend version')).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: 'Refresh now' }));
		expect(await screen.findByText('backend-version')).toBeTruthy();
		expect(mocks.get).toHaveBeenLastCalledWith('/api/v1/admin/version', 'admin-token', 'workspace', { refresh: true });
		expect(screen.queryByRole('alert')).toBeNull();
	});

	it('retains same-owner data on refresh failure and prevents overlapping manual refreshes', async () => {
		mocks.get.mockResolvedValueOnce(snapshot()); render(Page); await screen.findByText('backend-version');
		const pending = Promise.withResolvers<VersionInfo>(); mocks.get.mockReturnValue(pending.promise);
		const refresh = screen.getByRole('button', { name: 'Refresh now' });
		await fireEvent.click(refresh);
		expect((refresh as HTMLButtonElement).disabled).toBe(true);
		expect(screen.getByText('backend-version')).toBeTruthy();
		pending.reject(new Error('unavailable'));
		await screen.findByRole('alert'); expect(screen.getByText('backend-version')).toBeTruthy();
	});

	it.each(['unverified', 'revoked', 'logout', 'switching'] as const)('never reads with %s authority', async kind => {
		if (kind === 'unverified') authReady.set(false);
		if (kind === 'revoked') auth.update(state => ({ ...state, isSystemAdmin: false }));
		if (kind === 'logout') logoutInProgress.set(true);
		if (kind === 'switching') projectSwitching.set(true);
		render(Page); await flush(); expect(mocks.get).not.toHaveBeenCalled(); expect(mocks.servicesGet).not.toHaveBeenCalled();
	});

	it.each(['unverified', 'revoked', 'logout', 'switching'] as const)('clears settled private values and rejects late results after %s', async kind => {
		mocks.get.mockResolvedValueOnce(snapshot('private-version')); render(Page); await screen.findByText('private-version');
		const late = Promise.withResolvers<VersionInfo>(); mocks.get.mockReturnValue(late.promise);
		await fireEvent.click(screen.getByRole('button', { name: 'Refresh now' }));
		if (kind === 'unverified') authReady.set(false);
		if (kind === 'revoked') auth.update(state => ({ ...state, isSystemAdmin: false }));
		if (kind === 'logout') logoutInProgress.set(true);
		if (kind === 'switching') projectSwitching.set(true);
		await flush(); late.resolve(snapshot('stale-version')); await flush();
		expect(screen.queryByText('private-version')).toBeNull(); expect(screen.queryByText('stale-version')).toBeNull();
		expect(screen.queryByText('Nova')).toBeNull();
	});

	it('rejects a same-tick scope ABA result before current authority is verified', async () => {
		const late = Promise.withResolvers<VersionInfo>(); mocks.get.mockReturnValue(late.promise); render(Page);
		await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(1));
		const original = get(auth); auth.set({ ...original, projectId: 'other' }); auth.set(original);
		late.resolve(snapshot('stale-version')); await flush();
		expect(screen.queryByText('stale-version')).toBeNull();
		mocks.get.mockResolvedValue(snapshot('current-version')); authReady.set(true);
		expect(await screen.findByText('current-version')).toBeTruthy();
	});

	it('retains settled data across a verified same-owner bearer rotation and uses the renewed credential on refresh', async () => {
		mocks.get.mockResolvedValue(snapshot()); render(Page); await screen.findByText('backend-version');
		setAuth(refreshAuthState({
			token: 'renewed-token', user_id: 'admin', username: 'admin', project_id: 'workspace', project_name: 'Workspace', expires_at: null,
			domain_id: 'home', domain_name: 'Home', identity_domain_id: 'home', identity_domain_name: 'Home',
			roles: get(auth).roles, is_system_admin: true,
		}, get(auth)));
		await flush();
		expect(screen.getByText('backend-version')).toBeTruthy(); expect(mocks.get).toHaveBeenCalledTimes(1);
		await fireEvent.click(screen.getByRole('button', { name: 'Refresh now' }));
		expect(mocks.get).toHaveBeenLastCalledWith('/api/v1/admin/version', 'renewed-token', 'workspace', { refresh: true });
		expect(mocks.servicesGet).toHaveBeenLastCalledWith('/api/v1/admin/service-versions', 'renewed-token', 'workspace', { refresh: true });
	});

	it('discards an unmounted request and supports system administrators without a selected project', async () => {
		auth.update(state => ({ ...state, projectId: null })); authReady.set(true);
		const late = Promise.withResolvers<VersionInfo>(); mocks.get.mockReturnValueOnce(late.promise);
		const old = render(Page); await waitFor(() => expect(mocks.get).toHaveBeenCalledWith('/api/v1/admin/version', 'admin-token', undefined, { refresh: false })); old.unmount();
		mocks.get.mockResolvedValue(snapshot('current-version')); render(Page); await screen.findByText('current-version');
		late.resolve(snapshot('stale-version')); await flush(); expect(screen.queryByText('stale-version')).toBeNull();
	});

	it('labels API and product sources without treating an unknown version as a release', async () => {
		mocks.get.mockResolvedValue(snapshot()); render(Page);
		const nova = (await screen.findByText('Nova')).closest('tr')!;
		expect(within(nova).getByText('Advertised API')).toBeTruthy();
		expect(within(nova).queryByText('Product release')).toBeNull();
		const lumen = screen.getByText('Lumen').closest('tr')!;
		expect(within(lumen).getByText('Product release')).toBeTruthy();
		const drover = screen.getByText('Drover').closest('tr')!;
		expect(within(drover).getByText('Unknown')).toBeTruthy();
		expect(within(drover).getByText('Available')).toBeTruthy();
		expect(within(screen.getByText('Palimpsest').closest('tr')!).getByText('Unavailable')).toBeTruthy();
		expect(within(screen.getByText('Waygate').closest('tr')!).getByText('Disabled')).toBeTruthy();
	});

	it.each([404, 503])('keeps base information intact when service discovery returns %s', async status => {
		mocks.get.mockResolvedValue(snapshot());
		mocks.servicesGet.mockRejectedValue(new ApiError(status, 'private diagnostic must not render'));
		render(Page); expect(await screen.findByText('backend-version')).toBeTruthy();
		expect(await screen.findByText(status === 404 ? 'This backend does not provide service-version discovery.' : /Could not refresh service versions/)).toBeTruthy();
		expect(screen.queryByText('private diagnostic must not render')).toBeNull();
		expect(screen.queryByText('Nova')).toBeNull();
	});

	it('allows service discovery to complete even when the base version read fails', async () => {
		mocks.get.mockRejectedValue(new Error('base unavailable')); render(Page);
		expect(await screen.findByText('Nova')).toBeTruthy();
		expect(await screen.findByRole('alert')).toBeTruthy();
	});

	it('retains service observations on failed refresh and refreshes both endpoints explicitly', async () => {
		mocks.get.mockResolvedValue(snapshot()); render(Page); await screen.findByText('Nova');
		mocks.servicesGet.mockRejectedValueOnce(new Error('failed'));
		await fireEvent.click(screen.getByRole('button', { name: 'Refresh now' }));
		await screen.findByText(/Could not refresh service versions/);
		expect(screen.getByText('Nova')).toBeTruthy();
		expect(mocks.servicesGet).toHaveBeenLastCalledWith('/api/v1/admin/service-versions', 'admin-token', 'workspace', { refresh: true });
	});

	it('removes previous service observations if discovery becomes unsupported', async () => {
		mocks.get.mockResolvedValue(snapshot()); render(Page); await screen.findByText('Nova');
		mocks.servicesGet.mockRejectedValueOnce(new ApiError(404, 'unsupported'));
		await fireEvent.click(screen.getByRole('button', { name: 'Refresh now' }));
		await screen.findByText('This backend does not provide service-version discovery.');
		expect(screen.queryByText('Nova')).toBeNull();
		expect(screen.getByText('backend-version')).toBeTruthy();
	});

	it('rejects late service discovery after scope ABA and unmount', async () => {
		mocks.get.mockResolvedValue(snapshot());
		const late = Promise.withResolvers<ServiceVersions>(); mocks.servicesGet.mockReturnValueOnce(late.promise);
		const old = render(Page); await screen.findByText('backend-version');
		const original = get(auth); auth.set({ ...original, projectId: 'other' }); auth.set(original);
		late.resolve(services('stale-api-version')); await flush();
		expect(screen.queryByText('stale-api-version')).toBeNull();
		authReady.set(true); await screen.findByText('Nova'); old.unmount();
		expect(screen.queryByText('Nova')).toBeNull();
	});

	it('shows a successful empty discovery as unreported, not unavailable or disabled', async () => {
		mocks.get.mockResolvedValue(snapshot()); mocks.servicesGet.mockResolvedValue({ services: [] }); render(Page);
		expect(await screen.findByText('No service versions were reported.')).toBeTruthy();
		expect(screen.queryByRole('alert')).toBeNull();
	});
});
