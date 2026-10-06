import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { expect, it, vi } from 'vitest';
import GroupCard from '../GroupCard.svelte';

it('announces only the member whose removal is in flight and clears activity on settlement', async () => {
	const request = Promise.withResolvers<void>();
	const onRemoveMember = vi.fn(() => request.promise);
	render(GroupCard, {
		group: { id: 'group-1', name: 'Operators', description: '', domain_id: null, created_at: null },
		expanded: true,
		members: [
			{ id: 'u1', name: 'Alice', email: '', enabled: true },
			{ id: 'u2', name: 'Bob', email: '', enabled: true },
		],
		membersLoading: false,
		allUsers: [],
		addError: '',
		addSaving: false,
		onToggleMembers: vi.fn(),
		onEdit: vi.fn(),
		onDelete: vi.fn(),
		onAddMember: vi.fn(),
		onRemoveMember,
	});
	const aliceRow = screen.getByText('Alice').parentElement!.parentElement!;
	const bobRow = screen.getByText('Bob').parentElement!.parentElement!;
	await fireEvent.click(within(aliceRow).getByRole('button', { name: '제거' }));

	expect(onRemoveMember).toHaveBeenCalledWith('u1');
	expect(within(aliceRow).getByRole('status').textContent).toContain('제거 중...');
	expect(within(aliceRow).getByRole('button').getAttribute('aria-busy')).toBe('true');
	expect(within(bobRow).queryByRole('status')).toBeNull();
	expect(within(bobRow).getByRole('button').getAttribute('aria-busy')).toBe('false');
	request.resolve();
	await waitFor(() => expect(screen.queryByText('제거 중...')).toBeNull());
	expect((within(aliceRow).getByRole('button') as HTMLButtonElement).disabled).toBe(false);
});
