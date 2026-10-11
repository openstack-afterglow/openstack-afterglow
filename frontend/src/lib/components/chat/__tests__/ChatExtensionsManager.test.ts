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
		expect(screen.queryByRole('button', { name: '삭제' })).toBeNull();
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

});
