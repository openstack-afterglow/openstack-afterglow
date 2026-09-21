import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { pendingClaudeGatewayUserCode, postAuthDestination } from '$lib/utils/mcpConsent';

const { api, auth, goto, page } = vi.hoisted(() => {
	let value = { url: new URL('http://localhost/oauth/claude/authorize'), data: {} };
	const subscribers = new Set<(next: typeof value) => void>();
	return {
		api: { post: vi.fn() },
		auth: {
			subscribe(run: (next: { token: string; projectId: string }) => void) {
				run({ token: 'mock-token', projectId: 'mock-project-1' });
				return () => {};
			},
		},
		goto: vi.fn(),
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
vi.mock('$lib/api/client', () => ({
	api,
	ApiError: class ApiError extends Error {},
}));
vi.mock('$lib/stores/auth', () => ({ auth }));

import Page from '../+page.svelte';

describe('Claude gateway authorization route', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		sessionStorage.clear();
		page.set({
			url: new URL('http://localhost/oauth/claude/authorize?user_code=ABCD-2345'),
			data: {},
		});
		api.post.mockResolvedValue({ status: 'approved' });
	});

	afterEach(() => {
		sessionStorage.clear();
	});

	it('stores and scrubs a complete URL code before approving through the authenticated BFF', async () => {
		const replaceState = vi.spyOn(history, 'replaceState');
		render(Page);

		const input = await screen.findByRole('textbox', { name: 'Claude Code 연결 코드' });
		expect((input as HTMLInputElement).value).toBe('ABCD-2345');
		expect(pendingClaudeGatewayUserCode()).toBe('ABCD-2345');
		expect(replaceState).toHaveBeenCalledWith(null, '', '/oauth/claude/authorize');

		await fireEvent.click(screen.getByRole('button', { name: '연결 승인' }));
		await screen.findByText('Claude Code 연결을 승인했습니다.');
		expect(api.post).toHaveBeenCalledWith(
			'/api/v1/chat/claude-gateway/authorize',
			{ user_code: 'ABCD-2345', action: 'approve' },
			'mock-token',
			'mock-project-1',
		);
		expect(postAuthDestination('/dashboard')).toBe('/dashboard');
	});

	it('keeps the shell as the post-login destination for manual code entry', async () => {
		page.set({ url: new URL('http://localhost/oauth/claude/authorize'), data: {} });
		render(Page);

		await waitFor(() => expect(postAuthDestination('/dashboard')).toBe('/oauth/claude/authorize'));
		const input = screen.getByRole('textbox', { name: 'Claude Code 연결 코드' });
		await fireEvent.input(input, { target: { value: 'wxyz-6789' } });
		await fireEvent.click(screen.getByRole('button', { name: '연결 승인' }));

		await waitFor(() => expect(api.post).toHaveBeenCalledWith(
			'/api/v1/chat/claude-gateway/authorize',
			{ user_code: 'WXYZ-6789', action: 'approve' },
			'mock-token',
			'mock-project-1',
		));
	});
});
