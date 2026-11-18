import { grantLumen, setVerifiedLumenActor } from './lumenPermissionFixture';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { auth } from '$lib/stores/auth';

const mocks = vi.hoisted(() => ({
	get: vi.fn(),
	post: vi.fn(),
	patch: vi.fn(),
	put: vi.fn(),
	delete: vi.fn(),
	confirm: vi.fn(),
	toast: { error: vi.fn(), success: vi.fn() }
}));

vi.mock('$lib/api/client', () => ({
	api: { get: mocks.get, post: mocks.post, patch: mocks.patch, put: mocks.put, delete: mocks.delete },
	ApiError: class ApiError extends Error {}
}));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: mocks.confirm }));
vi.mock('$lib/stores/toast', () => ({ toast: mocks.toast }));

import ChatExtensionsManager from '../ChatExtensionsManager.svelte';

describe('ChatExtensionsManager MCP OAuth', () => {
	it.each(['mcp', 'tools', 'skills'] as const)('keeps the %s settings section in the page outline', async (only) => {
		render(ChatExtensionsManager, { base: '/api/v1/chat', only });
		const sectionTitle = only === 'mcp' ? 'MCP 연결' : only === 'tools' ? '커스텀 HTTP 툴' : '스킬';
		expect(screen.getByRole('heading', { level: 2, name: sectionTitle })).toBeTruthy();
		await screen.findByRole('button', { name: only === 'mcp' ? '연결 추가' : only === 'tools' ? '도구 추가' : '+ 스킬 추가' });
	});
	it('separates MCP editing from destruction and tool execution', async () => {
		grantLumen('lumen-mcp_editor');
		render(ChatExtensionsManager, { base: '/api/v1/chat', only: 'mcp' });
		await screen.findByRole('tab', { name: /연결됨 1/ });
		expect(screen.getByRole('button', { name: '연결 추가' }).hasAttribute('disabled')).toBe(false);
		expect(screen.queryByRole('button', { name: '삭제' })).toBeNull();
		grantLumen('lumen-tools_user');
		await waitFor(() => expect(screen.getByRole('button', { name: '연결 추가' }).hasAttribute('disabled')).toBe(true));
	});
	beforeEach(() => {
		vi.clearAllMocks();
		setVerifiedLumenActor({
			token: 'token',
			refreshToken: null,
			accessExpiresAt: null,
			userId: 'user-1',
			username: 'tester',
			projectId: 'project-1',
			projectName: 'Project',
			availableProjects: [],
			roles: [],
			isSystemAdmin: false,
			federated: false, domainId: 'domain-1', domainName: 'Domain', identityDomainId: 'domain-1', identityDomainName: 'Domain', isDomainManager: false
		});
		mocks.get.mockImplementation((path: string) => {
			if (path.includes('/mcp-settings?')) return Promise.resolve({
				entries: [], total: 0, offset: 0, limit: 12, next_offset: null,
				domain_id: 'domain-1', organization_available: true, can_manage_domain: false, custom_connections: []
			});
			if (path.includes('/domains/domain-1/mcp-connections?')) return Promise.resolve({
				connections: [], total: 0, next_offset: null
			});
			if (path.endsWith('/admin/mcp-registry')) return Promise.resolve({ entries: [] });
			if (path.endsWith('/mcp-servers')) {
				return Promise.resolve([
					{
						id: 7,
						name: 'Notion',
						scope: 'global',
						transport: 'http',
						url: 'https://mcp.notion.com/mcp',
						auth_mode: 'oauth',
						is_active: true,
						server_is_active: true,
						config_version: 1,
					}
				]);
			}
			if (path.endsWith('/oauth')) return Promise.resolve({ required: true, connected: false, expires_at: null });
			return Promise.resolve([]);
		});
	});
	it('starts OAuth only after remote consent and keeps a failed connection disabled', async () => {
		grantLumen('lumen-mcp_editor');
		mocks.patch.mockResolvedValue({});
		mocks.post.mockRejectedValue(new Error('Provider is unavailable'));
		render(ChatExtensionsManager, { base: '/api/v1/chat', only: 'mcp' });
		await fireEvent.click(await screen.findByRole('tab', { name: /연결됨 1/ }));
		await fireEvent.click(await screen.findByRole('button', { name: '관리 Notion' }));
		const activate = await screen.findByRole('button', { name: 'Notion 활성화' });
		await fireEvent.click(activate);
		expect(screen.getByRole('dialog').textContent).toContain('https://mcp.notion.com/mcp');
		expect(mocks.post).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: '취소' }));
		expect(mocks.patch).not.toHaveBeenCalled();
		await fireEvent.click(activate);
		await fireEvent.click(screen.getByRole('button', { name: '승인하고 활성화' }));
		await screen.findByRole('alert');
		expect(screen.getByRole('dialog')).toBeDefined();
		await fireEvent.click(screen.getByRole('button', { name: '취소' }));
		expect(screen.getByRole('button', { name: 'Notion 활성화' })).toBeDefined();
	});


	it('keeps approval state for a legacy global server without activation-version metadata', async () => {
		grantLumen('lumen-mcp_editor');
		const original = mocks.get.getMockImplementation()!;
		mocks.get.mockImplementation((path: string) => path.endsWith('/mcp-servers/7/oauth') ? Promise.resolve({ connected: true }) : original(path));
		render(ChatExtensionsManager, { base: '/api/v1/chat', only: 'mcp' });
		await fireEvent.click(await screen.findByRole('tab', { name: /연결됨 1/ }));
		const notion = await screen.findByText('Notion');
		await waitFor(() => expect(notion.closest('.connection-row')?.querySelector('[data-connection-status="active"] svg')).toBeTruthy());
	});


	it('submits the write-only static OAuth client only from the administrator form', async () => {
		auth.update((state) => ({ ...state, isSystemAdmin: true }));
		render(ChatExtensionsManager, { base: '/api/v1/chat/admin', only: 'mcp' });
		await fireEvent.click(screen.getByRole('tab', { name: '관리' }));

		await fireEvent.input(screen.getByPlaceholderText('이름'), { target: { value: 'GitHub' } });
		await fireEvent.input(screen.getByPlaceholderText('URL (예: https://mcp.example/mcp)'), {
			target: { value: 'https://mcp.github.example/mcp' }
		});
		await fireEvent.change(screen.getByLabelText('인증 정책'), { target: { value: 'oauth' } });
		await fireEvent.change(screen.getByLabelText('초기 로딩 정책'), { target: { value: 'preloaded' } });
		await fireEvent.input(screen.getByLabelText('OAuth client ID (DCR 미지원 서버만)'), {
			target: { value: 'github-client' }
		});
		await fireEvent.input(screen.getByLabelText('OAuth client secret (저장 후 표시되지 않음)'), {
			target: { value: 'github-secret' }
		});
		await fireEvent.click(screen.getByRole('button', { name: '+ MCP 서버 추가' }));

		await waitFor(() =>
			expect(mocks.post).toHaveBeenCalledWith(
				'/api/v1/chat/admin/mcp-servers',
				expect.objectContaining({
					name: 'GitHub',
					auth_mode: 'oauth',
					oauth_client_id: 'github-client',
					oauth_client_secret: 'github-secret',
					load_policy: 'preloaded',
				}),
				'token',
				'project-1',
				expect.objectContaining({ signal: expect.any(AbortSignal) })
			)
		);
	});

	it('filters the HTTP tool table and creates a tool only on dialog submit', async () => {
		grantLumen('lumen-assets_editor');
		mocks.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/custom-tools') ? [
			{ id: 1, name: 'Delivery status', description: 'Check tracking', method: 'GET', url: 'https://example.test/shipping', is_active: true },
			{ id: 2, name: 'Send feedback', description: 'Notify team', method: 'POST', url: 'https://example.test/feedback', is_active: false }
		] : []));
		mocks.post.mockResolvedValue({});
		render(ChatExtensionsManager, { base: '/api/v1/chat', only: 'tools' });
		await screen.findByText('Delivery status');
		const search = screen.getByRole('searchbox');
		await fireEvent.input(search, { target: { value: 'feedback' } });
		expect(screen.queryByText('Delivery status')).toBeNull();
		expect(screen.getByText('Send feedback').closest('.connection-row')?.querySelector('[data-connection-status="inactive"] svg')).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: '도구 추가' }));
		const dialog = within(screen.getByRole('dialog', { name: '도구 추가' }));
		expect(mocks.post).not.toHaveBeenCalled();
		await fireEvent.input(dialog.getByLabelText('툴 이름 (영숫자/_)'), { target: { value: 'new_tool' } });
		await fireEvent.input(dialog.getByLabelText('URL'), { target: { value: 'https://example.test/new' } });
		await fireEvent.click(dialog.getByRole('button', { name: '도구 추가' }));
		await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/v1/chat/custom-tools',
			{ name: 'new_tool', description: 'new_tool', method: 'GET', url: 'https://example.test/new' }, 'token', 'project-1'));
		expect(screen.queryByRole('dialog')).toBeNull();
	});

});
