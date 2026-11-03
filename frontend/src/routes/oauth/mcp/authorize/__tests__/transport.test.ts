import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { get } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { auth, clearAuth, projectSwitching, setAuth } from '$lib/stores/auth';
import { refreshSession } from '$lib/api/client';
import type * as ApiClient from '$lib/api/client';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/public-entry';
import { t as commonT } from '$lib/i18n/ns/common';
import { pendingMcpConsentTicket, postAuthDestination } from '$lib/utils/mcpConsent';

const { goto, page, metadataGet } = vi.hoisted(() => {
	let value = { url: new URL('http://localhost/oauth/mcp/authorize'), data: {} };
	const subscribers = new Set<(next: typeof value) => void>();
	return {
		goto: vi.fn(),
		metadataGet: vi.fn(),
		page: {
			subscribe(run: (next: typeof value) => void) {
				subscribers.add(run);
				run(value);
				return () => subscribers.delete(run);
			},
			set(next: typeof value) {
				value = next;
				for (const run of subscribers) run(value);
			},
		},
	};
});
vi.mock('$app/navigation', () => ({ goto }));
vi.mock('$app/stores', () => ({ page }));
vi.mock('$lib/api/client', async (importOriginal) => {
	const actual = await importOriginal<typeof ApiClient>();
	// Only metadata is stubbed. Decisions exercise the real refresh/recovery
	// transport, including its request signal and global unauthorized handling.
	return { ...actual, api: { ...actual.api, get: metadataGet } };
});

import Page from '../+page.svelte';

const ticket = 'A'.repeat(43);
const otherTicket = 'B'.repeat(43);
const actor = { token: 'token-a', userId: 'user-a', projectId: 'project-a', refreshToken: 'refresh-a', accessExpiresAt: null, domainId: 'domain-1', identityDomainId: 'domain-1' };
const mockFetch = vi.fn();
const assign = vi.fn();
const replace = vi.fn();
const changes = ['token', 'user', 'project', 'switch-aba', 'ticket-aba', 'owner-aba', 'unmount'] as const;

function deferred<T>() {
	let resolve!: (value: T) => void;
	const promise = new Promise<T>((yes) => { resolve = yes; });
	return { promise, resolve };
}
function setTicket(value: string) {
	page.set({ url: new URL(`http://localhost/oauth/mcp/authorize?ticket=${value}`), data: {} });
}
function changeOwner(kind: typeof changes[number], unmount: () => void) {
	if (kind === 'token') setAuth({ ...actor, token: 'token-b' });
	else if (kind === 'user') setAuth({ ...actor, userId: 'user-b' });
	else if (kind === 'project') setAuth({ ...actor, projectId: 'project-b' });
	else if (kind === 'switch-aba') { projectSwitching.set(true); projectSwitching.set(false); }
	else if (kind === 'ticket-aba') { setTicket(otherTicket); setTicket(ticket); }
	else if (kind === 'owner-aba') { setAuth({ ...actor, userId: 'user-b' }); setAuth(actor); }
	else unmount();
}
function decisions() {
	return mockFetch.mock.calls.filter(([url]) => /\/consents\/[^/]+\/(approve|deny)$/.test(String(url)));
}
async function reviewPermissions() {
	await fireEvent.click(await screen.findByRole('button', { name: commonT('pagination.next') }));
	await screen.findByRole('checkbox', { name: t('mcpConsent.duration.ongoingLabel') });
}
async function approve() {
	await reviewPermissions();
	await fireEvent.click(await screen.findByRole('button', { name: t('mcpConsent.actions.allowRead') }));
}

beforeEach(() => {
	vi.clearAllMocks();
	mockFetch.mockReset();
	initLocale('ko');
	localStorage.clear();
	sessionStorage.clear();
	clearAuth();
	projectSwitching.set(false);
	setAuth(actor);
	setTicket(ticket);
	metadataGet.mockImplementation(async (path: string) => path === '/api/v1/auth/mcp-projects?preview=true'
		? ['a', 'b'].map((id) => ({
			id: `project-${id}`, name: id === 'a' ? 'Current project' : 'Second project',
			can_write: id === 'a', service_permissions: { drover: [], palimpsest: [], waygate: [], lumen: [] }, service_errors: {},
		}))
		: { client_id: 'desktop', client_name: 'Desktop MCP', redirect_uri: 'https://client.example.test/callback', scopes: ['mcp:read', 'mcp:write'], grant_deadline: '2026-12-31T23:59:59Z', ongoing_supported: true });
	const realWindow = window;
	vi.stubGlobal('window', new Proxy(realWindow, {
		get(target, key) {
			return key === 'location'
				? { assign, replace, pathname: '/oauth/mcp/authorize', protocol: 'http:', hostname: 'localhost' }
				: Reflect.get(target, key, target);
		},
	}));
	vi.stubGlobal('fetch', mockFetch);
});
afterEach(() => {
	cleanup();
	vi.unstubAllGlobals();
	projectSwitching.set(false);
	clearAuth();
	localStorage.clear();
	sessionStorage.clear();
	initLocale('ko');
});

describe('MCP consent real decision transport', () => {
	it('sends an attenuated read payload with explicit projects and no-store transport', async () => {
		mockFetch.mockResolvedValueOnce(Response.json({ redirect_uri: 'https://client.example.test/approved', effective_ongoing: true }));
		render(Page);
		await approve();
		await waitFor(() => expect(assign).toHaveBeenCalledWith('https://client.example.test/approved'));
		const [url, options] = decisions()[0];
		expect(String(url)).toContain(`/api/v1/auth/mcp-oauth/consents/${ticket}/approve`);
		expect(JSON.parse(options.body)).toEqual({ access_level: 'read', project_scope: 'selected', project_ids: ['project-a'], ongoing: true });
		expect(new Headers(options.headers).get('Authorization')).toBe('Bearer token-a');
		expect(new Headers(options.headers).get('X-Project-Id')).toBe('project-a');
		expect(options.cache).toBe('no-store');
		expect(options.credentials).toBe('include');
		expect(pendingMcpConsentTicket()).toBeNull();
	});

	it.each([{}, { effective_ongoing: false }])('omits ongoing from the real transport after finite opt-out %j', async (confirmation) => {
		mockFetch.mockResolvedValueOnce(Response.json({ redirect_uri: 'https://client.example.test/approved', ...confirmation }));
		render(Page);
		await reviewPermissions();
		await fireEvent.click(screen.getByRole('checkbox', { name: t('mcpConsent.duration.ongoingLabel') }));
		expect(decisions()).toHaveLength(0);
		await fireEvent.click(screen.getByRole('button', { name: t('mcpConsent.actions.allowRead') }));
		await waitFor(() => expect(assign).toHaveBeenCalledWith('https://client.example.test/approved'));
		expect(JSON.parse(decisions()[0][1].body)).toEqual({ access_level: 'read', project_scope: 'selected', project_ids: ['project-a'] });
	});

	it('keeps the old finite GET and approval wire contract truthful during a rolling upgrade', async () => {
		const currentGet = metadataGet.getMockImplementation()!;
		metadataGet.mockImplementation(async (path: string) => {
			const result = await currentGet(path);
			if (path === '/api/v1/auth/mcp-projects?preview=true') return result;
			const legacy = { ...result };
			delete legacy.ongoing_supported;
			return legacy;
		});
		mockFetch.mockResolvedValueOnce(Response.json({ redirect_uri: 'https://client.example.test/approved' }));
		render(Page);
		await approve();
		await waitFor(() => expect(assign).toHaveBeenCalledWith('https://client.example.test/approved'));
		expect(JSON.parse(decisions()[0][1].body)).toEqual({ access_level: 'read', project_scope: 'selected', project_ids: ['project-a'] });
	});

	it.each([{}, { effective_ongoing: false }, { effective_ongoing: 'true' }])('halts an unconfirmed ongoing HTTP result without redirect or replay %j', async (confirmation) => {
		mockFetch.mockResolvedValueOnce(Response.json({ redirect_uri: 'https://client.example.test/approved', ...confirmation }));
		render(Page);
		await approve();
		await screen.findByText(t('mcpConsent.error.durationUnconfirmed'));
		expect(decisions()).toHaveLength(1);
		expect(JSON.parse(decisions()[0][1].body).ongoing).toBe(true);
		expect(assign).not.toHaveBeenCalled();
		expect(pendingMcpConsentTicket()).toBeNull();
		expect(postAuthDestination('/dashboard')).toBe('/dashboard');
		expect(screen.queryByRole('button', { name: t('mcpConsent.actions.allowRead') })).toBeNull();
		expect(screen.queryByRole('button', { name: t('mcpConsent.actions.retry') })).toBeNull();
	});

	it('does not treat a revoked authorization rejection as approval or automatically retry it', async () => {
		mockFetch.mockResolvedValueOnce(Response.json({ detail: 'Authorization revoked' }, { status: 403 }));
		render(Page);
		await approve();
		await screen.findByText('Authorization revoked');
		expect(decisions()).toHaveLength(1);
		expect(JSON.parse(decisions()[0][1].body).ongoing).toBe(true);
		expect(assign).not.toHaveBeenCalled();
		expect(pendingMcpConsentTicket()).toBe(ticket);
		expect((screen.getByRole('checkbox', { name: t('mcpConsent.duration.ongoingLabel') }) as HTMLInputElement).disabled).toBe(false);
		expect(get(auth).userId).toBe(actor.userId);
	});

	it.each(changes)('cancels a captured payload waiting for refresh after %s', async (kind) => {
		setAuth({ ...actor, accessExpiresAt: 1 });
		const refresh = deferred<Response>();
		let settlement: Promise<string | null> | null = null;
		mockFetch.mockImplementation((url: string) => {
			if (url.endsWith('/api/v1/auth/refresh')) return refresh.promise;
			throw new Error(`Unexpected decision dispatch: ${url}`);
		});
		const rendered = render(Page);
		try {
			await approve();
			await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(1));
			expect(String(mockFetch.mock.calls[0][0])).toContain('/api/v1/auth/refresh');
			settlement = refreshSession();
			await act(() => changeOwner(kind, rendered.unmount));
			await act(async () => {
				refresh.resolve(Response.json({ token: 'refreshed-token', refresh_token: 'refreshed-refresh', domain_id: 'domain-1', identity_domain_id: 'domain-1', identity_domain_name: 'Domain', user_id: 'user-a' }));
				await settlement;
			});
			expect(decisions()).toHaveLength(0);
			expect(assign).not.toHaveBeenCalled();
			expect(replace).not.toHaveBeenCalled();
			expect(goto).not.toHaveBeenCalled();
			expect(pendingMcpConsentTicket()).toBe(ticket);
		} finally {
			refresh.resolve(Response.json({ token: 'settled-token', refresh_token: 'settled-refresh', domain_id: 'domain-1', identity_domain_id: 'domain-1', identity_domain_name: 'Domain', user_id: 'user-a' }));
			await settlement;
		}
	});

	it.each(changes)('does not retry or globally redirect a late 401 after %s', async (kind) => {
		const response = deferred<Response>();
		mockFetch.mockReturnValueOnce(response.promise);
		const rendered = render(Page);
		try {
			await approve();
			await waitFor(() => expect(decisions()).toHaveLength(1));
			const signal = decisions()[0][1].signal as AbortSignal;
			await act(() => changeOwner(kind, rendered.unmount));
			const replacement = get(auth);
			expect(signal.aborted).toBe(true);
			await act(async () => response.resolve(Response.json({ detail: 'old request expired' }, { status: 401 })));
			expect(mockFetch).toHaveBeenCalledTimes(1);
			expect(get(auth).token).toBe(replacement.token);
			expect(get(auth).userId).toBe(replacement.userId);
			expect(get(auth).projectId).toBe(replacement.projectId);
			expect(assign).not.toHaveBeenCalled();
			expect(replace).not.toHaveBeenCalled();
			expect(goto).not.toHaveBeenCalled();
			expect(pendingMcpConsentTicket()).toBe(ticket);
		} finally {
			response.resolve(Response.json({ detail: 'settled' }, { status: 401 }));
		}
	});

	it('handles a current 401 locally without consuming the ticket or clearing the owner', async () => {
		setAuth({ ...actor, refreshToken: null });
		mockFetch.mockResolvedValueOnce(Response.json({ detail: 'Consent session expired' }, { status: 401 }));
		render(Page);
		await approve();
		await screen.findByText('Consent session expired');
		expect(get(auth).token).toBe(actor.token);
		expect(get(auth).userId).toBe(actor.userId);
		expect(goto).not.toHaveBeenCalled();
		expect(assign).not.toHaveBeenCalled();
		expect(replace).not.toHaveBeenCalled();
		expect(pendingMcpConsentTicket()).toBe(ticket);
	});
});
