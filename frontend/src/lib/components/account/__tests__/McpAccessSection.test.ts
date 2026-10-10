import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { authReady, clearAuth, projectSwitching, setAuth, setProject } from '$lib/stores/auth';
import { siteConfig } from '$lib/config/site';
import { t } from '$lib/i18n/ns/account';
import { initLocale } from '$lib/i18n/runtime.svelte';

const { api, ApiError, confirmDialog, getBaseUrl } = vi.hoisted(() => ({
	api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
	ApiError: class ApiError extends Error {},
	confirmDialog: vi.fn(),
	getBaseUrl: vi.fn(() => 'https://api.example.test'),
}));

vi.mock('$lib/api/client', () => ({ api, ApiError, getBaseUrl }));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog }));
vi.mock('$app/stores', async () => {
	const { readable } = await import('svelte/store');
	return { page: readable({ data: {}, url: new URL('https://afterglow.example.test/dashboard/account') }) };
});

import McpAccessSection from '../McpAccessSection.svelte';

const clipboardDescriptor = Object.getOwnPropertyDescriptor(navigator, 'clipboard');
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
	source: 'personal_token',
	access_level: 'read',
	status: 'active',
	visible_prefix: 'mcp-afgl-example',
	issued_at: '2026-07-27T00:00:00Z',
	expires_at: '2026-08-27T00:00:00Z',
	last_used_at: null,
	revoked_at: null,
	is_lumen_default: true,
};

function deferred<T>() {
	let resolve!: (value: T) => void;
	const promise = new Promise<T>((yes) => { resolve = yes; });
	return { promise, resolve };
}

describe('McpAccessSection', () => {
	beforeEach(() => {
		vi.clearAllMocks();
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
			accessExpiresAt: null,
			roles: [],
		});
		authReady.set(true);
		projectSwitching.set(false);
		siteConfig.update((config) => ({ ...config, mcp_url: '', services: { ...config.services, mcp: true } }));
		api.get.mockImplementation((path: string) => Promise.resolve(path.includes('oauth') ? [] : [activeToken]));
		api.post.mockResolvedValue({ ...activeToken, id: 'token-2', grant_id: 'grant-2', token: 'mcp-afgl-secret-value' });
	});

	afterEach(() => {
		cleanup();
		initLocale('ko');
		if (clipboardDescriptor) Object.defineProperty(navigator, 'clipboard', clipboardDescriptor);
		else Reflect.deleteProperty(navigator, 'clipboard');
		projectSwitching.set(false);
		clearAuth();
		siteConfig.update((config) => ({ ...config, services: { ...config.services, mcp: false } }));
	});

	it.each(['ko', 'en', 'ja', 'zh-CN'] as const)('opens the MCP guide in the account language %s', async (locale) => {
		initLocale(locale);
		render(McpAccessSection);
		const link = await screen.findByRole('link', { name: t('mcp.docs') });
		const url = new URL(link.getAttribute('href')!, 'https://afterglow.example.test');
		expect(url.pathname).toBe('/docs/mcp');
		expect(url.searchParams.get('lang')).toBe(locale === 'ko' ? null : locale);
	});

	it('shows the current Lumen default without exposing a token secret', async () => {
		render(McpAccessSection);

		await waitFor(() => expect(screen.getByText('Lumen 기본 토큰')).toBeTruthy());
		expect(screen.queryByText('mcp-afgl-secret-value')).toBeNull();
		expect(screen.getByRole('button', { name: 'Lumen 해제' })).toBeTruthy();
	});

	it('displays a newly issued token once after creation', async () => {
		render(McpAccessSection);
		await waitFor(() => expect(screen.getByLabelText(/이름/)).toBeTruthy());

		await fireEvent.input(screen.getByLabelText(/이름/), { target: { value: 'Desktop client' } });
		await fireEvent.click(screen.getByRole('button', { name: '토큰 만들기' }));

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
		render(McpAccessSection);
		await fireEvent.click(await screen.findByRole('button', { name: t('mcp.create') }));
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
		render(McpAccessSection);
		await fireEvent.click(await screen.findByRole('button', { name: t('mcp.create') }));
		const dialog = await screen.findByRole('dialog', { name: t('mcp.newToken') });
		await fireEvent.click(within(dialog).getByRole('button', { name: t('mcp.done') }));
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.copyOAuthConfig') }));
		await waitFor(() => expect(writeText).toHaveBeenCalledOnce());
		expect(JSON.parse(writeText.mock.calls[0][0])).toEqual({
			mcpServers: { 'my-stream-server': { type: 'http', url: 'https://cloud.dmslab.re.kr/mcp' } },
		});
		expect(screen.getByText('https://cloud.dmslab.re.kr/mcp/oauth/authorize')).toBeTruthy();
	});
	it('hides project-owned tokens and issued secrets while the new scope loads', async () => {
		const tokens = deferred<typeof activeToken[]>();
		const grants = deferred<typeof activeToken[]>();
		api.get.mockImplementation((path: string, _token: string, project: string) => project === 'other'
			? (path.includes('oauth') ? grants.promise : tokens.promise)
			: Promise.resolve(path.includes('oauth') ? [] : [activeToken]));
		render(McpAccessSection);
		await screen.findByText('Lumen');
		await fireEvent.click(screen.getByRole('button', { name: '토큰 만들기' }));
		await screen.findByText('mcp-afgl-secret-value');
		setProject('other', 'Other project');
		await waitFor(() => {
			expect(screen.queryByText('Lumen')).toBeNull();
			expect(screen.queryByText('mcp-afgl-secret-value')).toBeNull();
			expect(screen.queryByRole('button', { name: 'Lumen 해제' })).toBeNull();
		});
		tokens.resolve([{ ...activeToken, id: 'token-b', name: 'Beta token' }]);
		grants.resolve([]);
		await screen.findByText('Beta token');
		expect(screen.queryByText('mcp-afgl-secret-value')).toBeNull();
	});

	it('rejects an old revoke confirmation and late B response after an A→B→A switch', async () => {
		const confirm = deferred<boolean>();
		const bTokens = deferred<typeof activeToken[]>();
		let aReads = 0;
		confirmDialog.mockReturnValue(confirm.promise);
		api.get.mockImplementation((path: string, _token: string, project: string) => {
			if (path.includes('oauth')) return Promise.resolve([]);
			if (project === 'other') return bTokens.promise;
			aReads += 1;
			return Promise.resolve([{ ...activeToken, name: aReads === 1 ? 'Original A token' : 'Fresh A token' }]);
		});
		render(McpAccessSection);
		await screen.findByText('Original A token');
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.revoke') }));
		setProject('other', 'Other project');
		await waitFor(() => expect(screen.queryByText('Original A token')).toBeNull());
		setProject('project', 'Project');
		await screen.findByText('Fresh A token');
		confirm.resolve(true);
		bTokens.resolve([{ ...activeToken, name: 'Late B token' }]);
		await waitFor(() => expect(screen.queryByText('Late B token')).toBeNull());
		expect(api.delete).not.toHaveBeenCalled();
		expect(screen.getByText('Fresh A token')).toBeTruthy();
	});

	it('clears a saved credential after a failed verification without retaining plaintext or leaking raw server detail', async () => {
		api.post.mockRejectedValue(new ApiError('MCP authentication failed'));
		render(McpAccessSection);
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
		render(McpAccessSection);
		const input = await screen.findByLabelText(t('mcp.tokenLabel')) as HTMLInputElement;
		await fireEvent.input(input, { target: { value: '  mcp-afgl-saved-private-key  ' } });
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.verify') }));
		await screen.findByText(t('mcp.verified'));
		expect(api.post).toHaveBeenCalledWith('/api/v1/auth/mcp-tokens/verify', { token: 'mcp-afgl-saved-private-key' }, 'token', 'project');
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
		render(McpAccessSection);
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
		render(McpAccessSection);
		await fireEvent.click(await screen.findByRole('button', { name: t('mcp.create') }));
		await screen.findByText('mcp-afgl-secret-value');
		await fireEvent.click(screen.getAllByRole('button', { name: t('mcp.verify') }).find((button) => !button.hasAttribute('disabled'))!);
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.done') }));
		await act(async () => {
			verification.resolve({ endpoint: 'https://mcp.example.test', protocol_version: '2025-11-25', server_name: 'Private client', server_version: '1.0', tool_count: 5 });
		});
		expect(screen.queryByText(t('mcp.verified'))).toBeNull();
		expect(document.body.textContent).not.toContain('mcp-afgl-secret-value');
	});

	it('discards verification state and credentials when the owning project changes', async () => {
		const verification = deferred<{ endpoint: string; protocol_version: string; server_name: string; server_version: string; tool_count: number }>();
		api.post.mockReturnValue(verification.promise);
		render(McpAccessSection);
		const input = await screen.findByLabelText(t('mcp.tokenLabel')) as HTMLInputElement;
		await fireEvent.input(input, { target: { value: 'mcp-afgl-old-project-key' } });
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.verify') }));
		setProject('other', 'Other project');
		await waitFor(() => expect(input.value).toBe(''));
		await act(async () => {
			verification.resolve({ endpoint: 'https://mcp.example.test', protocol_version: '2025-11-25', server_name: 'Old project server', server_version: '1.0', tool_count: 5 });
		});
		expect(screen.queryByText(t('mcp.verified'))).toBeNull();
		expect(screen.queryByText(t('mcp.verifying'))).toBeNull();
	});

	it.each(['user', 'logout', 'unverified', 'switching', 'disabled'] as const)('drops one-time issuance and saved credentials on %s transition', async (transition) => {
		const issuance = deferred<typeof activeToken & { token: string }>();
		api.post.mockReturnValue(issuance.promise);
		render(McpAccessSection);
		await screen.findByText('Lumen');
		await fireEvent.input(screen.getByLabelText(t('mcp.tokenLabel')), { target: { value: 'private-saved-key' } });
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.create') }));
		if (transition === 'user') {
			api.get.mockImplementation((path: string) => Promise.resolve(path.includes('oauth') ? [] : [{ ...activeToken, name: 'New owner token' }]));
			setAuth({ token: 'token', userId: 'other-user' });
			await screen.findByText('New owner token');
		} else if (transition === 'logout') clearAuth();
		else if (transition === 'unverified') authReady.set(false);
		else if (transition === 'switching') projectSwitching.set(true);
		else siteConfig.update((config) => ({ ...config, services: { ...config.services, mcp: false } }));
		await waitFor(() => expect(screen.queryByText('Lumen')).toBeNull());
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
		const view = render(McpAccessSection);
		await fireEvent.click(await screen.findByRole('button', { name: t('mcp.create') }));
		const dialog = await screen.findByRole('dialog', { name: t('mcp.newToken') });
		await fireEvent.click(within(dialog).getByRole('button', { name: t('mcp.verify') }));
		view.unmount();
		render(McpAccessSection);
		await act(async () => { verification.resolve(connectionResult); });
		expect(screen.queryByText(t('mcp.verified'))).toBeNull();
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(document.body.textContent).not.toContain('mcp-afgl-secret-value');
	});
});
