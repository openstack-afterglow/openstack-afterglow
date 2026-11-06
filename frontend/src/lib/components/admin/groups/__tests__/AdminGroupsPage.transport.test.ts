import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
import { tick } from 'svelte';

const { noMatch } = vi.hoisted(() => ({ noMatch: Symbol('no-match') }));
vi.mock('$app/environment', () => ({ browser: true }));
vi.mock('$lib/config/site', async () => {
	const { writable } = await import('svelte/store');
	return { siteConfig: writable({ runtime: { api_base: 'http://group.fixture' } }) };
});
vi.mock('$lib/mockup/transport', () => ({
	getActiveMockupProfile: () => null,
	maybeMockJson: async () => noMatch,
	maybeMockBlob: async () => noMatch,
	maybeMockK3sStream: () => null,
	symbolNoMatch: noMatch,
}));

import { auth, authReady } from '$lib/stores/auth';
import { t as commonT } from '$lib/i18n/ns/common';
import Page from '../AdminGroupsPage.svelte';

const initialAuth = get(auth);
const initialReady = get(authReady);
afterEach(() => {
	cleanup();
	auth.set(initialAuth);
	authReady.set(initialReady);
	vi.unstubAllGlobals();
});

function reply(data: unknown, status = 200) {
	return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'private, no-store' } });
}

it('a source ABA gets a fresh directory rather than rejoining its earlier pending real-client flight', async () => {
	const old = Promise.withResolvers<Response>();
	const started = Promise.withResolvers<void>();
	const group = { id: 'g1', name: 'Team', domain_id: 'organization', description: '', created_at: null };
	const fresh = { id: 'fresh-native-uuid', name: 'pieroot', email: 'fresh@accounts.invalid', domain_id: 'accounts', enabled: true };
	let requests = 0;
	vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
		const url = new URL(String(input));
		if (url.pathname === '/api/v1/admin/groups') return reply([group]);
		if (url.pathname === '/api/v1/admin/groups/g1/users') return reply([]);
		if (url.pathname === '/api/v1/admin/domains/organization/members') return reply({ domain_id: 'organization', items: [] });
		if (url.pathname === '/api/v1/admin/domains') return reply({ items: [
			{ id: 'accounts', name: 'Accounts', enabled: true },
			{ id: 'research', name: 'Research', enabled: true },
		] });
		if (url.pathname.endsWith('/candidates')) {
			const source = url.searchParams.get('user_domain_id');
			if (source === 'research') return reply({ domain_id: 'organization', user_domain_id: source, items: [] });
			requests += 1;
			if (requests === 1) { started.resolve(); return old.promise; }
			if (requests === 2) return reply({ detail: 'new_source_unavailable' }, 503);
			return reply({ domain_id: 'organization', user_domain_id: 'accounts', items: [fresh] });
		}
		throw new Error(`Unexpected group fixture request: ${url.pathname}`);
	}));
	auth.set({ ...initialAuth, token: 'synthetic-transport-token', refreshToken: null, accessExpiresAt: 4102444800,
		userId: 'admin', username: 'Admin', sessionId: 'group-transport-session', identityDomainId: 'accounts',
		domainId: 'organization', projectId: 'operator-project', isSystemAdmin: true });
	authReady.set(true);

	async function source(name: string) {
		await fireEvent.click(screen.getByRole('button', { name: '계정 홈 도메인' }));
		await fireEvent.click(await within(screen.getByRole('listbox', { name: '계정 홈 도메인' })).findByRole('option', { name }));
	}

	try {
		render(Page, { domainId: 'organization', domainName: 'Organization' });
		await screen.findByText(group.name);
		await fireEvent.click(screen.getByRole('button', { name: '멤버' }));
		await waitFor(() => expect((screen.getByRole('button', { name: '계정 홈 도메인' }) as HTMLButtonElement).disabled).toBe(false));
		await source('Accounts accounts');
		await started.promise;
		await source('Research research');
		await source('Accounts accounts');
		await fireEvent.input(screen.getByRole('searchbox', { name: '사용자 검색' }), { target: { value: 'pieroot' } });
		await screen.findByText('new_source_unavailable');
		old.resolve(reply({ domain_id: 'organization', user_domain_id: 'accounts', items: [{ ...fresh, id: 'stale-native-uuid', email: 'stale@accounts.invalid' }] }));
		await old.promise;
		await tick();
		expect(screen.getByText('new_source_unavailable')).toBeTruthy();
		expect(screen.queryByText('stale@accounts.invalid')).toBeNull();
		expect(screen.queryByRole('button', { name: '추가' })).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: '사용자 목록 다시 조회' }));
		await screen.findByText(fresh.email);
		expect(screen.getByText(fresh.id)).toBeTruthy();
		expect(screen.getByRole('button', { name: '추가' })).toBeTruthy();
	} finally {
		old.resolve(reply({ domain_id: 'organization', user_domain_id: 'accounts', items: [] }));
	}
});

it('keeps group inventory when a successful refresh overlaps adding a member', async () => {
	const old = Promise.withResolvers<Response>();
	const started = Promise.withResolvers<void>();
	const group = { id: 'g1', name: 'Team', domain_id: 'organization', description: '', created_at: null };
	const user = { id: 'user1', name: 'Alice', email: 'alice@example.test', domain_id: 'organization', enabled: true };
	let groupReads = 0;
	vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
		const url = new URL(String(input));
		if (url.pathname === '/api/v1/admin/groups') {
			groupReads++;
			if (groupReads === 2) { started.resolve(); return old.promise; }
			return reply([group]);
		}
		if (url.pathname === '/api/v1/admin/groups/g1/users/user1' && init?.method === 'PUT') return new Response(null, { status: 204 });
		if (url.pathname === '/api/v1/admin/groups/g1/users') return reply([]);
		if (url.pathname === '/api/v1/admin/domains/organization/members') return reply({ domain_id: 'organization', items: [user] });
		if (url.pathname === '/api/v1/admin/domains') return reply({ items: [] });
		throw new Error(`Unexpected request: ${url.pathname}`);
	}));
	auth.set({ ...initialAuth, token: 'synthetic-race-token', refreshToken: null, accessExpiresAt: 4102444800,
		userId: 'admin', username: 'Admin', sessionId: 'group-race-session', identityDomainId: 'organization',
		domainId: 'organization', projectId: 'operator-project', isSystemAdmin: true });
	authReady.set(true);
	try {
		render(Page, { domainId: 'organization', domainName: 'Organization' });
		await screen.findByText('Team');
		await fireEvent.click(screen.getByRole('button', { name: '멤버' }));
		await screen.findByText(user.email);
		await fireEvent.click(screen.getByRole('button', { name: commonT('autoRefresh.refreshNow') }));
		await started.promise;
		await fireEvent.click(screen.getByRole('button', { name: '추가' }));
		old.resolve(reply([group]));
		await old.promise;
		await waitFor(() => expect(groupReads).toBe(3));
		expect(screen.getByText('Team')).toBeTruthy();
		expect(screen.queryByText('그룹 목록 조회 실패')).toBeNull();
	} finally { old.resolve(reply([group])); }
});
