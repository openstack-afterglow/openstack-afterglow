import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { auth } from '$lib/stores/auth';
import ChatPanel from '../ChatPanel.svelte';

const mocks = vi.hoisted(() => ({
	get: vi.fn(),
	post: vi.fn(),
	patch: vi.fn(),
	put: vi.fn(),
	delete: vi.fn(),
	confirmDialog: vi.fn(),
	toastSuccess: vi.fn(),
	toastError: vi.fn(),
	createRun: vi.fn(),
	followRun: vi.fn(),
	cancelRun: vi.fn(),
	previewContext: vi.fn(),
	ChatHttpError: class ChatHttpError extends Error {
		status: number;
		constructor(message: string, status: number) {
			super(message);
			this.status = status;
		}
	}
}));

vi.mock('$lib/api/client', () => ({
	api: {
		get: mocks.get,
		post: mocks.post,
		patch: mocks.patch,
		put: mocks.put,
		delete: mocks.delete
	},
	ApiError: class ApiError extends Error {}
}));

vi.mock('$lib/stores/confirm.svelte', () => ({
	confirmDialog: mocks.confirmDialog
}));

vi.mock('$lib/stores/toast', () => ({
	toast: {
		success: mocks.toastSuccess,
		error: mocks.toastError
	}
}));

vi.mock('$lib/api/chatStream', () => ({
	createChatRun: mocks.createRun,
	followChatRun: mocks.followRun,
	cancelChatRun: mocks.cancelRun,
	previewChatContext: mocks.previewContext,
	parseChatRunDescriptor: (value: unknown) => value,
	ChatHttpError: mocks.ChatHttpError
}));
beforeEach(() => {
	vi.clearAllMocks();
	auth.set({
		token: 'test-token',
		refreshToken: null,
		accessExpiresAt: null,
		userId: 'user-1',
		username: 'tester',
		projectId: 'proj-1',
		projectName: 'Test Project',
		availableProjects: [],
		roles: ['member'],
		isSystemAdmin: false,
		federated: false
	});

	vi.stubGlobal('matchMedia', (query: string) => ({
		matches: query.includes('min-width: 1024px'),
		media: query,
		onchange: null,
		addEventListener: () => {},
		removeEventListener: () => {},
		addListener: () => {},
		removeListener: () => {},
		dispatchEvent: () => false
	}));

	vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
		callback(performance.now());
		return 1;
	});
	vi.stubGlobal('cancelAnimationFrame', () => {});
	mocks.get.mockImplementation(async (path: string) => {
		if (path === '/api/v1/chat/models') {
			return [{ model_name: 'test-model', display_name: 'Test Model', capabilities: {} }];
		}
		if (path === '/api/v1/chat/conversations') {
			return [
				{ id: 'conv-with-title', title: '기존 중요한 대화', model_name: 'test-model', workspace_id: null },
				{ id: 'conv-untitled', title: null, model_name: 'test-model', workspace_id: null }
			];
		}
		if (path === '/api/v1/chat/workspaces') return [];
		if (path === '/api/v1/chat/agents') return [];
		if (path === '/api/v1/chat/tools') return [];
		if (path === '/api/v1/chat/mcp-servers') return [];
		if (path === '/api/v1/chat/runs?active=true') return [];
		if (path.includes('/messages')) {
			return { messages: [], tree_nodes: [], active_leaf_id: null, has_more: false, next_before_id: null };
		}
		return [];
	});
	mocks.delete.mockResolvedValue({});
});

describe('ChatPanel conversation deletion confirmation', () => {
	it('prompts confirmation with title and cancels deletion when user rejects', async () => {
		mocks.confirmDialog.mockResolvedValueOnce(false);
		render(ChatPanel);

		await waitFor(() => {
			expect(screen.getByText('기존 중요한 대화')).toBeDefined();
		});

		const deleteButtons = screen.getAllByRole('button', { name: '대화 삭제' });
		await fireEvent.click(deleteButtons[0]);

		expect(mocks.confirmDialog).toHaveBeenCalledTimes(1);
		expect(mocks.confirmDialog).toHaveBeenCalledWith("'기존 중요한 대화' 대화를 삭제하시겠습니까?");
		expect(mocks.delete).not.toHaveBeenCalled();
		expect(mocks.toastSuccess).not.toHaveBeenCalled();
		expect(screen.getByText('기존 중요한 대화')).toBeDefined();
	});

	it('prompts confirmation and deletes conversation when user accepts', async () => {
		mocks.confirmDialog.mockResolvedValueOnce(true);
		render(ChatPanel);

		await waitFor(() => {
			expect(screen.getByText('기존 중요한 대화')).toBeDefined();
		});

		const deleteButtons = screen.getAllByRole('button', { name: '대화 삭제' });
		await fireEvent.click(deleteButtons[0]);

		expect(mocks.confirmDialog).toHaveBeenCalledTimes(1);
		expect(mocks.confirmDialog).toHaveBeenCalledWith("'기존 중요한 대화' 대화를 삭제하시겠습니까?");

		await waitFor(() => {
			expect(mocks.delete).toHaveBeenCalledWith('/api/v1/chat/conversations/conv-with-title', 'test-token', 'proj-1');
		});
		expect(mocks.toastSuccess).toHaveBeenCalledWith('대화를 삭제했습니다');
		await waitFor(() => {
			expect(screen.queryByText('기존 중요한 대화')).toBeNull();
		});
	});

	it('prompts confirmation with generic message when conversation has no title', async () => {
		mocks.confirmDialog.mockResolvedValueOnce(true);
		render(ChatPanel);

		await waitFor(() => {
			expect(screen.getByText('새 대화')).toBeDefined();
		});

		const deleteButtons = screen.getAllByRole('button', { name: '대화 삭제' });
		// Second conversation is untitled
		await fireEvent.click(deleteButtons[1]);

		expect(mocks.confirmDialog).toHaveBeenCalledTimes(1);
		expect(mocks.confirmDialog).toHaveBeenCalledWith('대화를 삭제하시겠습니까?');

		await waitFor(() => {
			expect(mocks.delete).toHaveBeenCalledWith('/api/v1/chat/conversations/conv-untitled', 'test-token', 'proj-1');
		});
		expect(mocks.toastSuccess).toHaveBeenCalledWith('대화를 삭제했습니다');
	});
});
