import './lumenPermissionFixture';
import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';

import ChatProjectsView from '../ChatProjectsView.svelte';

function renderCreateDialog() {
	const onCreate = vi.fn().mockResolvedValue(true);
	render(ChatProjectsView, {
		conversations: [],
		workspaces: [],
		initialMode: 'create',
		onCreate,
		onUpdate: vi.fn().mockResolvedValue(true),
		onDelete: vi.fn().mockResolvedValue(true),
		onAssign: vi.fn(),
		onOpenConversation: vi.fn(),
		onNewInProject: vi.fn()
	});
	return { onCreate };
}

describe('ChatProjectsView project creation', () => {
	it('opens a name-only dialog and creates the project without leaving the project list', async () => {
		const { onCreate } = renderCreateDialog();

		expect(screen.getByLabelText('프로젝트 만들기')).toBeTruthy();
		expect(screen.queryByText('공통 지침')).toBeNull();

		await fireEvent.input(screen.getByPlaceholderText('예: OpenStack 운영'), { target: { value: '운영' } });
		await fireEvent.click(screen.getByRole('button', { name: '프로젝트 만들기' }));

		await waitFor(() => expect(onCreate).toHaveBeenCalledWith({ name: '운영' }));
		expect(screen.queryByLabelText('프로젝트 만들기')).toBeNull();
		expect(screen.getByRole('heading', { name: '프로젝트' })).toBeTruthy();
	});

	it('returns from project detail to the project list', async () => {
		render(ChatProjectsView, {
			conversations: [],
			workspaces: [{ id: 7, name: '운영', description: null, instructions: null }],
			onCreate: vi.fn().mockResolvedValue(true),
			onUpdate: vi.fn().mockResolvedValue(true),
			onDelete: vi.fn().mockResolvedValue(true),
			onAssign: vi.fn(),
			onOpenConversation: vi.fn(),
			onNewInProject: vi.fn()
		});

		await fireEvent.click(screen.getByRole('button', { name: /운영/ }));
		expect(screen.getByRole('heading', { name: '운영' })).toBeTruthy();

		await fireEvent.click(screen.getByRole('button', { name: '목록으로' }));
		expect(screen.getByRole('heading', { name: '프로젝트' })).toBeTruthy();
	});

	it('delegates project detail navigation to the route owner when provided', async () => {
		const onNavigate = vi.fn();
		render(ChatProjectsView, {
			conversations: [],
			workspaces: [{ id: 7, name: '운영', description: null, instructions: null }],
			onCreate: vi.fn().mockResolvedValue(true),
			onUpdate: vi.fn().mockResolvedValue(true),
			onDelete: vi.fn().mockResolvedValue(true),
			onAssign: vi.fn(),
			onOpenConversation: vi.fn(),
			onNewInProject: vi.fn(),
			onNavigate
		});

		await fireEvent.click(screen.getByRole('button', { name: /운영/ }));

		expect(onNavigate).toHaveBeenCalledWith(7);
	});

	it('shows a recoverable state for an unknown routed project', () => {
		render(ChatProjectsView, {
			conversations: [],
			workspaces: [],
			initialWorkspaceId: 99,
			onCreate: vi.fn().mockResolvedValue(true),
			onUpdate: vi.fn().mockResolvedValue(true),
			onDelete: vi.fn().mockResolvedValue(true),
			onAssign: vi.fn(),
			onOpenConversation: vi.fn(),
			onNewInProject: vi.fn(),
			onNavigate: vi.fn()
		});

		expect(screen.getByText('프로젝트를 찾을 수 없습니다')).toBeTruthy();
	});

	it('tracks a changed routed project id without remounting', async () => {
		const common = {
			conversations: [],
			workspaces: [
				{ id: 7, name: '운영', description: null, instructions: null },
				{ id: 8, name: '개발', description: null, instructions: null }
			],
			onCreate: vi.fn().mockResolvedValue(true),
			onUpdate: vi.fn().mockResolvedValue(true),
			onDelete: vi.fn().mockResolvedValue(true),
			onAssign: vi.fn(),
			onOpenConversation: vi.fn(),
			onNewInProject: vi.fn(),
			onNavigate: vi.fn()
		};
		const { rerender } = render(ChatProjectsView, { ...common, initialWorkspaceId: 7 });
		expect(screen.getByRole('heading', { name: '운영' })).toBeTruthy();

		await rerender({ ...common, initialWorkspaceId: 8 });

		await waitFor(() => expect(screen.getByRole('heading', { name: '개발' })).toBeTruthy());
	});

	it('shows only chats assigned to the routed project in its detail list', () => {
		const { container } = render(ChatProjectsView, {
			conversations: [
				{ id: 'a', title: '운영 대화', model_name: null, workspace_id: 7, updated_at: null },
				{ id: 'b', title: '개발 대화', model_name: null, workspace_id: 8, updated_at: null }
			],
			workspaces: [
				{ id: 7, name: '운영', description: null, instructions: null },
				{ id: 8, name: '개발', description: null, instructions: null }
			],
			initialWorkspaceId: 7,
			onCreate: vi.fn().mockResolvedValue(true),
			onUpdate: vi.fn().mockResolvedValue(true),
			onDelete: vi.fn().mockResolvedValue(true),
			onAssign: vi.fn(),
			onOpenConversation: vi.fn(),
			onNewInProject: vi.fn(),
			onNavigate: vi.fn()
		});

		expect(container.querySelector('.conv-list')?.textContent).toContain('운영 대화');
		expect(container.querySelector('.conv-list')?.textContent).not.toContain('개발 대화');
	});
});
