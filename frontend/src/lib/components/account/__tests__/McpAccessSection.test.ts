import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { clearAuth, setAuth, setProject } from '$lib/stores/auth';
import { siteConfig } from '$lib/config/site';
import { t } from '$lib/i18n/ns/account';

const { api, ApiError, confirmDialog, getBaseUrl } = vi.hoisted(() => ({
	api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
	ApiError: class ApiError extends Error {},
	confirmDialog: vi.fn(),
	getBaseUrl: vi.fn(() => 'https://api.example.test'),
}));

vi.mock('$lib/api/client', () => ({ api, ApiError, getBaseUrl }));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog }));

import McpAccessSection from '../McpAccessSection.svelte';

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
		siteConfig.update((config) => ({ ...config, services: { ...config.services, mcp: true } }));
		api.get.mockImplementation((path: string) => Promise.resolve(path.includes('oauth') ? [] : [activeToken]));
		api.post.mockResolvedValue({ ...activeToken, id: 'token-2', grant_id: 'grant-2', token: 'mcp-afgl-secret-value' });
	});

	afterEach(() => {
		cleanup();
		siteConfig.update((config) => ({ ...config, services: { ...config.services, mcp: false } }));
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

	it('clears a saved credential after a failed verification without retaining plaintext', async () => {
		api.post.mockRejectedValue(new ApiError('MCP authentication failed'));
		render(McpAccessSection);
		const input = await screen.findByLabelText(t('mcp.tokenLabel')) as HTMLInputElement;
		await fireEvent.input(input, { target: { value: 'mcp-afgl-saved-private-key' } });
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.verify') }));
		await screen.findByText('MCP authentication failed');
		expect(input.value).toBe('');
		expect(document.body.textContent).not.toContain('mcp-afgl-saved-private-key');
	});

	it.each([
		[400, 'invalid_token', 'invalidToken'],
		[503, 'not_configured', 'notConfigured'],
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
});
