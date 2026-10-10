import { grantLumen } from './lumenPermissionFixture';
import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
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
	it('separates MCP editing from destruction and tool execution', async () => {
		grantLumen('lumen-mcp_editor');
		render(ChatExtensionsManager, { base: '/api/v1/chat', only: 'mcp' });
		await screen.findByText('Notion');
		expect(screen.getByRole('button', { name: '+ MCP 서버 추가' }).hasAttribute('disabled')).toBe(false);
		expect(screen.getByRole('button', { name: '삭제' }).hasAttribute('disabled')).toBe(true);
		grantLumen('lumen-tools_user');
		await waitFor(() => expect(screen.getByRole('button', { name: '+ MCP 서버 추가' }).hasAttribute('disabled')).toBe(true));
	});
	beforeEach(() => {
		vi.clearAllMocks();
		auth.set({
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
			federated: false
		});
		mocks.get.mockImplementation((path: string) => {
			if (path.endsWith('/mcp-servers')) {
				return Promise.resolve([
					{
						id: 7,
						name: 'Notion',
						scope: 'global',
						transport: 'http',
						url: 'https://mcp.notion.com/mcp',
						auth_mode: 'oauth',
						is_active: true
					}
				]);
			}
			if (path.endsWith('/oauth')) return Promise.resolve({ required: true, connected: false, expires_at: null });
			return Promise.resolve([]);
		});
	});

	it('shows a per-user Notion connection action instead of requesting a static token', async () => {
		render(ChatExtensionsManager, { base: '/api/v1/chat', only: 'mcp' });

		await waitFor(() => expect(screen.getByRole('button', { name: 'Notion OAuth 연결' })).toBeTruthy());
		expect(screen.queryByText('Notion Integration Token')).toBeNull();
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/chat/mcp-servers/7/oauth', 'token', 'project-1');
	});

	it('does not request user-scoped OAuth status from the admin route', async () => {
		render(ChatExtensionsManager, { base: '/api/v1/chat/admin', only: 'mcp' });

		await waitFor(() => expect(screen.getByText('Notion')).toBeTruthy());
		expect(mocks.get).not.toHaveBeenCalledWith('/api/v1/chat/admin/mcp-servers/7/oauth', 'token', 'project-1');
	});

	it('submits the write-only static OAuth client only from the administrator form', async () => {
		auth.update((state) => ({ ...state, isSystemAdmin: true }));
		render(ChatExtensionsManager, { base: '/api/v1/chat/admin', only: 'mcp' });

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
				'project-1'
			)
		);
	});

	it('keeps loading policy controls out of the user-scoped route', async () => {
		render(ChatExtensionsManager, { base: '/api/v1/chat', only: 'mcp' });

		await waitFor(() => expect(screen.getByText('Notion')).toBeTruthy());
		expect(screen.queryByLabelText('초기 로딩 정책')).toBeNull();
		expect(screen.queryByLabelText('Notion 로딩 정책')).toBeNull();
	});
});
