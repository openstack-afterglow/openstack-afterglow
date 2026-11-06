import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { acceptAuthVerification, auth, authReady, clearAuth, getAuthVerificationEpoch, logoutInProgress, projectSwitching, setAuth, setProject } from '$lib/stores/auth';
import { siteConfig } from '$lib/config/site';
import { t } from '$lib/i18n/ns/account';
import { t as tp } from '$lib/i18n/ns/public-entry';
import type { McpConsentProject } from '$lib/utils/mcpConsentPermissions';
import { initLocale, intlLocale } from '$lib/i18n/runtime.svelte';
import { get } from 'svelte/store';

const { api, ApiError, confirmDialog, getBaseUrl } = vi.hoisted(() => ({
	api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
	ApiError: class ApiError extends Error {},
	confirmDialog: vi.fn(),
	getBaseUrl: vi.fn(() => 'https://api.example.test'),
}));

vi.mock('$lib/api/client', () => ({ api, ApiError, getBaseUrl }));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog, dialogState: { requestId: 0, open: false, reject: vi.fn() } }));
vi.mock('$app/stores', async () => {
	const { readable } = await import('svelte/store');
	return { page: readable({ data: {}, url: new URL('https://afterglow.example.test/dashboard/account') }) };
});

import McpAccessSection from '../McpAccessSection.svelte';
import type { McpClientObservation } from '../McpAccessSection.svelte';

const clipboardDescriptor = Object.getOwnPropertyDescriptor(navigator, 'clipboard');
const scopedPostOptions = { signal: expect.any(AbortSignal), suppressAuthRedirect: true, cache: 'no-store' };
const clock = '2028-01-31T23:45:12.345Z';
const defaultExpiry = '2028-02-29T23:45:12.345Z';
const scopedGetOptions = { refresh: true, signal: expect.any(AbortSignal), suppressAuthRedirect: true };
const connectionResult = {
	endpoint: 'https://cloud.dmslab.re.kr/mcp',
	protocol_version: '2025-11-25',
	server_name: 'Afterglow',
	server_version: '1.0',
	tool_count: 5,
};

const activeToken = {
	id: 'token-1',
	grant_id: 'grant-1',
	name: 'Lumen',
	owner_project_id: 'project',
	owner_project_name: 'Saved issuance origin',
	source: 'personal_token',
	access_level: 'read',
	project_scope: 'current',
	project_ids: ['project'],
	projects: [{ id: 'project', name: 'Saved home project' }],
	status: 'active',
	visible_prefix: 'mcp-afgl-example',
	issued_at: '2026-07-27T00:00:00Z',
	expires_at: '2026-08-27T00:00:00Z',
	last_used_at: null,
	revoked_at: null,
	is_lumen_default: true,
	client_observations: [] as McpClientObservation[],
};

const availableProjects = [
	{ id: 'project', name: 'Project' },
	{ id: 'other', name: 'Other project' },
];
const previewProjects: McpConsentProject[] = availableProjects.map((project) => ({
	...project, can_write: true,
	service_permissions: {
		drover: ['drover-inventory_reader', 'drover-clusters_editor'],
		palimpsest: ['palimpsest-download_user'], waygate: [],
		lumen: ['lumen-history_reader', 'lumen-chat_user', 'lumen-tools_user'],
	},
	service_errors: {},
}));

function accountResponse(path: string, personalTokens = [activeToken]) {
	return path === '/api/v1/auth/mcp-projects?preview=true' ? previewProjects
		: path.endsWith('/mcp-projects') ? availableProjects : path.includes('oauth') ? [] : personalTokens;
}
async function selectMethod(method: 'oauth' | 'api') {
	await fireEvent.click(screen.getByRole('button', { name: t(method === 'oauth' ? 'mcp.methodOAuth' : 'mcp.methodApiKey') }));
}

async function renderApi() {
	const view = render(McpAccessSection);
	await selectMethod('api');
	return view;
}

function configBlock(target: 'oauth' | 'setup' | 'config') {
	const block = document.querySelector(`[data-mcp-config="${target}"]`);
	expect(block).not.toBeNull();
	return block as HTMLElement;
}

function configJson(target: 'oauth' | 'setup' | 'config') {
	return JSON.parse(within(configBlock(target)).getByRole('region', { name: t(target === 'oauth' ? 'mcp.oauthConfig' : 'mcp.config') }).textContent!);
}

function clipboard(writeText = vi.fn().mockResolvedValue(undefined)) {
	Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
	return writeText;
}


async function createButton() {
	const button = await screen.findByRole('button', { name: t('mcp.create') });
	await waitFor(() => expect(button.hasAttribute('disabled')).toBe(false));
	return button;
}

function projectCheckbox(id: string, name: string) {
	return screen.getByRole('checkbox', { name: t('mcp.selectProject', { name, id }) }) as HTMLInputElement;
}

function deferred<T>() {
	return Promise.withResolvers<T>();
}

function verifyAuth() {
	// Model /auth/me acceptance for the current credentials and scope, never for an old epoch.
	// Keep this separate from setAuth/setProject: unverified boundaries must stay unverified.
	expect(acceptAuthVerification(getAuthVerificationEpoch(), {})).toBe(true);
}

describe('McpAccessSection', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		vi.useFakeTimers({ toFake: ['Date'] });
		vi.setSystemTime(new Date(clock));
		initLocale('ko');
		confirmDialog.mockResolvedValue(true);
		clearAuth();
		setAuth({
			token: 'token',
			refreshToken: 'refresh-token',
			userId: 'user',
			username: 'user',
			projectId: 'project',
			projectName: 'Project',
			domainId: 'domain-a',
			identityDomainId: 'identity-home',
			accessExpiresAt: null,
			roles: [],
		});
		verifyAuth();
		projectSwitching.set(false);
		logoutInProgress.set(false);
		siteConfig.update((config) => ({ ...config, mcp_url: '', services: { ...config.services, mcp: true } }));
		api.get.mockImplementation((path: string) => Promise.resolve(accountResponse(path)));
		api.post.mockResolvedValue({ ...activeToken, id: 'token-2', grant_id: 'grant-2', token: 'mcp-afgl-secret-value' });
	});

	afterEach(() => {
		cleanup();
		vi.useRealTimers();
		initLocale('ko');
		if (clipboardDescriptor) Object.defineProperty(navigator, 'clipboard', clipboardDescriptor);
		else Reflect.deleteProperty(navigator, 'clipboard');
		projectSwitching.set(false);
		logoutInProgress.set(false);
		clearAuth();
		siteConfig.update((config) => ({ ...config, services: { ...config.services, mcp: false } }));
	});

	it.each(['oauth', 'api'] as const)('lists the same account-owned %s connection across projects, domains and no workspace', async (selected) => {
		const record = { ...activeToken, name: 'Account-owned connection', owner_project_id: 'issuance-project', owner_project_name: 'Saved origin',
			projects: [{ id: 'approved-one', name: 'Saved approved one' }, { id: 'approved-two', name: 'Saved approved two' }] };
		let removed = false;
		api.get.mockImplementation((path: string) => Promise.resolve(path.startsWith('/api/v1/auth/mcp-projects')
			? accountResponse(path) : path.includes('oauth') === (selected === 'oauth') && !removed ? [record] : []));
		api.delete.mockImplementation(() => { removed = true; return Promise.resolve(); });
		render(McpAccessSection);
		if (selected === 'api') await selectMethod('api');
		for (const workspace of [
			{ projectId: 'project', domainId: 'domain-a' },
			{ projectId: 'other', domainId: 'domain-a' },
			{ projectId: 'domain-b-project', domainId: 'domain-b' },
			{ projectId: null, domainId: null },
		]) {
			setAuth({ token: 'token', ...workspace });
			verifyAuth();
			await screen.findByText(t('mcp.issuingProject', { project: 'Saved origin' }));
			const restrictions = screen.getByRole('group', { name: t('mcp.savedRestrictions') });
			expect(restrictions.textContent).toContain('Saved approved one');
			expect(restrictions.textContent).toContain('Saved approved two');
			expect(screen.getByRole('button', { name: t(selected === 'oauth' ? 'mcp.revokeAccess' : 'mcp.revoke') }).hasAttribute('disabled')).toBe(false);
			expect(screen.queryByRole('button', { name: t('mcp.setLumen') })).toBeNull();
			expect(screen.queryByRole('button', { name: t('mcp.clearLumen') })).toBeNull();
		}
		expect(screen.getByText(t('mcp.workspaceRequired'))).toBeTruthy();
		expect(screen.queryByRole('button', { name: t('mcp.create') })).toBeNull();
		expect(screen.queryByRole('button', { name: t('mcp.verify') })).toBeNull();
		expect(screen.queryByRole('heading', { name: t('mcp.previewTitle') })).toBeNull();
		for (const [path, token, project] of api.get.mock.calls) {
			if (!path.startsWith('/api/v1/auth/mcp-projects')) {
				expect(token).toBe('token');
				expect(project).toBeUndefined();
			}
		}
		await fireEvent.click(screen.getByRole('button', { name: t(selected === 'oauth' ? 'mcp.revokeAccess' : 'mcp.revoke') }));
		await waitFor(() => expect(api.delete).toHaveBeenCalledExactlyOnceWith(selected === 'oauth'
			? '/api/v1/auth/mcp-oauth/grants/grant-1' : '/api/v1/auth/mcp-tokens/token-1', 'token'));
		await screen.findByText(t(selected === 'oauth' ? 'mcp.emptyOAuth' : 'mcp.emptyTokens'));
	});

	it.each(['oauth', 'api'] as const)('loads and revokes %s with only a verified identity and never fetches issuance projects', async (selected) => {
		setAuth({ token: 'token', projectId: null, domainId: null });
		verifyAuth();
		const record = { ...activeToken, name: 'Identity-only connection' };
		api.get.mockImplementation((path: string) => Promise.resolve(path.includes('oauth') === (selected === 'oauth') ? [record] : []));
		api.delete.mockResolvedValue(undefined);
		const writeText = clipboard();
		render(McpAccessSection);
		if (selected === 'api') await selectMethod('api');
		await screen.findByText(t('mcp.issuingProject', { project: record.owner_project_name }));
		expect(api.get.mock.calls.some(([path]) => path.startsWith('/api/v1/auth/mcp-projects'))).toBe(false);
		expect(screen.queryByLabelText(t('mcp.name'))).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: t(selected === 'oauth' ? 'mcp.copyOAuthConfig' : 'mcp.copySetupConfig') }));
		await waitFor(() => expect(writeText).toHaveBeenCalledOnce());
		await fireEvent.click(screen.getByRole('button', { name: t(selected === 'oauth' ? 'mcp.revokeAccess' : 'mcp.revoke') }));
		await waitFor(() => expect(api.delete).toHaveBeenCalledExactlyOnceWith(selected === 'oauth'
			? '/api/v1/auth/mcp-oauth/grants/grant-1' : '/api/v1/auth/mcp-tokens/token-1', 'token'));
	});

	it.each(['oauth', 'api'] as const)('clears %s account rows and pending confirmation on a different actor', async (selected) => {
		const confirmation = deferred<boolean>();
		confirmDialog.mockReturnValue(confirmation.promise);
		api.get.mockImplementation((path: string, token: string) => Promise.resolve(path.startsWith('/api/v1/auth/mcp-projects')
			? accountResponse(path) : token === 'token' && path.includes('oauth') === (selected === 'oauth') ? [activeToken] : []));
		render(McpAccessSection);
		if (selected === 'api') await selectMethod('api');
		await screen.findByRole('group', { name: t('mcp.savedRestrictions') });
		await fireEvent.click(screen.getByRole('button', { name: t(selected === 'oauth' ? 'mcp.revokeAccess' : 'mcp.revoke') }));
		setAuth({ token: 'other-actor-token', userId: 'other-actor', projectId: null });
		verifyAuth();
		await screen.findByText(t(selected === 'oauth' ? 'mcp.emptyOAuth' : 'mcp.emptyTokens'));
		await act(async () => { confirmation.resolve(true); });
		expect(api.delete).not.toHaveBeenCalled();
		expect(screen.queryByRole('group', { name: t('mcp.savedRestrictions') })).toBeNull();
	});

	it.each((['oauth', 'api'] as const).flatMap(selected => (['actor', 'logout'] as const).map(boundary => [selected, boundary] as const)))('drops late %s revoke feedback after %s invalidates account state', async (selected, boundary) => {
		const mutation = deferred<void>();
		api.get.mockImplementation((path: string) => Promise.resolve(path.startsWith('/api/v1/auth/mcp-projects')
			? accountResponse(path) : path.includes('oauth') === (selected === 'oauth') ? [activeToken] : []));
		api.delete.mockReturnValue(mutation.promise);
		render(McpAccessSection);
		if (selected === 'api') await selectMethod('api');
		await screen.findByRole('group', { name: t('mcp.savedRestrictions') });
		await fireEvent.click(screen.getByRole('button', { name: t(selected === 'oauth' ? 'mcp.revokeAccess' : 'mcp.revoke') }));
		await waitFor(() => expect(api.delete).toHaveBeenCalledOnce());
		if (boundary === 'logout') logoutInProgress.set(true);
		else setAuth({ userId: 'different-actor', token: 'different-token', projectId: null });
		await waitFor(() => expect(screen.queryByRole('group', { name: t('mcp.savedRestrictions') })).toBeNull());
		await act(async () => { mutation.reject(new ApiError('Old actor mutation error')); });
		expect(screen.queryByText('Old actor mutation error')).toBeNull();
		expect(screen.queryByRole('heading', { name: t('mcp.title') })).toBeNull();
		expect(api.delete).toHaveBeenCalledOnce();
	});

	it.each(['identity-domain', 'working-domain', 'session', 'readiness', 'logout'] as const)('fences account list reads and removal through same-tick %s ABA', async (boundary) => {
		const confirmation = deferred<boolean>();
		const stale = deferred<typeof activeToken[]>();
		confirmDialog.mockReturnValue(confirmation.promise);
		await renderApi();
		await screen.findByRole('group', { name: t('mcp.savedRestrictions') });
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.revoke') }));
		api.get.mockImplementation((path: string) => path === '/api/v1/auth/mcp-tokens' ? stale.promise : Promise.resolve(accountResponse(path)));
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.refresh') }));
		const signal = api.get.mock.calls.findLast(([path]) => path === '/api/v1/auth/mcp-tokens')![3].signal as AbortSignal;
		api.get.mockImplementation((path: string) => Promise.resolve(accountResponse(path, [{ ...activeToken, name: 'Fresh account row' }])));
		const before = get(auth);
		if (boundary === 'readiness') { authReady.set(false); authReady.set(true); }
		else if (boundary === 'logout') { logoutInProgress.set(true); logoutInProgress.set(false); }
		else {
			const key = boundary === 'session' ? 'sessionId' : boundary === 'working-domain' ? 'domainId' : 'identityDomainId';
			setAuth({ token: 'token', [key]: 'foreign' });
			setAuth({ token: 'token', [key]: before[key] });
			verifyAuth();
		}
		await screen.findByText('Fresh account row');
		await act(async () => { confirmation.resolve(true); stale.resolve([{ ...activeToken, name: 'Stale account row' }]); });
		expect(api.delete).not.toHaveBeenCalled();
		expect(screen.queryByText('Stale account row')).toBeNull();
		expect(screen.getByText('Fresh account row')).toBeTruthy();
		expect(signal.aborted).toBe(true);
	});

	it.each((['ko', 'en', 'ja', 'zh-CN'] as const).flatMap((locale) => (['oauth', 'api'] as const).map((method) => [locale, method] as const)))('shows grant-owned escaped client identity with details closed and credential-wide removal in %s via %s', async (locale, selected) => {
		initLocale(locale);
		const hostile = '<img src=x onerror="window.clientLeak=1">';
		const observed = {
			client_name: hostile, client_version: '<script>private()</script>', product: 'Claimed product', kind: 'agent',
			identity_source: 'client_info', browser: 'Browser 123', os: 'OS 14',
			first_seen_at: '2026-07-01T00:00:00Z', last_seen_at: '2026-07-08T00:00:00Z',
		} satisfies McpClientObservation;
		const unknown: McpClientObservation = { client_name: null, client_version: null, product: null, kind: 'unknown', identity_source: 'unknown', browser: null, os: null, first_seen_at: null, last_seen_at: null };
		const record = { ...activeToken, name: 'Shared credential', source: selected === 'oauth' ? 'oauth' : 'personal_token', client_observations: [observed, unknown], token: 'must-not-render-secret' };
		let rows = [record];
		api.get.mockImplementation((path: string) => Promise.resolve(path.startsWith('/api/v1/auth/mcp-projects') ? accountResponse(path) : path.includes('oauth') === (selected === 'oauth') ? rows : []));
		api.delete.mockImplementation(() => { rows = []; return Promise.resolve(); });
		render(McpAccessSection);
		if (selected === 'api') await selectMethod('api');
		await screen.findByRole('group', { name: t('mcp.observations') });
		const observations = screen.getByRole('group', { name: t('mcp.observations') });
		expect(within(observations).getByText(t('mcp.observationHelp'))).toBeTruthy();
		expect(within(observations).getByText(tp('mcpClients.count', { count: 2 }))).toBeTruthy();
		const summaries = observations.querySelectorAll('summary');
		expect(summaries).toHaveLength(2);
		const details = summaries[0].closest('details')!;
		expect(details.open).toBe(false);
		expect(within(summaries[0]).getByText(hostile)).toBeTruthy();
		expect(summaries[0].textContent).toContain(observed.client_version);
		expect(observations.querySelector('img,script')).toBeNull();
		expect(within(summaries[1]).getByText(t('mcp.unknownClient'))).toBeTruthy();
		expect(within(summaries[1]).getByText(t('mcp.clientEvidence', { source: t('mcp.clientSource.unknown') }))).toBeTruthy();
		expect(summaries[1].closest('details')!.open).toBe(false);
		await fireEvent.click(summaries[0]);
		expect(details.open).toBe(true);
		expect(within(details).getByText(t('mcp.clientInference', { product: observed.product, kind: t('mcp.clientKind.agent') }))).toBeTruthy();
		expect(within(details).getByText(t('mcp.clientEvidence', { source: t('mcp.clientSource.client_info') }))).toBeTruthy();
		expect(within(details).getByText(t('mcp.clientPlatform', { browser: observed.browser, os: observed.os }))).toBeTruthy();
		expect(within(details).getAllByText(hostile)).toHaveLength(1);
		const date = (value: string) => new Intl.DateTimeFormat(intlLocale(), { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
		expect(within(details).getByText(t('mcp.clientDates', { first: date(observed.first_seen_at), last: date(observed.last_seen_at) }))).toBeTruthy();
		expect(document.body.textContent).not.toContain('must-not-render-secret');
		await screen.findByText(t('mcp.count', { count: 1 }));
		await fireEvent.click(screen.getByRole('button', { name: t(selected === 'oauth' ? 'mcp.revokeAccess' : 'mcp.revoke') }));
		await waitFor(() => expect(api.delete).toHaveBeenCalledExactlyOnceWith(selected === 'oauth' ? '/api/v1/auth/mcp-oauth/grants/grant-1' : '/api/v1/auth/mcp-tokens/token-1', 'token'));
		expect(confirmDialog).toHaveBeenCalledExactlyOnceWith(t(selected === 'oauth' ? 'mcp.revokeOAuthConfirm' : 'mcp.revokeConfirm', { name: selected === 'oauth' ? `${t('mcp.oauth')} 1` : record.name }));
		await screen.findByText(t(selected === 'oauth' ? 'mcp.emptyOAuth' : 'mcp.emptyTokens'));
		expect(screen.queryByRole('group', { name: t('mcp.observations') })).toBeNull();
	});

	it('hides OAuth client and project identifiers while revoking the selected grant', async () => {
		const records = [
			{ ...activeToken, id: 'opaque-row-one', grant_id: 'grant-one', name: 'OAuth: afterglow-dcr-private-client', source: 'oauth', projects: [{ id: 'private-project-uuid', name: 'Research' }], client_observations: [{ client_name: 'Codex', client_version: '1.2.3', product: 'Codex', kind: 'agent', identity_source: 'client_info', browser: null, os: 'macOS', first_seen_at: null, last_seen_at: null } satisfies McpClientObservation] },
			{ ...activeToken, id: 'opaque-row-two', grant_id: 'grant-two', name: 'OAuth: second-private-client', source: 'oauth', access_level: 'manage', expires_at: null, projects: [{ id: 'second-project-uuid', name: 'Systems' }], client_observations: [{ client_name: 'Claude Code', client_version: '2.0', product: 'Claude Code', kind: 'agent', identity_source: 'client_info', browser: null, os: 'Linux', first_seen_at: null, last_seen_at: null } satisfies McpClientObservation] },
		];
		api.get.mockImplementation((path: string) => Promise.resolve(path.startsWith('/api/v1/auth/mcp-projects') ? accountResponse(path) : path.includes('oauth') ? records : []));
		api.delete.mockResolvedValue(undefined);
		const { container } = render(McpAccessSection);
		await screen.findByText(t('mcp.savedProjects', { projects: 'Systems' }));
		const cards = container.querySelectorAll('.record');
		expect(cards).toHaveLength(2);
		expect(within(cards[1] as HTMLElement).getByText(t('mcp.oauthDetails', { access: t('mcp.manage'), expires: t('mcp.expiryNever') }))).toBeTruthy();
		expect(within(cards[0] as HTMLElement).getByText('Codex', { selector: 'summary strong' })).toBeTruthy();
		expect(within(cards[1] as HTMLElement).getByText('Claude Code', { selector: 'summary strong' })).toBeTruthy();
		for (const details of container.querySelectorAll('details')) expect(details.open).toBe(false);
		expect(container.innerHTML).not.toContain('afterglow-dcr-private-client');
		expect(container.innerHTML).not.toContain('second-private-client');
		expect(container.innerHTML).not.toContain('private-project-uuid');
		expect(container.innerHTML).not.toContain('second-project-uuid');
		await fireEvent.click(within(cards[1] as HTMLElement).getByRole('button', { name: t('mcp.revokeAccess') }));
		expect(confirmDialog).toHaveBeenCalledWith(t('mcp.revokeOAuthConfirm', { name: `${t('mcp.oauth')} 2` }));
		expect(api.delete).toHaveBeenCalledExactlyOnceWith('/api/v1/auth/mcp-oauth/grants/grant-two', 'token');
	});

	it.each(['ko', 'en', 'ja', 'zh-CN', 'bn', 'ms', 'nb', 'sw', 'vi'] as const)('shows an allowlisted product fallback and its header evidence without claiming the key name as identity in %s', async (locale) => {
		initLocale(locale);
		const observation: McpClientObservation = {
			client_name: null, client_version: null, product: 'Chrome', kind: 'browser',
			identity_source: 'user_agent', browser: 'Chrome', os: 'macOS',
			first_seen_at: null, last_seen_at: null,
		};
		api.get.mockImplementation((path: string) => Promise.resolve(accountResponse(path, [{ ...activeToken, client_observations: [observation] }])));
		await renderApi();
		const group = await screen.findByRole('group', { name: t('mcp.observations') });
		const summary = group.querySelector('summary')!;
		expect(summary.closest('details')!.open).toBe(false);
		expect(within(summary).getByText('Chrome', { selector: 'strong' })).toBeTruthy();
		expect(summary.textContent).toContain(t('mcp.clientVersion', { version: t('mcp.unknown') }));
		expect(within(summary).getByText(t('mcp.clientEvidence', { source: t('mcp.clientSource.user_agent') }))).toBeTruthy();
		expect(within(group).getByText(tp('mcpClients.count', { count: 1 }))).toBeTruthy();
		expect(group.textContent).not.toContain('Lumen');
	});

	it('labels a self-reported name separately from header-inferred product evidence', async () => {
		const observation: McpClientObservation = {
			client_name: 'custom-agent', client_version: '1.2.3', product: 'Chrome', kind: 'browser',
			identity_source: 'user_agent', browser: 'Chrome', os: 'Linux',
			first_seen_at: null, last_seen_at: null,
		};
		api.get.mockImplementation((path: string) => Promise.resolve(accountResponse(path, [{ ...activeToken, client_observations: [observation] }])));
		await renderApi();
		const group = await screen.findByRole('group', { name: t('mcp.observations') });
		const summary = group.querySelector('summary')!;
		const nameLine = summary.querySelector('strong')!.parentElement!;
		expect(summary.closest('details')!.open).toBe(false);
		expect(nameLine.textContent).toContain('custom-agent');
		expect(nameLine.textContent).toContain(t('mcp.clientSource.client_info'));
		expect(nameLine.textContent).not.toContain(t('mcp.clientSource.user_agent'));
		const inference = within(summary.closest('details')!).getByText(t('mcp.clientInference', { product: 'Chrome', kind: t('mcp.clientKind.browser') })).parentElement!;
		expect(within(inference).getByText(t('mcp.clientEvidence', { source: t('mcp.clientSource.user_agent') }))).toBeTruthy();
		expect(inference.textContent).not.toContain('custom-agent');
	});

	it('keeps sanitized hostile client information unknown and ignores non-public observation fields', async () => {
		// The API allowlist discards hostile clientInfo and raw headers before this projection.
		const observation = {
			client_name: null, client_version: null, product: null, kind: 'unknown', identity_source: 'unknown',
			browser: null, os: null, first_seen_at: null, last_seen_at: null,
			raw_client_info: '<script>private-client-info</script>', user_agent: 'private-raw-user-agent',
			token: 'private-observation-token', fingerprint: 'private-observation-hash',
		} satisfies McpClientObservation & Record<string, unknown>;
		api.get.mockImplementation((path: string) => Promise.resolve(accountResponse(path, [{ ...activeToken, client_observations: [observation] }])));
		const { container } = await renderApi();
		const group = await screen.findByRole('group', { name: t('mcp.observations') });
		const summary = group.querySelector('summary')!;
		expect(summary.closest('details')!.open).toBe(false);
		expect(within(summary).getByText(t('mcp.unknownClient'))).toBeTruthy();
		expect(within(summary).getByText(t('mcp.clientEvidence', { source: t('mcp.clientSource.unknown') }))).toBeTruthy();
		expect(group.textContent).not.toContain('Lumen');
		for (const hidden of ['private-client-info', 'private-raw-user-agent', 'private-observation-token', 'private-observation-hash']) {
			expect(container.innerHTML).not.toContain(hidden);
		}
	});

	it('treats legacy null client observations as not observed, not as the credential name', async () => {
		api.get.mockImplementation((path: string) => Promise.resolve(path.startsWith('/api/v1/auth/mcp-projects')
			? accountResponse(path) : path.includes('oauth') ? [] : [{ ...activeToken, client_observations: null }]));
		await renderApi();
		const group = await screen.findByRole('group', { name: t('mcp.observations') });
		expect(within(group).getByText(t('mcp.noObservations'))).toBeTruthy();
		expect(group.querySelector('details')).toBeNull();
		expect(group.textContent).not.toContain('Lumen');
	});

	it('shows no observation separately from an unknown observed client and caps displayed signatures at ten', async () => {
		await renderApi();
		const noObservation = await screen.findByText(t('mcp.noObservations'));
		expect(noObservation.closest('[role="group"]')?.querySelector('details')).toBeNull();
		const observations = Array.from({ length: 11 }, (_, index): McpClientObservation => ({ client_name: `Observed ${index}`, client_version: null, product: null, kind: 'unknown', identity_source: 'unknown', browser: null, os: null, first_seen_at: null, last_seen_at: null }));
		api.get.mockImplementation((path: string) => Promise.resolve(accountResponse(path, [{ ...activeToken, client_observations: observations }])));
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.refresh') }));
		await screen.findByText(tp('mcpClients.count', { count: 10 }));
		const group = screen.getByRole('group', { name: t('mcp.observations') });
		expect(within(group).getAllByRole('listitem')).toHaveLength(10);
		expect(group.querySelectorAll('summary')).toHaveLength(10);
		for (const details of group.querySelectorAll('details')) expect(details.open).toBe(false);
		expect(within(group).getByText('Observed 0', { selector: 'summary strong' })).toBeTruthy();
		expect(screen.queryByText('Observed 10')).toBeNull();
		expect(screen.queryByText(t('mcp.noObservations'))).toBeNull();
		expect(screen.getByText(t('mcp.count', { count: 1 }))).toBeTruthy();
	});
	it.each(['oauth', 'api'] as const)('shows selected %s records even while the other list is pending and then fails', async (selected) => {
		const other = deferred<typeof activeToken[]>();
		const record = { ...activeToken, name: 'Selected credential', source: selected === 'oauth' ? 'oauth' : 'personal_token' };
		api.get.mockImplementation((path: string) => path.startsWith('/api/v1/auth/mcp-projects') ? Promise.resolve(accountResponse(path))
			: path.includes('oauth') === (selected === 'oauth') ? Promise.resolve([record]) : other.promise);
		render(McpAccessSection);
		if (selected === 'api') await selectMethod('api');
		await screen.findByRole('button', { name: t(selected === 'oauth' ? 'mcp.revokeAccess' : 'mcp.revoke') });
		expect(screen.getByRole('button', { name: t(selected === 'oauth' ? 'mcp.revokeAccess' : 'mcp.revoke') }).hasAttribute('disabled')).toBe(false);
		await act(async () => { other.reject(new Error('Unselected private failure')); });
		expect(screen.getByRole('group', { name: t('mcp.savedRestrictions') })).toBeTruthy();
		expect(screen.queryByText(t('mcp.loadFailed'))).toBeNull();
		expect(screen.queryByRole('button', { name: t('mcp.retryList') })).toBeNull();
		await selectMethod(selected === 'oauth' ? 'api' : 'oauth');
		await screen.findByRole('button', { name: t('mcp.retryList') });
		expect(screen.queryByText(t('mcp.count', { count: 0 }))).toBeNull();
	});

	it.each(['oauth', 'api'] as const)('keeps a selected %s load error truthful and retries inline without stale actions', async (selected) => {
		let failing = false;
		const record = { ...activeToken, name: 'Current credential' };
		api.get.mockImplementation((path: string) => path.startsWith('/api/v1/auth/mcp-projects') ? Promise.resolve(accountResponse(path))
			: path.includes('oauth') === (selected === 'oauth')
				? failing ? Promise.reject(new Error('Private own-list error')) : Promise.resolve([record]) : Promise.resolve([]));
		render(McpAccessSection);
		if (selected === 'api') await selectMethod('api');
		await screen.findByRole('group', { name: t('mcp.savedRestrictions') });
		const oldAction = screen.getByRole('button', { name: t(selected === 'oauth' ? 'mcp.revokeAccess' : 'mcp.revoke') });
		failing = true;
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.refresh') }));
		const retry = await screen.findByRole('button', { name: t('mcp.retryList') });
		expect(screen.getByText(t('mcp.loadFailed'))).toBeTruthy();
		expect(screen.queryByText(t('mcp.count', { count: 0 }))).toBeNull();
		expect(screen.queryByText(t(selected === 'oauth' ? 'mcp.emptyOAuth' : 'mcp.emptyTokens'))).toBeNull();
		await fireEvent.click(oldAction);
		expect(confirmDialog).not.toHaveBeenCalled();
		expect(api.delete).not.toHaveBeenCalled();
		if (selected === 'api') {
			const create = screen.getByRole('button', { name: t('mcp.create') });
			expect(create.hasAttribute('disabled')).toBe(true);
			await fireEvent.submit(create.closest('form')!);
			expect(api.post).not.toHaveBeenCalled();
		}
		failing = false;
		await fireEvent.click(retry);
		await screen.findByRole('group', { name: t('mcp.savedRestrictions') });
		expect(screen.queryByRole('button', { name: t('mcp.retryList') })).toBeNull();
	});

	it.each(['token', 'project'] as const)('keeps unverified %s credentials private until current verification is accepted', async (boundary) => {
		const oldEpoch = getAuthVerificationEpoch();
		if (boundary === 'token') setAuth({ token: 'unverified-token' });
		else setProject('other', 'Other project');
		// Neither stored credentials nor proof from the preceding scope makes this owner ready.
		expect(acceptAuthVerification(oldEpoch, {})).toBe(false);
		render(McpAccessSection);
		await act(async () => {});
		expect(screen.queryByRole('heading', { name: t('mcp.title') })).toBeNull();
		expect(screen.queryByRole('button', { name: t('mcp.methodApiKey') })).toBeNull();
		expect(api.get).not.toHaveBeenCalled();
		expect(api.post).not.toHaveBeenCalled();
		expect(api.put).not.toHaveBeenCalled();
		expect(api.delete).not.toHaveBeenCalled();
		verifyAuth();
		await screen.findByText(t('mcp.emptyOAuth'));
		expect(screen.getByRole('heading', { name: t('mcp.title') })).toBeTruthy();
		expect(api.get).toHaveBeenCalledWith('/api/v1/auth/mcp-projects', boundary === 'token' ? 'unverified-token' : 'token', boundary === 'project' ? 'other' : 'project', scopedGetOptions);
	});

	it.each(['oauth', 'api'] as const)('invalidates a pending %s removal dialog on own-record refresh, project ABA, token or user change', async (selected) => {
		for (const boundary of ['refresh', 'project', 'token', 'user'] as const) {
			const confirmation = deferred<boolean>();
			confirmDialog.mockReturnValue(confirmation.promise);
			let generation = 'Old';
			api.get.mockImplementation((path: string) => Promise.resolve(path.startsWith('/api/v1/auth/mcp-projects') ? accountResponse(path)
				: path.includes('oauth') === (selected === 'oauth') ? [{ ...activeToken, name: `${generation} credential`, projects: [{ id: 'project', name: `${generation} project` }] }] : []));
			render(McpAccessSection);
			if (selected === 'api') await selectMethod('api');
			await screen.findByText(t('mcp.savedProjects', { projects: selected === 'oauth' ? 'Old project' : 'Old project (project)' }));
			await fireEvent.click(screen.getByRole('button', { name: t(selected === 'oauth' ? 'mcp.revokeAccess' : 'mcp.revoke') }));
			generation = 'Fresh';
			if (boundary === 'refresh') await fireEvent.click(screen.getByRole('button', { name: t('mcp.refresh') }));
			else if (boundary === 'project') { setProject('other', 'Other project'); setProject('project', 'Project'); }
			else if (boundary === 'token') setAuth({ token: 'fresh-token' });
			else setAuth({ token: 'token', userId: 'fresh-user' });
			if (boundary !== 'refresh') verifyAuth();
			await screen.findByText(t('mcp.savedProjects', { projects: selected === 'oauth' ? 'Fresh project' : 'Fresh project (project)' }));
			await act(async () => { confirmation.resolve(true); });
			expect(api.delete).not.toHaveBeenCalled();
			expect(screen.getByText(t('mcp.savedProjects', { projects: selected === 'oauth' ? 'Fresh project' : 'Fresh project (project)' }))).toBeTruthy();
			cleanup();
			setAuth({ token: 'token', userId: 'user', projectId: 'project' });
			verifyAuth();
		}
	});


	it.each(['ko', 'en', 'ja', 'zh-CN'] as const)('opens the MCP guide in the account language %s', async (locale) => {
		initLocale(locale);
		render(McpAccessSection);
		const link = await screen.findByRole('link', { name: t('mcp.docs') });
		const url = new URL(link.getAttribute('href')!, 'https://afterglow.example.test');
		expect(url.pathname).toBe('/docs/mcp');
		expect(url.searchParams.get('lang')).toBe(locale === 'ko' ? null : locale);
	});

	it.each(['ko', 'en', 'ja', 'zh-CN'] as const)('localizes explicit project access controls in %s', async (locale) => {
		initLocale(locale);
		await renderApi();
		await createButton();
		expect(screen.getByText(t('mcp.projectsHelp'))).toBeTruthy();
		expect(screen.getByRole('option', { name: t('mcp.selectedProjects') })).toBeTruthy();
		expect(screen.getByRole('option', { name: t('mcp.allProjects') })).toBeTruthy();
		await fireEvent.click(projectCheckbox('project', 'Project'));
		expect(screen.getByText(t('mcp.projectsRequired'))).toBeTruthy();
	});

	it.each(['ko', 'en', 'ja', 'zh-CN'] as const)('shows immutable saved access and projects on token and OAuth grant lists in %s', async (locale) => {
		initLocale(locale);
		const grant = {
			...activeToken, id: 'oauth-grant', name: 'External client', source: 'oauth', access_level: 'manage', is_lumen_default: false,
			project_scope: 'all', project_ids: ['other'], projects: [{ id: 'other', name: 'Saved other project' }],
		};
		api.get.mockImplementation((path: string) => Promise.resolve(path.includes('oauth') ? [grant] : accountResponse(path)));
		await renderApi();
		await createButton();
		const restriction = screen.getByRole('group', { name: t('mcp.savedRestrictions') });
		expect(within(restriction).getByText(t('mcp.savedAccess', { access: t('mcp.read') }))).toBeTruthy();
		expect(within(restriction).getByText(t('mcp.savedCurrentProject'))).toBeTruthy();
		expect(within(restriction).getByText(t('mcp.savedProjects', { projects: 'Saved home project (project)' }))).toBeTruthy();
		expect(within(restriction).queryByRole('combobox')).toBeNull();
		expect(within(restriction).queryByRole('checkbox')).toBeNull();
		await fireEvent.change(screen.getByLabelText(t('mcp.permission')), { target: { value: 'manage' } });
		await fireEvent.change(screen.getByLabelText(t('mcp.projects')), { target: { value: 'all' } });
		expect(within(restriction).getByText(t('mcp.savedAccess', { access: t('mcp.read') }))).toBeTruthy();
		expect(within(restriction).getByText(t('mcp.savedProjects', { projects: 'Saved home project (project)' }))).toBeTruthy();
		await selectMethod('oauth');
		const oauthRestriction = screen.getByRole('group', { name: t('mcp.savedRestrictions') });
		expect(within(oauthRestriction).getByText(t('mcp.savedAccess', { access: t('mcp.manage') }))).toBeTruthy();
		expect(within(oauthRestriction).getByText(t('mcp.savedAllProjects'))).toBeTruthy();
		expect(within(oauthRestriction).getByText(t('mcp.savedProjects', { projects: 'Saved other project' }))).toBeTruthy();
		expect(within(oauthRestriction).queryByRole('combobox')).toBeNull();
		expect(within(oauthRestriction).queryByRole('checkbox')).toBeNull();
		expect(screen.getAllByRole('group', { name: t('mcp.savedRestrictions') })).toHaveLength(1);
	});

	it.each(['personal_token', 'oauth'] as const)('shows the explicit saved %s project set rather than current memberships or the creation draft', async (source) => {
		const record = {
			...activeToken, source, project_scope: 'selected', project_ids: ['saved-one', 'saved-two'],
			projects: [{ id: 'saved-one', name: 'Archived name' }, { id: 'saved-two', name: 'Other saved name' }],
		};
		api.get.mockImplementation((path: string) => Promise.resolve(path.startsWith('/api/v1/auth/mcp-projects') ? accountResponse(path)
			: path.includes('oauth') ? source === 'oauth' ? [record] : [] : source === 'personal_token' ? [record] : []));
		await renderApi();
		await createButton();
		await fireEvent.click(projectCheckbox('other', 'Other project'));
		if (source === 'oauth') await selectMethod('oauth');
		const restriction = screen.getByRole('group', { name: t('mcp.savedRestrictions') });
		expect(within(restriction).getByText(t('mcp.savedSelectedProjects'))).toBeTruthy();
		const savedNames = source === 'oauth' ? 'Archived name, Other saved name' : 'Archived name (saved-one), Other saved name (saved-two)';
		expect(within(restriction).getByText(t('mcp.savedProjects', { projects: savedNames }))).toBeTruthy();
		expect(restriction.textContent).not.toContain('Other project (other)');
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.refresh') }));
		await screen.findByRole('button', { name: t('mcp.refresh') });
		expect(screen.getByRole('group', { name: t('mcp.savedRestrictions') }).textContent).toContain(savedNames);
	});

	it.each(['empty', 'missing'] as const)('does not invent saved project restrictions when metadata is %s', async (metadata) => {
		const record = { ...activeToken, projects: metadata === 'empty' ? [] : undefined };
		api.get.mockImplementation((path: string) => Promise.resolve(path.startsWith('/api/v1/auth/mcp-projects') ? accountResponse(path) : path.includes('oauth') ? [] : [record]));
		await renderApi();
		await createButton();
		const restriction = screen.getByRole('group', { name: t('mcp.savedRestrictions') });
		expect(within(restriction).getByText(t('mcp.savedProjectsUnavailable'))).toBeTruthy();
		expect(restriction.textContent).not.toContain('Saved home project (project)');
		expect(restriction.textContent).not.toContain('Project (project)');
	});


	it.each(['ko', 'en', 'ja', 'zh-CN', 'bn', 'ms', 'nb', 'sw', 'vi'] as const)('shares the selected project permission preview in %s without issuing on selection', async (locale) => {
		initLocale(locale);
		await renderApi();
		await createButton();
		const preview = within(await screen.findByRole('region', { name: t('mcp.previewTitle') }));
		expect(screen.getByRole('heading', { name: t('mcp.previewTitle'), level: 3 })).toBeTruthy();
		expect(preview.getByRole('heading', { name: /Project\s*project/, level: 4 })).toBeTruthy();
		expect(screen.queryByText(tp('mcpConsent.preview.title'))).toBeNull();
		expect(preview.getByRole('listitem', { name: 'Project project' })).toBeTruthy();
		expect(preview.queryByRole('listitem', { name: 'Other project other' })).toBeNull();
		expect(preview.getByText('drover-inventory_reader')).toBeTruthy();
		expect(preview.getByText(tp('mcpConsent.permission.droverInventory'))).toBeTruthy();
		expect(preview.queryByText('lumen-history_reader')).toBeNull();
		expect(preview.queryByText('drover-clusters_editor')).toBeNull();
		expect(preview.queryByText('lumen-chat_user')).toBeNull();
		expect(preview.getByText(tp('mcpConsent.preview.service.denied'))).toBeTruthy();
		await fireEvent.click(projectCheckbox('other', 'Other project'));
		expect(preview.getByRole('listitem', { name: 'Other project other' })).toBeTruthy();
		expect(api.get.mock.calls.filter(([path]) => path === '/api/v1/auth/mcp-projects?preview=true')).toHaveLength(1);
		expect(api.post).not.toHaveBeenCalled();
		expect(preview.getByText(tp('mcpConsent.preview.help'))).toBeTruthy();
	});

	it('does not expose Lumen or its API key permissions in account project previews', async () => {
		const hostile = previewProjects.map((project) => ({ ...project, service_permissions: {
			...project.service_permissions, lumen: ['lumen-keys_editor', 'lumen-chat_user', 'lumen-mcp_editor'],
		} }));
		api.get.mockImplementation((path: string) => Promise.resolve(path.includes('preview=true') ? hostile : accountResponse(path)));
		await renderApi();
		await createButton();
		const preview = within(screen.getByRole('region', { name: t('mcp.previewTitle') }));
		await waitFor(() => expect(preview.getByText('drover-inventory_reader')).toBeTruthy());
		expect(preview.queryByText('Lumen')).toBeNull();
		expect(preview.queryByText('lumen-keys_editor')).toBeNull();
		expect(preview.queryByText('lumen-chat_user')).toBeNull();
		expect(preview.queryByText('lumen-mcp_editor')).toBeNull();
	});

	it('keeps cheap membership and read-only issuance independent of slow native checks while blocking manage', async () => {
		const pending = deferred<McpConsentProject[]>();
		api.get.mockImplementation((path: string) => path === '/api/v1/auth/mcp-projects?preview=true'
			? pending.promise : Promise.resolve(accountResponse(path)));
		render(McpAccessSection);
		await screen.findByText(t('mcp.emptyOAuth'));
		expect(api.get.mock.calls.some(([path]) => path.includes('preview=true'))).toBe(false);
		await selectMethod('api');
		const button = await createButton();
		expect(api.get).toHaveBeenCalledWith('/api/v1/auth/mcp-projects', 'token', 'project', scopedGetOptions);
		expect(api.get).toHaveBeenCalledWith('/api/v1/auth/mcp-projects?preview=true', 'token', 'project', scopedGetOptions);
		expect(screen.getByText(tp('mcpConsent.preview.loading'))).toBeTruthy();
		expect(screen.getByText(tp('mcpConsent.preview.cloud.unknown'))).toBeTruthy();
		await fireEvent.change(screen.getByLabelText(t('mcp.permission')), { target: { value: 'manage' } });
		expect(screen.getByText(t('mcp.managePreviewPending'))).toBeTruthy();
		expect(screen.queryByText(t('mcp.managePreviewUnknown'))).toBeNull();
		expect(screen.queryByText(tp('mcpConsent.preview.unknownWrite'))).toBeNull();
		expect(screen.queryByText(tp('mcpConsent.preview.unavailable'))).toBeNull();
		expect(button.hasAttribute('disabled')).toBe(true);
		await fireEvent.submit(button.closest('form')!);
		expect(api.post).not.toHaveBeenCalled();
		await fireEvent.change(screen.getByLabelText(t('mcp.permission')), { target: { value: 'read' } });
		await fireEvent.click(button);
		expect(api.post).toHaveBeenCalledOnce();
		await act(async () => { pending.resolve(previewProjects); });
	});

	it('permits mixed manage-all ceilings, refuses selected readers, and attenuates locally without refetching', async () => {
		const mixed = [previewProjects[0], { ...previewProjects[1], can_write: false }];
		api.get.mockImplementation((path: string) => Promise.resolve(path.includes('preview=true') ? mixed : accountResponse(path)));
		await renderApi();
		const button = await createButton();
		await screen.findByText('drover-inventory_reader');
		const preview = within(screen.getByRole('region', { name: t('mcp.previewTitle') }));
		await fireEvent.change(screen.getByLabelText(t('mcp.permission')), { target: { value: 'manage' } });
		await fireEvent.click(projectCheckbox('other', 'Other project'));
		expect(screen.getByText(t('mcp.managePreviewReader'))).toBeTruthy();
		expect(button.hasAttribute('disabled')).toBe(true);
		await fireEvent.submit(button.closest('form')!);
		expect(api.post).not.toHaveBeenCalled();
		await fireEvent.change(screen.getByLabelText(t('mcp.projects')), { target: { value: 'all' } });
		expect(within(preview.getByRole('listitem', { name: 'Project project' })).getByText(tp('mcpConsent.preview.cloud.manage'))).toBeTruthy();
		expect(within(preview.getByRole('listitem', { name: 'Other project other' })).getByText(tp('mcpConsent.preview.cloud.read'))).toBeTruthy();
		expect(preview.getAllByText('drover-clusters_editor')).toHaveLength(2);
		expect(preview.queryByText('lumen-tools_user')).toBeNull();
		expect(button.hasAttribute('disabled')).toBe(false);
		await fireEvent.change(screen.getByLabelText(t('mcp.permission')), { target: { value: 'read' } });
		expect(preview.getAllByText('drover-inventory_reader')).toHaveLength(2);
		for (const leaf of ['lumen-tools_user', 'lumen-chat_user', 'drover-clusters_editor']) expect(preview.queryByText(leaf)).toBeNull();
		expect(preview.queryByText('lumen-history_reader')).toBeNull();
		await fireEvent.change(screen.getByLabelText(t('mcp.permission')), { target: { value: 'manage' } });
		expect(api.get.mock.calls.filter(([path]) => path.includes('preview=true'))).toHaveLength(1);
		await fireEvent.click(button);
		expect(api.post).toHaveBeenCalledWith('/api/v1/auth/mcp-tokens', expect.objectContaining({
			access_level: 'manage', project_scope: 'all', project_ids: [],
		}), 'token', 'project', scopedPostOptions);
	});

	it('keeps independent service failure unknown without denying known cloud management', async () => {
		api.get.mockImplementation((path: string) => Promise.resolve(path.includes('preview=true') ? [{
			...previewProjects[0], service_errors: { waygate: 'private policy error must not render' },
		}] : accountResponse(path)));
		await renderApi();
		await screen.findByText('drover-inventory_reader');
		await fireEvent.change(screen.getByLabelText(t('mcp.permission')), { target: { value: 'manage' } });
		const preview = within(screen.getByRole('region', { name: t('mcp.previewTitle') }));
		expect(preview.getByText(tp('mcpConsent.preview.service.unavailable'))).toBeTruthy();
		expect(preview.getByText('drover-clusters_editor')).toBeTruthy();
		expect(preview.queryByText('lumen-tools_user')).toBeNull();
		expect(document.body.textContent).not.toContain('private policy error');
		await fireEvent.click(await createButton());
		expect(api.post).toHaveBeenCalledOnce();
	});

	it.each(['failure', 'unknown-cloud', 'missing-row'] as const)('preserves read creation but blocks management for preview %s', async (outcome) => {
		api.get.mockImplementation((path: string) => path.includes('preview=true')
			? outcome === 'failure' ? Promise.reject(new Error('private upstream details'))
				: Promise.resolve(outcome === 'missing-row' ? [] : [{ ...previewProjects[0], can_write: null, service_permissions: {}, service_errors: {} }])
			: Promise.resolve(accountResponse(path)));
		await renderApi();
		const button = await createButton();
		if (outcome === 'failure') await screen.findByText(tp('mcpConsent.preview.unavailable'));
		expect(screen.getByText(tp('mcpConsent.preview.cloud.unknown'))).toBeTruthy();
		expect(screen.getAllByText(tp('mcpConsent.preview.service.unavailable'))).toHaveLength(3);
		expect(document.body.textContent).not.toContain('private upstream details');
		await fireEvent.change(screen.getByLabelText(t('mcp.permission')), { target: { value: 'manage' } });
		expect(screen.getByText(t('mcp.managePreviewUnknown'))).toBeTruthy();
		expect(screen.queryByText(t('mcp.managePreviewPending'))).toBeNull();
		expect(button.hasAttribute('disabled')).toBe(true);
		await fireEvent.submit(button.closest('form')!);
		expect(api.post).not.toHaveBeenCalled();
		await fireEvent.change(screen.getByLabelText(t('mcp.permission')), { target: { value: 'read' } });
		await fireEvent.click(button);
		expect(api.post).toHaveBeenCalledOnce();
	});

	it.each((['token', 'user', 'project-aba', 'reload', 'unmount'] as const)
		.flatMap((boundary) => (['success', 'failure'] as const).map((outcome) => [boundary, outcome] as const)))('aborts and discards late permission preview after %s (%s)', async (boundary, outcome) => {
		const pending = deferred<McpConsentProject[]>();
		let old = true;
		api.get.mockImplementation((path: string) => path.includes('preview=true')
			? old ? pending.promise : Promise.resolve(previewProjects.map((project) => ({ ...project, service_permissions: {}, service_errors: {} })))
			: Promise.resolve(accountResponse(path)));
		const view = await renderApi();
		await createButton();
		await screen.findByText(tp('mcpConsent.preview.loading'));
		const signal = api.get.mock.calls.find(([path]) => path.includes('preview=true'))![3].signal as AbortSignal;
		old = false;
		if (boundary === 'token') setAuth({ token: 'new-token' });
		else if (boundary === 'user') setAuth({ token: 'token', userId: 'new-user' });
		else if (boundary === 'project-aba') {
			setProject('other', 'Other project');
			setProject('project', 'Project');
		} else if (boundary === 'reload') await fireEvent.click(screen.getByRole('button', { name: t('mcp.refresh') }));
		else { view.unmount(); await renderApi(); }
		if (boundary === 'token' || boundary === 'user' || boundary === 'project-aba') verifyAuth();
		await createButton();
		await waitFor(() => expect(screen.queryByText(tp('mcpConsent.preview.loading'))).toBeNull());
		expect(signal.aborted).toBe(true);
		await act(async () => {
			if (outcome === 'failure') pending.reject(new Error('Stale permission preview failure'));
			else pending.resolve([{
				...previewProjects[0], service_permissions: { drover: ['drover-workloads_editor'] },
			}]);
		});
		await fireEvent.change(screen.getByLabelText(t('mcp.permission')), { target: { value: 'manage' } });
		expect(screen.queryByText('drover-workloads_editor')).toBeNull();
		expect(screen.queryByText(tp('mcpConsent.preview.unavailable'))).toBeNull();
		expect(api.post).not.toHaveBeenCalled();
	});

	it('defaults to read access and the authoritative current project payload', async () => {
		await renderApi();
		await createButton();
		expect(api.get).toHaveBeenCalledWith('/api/v1/auth/mcp-projects', 'token', 'project', scopedGetOptions);
		expect(projectCheckbox('project', 'Project').checked).toBe(true);
		expect(projectCheckbox('other', 'Other project').checked).toBe(false);
		expect((screen.getByLabelText(t('mcp.permission')) as HTMLSelectElement).value).toBe('read');
		expect((screen.getByLabelText(t('mcp.expiry')) as HTMLSelectElement).value).toBe('1m');
		await fireEvent.click(await createButton());
		expect(api.post).toHaveBeenCalledWith('/api/v1/auth/mcp-tokens', {
			name: 'Lumen', access_level: 'read', project_scope: 'selected', project_ids: ['project'], expires_at: defaultExpiry,
		}, 'token', 'project', scopedPostOptions);
	});

	it('issues manage access for explicit projects without adding the home project implicitly', async () => {
		await renderApi();
		await createButton();
		await fireEvent.change(screen.getByLabelText(t('mcp.permission')), { target: { value: 'manage' } });
		await fireEvent.click(projectCheckbox('project', 'Project'));
		await fireEvent.click(projectCheckbox('other', 'Other project'));
		await fireEvent.input(screen.getByRole('textbox', { name: t('mcp.name') }), { target: { value: 'Explicit client' } });
		await fireEvent.click(await createButton());
		expect(api.post).toHaveBeenCalledWith('/api/v1/auth/mcp-tokens', {
			name: 'Explicit client', access_level: 'manage', project_scope: 'selected', project_ids: ['other'], expires_at: defaultExpiry,
		}, 'token', 'project', scopedPostOptions);
	});

	it('preserves an explicit multi-project payload', async () => {
		await renderApi();
		await createButton();
		await fireEvent.click(projectCheckbox('other', 'Other project'));
		await fireEvent.click(await createButton());
		expect(api.post).toHaveBeenCalledWith('/api/v1/auth/mcp-tokens', expect.objectContaining({
			project_scope: 'selected', project_ids: ['project', 'other'],
		}), 'token', 'project', scopedPostOptions);
	});

	it('keeps valid explicit choices after a successful authoritative reload', async () => {
		await renderApi();
		await createButton();
		await fireEvent.click(projectCheckbox('other', 'Other project'));
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.refresh') }));
		await createButton();
		expect(projectCheckbox('project', 'Project').checked).toBe(true);
		expect(projectCheckbox('other', 'Other project').checked).toBe(true);
	});

	it('blocks issuance and discards previous project choices when collection reload fails', async () => {
		await renderApi();
		const button = await createButton();
		expect(screen.getByRole('group', { name: t('mcp.savedRestrictions') })).toBeTruthy();
		await fireEvent.change(screen.getByLabelText(t('mcp.projects')), { target: { value: 'all' } });
		const reload = deferred<typeof activeToken[]>();
		api.get.mockImplementation((path: string) => path.endsWith('/mcp-tokens') ? reload.promise : Promise.resolve(accountResponse(path)));
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.refresh') }));
		expect(button.hasAttribute('disabled')).toBe(true);
		await act(async () => { reload.reject(new ApiError('Collection unavailable')); });
		await screen.findByText('Collection unavailable');
		expect((screen.getByLabelText(t('mcp.projects')) as HTMLSelectElement).value).toBe('selected');
		expect(projectCheckbox('project', 'Project').checked).toBe(false);
		expect(projectCheckbox('other', 'Other project').checked).toBe(false);
		await fireEvent.submit(button.closest('form')!);
		expect(api.post).not.toHaveBeenCalled();
		api.get.mockImplementation((path: string) => Promise.resolve(accountResponse(path)));
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.refresh') }));
		await screen.findByText(t('mcp.projectsRequired'));
		expect(button.hasAttribute('disabled')).toBe(true);
		await fireEvent.click(projectCheckbox('other', 'Other project'));
		await fireEvent.click(await createButton());
		expect(api.post).toHaveBeenCalledWith('/api/v1/auth/mcp-tokens', expect.objectContaining({ project_ids: ['other'] }), 'token', 'project', scopedPostOptions);
	});

	it.each(['failure', 'empty'] as const)('blocks all-project issuance after a same-owner inventory reload %s', async (result) => {
		await renderApi();
		await createButton();
		await fireEvent.change(screen.getByLabelText(t('mcp.projects')), { target: { value: 'all' } });
		api.get.mockImplementation((path: string) => path.endsWith('/mcp-projects')
			? result === 'failure' ? Promise.reject(new Error('Failed reload')) : Promise.resolve([])
			: Promise.resolve(accountResponse(path)));
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.refresh') }));
		await screen.findByText(result === 'failure' ? t('mcp.projectsLoadFailed') : t('mcp.noProjects'));
		const button = screen.getByRole('button', { name: t('mcp.create') });
		expect(button.hasAttribute('disabled')).toBe(true);
		await fireEvent.submit(button.closest('form')!);
		expect(api.post).not.toHaveBeenCalled();
	});

	it('submits all projects for server-side resolution without stale selected ids', async () => {
		await renderApi();
		await createButton();
		await fireEvent.click(projectCheckbox('other', 'Other project'));
		await fireEvent.change(screen.getByLabelText(t('mcp.projects')), { target: { value: 'all' } });
		expect(screen.queryByRole('checkbox')).toBeNull();
		await fireEvent.click(await createButton());
		expect(api.post).toHaveBeenCalledWith('/api/v1/auth/mcp-tokens', {
			name: 'Lumen', access_level: 'read', project_scope: 'all', project_ids: [], expires_at: defaultExpiry,
		}, 'token', 'project', scopedPostOptions);
	});

	it('blocks empty explicit selection even when the form is submitted directly', async () => {
		await renderApi();
		const button = await createButton();
		await fireEvent.click(projectCheckbox('project', 'Project'));
		expect(button.hasAttribute('disabled')).toBe(true);
		expect(screen.getByText(t('mcp.projectsRequired'))).toBeTruthy();
		await fireEvent.submit(button.closest('form')!);
		expect(api.post).not.toHaveBeenCalled();
	});

	it.each(['failure', 'empty', 'missing-current'] as const)('fails closed on initial project %s', async (result) => {
		api.get.mockImplementation((path: string) => path.endsWith('/mcp-projects')
			? result === 'failure' ? Promise.reject(new Error('Private upstream failure'))
				: Promise.resolve(result === 'empty' ? [] : [availableProjects[1]])
			: Promise.resolve(accountResponse(path)));
		await renderApi();
		await screen.findByText(result === 'failure' ? t('mcp.projectsLoadFailed') : result === 'empty' ? t('mcp.noProjects') : t('mcp.projectsRequired'));
		const button = screen.getByRole('button', { name: t('mcp.create') });
		expect(button.hasAttribute('disabled')).toBe(true);
		await fireEvent.submit(button.closest('form')!);
		expect(api.post).not.toHaveBeenCalled();
		expect(document.body.textContent).not.toContain('Private upstream failure');
		if (result === 'missing-current') {
			await fireEvent.click(projectCheckbox('other', 'Other project'));
			expect(button.hasAttribute('disabled')).toBe(false);
		}
	});

	it('removes invalid selections and blocks submission throughout a same-owner reload', async () => {
		await renderApi();
		const button = await createButton();
		await fireEvent.click(projectCheckbox('project', 'Project'));
		await fireEvent.click(projectCheckbox('other', 'Other project'));
		const reload = deferred<typeof availableProjects>();
		api.get.mockImplementation((path: string) => path.endsWith('/mcp-projects') ? reload.promise : Promise.resolve(accountResponse(path)));
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.refresh') }));
		expect(button.hasAttribute('disabled')).toBe(true);
		expect(screen.queryByRole('checkbox')).toBeNull();
		await fireEvent.submit(button.closest('form')!);
		expect(api.post).not.toHaveBeenCalled();
		await act(async () => { reload.resolve([availableProjects[0]]); });
		await screen.findByText(t('mcp.projectsRequired'));
		expect(projectCheckbox('project', 'Project').checked).toBe(false);
		expect(screen.queryByRole('checkbox', { name: t('mcp.selectProject', { name: 'Other project', id: 'other' }) })).toBeNull();
		expect(button.hasAttribute('disabled')).toBe(true);
		await fireEvent.submit(button.closest('form')!);
		expect(api.post).not.toHaveBeenCalled();
	});

	it('discards old selection after reload failure and requires a new explicit choice on recovery', async () => {
		await renderApi();
		const button = await createButton();
		api.get.mockImplementation((path: string) => path.endsWith('/mcp-projects') ? Promise.reject(new Error('Failed reload')) : Promise.resolve(accountResponse(path)));
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.refresh') }));
		await screen.findByText(t('mcp.projectsLoadFailed'));
		expect(screen.queryByRole('checkbox')).toBeNull();
		expect(button.hasAttribute('disabled')).toBe(true);
		await fireEvent.submit(button.closest('form')!);
		expect(api.post).not.toHaveBeenCalled();
		api.get.mockImplementation((path: string) => Promise.resolve(accountResponse(path)));
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.refresh') }));
		await screen.findByText(t('mcp.projectsRequired'));
		expect(projectCheckbox('project', 'Project').checked).toBe(false);
		expect(button.hasAttribute('disabled')).toBe(true);
		await fireEvent.click(projectCheckbox('project', 'Project'));
		await fireEvent.click(await createButton());
		expect(api.post).toHaveBeenCalledWith('/api/v1/auth/mcp-tokens', expect.objectContaining({ project_ids: ['project'] }), 'token', 'project', scopedPostOptions);
	});

	it.each(['issuance', 'verification'] as const)('preserves the 30-second deadline for scoped %s POST', async (operation) => {
		const deadline = new AbortController();
		const timeout = vi.spyOn(AbortSignal, 'timeout').mockReturnValue(deadline.signal);
		api.post.mockImplementation((_path: string, _payload: unknown, _token: string, _project: string, options: { signal: AbortSignal }) => {
			const { promise, reject } = Promise.withResolvers();
			options.signal.addEventListener('abort', () => reject(options.signal.reason), { once: true });
			return promise;
		});
		try {
			await renderApi();
			await createButton();
			if (operation === 'issuance') await fireEvent.click(await createButton());
			else {
				await fireEvent.input(screen.getByLabelText(t('mcp.tokenLabel')), { target: { value: 'private-saved-key' } });
				await fireEvent.click(screen.getByRole('button', { name: t('mcp.verify') }));
			}
			expect(timeout).toHaveBeenCalledWith(30_000);
			const signal = api.post.mock.calls[0][4].signal as AbortSignal;
			expect(signal.aborted).toBe(false);
			await act(async () => { deadline.abort(new DOMException('Deadline exceeded', 'TimeoutError')); });
			expect(signal.aborted).toBe(true);
			await screen.findByText(operation === 'issuance' ? t('mcp.createFailed') : t('mcp.verifyError.unavailable'));
			expect(screen.queryByRole('dialog')).toBeNull();
			expect(document.body.textContent).not.toContain('Deadline exceeded');
		} finally {
			timeout.mockRestore();
		}
	});

	it.each(['token', 'user', 'project-aba', 'unmount'] as const)('discards a late project inventory after %s boundary', async (boundary) => {
		const oldProjects = deferred<typeof availableProjects>();
		api.get.mockImplementation((path: string) => path.endsWith('/mcp-projects') ? oldProjects.promise : Promise.resolve(accountResponse(path)));
		const view = await renderApi();
		await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/v1/auth/mcp-projects', 'token', 'project', scopedGetOptions));
		const oldSignal = api.get.mock.calls.find(([path]) => path.endsWith('/mcp-projects'))![3].signal as AbortSignal;
		api.get.mockImplementation((path: string) => path.endsWith('/mcp-projects')
			? Promise.resolve([{ id: 'project', name: 'Fresh membership' }]) : Promise.resolve(accountResponse(path)));
		if (boundary === 'token') setAuth({ token: 'new-token' });
		else if (boundary === 'user') setAuth({ token: 'token', userId: 'new-user' });
		else if (boundary === 'project-aba') {
			setProject('other', 'Other project');
			setProject('project', 'Project');
		} else {
			view.unmount();
			await renderApi();
		}
		if (boundary !== 'unmount') verifyAuth();
		await createButton();
		expect(oldSignal.aborted).toBe(true);
		await act(async () => { oldProjects.resolve([{ id: 'old-id', name: 'Stale membership' }]); });
		expect(screen.queryByText('Stale membership')).toBeNull();
		expect(projectCheckbox('project', 'Fresh membership').checked).toBe(true);
		await fireEvent.click(await createButton());
		expect(api.post).toHaveBeenCalledWith('/api/v1/auth/mcp-tokens', expect.objectContaining({ project_ids: ['project'] }), boundary === 'token' ? 'new-token' : 'token', 'project', scopedPostOptions);
	});

	it('does not publish stale issuance when authoritative projects reload for the same owner', async () => {
		const issuance = deferred<typeof activeToken & { token: string }>();
		api.post.mockReturnValue(issuance.promise);
		await renderApi();
		await fireEvent.click(await createButton());
		const signal = api.post.mock.calls[0][4].signal as AbortSignal;
		expect(signal.aborted).toBe(false);
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.refresh') }));
		expect(signal.aborted).toBe(true);
		await createButton();
		await act(async () => { issuance.resolve({ ...activeToken, token: 'stale-reload-secret' }); });
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(document.body.textContent).not.toContain('stale-reload-secret');
	});

	it('ignores an old project load failure after a new token has fresh metadata', async () => {
		const oldProjects = deferred<typeof availableProjects>();
		api.get.mockImplementation((path: string) => path.endsWith('/mcp-projects') ? oldProjects.promise : Promise.resolve(accountResponse(path)));
		await renderApi();
		await screen.findByText('Lumen', { selector: '.record-title strong' });
		api.get.mockImplementation((path: string) => Promise.resolve(accountResponse(path)));
		setAuth({ token: 'fresh-token' });
		verifyAuth();
		await createButton();
		await act(async () => { oldProjects.reject(new Error('Old load failed')); });
		expect(screen.queryByText(t('mcp.projectsLoadFailed'))).toBeNull();
		expect(projectCheckbox('project', 'Project').checked).toBe(true);
		await fireEvent.click(await createButton());
		expect(api.post).toHaveBeenCalledWith('/api/v1/auth/mcp-tokens', expect.objectContaining({ project_ids: ['project'] }), 'fresh-token', 'project', scopedPostOptions);
	});

	it.each(['success', 'failure'] as const)('ignores a stale issuance %s after a newer same-owner issuance succeeds', async (result) => {
		const oldIssuance = deferred<typeof activeToken & { token: string }>();
		api.post.mockReturnValueOnce(oldIssuance.promise);
		await renderApi();
		await fireEvent.click(await createButton());
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.refresh') }));
		await fireEvent.click(await createButton());
		await screen.findByRole('dialog', { name: t('mcp.newToken') });
		await act(async () => {
			if (result === 'success') oldIssuance.resolve({ ...activeToken, token: 'older-issued-secret' });
			else oldIssuance.reject(new ApiError('Old issuance error'));
		});
		expect(screen.queryByText('Old issuance error')).toBeNull();
		expect(document.body.textContent).not.toContain('older-issued-secret');
		expect(screen.getByText('mcp-afgl-secret-value')).toBeTruthy();
	});
	it('shows the current Lumen default without exposing a token secret', async () => {
		await renderApi();

		await createButton();
		expect(screen.queryByText('mcp-afgl-secret-value')).toBeNull();
		expect(screen.getByRole('button', { name: 'Lumen 해제' })).toBeTruthy();
	});

	it('displays a newly issued token once after creation', async () => {
		await renderApi();
		await createButton();

		await fireEvent.input(screen.getByRole('textbox', { name: /이름/ }), { target: { value: 'Desktop client' } });
		await fireEvent.click(await createButton());

		expect(await screen.findByText('mcp-afgl-secret-value')).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: '완료' }));
		expect(screen.queryByText('mcp-afgl-secret-value')).toBeNull();
	});

	it.each([
		['https://cloud.dmslab.re.kr/mcp', 'https://cloud.dmslab.re.kr/mcp'],
		['https://mcp.example.test', 'https://mcp.example.test'],
		['', 'https://api.example.test/api/v1/mcp'],
	])('copies authenticated HTTP JSON using the configured resource %s', async (configured, endpoint) => {
		const writeText = vi.fn().mockResolvedValue(undefined);
		Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
		siteConfig.update((config) => ({ ...config, mcp_url: configured }));
		await renderApi();
		await fireEvent.click(await createButton());
		const dialog = await screen.findByRole('dialog', { name: t('mcp.newToken') });
		await fireEvent.click(within(dialog).getByRole('button', { name: t('mcp.copyConfig') }));
		await waitFor(() => expect(writeText).toHaveBeenCalledOnce());
		expect(JSON.parse(writeText.mock.calls[0][0])).toEqual({
			mcpServers: { 'my-stream-server': { type: 'http', url: endpoint, headers: { Authorization: ['Bearer', 'mcp-afgl-secret-value'].join(' ') } } },
		});
		await fireEvent.click(within(dialog).getByRole('button', { name: t('mcp.done') }));
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(document.body.textContent).not.toContain('mcp-afgl-secret-value');
		expect(JSON.parse(screen.getByRole('region', { name: t('mcp.config') }).textContent!).mcpServers['my-stream-server'].headers.Authorization).toBe(['Bearer', 'YOUR_PERSONAL_MCP_TOKEN'].join(' '));
	});

	it('copies credential-free OAuth configuration even after issuing a personal token', async () => {
		const writeText = vi.fn().mockResolvedValue(undefined);
		Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
		siteConfig.update((config) => ({ ...config, mcp_url: 'https://cloud.dmslab.re.kr/mcp' }));
		await renderApi();
		await fireEvent.click(await createButton());
		const dialog = await screen.findByRole('dialog', { name: t('mcp.newToken') });
		await fireEvent.click(within(dialog).getByRole('button', { name: t('mcp.done') }));
		await selectMethod('oauth');
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.copyOAuthConfig') }));
		await waitFor(() => expect(writeText).toHaveBeenCalledOnce());
		expect(JSON.parse(writeText.mock.calls[0][0])).toEqual({
			mcpServers: { 'my-stream-server': { type: 'http', url: 'https://cloud.dmslab.re.kr/mcp' } },
		});
		expect(screen.getByText('https://cloud.dmslab.re.kr/mcp/oauth/authorize')).toBeTruthy();
	});
	it('clears one-time secrets during workspace reload without filtering the account list', async () => {
		const tokens = deferred<typeof activeToken[]>();
		const grants = deferred<typeof activeToken[]>();
		let reloading = false;
		api.get.mockImplementation((path: string) => path.startsWith('/api/v1/auth/mcp-projects')
			? Promise.resolve(accountResponse(path))
			: reloading ? (path.includes('oauth') ? grants.promise : tokens.promise)
				: Promise.resolve(accountResponse(path)));
		await renderApi();
		await createButton();
		await screen.findByText('Lumen', { selector: '.record-title strong' });
		await fireEvent.click(await createButton());
		await screen.findByText('mcp-afgl-secret-value');
		reloading = true;
		setProject('other', 'Other project');
		verifyAuth();
		await waitFor(() => {
			expect(api.get).toHaveBeenCalledWith('/api/v1/auth/mcp-tokens', 'token', undefined, scopedGetOptions);
			expect(api.get).toHaveBeenCalledWith('/api/v1/auth/mcp-oauth/grants', 'token', undefined, scopedGetOptions);
		});
		await waitFor(() => {
			expect(screen.queryByText('Lumen', { selector: '.record-title strong' })).toBeNull();
			expect(screen.queryByText('mcp-afgl-secret-value')).toBeNull();
			expect(screen.queryByRole('button', { name: 'Lumen 해제' })).toBeNull();
		});
		tokens.resolve([activeToken]);
		grants.resolve([]);
		await screen.findByText('Lumen', { selector: '.record-title strong' });
		expect(screen.queryByText('mcp-afgl-secret-value')).toBeNull();
	});

	it('rejects an old revoke confirmation and late B response after an A→B→A switch', async () => {
		const confirm = deferred<boolean>();
		const bTokens = deferred<typeof activeToken[]>();
		let aReads = 0;
		confirmDialog.mockReturnValue(confirm.promise);
		api.get.mockImplementation((path: string) => {
			if (path.startsWith('/api/v1/auth/mcp-projects')) return Promise.resolve(accountResponse(path));
			if (path.includes('oauth')) return Promise.resolve([]);
			if (get(auth).projectId === 'other') return bTokens.promise;
			aReads += 1;
			return Promise.resolve([{ ...activeToken, name: aReads === 1 ? 'Original A token' : 'Fresh A token' }]);
		});
		await renderApi();
		await createButton();
		await screen.findByText('Original A token');
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.revoke') }));
		setProject('other', 'Other project');
		verifyAuth();
		await waitFor(() => expect(screen.queryByText('Original A token')).toBeNull());
		await waitFor(() => expect(api.get.mock.calls.filter(([path]) => path === '/api/v1/auth/mcp-tokens')).toHaveLength(2));
		setProject('project', 'Project');
		verifyAuth();
		await screen.findByText('Fresh A token');
		confirm.resolve(true);
		bTokens.resolve([{ ...activeToken, name: 'Late B token' }]);
		await waitFor(() => expect(screen.queryByText('Late B token')).toBeNull());
		expect(api.delete).not.toHaveBeenCalled();
		expect(screen.getByText('Fresh A token')).toBeTruthy();
	});

	it('clears a saved credential after a failed verification without retaining plaintext or leaking raw server detail', async () => {
		api.post.mockRejectedValue(new ApiError('MCP authentication failed'));
		await renderApi();
		const input = await screen.findByLabelText(t('mcp.tokenLabel')) as HTMLInputElement;
		await fireEvent.input(input, { target: { value: 'mcp-afgl-saved-private-key' } });
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.verify') }));
		await screen.findByText(t('mcp.verifyError.unavailable'));
		expect(screen.queryByText('MCP authentication failed')).toBeNull();
		expect(input.value).toBe('');
		expect(document.body.textContent).not.toContain('mcp-afgl-saved-private-key');
	});

	it('checks a saved key with browser credentials for the current project and clears it on success', async () => {
		api.post.mockResolvedValue(connectionResult);
		await renderApi();
		const input = await screen.findByLabelText(t('mcp.tokenLabel')) as HTMLInputElement;
		await fireEvent.input(input, { target: { value: '  mcp-afgl-saved-private-key  ' } });
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.verify') }));
		await screen.findByText(t('mcp.verified'));
		expect(api.post).toHaveBeenCalledWith('/api/v1/auth/mcp-tokens/verify', { token: 'mcp-afgl-saved-private-key' }, 'token', 'project', scopedPostOptions);
		expect(input.value).toBe('');
		expect(document.body.textContent).not.toContain('mcp-afgl-saved-private-key');
		expect(screen.getByText(t('mcp.verificationDetails', { name: 'Afterglow', version: '1.0', protocol: '2025-11-25', count: 5 }))).toBeTruthy();
		expect(screen.getByText(t('mcp.verificationLimit'))).toBeTruthy();
	});

	it.each([
		[400, 'invalid_request', 'invalidRequest'],
		[400, 'invalid_token', 'invalidToken'],
		[503, 'not_configured', 'notConfigured'],
		[502, 'rejected', 'rejected'],
		[502, 'redirect', 'redirect'],
		[502, 'protocol', 'protocol'],
		[504, 'unavailable', 'unavailable'],
		[429, undefined, 'rateLimited'],
	])('localizes verification failure %s/%s rather than displaying the server detail', async (status, code, key) => {
		api.post.mockRejectedValue(Object.assign(new ApiError('Raw server detail'), { status, code }));
		await renderApi();
		const input = await screen.findByLabelText(t('mcp.tokenLabel')) as HTMLInputElement;
		await fireEvent.input(input, { target: { value: 'mcp-afgl-foreign-key' } });
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.verify') }));
		await screen.findByText(t(`mcp.verifyError.${key}` as Parameters<typeof t>[0]));
		expect(screen.queryByText('Raw server detail')).toBeNull();
		expect(input.value).toBe('');
	});

	it('drops an in-flight issued-key result when the one-time dialog closes', async () => {
		const verification = deferred<{ endpoint: string; protocol_version: string; server_name: string; server_version: string; tool_count: number }>();
		api.post.mockImplementation((path: string) => path.endsWith('/verify')
			? verification.promise
			: Promise.resolve({ ...activeToken, token: 'mcp-afgl-secret-value' }));
		await renderApi();
		await fireEvent.click(await createButton());
		await screen.findByText('mcp-afgl-secret-value');
		await fireEvent.click(screen.getAllByRole('button', { name: t('mcp.verify') }).find((button) => !button.hasAttribute('disabled'))!);
		const signal = api.post.mock.calls.at(-1)![4].signal as AbortSignal;
		expect(api.post.mock.calls.at(-1)![4]).toEqual(scopedPostOptions);
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.done') }));
		expect(signal.aborted).toBe(true);
		await act(async () => {
			verification.resolve({ endpoint: 'https://mcp.example.test', protocol_version: '2025-11-25', server_name: 'Private client', server_version: '1.0', tool_count: 5 });
		});
		expect(screen.queryByText(t('mcp.verified'))).toBeNull();
		expect(document.body.textContent).not.toContain('mcp-afgl-secret-value');
	});

	it('discards verification state and credentials when the owning project changes', async () => {
		const verification = deferred<{ endpoint: string; protocol_version: string; server_name: string; server_version: string; tool_count: number }>();
		api.post.mockReturnValue(verification.promise);
		await renderApi();
		const input = await screen.findByLabelText(t('mcp.tokenLabel')) as HTMLInputElement;
		await fireEvent.input(input, { target: { value: 'mcp-afgl-old-project-key' } });
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.verify') }));
		const signal = api.post.mock.calls[0][4].signal as AbortSignal;
		setProject('other', 'Other project');
		// Reverify before the DOM flush so the retained input still proves the draft was cleared.
		verifyAuth();
		expect(signal.aborted).toBe(true);
		await waitFor(() => expect(input.value).toBe(''));
		await act(async () => {
			verification.resolve({ endpoint: 'https://mcp.example.test', protocol_version: '2025-11-25', server_name: 'Old project server', server_version: '1.0', tool_count: 5 });
		});
		expect(screen.queryByText(t('mcp.verified'))).toBeNull();
		expect(screen.queryByText(t('mcp.verifying'))).toBeNull();
	});

	it.each(['user', 'token', 'project-aba', 'logout', 'unverified', 'switching', 'disabled', 'unmount', 'unverified-token', 'unverified-project'] as const)('drops one-time issuance and saved credentials on %s transition', async (transition) => {
		const issuance = deferred<typeof activeToken & { token: string }>();
		api.post.mockReturnValue(issuance.promise);
		const view = await renderApi();
		await createButton();
		await screen.findByText('Lumen', { selector: '.record-title strong' });
		await fireEvent.input(screen.getByLabelText(t('mcp.tokenLabel')), { target: { value: 'private-saved-key' } });
		await fireEvent.click(await createButton());
		if (transition === 'user' || transition === 'token' || transition === 'project-aba') {
			api.get.mockImplementation((path: string) => Promise.resolve(accountResponse(path, [{ ...activeToken, name: 'New owner token' }])));
			if (transition === 'user') setAuth({ token: 'token', userId: 'other-user' });
			else if (transition === 'token') setAuth({ token: 'other-token' });
			else {
				setProject('other', 'Other project');
				setProject('project', 'Project');
			}
			verifyAuth();
			await screen.findByText('New owner token');
		} else if (transition === 'logout') clearAuth();
		else if (transition === 'unmount') view.unmount();
		else if (transition === 'unverified') authReady.set(false);
		else if (transition === 'unverified-token') setAuth({ token: 'other-token' });
		else if (transition === 'unverified-project') setProject('other', 'Other project');
		else if (transition === 'switching') projectSwitching.set(true);
		else siteConfig.update((config) => ({ ...config, services: { ...config.services, mcp: false } }));
		await waitFor(() => expect(screen.queryByText('Lumen', { selector: '.record-title strong' })).toBeNull());
		expect((api.post.mock.calls[0][4].signal as AbortSignal).aborted).toBe(true);
		await act(async () => { issuance.resolve({ ...activeToken, token: 'late-issued-secret' }); });
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(document.body.textContent).not.toContain('late-issued-secret');
		expect(document.body.textContent).not.toContain('private-saved-key');
		const input = screen.queryByLabelText(t('mcp.tokenLabel')) as HTMLInputElement | null;
		if (input) expect(input.value).toBe('');
	});

	it('clears issued secrets when unmounted and ignores a late verification result after remount', async () => {
		const verification = deferred<typeof connectionResult>();
		api.post.mockImplementation((path: string) => path.endsWith('/verify')
			? verification.promise
			: Promise.resolve({ ...activeToken, token: 'mcp-afgl-secret-value' }));
		const view = await renderApi();
		await fireEvent.click(await createButton());
		const dialog = await screen.findByRole('dialog', { name: t('mcp.newToken') });
		await fireEvent.click(within(dialog).getByRole('button', { name: t('mcp.verify') }));
		const signal = api.post.mock.calls.at(-1)![4].signal as AbortSignal;
		view.unmount();
		expect(signal.aborted).toBe(true);
		await renderApi();
		await act(async () => { verification.resolve(connectionResult); });
		expect(screen.queryByText(t('mcp.verified'))).toBeNull();
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(document.body.textContent).not.toContain('mcp-afgl-secret-value');
	});

	it('initially renders only OAuth setup and grants, then only the explicitly selected API setup and tokens', async () => {
		const grant = { ...activeToken, id: 'oauth-1', name: 'OAuth client', source: 'oauth', is_lumen_default: false };
		api.get.mockImplementation((path: string) => Promise.resolve(path.includes('oauth') ? [grant] : accountResponse(path)));
		render(McpAccessSection);
		await screen.findByRole('button', { name: t('mcp.revokeAccess') });
		const methods = screen.getByRole('group', { name: t('mcp.method') });
		expect(within(methods).getByRole('button', { name: t('mcp.methodOAuth') }).getAttribute('aria-pressed')).toBe('true');
		expect(within(methods).getByRole('button', { name: t('mcp.methodApiKey') }).getAttribute('aria-pressed')).toBe('false');
		expect(screen.getByRole('heading', { name: t('mcp.oauthSetupTitle') })).toBeTruthy();
		expect(screen.getByRole('heading', { name: t('mcp.oauth') })).toBeTruthy();
		expect(screen.queryByRole('heading', { name: t('mcp.personal') })).toBeNull();
		expect(screen.queryByLabelText(t('mcp.name'))).toBeNull();
		expect(screen.queryByLabelText(t('mcp.tokenLabel'))).toBeNull();
		expect(screen.queryByText('Lumen', { selector: '.record-title strong' })).toBeNull();
		expect(screen.queryByRole('region', { name: t('mcp.config') })).toBeNull();
		expect(configJson('oauth')).toEqual({ mcpServers: { 'my-stream-server': { type: 'http', url: 'https://api.example.test/api/v1/mcp' } } });
		expect(api.post).not.toHaveBeenCalled();
		await selectMethod('api');
		await createButton();
		expect(within(methods).getByRole('button', { name: t('mcp.methodApiKey') }).getAttribute('aria-pressed')).toBe('true');
		expect(within(methods).getByRole('button', { name: t('mcp.methodOAuth') }).getAttribute('aria-pressed')).toBe('false');
		expect(screen.getByRole('heading', { name: t('mcp.personal') })).toBeTruthy();
		expect(screen.getByRole('heading', { name: t('mcp.setupTitle') })).toBeTruthy();
		expect(screen.getByLabelText(t('mcp.tokenLabel'))).toBeTruthy();
		expect(screen.getByText('Lumen', { selector: '.record-title strong' })).toBeTruthy();
		expect(screen.queryByText('OAuth client')).toBeNull();
		expect(screen.queryByRole('heading', { name: t('mcp.oauth') })).toBeNull();
		expect(screen.queryByRole('region', { name: t('mcp.oauthConfig') })).toBeNull();
		expect(configJson('setup').mcpServers['my-stream-server'].headers.Authorization).toBe(['Bearer', 'YOUR_PERSONAL_MCP_TOKEN'].join(' '));
		await selectMethod('oauth');
		expect(screen.getByRole('button', { name: t('mcp.revokeAccess') })).toBeTruthy();
		expect(screen.queryByText('Lumen', { selector: '.record-title strong' })).toBeNull();
		expect(screen.queryByRole('button', { name: t('mcp.create') })).toBeNull();
		expect(api.post).not.toHaveBeenCalled();
	});

	it.each([
		['1d', { expires_at: '2028-02-01T23:45:12.345Z' }],
		['1w', { expires_at: '2028-02-07T23:45:12.345Z' }],
		['1m', { expires_at: defaultExpiry }],
		['3m', { expires_at: '2028-04-30T23:45:12.345Z' }],
		['6m', { expires_at: '2028-07-31T23:45:12.345Z' }],
		['1y', { expires_at: '2029-01-31T23:45:12.345Z' }],
		['never', { non_expiring: true }],
		['custom', { expires_at: new Date(2028, 2, 15, 10, 20).toISOString() }],
	] as const)('posts the actual %s lifetime with mutually exclusive expiration fields', async (lifetime, expiration) => {
		await renderApi();
		await createButton();
		const select = screen.getByRole('combobox', { name: t('mcp.expiry') });
		expect(within(select).getAllByRole('option').map((option) => (option as HTMLOptionElement).value)).toEqual(['1d', '1w', '1m', '3m', '6m', '1y', 'never', 'custom']);
		await fireEvent.change(select, { target: { value: lifetime } });
		if (lifetime === 'custom') await fireEvent.input(screen.getByLabelText(t('mcp.customExpiry')), { target: { value: '2028-03-15T10:20' } });
		await fireEvent.click(await createButton());
		expect(api.post).toHaveBeenCalledExactlyOnceWith('/api/v1/auth/mcp-tokens', {
			name: 'Lumen', access_level: 'read', project_scope: 'selected', project_ids: ['project'], ...expiration,
		}, 'token', 'project', scopedPostOptions);
		const dialog = await screen.findByRole('dialog', { name: t('mcp.newToken') });
		await fireEvent.click(within(dialog).getByRole('button', { name: t('mcp.done') }));
		expect((screen.getByLabelText(t('mcp.expiry')) as HTMLSelectElement).value).toBe('1m');
		expect(screen.queryByLabelText(t('mcp.customExpiry'))).toBeNull();
	});

	it.each([
		['2027-01-31T00:15:42.123Z', '1m', '2027-02-28T00:15:42.123Z'],
		['2028-03-31T00:15:42.123Z', '3m', '2028-06-30T00:15:42.123Z'],
		['2027-08-31T00:15:42.123Z', '6m', '2028-02-29T00:15:42.123Z'],
		['2028-08-31T00:15:42.123Z', '6m', '2029-02-28T00:15:42.123Z'],
		['2028-02-29T00:15:42.123Z', '1y', '2029-02-28T00:15:42.123Z'],
	] as const)('clamps %s plus %s in the UTC calendar in the posted payload', async (now, lifetime, expires_at) => {
		vi.setSystemTime(new Date(now));
		await renderApi();
		await createButton();
		await fireEvent.change(screen.getByLabelText(t('mcp.expiry')), { target: { value: lifetime } });
		await fireEvent.click(await createButton());
		expect(api.post).toHaveBeenCalledExactlyOnceWith('/api/v1/auth/mcp-tokens', {
			name: 'Lumen', access_level: 'read', project_scope: 'selected', project_ids: ['project'], expires_at,
		}, 'token', 'project', scopedPostOptions);
	});

	it.each([
		['empty', ''],
		['invalid', 'not-a-date'],
		['past', '2027-12-31T12:00'],
	] as const)('rejects a %s custom expiry even on direct form submission', async (_kind, value) => {
		await renderApi();
		const button = await createButton();
		await fireEvent.change(screen.getByLabelText(t('mcp.expiry')), { target: { value: 'custom' } });
		await fireEvent.input(screen.getByLabelText(t('mcp.customExpiry')), { target: { value } });
		await fireEvent.submit(button.closest('form')!);
		await screen.findByText(t('mcp.invalidExpiry'));
		expect(api.post).not.toHaveBeenCalled();
		expect(screen.queryByRole('dialog')).toBeNull();
	});

	it('rejects a custom expiry equal to now', async () => {
		const now = new Date(2028, 0, 31, 12, 0);
		vi.setSystemTime(now);
		await renderApi();
		const button = await createButton();
		await fireEvent.change(screen.getByLabelText(t('mcp.expiry')), { target: { value: 'custom' } });
		await fireEvent.input(screen.getByLabelText(t('mcp.customExpiry')), { target: { value: '2028-01-31T12:00' } });
		await fireEvent.submit(button.closest('form')!);
		await screen.findByText(t('mcp.invalidExpiry'));
		expect(api.post).not.toHaveBeenCalled();
	});

	it('reveals the custom date field only for custom without issuing until submit or leaking it into a preset', async () => {
		await renderApi();
		await createButton();
		expect(screen.queryByLabelText(t('mcp.customExpiry'))).toBeNull();
		await fireEvent.change(screen.getByLabelText(t('mcp.expiry')), { target: { value: 'custom' } });
		await fireEvent.input(screen.getByLabelText(t('mcp.customExpiry')), { target: { value: '2028-05-01T10:20' } });
		expect(api.post).not.toHaveBeenCalled();
		expect(screen.queryByRole('dialog')).toBeNull();
		await fireEvent.change(screen.getByLabelText(t('mcp.expiry')), { target: { value: '1m' } });
		expect(screen.queryByLabelText(t('mcp.customExpiry'))).toBeNull();
		await fireEvent.click(await createButton());
		expect(api.post).toHaveBeenCalledExactlyOnceWith('/api/v1/auth/mcp-tokens', {
			name: 'Lumen', access_level: 'read', project_scope: 'selected', project_ids: ['project'], expires_at: defaultExpiry,
		}, 'token', 'project', scopedPostOptions);
	});

	it('clears issued secrets, saved credentials and successful verification when the method changes', async () => {
		api.post.mockImplementation((path: string) => Promise.resolve(path.endsWith('/verify') ? connectionResult : { ...activeToken, token: 'method-private-secret' }));
		await renderApi();
		await fireEvent.click(await createButton());
		const dialog = await screen.findByRole('dialog', { name: t('mcp.newToken') });
		await fireEvent.click(within(dialog).getByRole('button', { name: t('mcp.verify') }));
		await screen.findByText(t('mcp.verified'));
		await selectMethod('oauth');
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(screen.queryByText(t('mcp.verified'))).toBeNull();
		expect(document.body.textContent).not.toContain('method-private-secret');
		await selectMethod('api');
		expect((screen.getByLabelText(t('mcp.tokenLabel')) as HTMLInputElement).value).toBe('');
		expect(screen.queryByText(t('mcp.verified'))).toBeNull();
		await fireEvent.input(screen.getByLabelText(t('mcp.tokenLabel')), { target: { value: 'saved-method-secret' } });
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.verify') }));
		await screen.findByText(t('mcp.verified'));
		await selectMethod('oauth');
		await selectMethod('api');
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(document.body.textContent).not.toContain('method-private-secret');
		expect(screen.queryByText(t('mcp.verified'))).toBeNull();
		await fireEvent.input(screen.getByLabelText(t('mcp.tokenLabel')), { target: { value: 'unverified-method-secret' } });
		await selectMethod('oauth');
		await selectMethod('api');
		expect((screen.getByLabelText(t('mcp.tokenLabel')) as HTMLInputElement).value).toBe('');
	});

	it.each(['success', 'failure'] as const)('fences a pending issuance %s through API→OAuth→API even after a newer issuance', async (outcome) => {
		const pending = deferred<typeof activeToken & { token: string }>();
		api.post.mockReturnValueOnce(pending.promise);
		await renderApi();
		await fireEvent.click(await createButton());
		const signal = api.post.mock.calls[0][4].signal as AbortSignal;
		await selectMethod('oauth');
		expect(signal.aborted).toBe(true);
		expect(screen.queryByRole('dialog')).toBeNull();
		await selectMethod('api');
		await fireEvent.click(await createButton());
		await screen.findByText('mcp-afgl-secret-value');
		await act(async () => {
			if (outcome === 'success') pending.resolve({ ...activeToken, token: 'stale-method-secret' });
			else pending.reject(new ApiError('Stale method issuance error'));
		});
		expect(screen.getByText('mcp-afgl-secret-value')).toBeTruthy();
		expect(document.body.textContent).not.toContain('stale-method-secret');
		expect(screen.queryByText('Stale method issuance error')).toBeNull();
	});

	describe.each(['saved', 'issued'] as const)('%s verification fences', (source) => {
		it.each(['method', 'method-aba', 'scope-aba', 'secret-aba'] as const)('discards late success and failure across %s', async (boundary) => {
			// A fresh verification must survive either outcome of the old request.
			for (const outcome of ['success', 'failure'] as const) {
				const pending = deferred<typeof connectionResult>();
				let verifies = 0;
				api.post.mockImplementation((path: string) => path.endsWith('/verify')
					? ++verifies === 1 ? pending.promise : Promise.resolve({ ...connectionResult, server_name: 'Current server' })
					: Promise.resolve({ ...activeToken, token: 'same-issued-secret' }));
				await renderApi();
				await createButton();
				if (source === 'issued') {
					await fireEvent.click(await createButton());
					const dialog = await screen.findByRole('dialog', { name: t('mcp.newToken') });
					await fireEvent.click(within(dialog).getByRole('button', { name: t('mcp.verify') }));
				} else {
					await fireEvent.input(screen.getByLabelText(t('mcp.tokenLabel')), { target: { value: 'same-saved-secret' } });
					await fireEvent.click(screen.getByRole('button', { name: t('mcp.verify') }));
				}
				const signal = api.post.mock.calls.at(-1)![4].signal as AbortSignal;
				if (boundary === 'method' || boundary === 'method-aba') {
					await selectMethod('oauth');
					if (boundary === 'method') {
						await act(async () => {
							if (outcome === 'success') pending.resolve({ ...connectionResult, server_name: 'Stale server' });
							else pending.reject(Object.assign(new ApiError('Private error'), { code: 'invalid_token' }));
						});
					}
					await selectMethod('api');
				} else if (boundary === 'scope-aba') {
					setProject('other', 'Other project');
					setProject('project', 'Project');
					verifyAuth();
					await createButton();
				} else if (source === 'issued') {
					await fireEvent.click(screen.getByRole('button', { name: t('mcp.done') }));
				} else {
					// Closing an issued dialog clears the shared saved-verification generation too.
					await fireEvent.click(await createButton());
					await screen.findByRole('dialog', { name: t('mcp.newToken') });
					await fireEvent.click(screen.getByRole('button', { name: t('mcp.done') }));
				}
				expect(signal.aborted).toBe(true);
				expect(screen.queryByText(t('mcp.verified'))).toBeNull();
				expect(screen.queryByText(t('mcp.verifyError.invalidToken'))).toBeNull();
				if (source === 'issued') {
					await fireEvent.click(await createButton());
					const dialog = await screen.findByRole('dialog', { name: t('mcp.newToken') });
					await fireEvent.click(within(dialog).getByRole('button', { name: t('mcp.verify') }));
				} else {
					await fireEvent.input(screen.getByLabelText(t('mcp.tokenLabel')), { target: { value: 'same-saved-secret' } });
					await fireEvent.click(screen.getByRole('button', { name: t('mcp.verify') }));
				}
				await screen.findByText(t('mcp.verificationDetails', { name: 'Current server', version: '1.0', protocol: '2025-11-25', count: 5 }));
				if (boundary !== 'method') await act(async () => {
					if (outcome === 'success') pending.resolve({ ...connectionResult, server_name: 'Stale server' });
					else pending.reject(Object.assign(new ApiError('Private error'), { code: 'invalid_token' }));
				});
				expect(screen.getByText(t('mcp.verified'))).toBeTruthy();
				expect(screen.queryByText(t('mcp.verifyError.invalidToken'))).toBeNull();
				expect(document.body.textContent).not.toContain('Stale server');
				expect(document.body.textContent).not.toContain('Private error');
				cleanup();
				api.post.mockClear();
			}
		});
	});

	it('copies whole parseable JSON from each labeled JSON block, never its badge or controls', async () => {
		const writeText = clipboard();
		siteConfig.update((config) => ({ ...config, mcp_url: 'https://mcp.example.test/custom' }));
		render(McpAccessSection);
		await screen.findByRole('button', { name: t('mcp.copyOAuthConfig') });
		const oauth = configBlock('oauth');
		expect(within(oauth).getByText('mcp.json')).toBeTruthy();
		await fireEvent.click(within(oauth).getByRole('button', { name: t('mcp.copyOAuthConfig') }));
		await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
		expect(JSON.parse(writeText.mock.calls[0][0])).toEqual(configJson('oauth'));
		expect(JSON.parse(writeText.mock.calls[0][0])).toEqual({ mcpServers: { 'my-stream-server': { type: 'http', url: 'https://mcp.example.test/custom' } } });
		await selectMethod('api');
		await createButton();
		const setup = configBlock('setup');
		expect(within(setup).getByText('mcp.json')).toBeTruthy();
		await fireEvent.click(within(setup).getByRole('button', { name: t('mcp.copySetupConfig') }));
		await waitFor(() => expect(writeText).toHaveBeenCalledTimes(2));
		expect(JSON.parse(writeText.mock.calls[1][0])).toEqual(configJson('setup'));
		expect(JSON.parse(writeText.mock.calls[1][0])).toEqual({ mcpServers: { 'my-stream-server': { type: 'http', url: 'https://mcp.example.test/custom', headers: { Authorization: ['Bearer', 'YOUR_PERSONAL_MCP_TOKEN'].join(' ') } } } });
		await fireEvent.click(await createButton());
		const dialog = await screen.findByRole('dialog', { name: t('mcp.newToken') });
		const issued = configBlock('config');
		expect(within(issued).getByText('mcp.json')).toBeTruthy();
		await fireEvent.click(within(issued).getByRole('button', { name: t('mcp.copyConfig') }));
		await waitFor(() => expect(writeText).toHaveBeenCalledTimes(3));
		expect(JSON.parse(writeText.mock.calls[2][0])).toEqual(configJson('config'));
		expect(JSON.parse(writeText.mock.calls[2][0])).toEqual({ mcpServers: { 'my-stream-server': { type: 'http', url: 'https://mcp.example.test/custom', headers: { Authorization: ['Bearer', 'mcp-afgl-secret-value'].join(' ') } } } });
		await fireEvent.click(within(dialog).getByRole('button', { name: t('mcp.copy') }));
		await waitFor(() => expect(writeText).toHaveBeenCalledTimes(4));
		expect(writeText.mock.calls[3][0]).toBe('mcp-afgl-secret-value');
	});

	describe.each(['oauth', 'setup', 'token', 'config'] as const)('%s clipboard feedback', (target) => {
		const copyKey = { oauth: 'mcp.copyOAuthConfig', setup: 'mcp.copySetupConfig', token: 'mcp.copy', config: 'mcp.copyConfig' } as const;

		async function openTarget() {
			if (target === 'oauth') render(McpAccessSection);
			else {
				await renderApi();
				await createButton();
				if (target === 'token' || target === 'config') {
					await fireEvent.click(await createButton());
					await screen.findByRole('dialog', { name: t('mcp.newToken') });
				}
			}
		}

		function targetScope() {
			return target === 'token' ? screen.getByRole('dialog', { name: t('mcp.newToken') }) : configBlock(target);
		}

		it.each(['success', 'failure'] as const)('keeps %s feedback local to the clicked control and allows retry', async (outcome) => {
			const writeText = clipboard();
			if (outcome === 'failure') writeText.mockRejectedValueOnce(new Error('Private clipboard failure'));
			await openTarget();
			const scope = targetScope();
			const button = within(scope).getByRole('button', { name: t(copyKey[target]) });
			await fireEvent.click(button);
			if (outcome === 'success') {
				await waitFor(() => expect(button.textContent).toContain(t('mcp.copied')));
				expect(screen.getAllByRole('button', { name: t('mcp.copied') })).toHaveLength(1);
				expect(screen.queryByText(t('mcp.copyFailed'))).toBeNull();
			} else {
				const failure = await within(scope).findByText(t('mcp.copyFailed'));
				expect(failure.getAttribute('role')).toBe('alert');
				expect(screen.getAllByText(t('mcp.copyFailed'))).toHaveLength(1);
				expect(screen.queryByRole('button', { name: t('mcp.copied') })).toBeNull();
				expect(button.textContent).toContain(t(copyKey[target]));
				expect(document.body.textContent).not.toContain('Private clipboard failure');
			}
			if (target === 'config') expect(within(screen.getByRole('dialog')).getByRole('button', { name: t('mcp.copy') })).toBeTruthy();
			if (target === 'token') expect(within(configBlock('config')).getByRole('button', { name: t('mcp.copyConfig') })).toBeTruthy();
			if (target === 'token' || target === 'config') {
				expect(within(configBlock('setup')).queryByText(t('mcp.copyFailed'))).toBeNull();
				expect(within(configBlock('setup')).getByRole('button', { name: t('mcp.copySetupConfig') })).toBeTruthy();
			}
			await fireEvent.click(button);
			await waitFor(() => expect(writeText).toHaveBeenCalledTimes(2));
			await waitFor(() => expect(button.textContent).toContain(t('mcp.copied')));
			expect(screen.queryByText(t('mcp.copyFailed'))).toBeNull();
		});

		it.each((['method-aba', 'scope-aba', 'endpoint'] as const).filter((boundary) => target !== 'token' || boundary !== 'endpoint'))('ignores delayed success and failure across %s even with identical final content', async (boundary) => {
			for (const outcome of ['success', 'failure'] as const) {
				const pending = deferred<void>();
				const writeText = clipboard(vi.fn().mockReturnValueOnce(pending.promise).mockResolvedValue(undefined));
				await openTarget();
				await fireEvent.click(within(targetScope()).getByRole('button', { name: t(copyKey[target]) }));
				expect(writeText).toHaveBeenCalledOnce();
				if (boundary === 'method-aba') {
					await selectMethod(target === 'oauth' ? 'api' : 'oauth');
					await selectMethod(target === 'oauth' ? 'oauth' : 'api');
				} else if (boundary === 'scope-aba') {
					setProject('other', 'Other project');
					setProject('project', 'Project');
					verifyAuth();
					await screen.findByRole('button', { name: t('mcp.refresh') });
				} else {
					siteConfig.update((config) => ({ ...config, mcp_url: 'https://changed.example.test/mcp' }));
					await act(async () => {});
				}
				if (boundary !== 'endpoint' && (target === 'token' || target === 'config')) {
					await fireEvent.click(await createButton());
					await screen.findByRole('dialog', { name: t('mcp.newToken') });
				}
				const scope = targetScope();
				expect(within(scope).queryByRole('button', { name: t('mcp.copied') })).toBeNull();
				await act(async () => {
					if (outcome === 'success') pending.resolve();
					else pending.reject(new Error('Stale clipboard error'));
				});
				expect(within(scope).queryByRole('button', { name: t('mcp.copied') })).toBeNull();
				expect(screen.queryByText(t('mcp.copyFailed'))).toBeNull();
				expect(document.body.textContent).not.toContain('Stale clipboard error');
				await fireEvent.click(within(scope).getByRole('button', { name: t(copyKey[target]) }));
				await within(scope).findByRole('button', { name: t('mcp.copied') });
				cleanup();
				siteConfig.update((config) => ({ ...config, mcp_url: '' }));
			}
		});
	});

	describe.each(['token', 'config'] as const)('%s secret-bound clipboard', (target) => {
		it.each(['changed', 'aba'] as const)('discards delayed results after a %s one-time secret, preserving a newer copy', async (boundary) => {
			for (const outcome of ['success', 'failure'] as const) {
				const pending = deferred<void>();
				const writeText = clipboard(vi.fn().mockReturnValueOnce(pending.promise).mockResolvedValue(undefined));
				api.post.mockResolvedValueOnce({ ...activeToken, token: 'first-secret' })
					.mockResolvedValue({ ...activeToken, token: boundary === 'aba' ? 'first-secret' : 'replacement-secret' });
				await renderApi();
				await fireEvent.click(await createButton());
				let dialog = await screen.findByRole('dialog', { name: t('mcp.newToken') });
				await fireEvent.click(within(dialog).getByRole('button', { name: t(target === 'token' ? 'mcp.copy' : 'mcp.copyConfig') }));
				await fireEvent.click(within(dialog).getByRole('button', { name: t('mcp.done') }));
				await fireEvent.click(await createButton());
				dialog = await screen.findByRole('dialog', { name: t('mcp.newToken') });
				expect(within(dialog).queryByRole('button', { name: t('mcp.copied') })).toBeNull();
				const button = within(dialog).getByRole('button', { name: t(target === 'token' ? 'mcp.copy' : 'mcp.copyConfig') });
				await fireEvent.click(button);
				await waitFor(() => expect(button.textContent).toContain(t('mcp.copied')));
				const secret = boundary === 'aba' ? 'first-secret' : 'replacement-secret';
				expect(target === 'token' ? writeText.mock.calls[1][0] : JSON.parse(writeText.mock.calls[1][0]).mcpServers['my-stream-server'].headers.Authorization).toBe(target === 'token' ? secret : ['Bearer', secret].join(' '));
				await act(async () => {
					if (outcome === 'success') pending.resolve();
					else pending.reject(new Error('Old secret clipboard error'));
				});
				expect(button.textContent).toContain(t('mcp.copied'));
				expect(screen.queryByText(t('mcp.copyFailed'))).toBeNull();
				expect(document.body.textContent).not.toContain('Old secret clipboard error');
				cleanup();
			}
		});
	});

	it('keeps overlapping raw-token and issued-JSON clipboard outcomes independent', async () => {
		const raw = deferred<void>();
		const json = deferred<void>();
		clipboard(vi.fn().mockReturnValueOnce(raw.promise).mockReturnValueOnce(json.promise));
		await renderApi();
		await fireEvent.click(await createButton());
		const dialog = await screen.findByRole('dialog', { name: t('mcp.newToken') });
		const tokenButton = within(dialog).getByRole('button', { name: t('mcp.copy') });
		const configButton = within(configBlock('config')).getByRole('button', { name: t('mcp.copyConfig') });
		await fireEvent.click(tokenButton);
		await fireEvent.click(configButton);
		await act(async () => { json.resolve(); });
		expect(configButton.textContent).toContain(t('mcp.copied'));
		expect(tokenButton.textContent).toContain(t('mcp.copy'));
		await act(async () => { raw.reject(new Error('Clipboard denied')); });
		expect(within(dialog).getByText(t('mcp.copyFailed')).getAttribute('role')).toBe('alert');
		expect(within(configBlock('config')).queryByText(t('mcp.copyFailed'))).toBeNull();
		expect(configButton.textContent).toContain(t('mcp.copied'));
		expect(tokenButton.textContent).toContain(t('mcp.copy'));
	});

	it.each(['old-success', 'old-failure'] as const)('keeps a newer copy outcome when an overlapping %s arrives', async (outcome) => {
		const old = deferred<void>();
		const writeText = clipboard(vi.fn().mockReturnValueOnce(old.promise));
		if (outcome === 'old-success') writeText.mockRejectedValueOnce(new Error('Current clipboard failure'));
		else writeText.mockResolvedValueOnce(undefined);
		render(McpAccessSection);
		const button = await screen.findByRole('button', { name: t('mcp.copyOAuthConfig') });
		await fireEvent.click(button);
		await fireEvent.click(button);
		if (outcome === 'old-success') await screen.findByText(t('mcp.copyFailed'));
		else await waitFor(() => expect(button.textContent).toContain(t('mcp.copied')));
		await act(async () => {
			if (outcome === 'old-success') old.resolve();
			else old.reject(new Error('Old clipboard failure'));
		});
		if (outcome === 'old-success') {
			expect(screen.getByText(t('mcp.copyFailed'))).toBeTruthy();
			expect(button.textContent).toContain(t('mcp.copyOAuthConfig'));
		} else {
			expect(screen.queryByText(t('mcp.copyFailed'))).toBeNull();
			expect(button.textContent).toContain(t('mcp.copied'));
		}
	});

	describe.each(['set-default', 'clear-default', 'revoke-token', 'revoke-oauth'] as const)('%s action', (action) => {
		const record = { ...activeToken, id: 'token/one', grant_id: 'grant/one', name: 'Action client', is_lumen_default: action === 'clear-default' };
		const label = { 'set-default': 'mcp.setLumen', 'clear-default': 'mcp.clearLumen', 'revoke-token': 'mcp.revoke', 'revoke-oauth': 'mcp.revokeAccess' } as const;
		const errorKey = { 'set-default': 'mcp.selectFailed', 'clear-default': 'mcp.clearFailed', 'revoke-token': 'mcp.revokeFailed', 'revoke-oauth': 'mcp.revokeOAuthFailed' } as const;
		const path = action === 'set-default' ? '/api/v1/auth/mcp-tokens/token%2Fone/lumen-default'
			: action === 'clear-default' ? '/api/v1/auth/mcp-tokens/lumen-default'
				: action === 'revoke-token' ? '/api/v1/auth/mcp-tokens/token%2Fone' : '/api/v1/auth/mcp-oauth/grants/grant%2Fone';

		async function openAction() {
			if (action === 'revoke-oauth') render(McpAccessSection);
			else await renderApi();
			await screen.findByRole('group', { name: t('mcp.savedRestrictions') });
			return screen.getByRole('button', { name: t(label[action]) });
		}

		it('sends the scoped mutation and renders the authoritative reload', async () => {
			let rows = [record];
			api.get.mockImplementation((path: string) => Promise.resolve(path.startsWith('/api/v1/auth/mcp-projects') ? accountResponse(path)
				: path.includes('oauth') ? action === 'revoke-oauth' ? rows : [] : action === 'revoke-oauth' ? [] : rows));
			const mutation = deferred<void>();
			const mutate = () => mutation.promise.then(() => {
				rows = action === 'set-default' || action === 'clear-default' ? [{ ...record, is_lumen_default: action === 'set-default' }] : [];
			});
			api.put.mockImplementation(mutate);
			api.delete.mockImplementation(mutate);
			await fireEvent.click(await openAction());
			await waitFor(() => {
				if (action === 'set-default') expect(api.put).toHaveBeenCalledExactlyOnceWith(path, {}, 'token', 'project');
				else if (action === 'clear-default') expect(api.delete).toHaveBeenCalledExactlyOnceWith(path, 'token', 'project');
				else expect(api.delete).toHaveBeenCalledExactlyOnceWith(path, 'token');
			});
			if (action.startsWith('revoke')) expect(confirmDialog).toHaveBeenCalledExactlyOnceWith(t(action === 'revoke-oauth' ? 'mcp.revokeOAuthConfirm' : 'mcp.revokeConfirm', { name: action === 'revoke-oauth' ? `${t('mcp.oauth')} 1` : record.name }));
			else expect(confirmDialog).not.toHaveBeenCalled();
			for (const button of screen.getAllByRole('button', { name: t(label[action]) })) expect(button.hasAttribute('disabled')).toBe(true);
			await act(async () => { mutation.resolve(); });
			if (action === 'set-default') await screen.findByRole('button', { name: t('mcp.clearLumen') });
			else if (action === 'clear-default') await screen.findByRole('button', { name: t('mcp.setLumen') });
			else {
				await screen.findByText(t(action === 'revoke-oauth' ? 'mcp.emptyOAuth' : 'mcp.emptyTokens'));
				expect(screen.queryByText(record.name)).toBeNull();
			}
			expect(api.get).toHaveBeenCalledWith(action === 'revoke-oauth' ? '/api/v1/auth/mcp-oauth/grants' : '/api/v1/auth/mcp-tokens', 'token', undefined, scopedGetOptions);
		});

		it('keeps the record and localizes a failed mutation', async () => {
			api.get.mockImplementation((path: string) => Promise.resolve(path.startsWith('/api/v1/auth/mcp-projects') ? accountResponse(path)
				: path.includes('oauth') ? action === 'revoke-oauth' ? [record] : [] : action === 'revoke-oauth' ? [] : [record]));
			api.put.mockRejectedValue(new Error('Private mutation detail'));
			api.delete.mockRejectedValue(new Error('Private mutation detail'));
			await fireEvent.click(await openAction());
			await screen.findByText(t(errorKey[action]));
			expect(screen.getByRole('group', { name: t('mcp.savedRestrictions') })).toBeTruthy();
			expect(screen.getByRole('button', { name: t(label[action]) }).hasAttribute('disabled')).toBe(false);
			expect(document.body.textContent).not.toContain('Private mutation detail');
		});
	});

	it.each(['personal_token', 'oauth'] as const)('does not revoke %s access when confirmation is canceled', async (source) => {
		confirmDialog.mockResolvedValue(false);
		const record = { ...activeToken, source, name: 'Canceled client' };
		api.get.mockImplementation((path: string) => Promise.resolve(path.startsWith('/api/v1/auth/mcp-projects') ? accountResponse(path)
			: path.includes('oauth') ? source === 'oauth' ? [record] : [] : source === 'personal_token' ? [record] : []));
		if (source === 'oauth') render(McpAccessSection);
		else await renderApi();
		await screen.findByRole('button', { name: t(source === 'oauth' ? 'mcp.revokeAccess' : 'mcp.revoke') });
		await fireEvent.click(screen.getByRole('button', { name: t(source === 'oauth' ? 'mcp.revokeAccess' : 'mcp.revoke') }));
		expect(confirmDialog).toHaveBeenCalledOnce();
		expect(api.delete).not.toHaveBeenCalled();
		expect(screen.getByRole('group', { name: t('mcp.savedRestrictions') })).toBeTruthy();
	});

	it('discards an OAuth revoke confirmation across an A→B→A scope change', async () => {
		const confirmation = deferred<boolean>();
		confirmDialog.mockReturnValue(confirmation.promise);
		let generation = 'Old';
		api.get.mockImplementation((path: string) => Promise.resolve(path.startsWith('/api/v1/auth/mcp-projects') ? accountResponse(path)
			: path.includes('oauth') ? [{ ...activeToken, source: 'oauth', name: `${generation} OAuth client`, projects: [{ id: 'project', name: `${generation} project` }] }] : []));
		render(McpAccessSection);
		await screen.findByText(t('mcp.savedProjects', { projects: 'Old project' }));
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.revokeAccess') }));
		generation = 'Current';
		setProject('other', 'Other project');
		setProject('project', 'Project');
		verifyAuth();
		await screen.findByText(t('mcp.savedProjects', { projects: 'Current project' }));
		await act(async () => { confirmation.resolve(true); });
		expect(api.delete).not.toHaveBeenCalled();
		expect(screen.getByText(t('mcp.savedProjects', { projects: 'Current project' }))).toBeTruthy();
	});

	it.each(['expired', 'revoked'] as const)('does not offer a %s token as the Lumen default but leaves revoke reachable', async (status) => {
		api.get.mockImplementation((path: string) => Promise.resolve(accountResponse(path, [{ ...activeToken, status, is_lumen_default: false }])));
		await renderApi();
		await createButton();
		expect(screen.getByRole('button', { name: t('mcp.setLumen') }).hasAttribute('disabled')).toBe(true);
		expect(screen.getByRole('button', { name: t('mcp.revoke') }).hasAttribute('disabled')).toBe(false);
		expect(api.put).not.toHaveBeenCalled();
	});

	it.each(['personal_token', 'oauth'] as const)('discards a delayed %s revoke confirmation across method ABA', async (source) => {
		const confirmation = deferred<boolean>();
		confirmDialog.mockReturnValue(confirmation.promise);
		const record = { ...activeToken, source, name: 'Method-fenced client' };
		api.get.mockImplementation((path: string) => Promise.resolve(path.startsWith('/api/v1/auth/mcp-projects') ? accountResponse(path)
			: path.includes('oauth') ? source === 'oauth' ? [record] : [] : source === 'personal_token' ? [record] : []));
		if (source === 'oauth') render(McpAccessSection);
		else await renderApi();
		await screen.findByRole('button', { name: t(source === 'oauth' ? 'mcp.revokeAccess' : 'mcp.revoke') });
		await fireEvent.click(screen.getByRole('button', { name: t(source === 'oauth' ? 'mcp.revokeAccess' : 'mcp.revoke') }));
		await selectMethod(source === 'oauth' ? 'api' : 'oauth');
		await selectMethod(source === 'oauth' ? 'oauth' : 'api');
		expect(screen.getByRole('group', { name: t('mcp.savedRestrictions') })).toBeTruthy();
		await act(async () => { confirmation.resolve(true); });
		expect(api.delete).not.toHaveBeenCalled();
		expect(screen.getByRole('group', { name: t('mcp.savedRestrictions') })).toBeTruthy();
	});

	it.each(['set-default', 'clear-default', 'revoke-token', 'revoke-oauth'] as const)('does not publish a late %s failure after method ABA', async (action) => {
		const mutation = deferred<void>();
		const record = { ...activeToken, name: 'Pending action client', is_lumen_default: action === 'clear-default' };
		api.get.mockImplementation((path: string) => Promise.resolve(path.startsWith('/api/v1/auth/mcp-projects') ? accountResponse(path)
			: path.includes('oauth') ? action === 'revoke-oauth' ? [record] : [] : action === 'revoke-oauth' ? [] : [record]));
		api.put.mockReturnValue(mutation.promise);
		api.delete.mockReturnValue(mutation.promise);
		if (action === 'revoke-oauth') render(McpAccessSection);
		else await renderApi();
		await screen.findByRole('group', { name: t('mcp.savedRestrictions') });
		const label = { 'set-default': 'mcp.setLumen', 'clear-default': 'mcp.clearLumen', 'revoke-token': 'mcp.revoke', 'revoke-oauth': 'mcp.revokeAccess' } as const;
		await fireEvent.click(screen.getByRole('button', { name: t(label[action]) }));
		await waitFor(() => expect(action === 'set-default' ? api.put : api.delete).toHaveBeenCalledOnce());
		await selectMethod(action === 'revoke-oauth' ? 'api' : 'oauth');
		await selectMethod(action === 'revoke-oauth' ? 'oauth' : 'api');
		await act(async () => { mutation.reject(new ApiError('Late method mutation error')); });
		expect(screen.queryByText('Late method mutation error')).toBeNull();
		expect(screen.getByRole('group', { name: t('mcp.savedRestrictions') })).toBeTruthy();
		expect(screen.getByRole('button', { name: t(label[action]) }).hasAttribute('disabled')).toBe(false);
	});

	it('keeps saved lists and the explicit API project draft across a method change while clearing action feedback', async () => {
		await renderApi();
		const button = await createButton();
		await fireEvent.click(projectCheckbox('project', 'Project'));
		await fireEvent.click(projectCheckbox('other', 'Other project'));
		await fireEvent.change(screen.getByLabelText(t('mcp.permission')), { target: { value: 'manage' } });
		await fireEvent.input(screen.getByRole('textbox', { name: t('mcp.name') }), { target: { value: 'Draft client' } });
		await fireEvent.change(screen.getByLabelText(t('mcp.expiry')), { target: { value: 'custom' } });
		await fireEvent.submit(button.closest('form')!);
		await screen.findByText(t('mcp.invalidExpiry'));
		const reads = api.get.mock.calls.length;
		await selectMethod('oauth');
		await selectMethod('api');
		expect(api.get).toHaveBeenCalledTimes(reads);
		expect(screen.getByText('Lumen', { selector: '.record-title strong' })).toBeTruthy();
		expect(projectCheckbox('project', 'Project').checked).toBe(false);
		expect(projectCheckbox('other', 'Other project').checked).toBe(true);
		expect((screen.getByRole('textbox', { name: t('mcp.name') }) as HTMLInputElement).value).toBe('Draft client');
		expect((screen.getByLabelText(t('mcp.permission')) as HTMLSelectElement).value).toBe('manage');
		expect(screen.queryByText(t('mcp.invalidExpiry'))).toBeNull();
	});

	it('retains the explicitly selected API method on auth reset but drops creation and verification drafts', async () => {
		await renderApi();
		await createButton();
		await fireEvent.click(projectCheckbox('other', 'Other project'));
		await fireEvent.input(screen.getByRole('textbox', { name: t('mcp.name') }), { target: { value: 'Old owner draft' } });
		await fireEvent.change(screen.getByLabelText(t('mcp.permission')), { target: { value: 'manage' } });
		await fireEvent.change(screen.getByLabelText(t('mcp.expiry')), { target: { value: 'custom' } });
		await fireEvent.input(screen.getByLabelText(t('mcp.customExpiry')), { target: { value: '2028-05-01T10:00' } });
		await fireEvent.input(screen.getByLabelText(t('mcp.tokenLabel')), { target: { value: 'old-owner-private-key' } });
		setAuth({ token: 'new-token' });
		verifyAuth();
		await createButton();
		expect(screen.getByRole('button', { name: t('mcp.methodApiKey') }).getAttribute('aria-pressed')).toBe('true');
		expect((screen.getByRole('textbox', { name: t('mcp.name') }) as HTMLInputElement).value).toBe('Lumen');
		expect((screen.getByLabelText(t('mcp.permission')) as HTMLSelectElement).value).toBe('read');
		expect((screen.getByLabelText(t('mcp.expiry')) as HTMLSelectElement).value).toBe('1m');
		expect(screen.queryByLabelText(t('mcp.customExpiry'))).toBeNull();
		expect((screen.getByLabelText(t('mcp.tokenLabel')) as HTMLInputElement).value).toBe('');
		expect(projectCheckbox('project', 'Project').checked).toBe(true);
		expect(projectCheckbox('other', 'Other project').checked).toBe(false);
	});

	it('labels a saved non-expiring personal token explicitly', async () => {
		const record = { ...activeToken, expires_at: null };
		api.get.mockImplementation((path: string) => Promise.resolve(path.startsWith('/api/v1/auth/mcp-projects') ? accountResponse(path)
			: path.includes('oauth') ? [] : [record]));
		await renderApi();
		await screen.findByText(t('mcp.recordDetails', { prefix: activeToken.visible_prefix, access: t('mcp.read'), lastUsed: '—', expires: t('mcp.expiryNever') }));
	});
});
