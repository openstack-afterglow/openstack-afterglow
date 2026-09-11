import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';

import ChatSidebar from '../ChatSidebar.svelte';

type SidebarConversation = {
	id: string;
	title: string | null;
	model_name: string | null;
	workspace_id: number | null;
	updated_at: string | null;
	title_status?: 'idle' | 'pending' | 'ready' | 'failed' | 'unavailable';
};

const conversations: SidebarConversation[] = [
	{ id: 'conv-1', title: 'OpenStack 네트워크 점검', model_name: 'gemini', workspace_id: null, updated_at: null },
	{ id: 'conv-2', title: 'Kubernetes 클러스터 상태', model_name: 'claude', workspace_id: null, updated_at: null }
];

function renderSidebar(
	runningConversationIds = new Set<string>(),
	activeConvId: string | null = null,
	workspaces: { id: number; name: string; description: string | null; instructions: string | null }[] = [],
	sidebarConversations: SidebarConversation[] = conversations,
	busy = false
) {
	const onSelect = vi.fn();
	const onNewInWorkspace = vi.fn();
	const onDelete = vi.fn();
	const view = render(ChatSidebar, {
		conversations: sidebarConversations,
		workspaces,
		activeConvId,
		busy,
		onSelect,
		onNew: vi.fn(),
		onDelete,
		onAssign: vi.fn(),
		onAgents: vi.fn(),
		onWorkspaces: vi.fn(),
		onToggle: vi.fn(),
		onOpenWorkspace: vi.fn(),
		runningConversationIds,
		onSearch: vi.fn().mockImplementation(async (query: string) =>
			sidebarConversations.filter((conversation) => (conversation.title ?? '').toLowerCase().includes(query.toLowerCase()))
		),
		onNewInWorkspace,
		onDeleteWorkspace: vi.fn(),
		onSettings: vi.fn()
	});
	return { ...view, onSelect, onNewInWorkspace, onDelete };
}

describe('ChatSidebar search palette', () => {
	it('opens from the search trigger, filters conversations, and selects a result', async () => {
		const { onSelect } = renderSidebar();

		await fireEvent.click(screen.getByRole('button', { name: '대화 검색' }));
		const input = screen.getByPlaceholderText('대화 검색');
		await fireEvent.input(input, { target: { value: 'Kubernetes' } });

		const results = within(screen.getByRole('listbox', { name: '검색 결과' }));
		expect(results.getByText('Kubernetes 클러스터 상태')).toBeTruthy();
		expect(results.queryByText('OpenStack 네트워크 점검')).toBeNull();

		await fireEvent.click(results.getByRole('option', { name: /Kubernetes 클러스터 상태/ }));
		expect(onSelect).toHaveBeenCalledWith(conversations[1]);
		expect(screen.queryByPlaceholderText('대화 검색')).toBeNull();
	});

	it('shows a spinner and unseen indicator for inactive running conversations', () => {
		renderSidebar(new Set(['conv-1']), 'conv-2');

		expect(document.querySelector('.run-spinner')).toBeTruthy();
		expect(screen.getByLabelText('확인하지 않은 실행 중 대화')).toBeTruthy();
	});

	it('opens with Ctrl+I and closes with Escape', async () => {
		renderSidebar();

		await fireEvent.keyDown(window, { key: 'i', ctrlKey: true });
		const input = screen.getByPlaceholderText('대화 검색');
		await fireEvent.keyDown(input, { key: 'Escape' });

		expect(screen.queryByPlaceholderText('대화 검색')).toBeNull();
	});

	it('closes project options when clicking elsewhere', async () => {
		renderSidebar(new Set(), null, [{ id: 1, name: 'dms cloud', description: null, instructions: null }]);

		await fireEvent.click(screen.getByRole('button', { name: '프로젝트 옵션' }));
		expect(screen.getByRole('menu')).toBeTruthy();

		await fireEvent.pointerDown(document.body);
		expect(screen.queryByRole('menu')).toBeNull();
	});

	it('keeps the chat count visible and exposes workspace actions on interaction', async () => {
		const projectConversations = conversations.map((conversation) => ({ ...conversation, workspace_id: 1 }));
		const { onNewInWorkspace } = renderSidebar(
			new Set(),
			null,
			[{ id: 1, name: 'dms cloud', description: null, instructions: null }],
			projectConversations
		);

		expect(screen.getByText('2')).toBeTruthy();
		await fireEvent.mouseEnter(screen.getByText('dms cloud').closest('.group-row')!);
		await fireEvent.click(screen.getByRole('button', { name: '이 프로젝트에서 새 채팅' }));
		expect(onNewInWorkspace).toHaveBeenCalledWith(1);
	});

	it('reveals only the newly created workspace group and retains the five-row history limit', async () => {
		const existing = Array.from({ length: 6 }, (_, index) => ({
			...conversations[0], id: `old-${index}`, title: `과거 대화 ${index}`, workspace_id: 1
		}));
		const view = renderSidebar(new Set(), null, [
			{ id: 1, name: '새 대화 프로젝트', description: null, instructions: null },
			{ id: 2, name: '접힌 다른 프로젝트', description: null, instructions: null }
		], existing);
		const firstGroup = screen.getByRole('button', { name: /새 대화 프로젝트/ });
		const secondGroup = screen.getByRole('button', { name: /접힌 다른 프로젝트/ });
		await fireEvent.click(firstGroup);
		await fireEvent.click(secondGroup);
		expect(firstGroup.getAttribute('aria-expanded')).toBe('false');
		const created = {
			...existing[0], id: 'created', title: null, title_status: 'pending' as const
		};
		await view.rerender({
			conversations: [created, ...existing],
			newlyCreatedConversationId: 'created',
			activeConvId: 'created'
		});
		expect(firstGroup.getAttribute('aria-expanded')).toBe('true');
		expect(secondGroup.getAttribute('aria-expanded')).toBe('false');
		await fireEvent.click(screen.getByRole('button', { name: '제목 요약 중' }));
		expect(view.onSelect).toHaveBeenCalledWith(created);
		expect(screen.queryByText('과거 대화 4')).toBeNull();
	});

	it('invokes onDelete with conversation when delete button is clicked', async () => {
		const { onDelete } = renderSidebar();
		const deleteButtons = screen.getAllByRole('button', { name: '대화 삭제' });
		expect(deleteButtons.length).toBe(2);
		await fireEvent.click(deleteButtons[0]);
		expect(onDelete).toHaveBeenCalledWith(conversations[0]);
	});

	it('disables delete buttons when busy/streaming', () => {
		renderSidebar(new Set(), null, [], conversations, true);
		const deleteButtons = screen.getAllByRole('button', { name: '대화 삭제' });
		expect(deleteButtons.length).toBe(2);
		expect(deleteButtons[0].hasAttribute('disabled')).toBe(true);
		expect(deleteButtons[1].hasAttribute('disabled')).toBe(true);
	});
});
