import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { writable } from 'svelte/store';
import { tick } from 'svelte';
import type * as DomainsModule from '$lib/api/domains';

const mocks = vi.hoisted(() => ({ get: vi.fn(), list: vi.fn() }));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token', projectId: 'caller-project', userId: 'admin', isSystemAdmin: true, domainId: 'working', sessionId: 'session' }),
	authReady: writable(true), projectSwitching: writable(false), logoutInProgress: writable(false),
}));
vi.mock('$lib/api/client', () => ({ api: { get: mocks.get, prefetch: vi.fn() }, fetchWithAuth: vi.fn(), ApiError: class extends Error {} }));
vi.mock('$lib/api/domains', async importOriginal => ({ ...(await importOriginal<typeof DomainsModule>()), domainsApi: { list: mocks.list } }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({ createAutoRefresh: () => ({ active: false, intervalSeconds: 60, intervalOptions: [30, 60] }) }));

import Users from '../../../../routes/admin/users/+page.svelte';
import Projects from '../../../../routes/admin/projects/+page.svelte';
import ProjectDetail from '../../../../routes/admin/projects/[id]/+page.svelte';
import Groups from '../../../../routes/admin/groups/+page.svelte';
import Applications from '../../../../routes/admin/application-credentials/+page.svelte';
import Credentials from '../../../../routes/admin/user-credentials/+page.svelte';
import ChatQuotas from '../../../../routes/admin/chat/quotas/+page.svelte';
import { page } from '$app/state';
import { auth, authReady, projectSwitching } from '$lib/stores/auth';
import { t } from '$lib/i18n/ns/domain-admin';

const domain = { id: 'selected-domain', name: 'Selected domain', enabled: true };
const user = { id: 'user-a', name: 'Scoped user', email: 'scope@example.invalid', enabled: true, domain_id: domain.id };
beforeEach(() => {
	mocks.get.mockReset().mockImplementation((path: string) => Promise.resolve(path.includes('/activity?') ? [] : { items: [user], next_marker: null }));
	mocks.list.mockReset().mockResolvedValue({ items: [domain] });
	auth.set({ token: 'token', projectId: 'caller-project', userId: 'admin', isSystemAdmin: true, domainId: 'working', sessionId: 'session' } as never);
	authReady.set(true); projectSwitching.set(false);
	Object.assign(page, { url: new URL('http://localhost/admin/users') });
});
afterEach(cleanup);

describe('required IAM domain boundaries', () => {
	it.each([
		['users', Users], ['projects', Projects], ['project detail', ProjectDetail], ['groups', Groups],
		['application credentials', Applications], ['user credentials', Credentials], ['chat quotas', ChatQuotas],
	] as const)('does not mount %s inventory under an implicit all-domain scope', async (_name, component) => {
		render(component);
		await screen.findByText(t('scope.required'));
		expect(mocks.get).not.toHaveBeenCalled();
	});
	it('does not publish a domain-scoped user page until the current authority directory is verified', async () => {
		const directory = Promise.withResolvers<unknown>(); mocks.list.mockReturnValueOnce(directory.promise);
		Object.assign(page, { url: new URL(`http://localhost/admin/users?domain_id=${domain.id}`) });
		render(Users);
		expect(mocks.get).not.toHaveBeenCalled();
		directory.resolve({ items: [domain] });
		await screen.findByText('Scoped user');
		for (const [path, token, project] of mocks.get.mock.calls) {
			expect(new URL(path, 'http://localhost').searchParams.get('domain_id')).toBe(domain.id);
			expect([token, project]).toEqual(['token', 'caller-project']);
		}
	});
	it('rejects a foreign user directory without exposing its edit actions', async () => {
		Object.assign(page, { url: new URL(`http://localhost/admin/users?domain_id=${domain.id}`) });
		mocks.get.mockImplementation((path: string) => Promise.resolve(path.includes('/activity?') ? [] : { items: [{ ...user, domain_id: 'foreign' }], next_marker: null }));
		render(Users);
		await screen.findByRole('alert');
		expect(screen.queryByText('Scoped user')).toBeNull();
	});
	it('rechecks the selected domain before remounting user data for a changed caller project', async () => {
		Object.assign(page, { url: new URL(`http://localhost/admin/users?domain_id=${domain.id}`) });
		render(Users); await screen.findByText('Scoped user');
		const directory = Promise.withResolvers<unknown>(); mocks.list.mockReturnValueOnce(directory.promise);
		auth.update(state => ({ ...state, projectId: 'new-project' })); await tick();
		expect(screen.queryByText('Scoped user')).toBeNull();
		const count = mocks.get.mock.calls.length;
		directory.resolve({ items: [domain] }); await screen.findByText('Scoped user');
		expect(mocks.get.mock.calls.slice(count).every(([, , project]) => project === 'new-project')).toBe(true);
	});
	it('preserves a denied domain lookup instead of mounting an empty successful user inventory', async () => {
		Object.assign(page, { url: new URL(`http://localhost/admin/users?domain_id=${domain.id}`) });
		mocks.list.mockRejectedValue(new Error('denied'));
		render(Users); await screen.findByText(t('scope.loadFailed'));
		expect(mocks.get).not.toHaveBeenCalled();
	});
	it('unmounts user data while authority is switching or revoked', async () => {
		Object.assign(page, { url: new URL(`http://localhost/admin/users?domain_id=${domain.id}`) });
		render(Users); await screen.findByText('Scoped user');
		projectSwitching.set(true); await tick();
		expect(screen.queryByText('Scoped user')).toBeNull();
		auth.update(state => ({ ...state, isSystemAdmin: false })); projectSwitching.set(false);
		await waitFor(() => expect(screen.queryByText('Scoped user')).toBeNull());
	});
	it('never mounts an IAM child with initial metadata after same-tick authority ABA while the directory is pending', async () => {
		const initial = Promise.withResolvers<unknown>();
		const fresh = Promise.withResolvers<unknown>();
		mocks.list.mockReturnValueOnce(initial.promise).mockReturnValueOnce(fresh.promise);
		Object.assign(page, { url: new URL(`http://localhost/admin/users?domain_id=${domain.id}`) });
		render(Users);
		await waitFor(() => expect(mocks.list).toHaveBeenCalledTimes(1));
		auth.update(state => ({ ...state, projectId: 'temporary-project' }));
		auth.update(state => ({ ...state, projectId: 'caller-project' }));
		await waitFor(() => expect(mocks.list).toHaveBeenCalledTimes(2));
		initial.resolve({ items: [{ ...domain, name: 'Obsolete metadata' }] });
		await tick(); await tick();
		expect(mocks.get).not.toHaveBeenCalled();
		expect(screen.queryByText('Scoped user')).toBeNull();
		fresh.resolve({ items: [{ ...domain, name: 'Fresh metadata' }] });
		await screen.findByText('Scoped user');
		await fireEvent.click(screen.getByRole('button', { name: t('scope.domain') }));
		expect(screen.queryByRole('option', { name: /Obsolete metadata/ })).toBeNull();
		expect(screen.getByRole('option', { name: /Fresh metadata/ })).toBeTruthy();
	});
});
