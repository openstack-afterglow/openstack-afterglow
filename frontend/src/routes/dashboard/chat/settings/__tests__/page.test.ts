import { render, screen } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { auth } from '$lib/stores/auth';

const mocks = vi.hoisted(() => ({ get: vi.fn(), goto: vi.fn() }));
vi.mock('$lib/api/client', () => ({
	api: { get: mocks.get, post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
	ApiError: class ApiError extends Error {}
}));
vi.mock('$app/navigation', () => ({ goto: mocks.goto }));

import Page from '../+page.svelte';
import { load } from '../+page';

describe('/dashboard/chat/settings route', () => {
	beforeEach(() => {
		mocks.get.mockReset();
		mocks.get.mockResolvedValue({});
		auth.set({
			token: 'browser-token',
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
	});
	it('keeps a valid section while ignoring OAuth metadata', () => {
		const data = load({
			url: new URL(
				'http://localhost:3080/dashboard/chat/settings?section=mcp&mcp_oauth=connected'
			)
		} as Parameters<typeof load>[0]);

		expect(data).toEqual({ section: 'mcp' });
	});

	it('falls back to usage for an unknown section', () => {
		const data = load({
			url: new URL('http://localhost:3080/dashboard/chat/settings?section=bogus')
		} as Parameters<typeof load>[0]);

		expect(data).toEqual({ section: 'usage' });
	});
	it('offers a direct return to the chat route', () => {
		render(Page, { data: { section: 'usage' } });

		const returnToChat = screen.getByRole('link', { name: '채팅으로 돌아가기' });
		expect(returnToChat.getAttribute('href')).toBe('/dashboard/chat');
	});
});

