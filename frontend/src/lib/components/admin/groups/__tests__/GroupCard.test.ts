import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, expect, it, vi } from 'vitest';
import { tick, type ComponentProps } from 'svelte';
import type { User } from '$lib/types/adminGroup';
import GroupCard from '../GroupCard.svelte';

afterEach(cleanup);

const firstUser: User = { id: 'a1111111-1111-4111-8111-111111111111', name: 'pieroot', email: 'first@example.test', enabled: true, domain_id: 'home-first' };
const secondUser: User = { id: 'b2222222-2222-4222-8222-222222222222', name: 'pieroot', email: 'second@example.test', enabled: true, domain_id: 'home-second' };
function props(overrides: Partial<ComponentProps<typeof GroupCard>> = {}): ComponentProps<typeof GroupCard> {
	return {
		group: { id: 'group-1', name: 'Operators', description: '', domain_id: 'selected-domain', created_at: null },
		expanded: true, members: [], membersLoading: false, usersLoading: false,
		allUsers: [firstUser, secondUser], addError: '', addSaving: false,
		onToggleMembers: vi.fn(), onEdit: vi.fn(), onDelete: vi.fn(),
		onAddMember: vi.fn().mockResolvedValue(true), onRemoveMember: vi.fn().mockResolvedValue(undefined),
		onRetryUsers: vi.fn().mockResolvedValue(undefined), ...overrides,
	};
}

const search = (value: string) => fireEvent.input(screen.getByRole('searchbox', { name: '사용자 검색' }), { target: { value } });
const candidate = (id: string) => screen.getByText(id).closest('li')!;

it('announces only the member whose removal is in flight and clears activity on settlement', async () => {
	const request = Promise.withResolvers<void>();
	const onRemoveMember = vi.fn(() => request.promise);
	render(GroupCard, {
		group: { id: 'group-1', name: 'Operators', description: '', domain_id: null, created_at: null },
		expanded: true,
		members: [
			{ id: 'u1', name: 'Alice', email: '', enabled: true, domain_id: 'home-first', identity_read_only: false },
			{ id: 'u2', name: 'Bob', email: '', enabled: true, domain_id: 'home-second', identity_read_only: true },
		],
		membersLoading: false,
		usersLoading: false,
		allUsers: [],
		addError: '',
		addSaving: false,
		onToggleMembers: vi.fn(),
		onEdit: vi.fn(),
		onDelete: vi.fn(),
		onAddMember: vi.fn(),
		onRemoveMember,
		onRetryUsers: vi.fn().mockResolvedValue(undefined),
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

it('shows same-name users with their email, full UUID and native home domain and adds the exact UUID', async () => {
	const onAddMember = vi.fn().mockResolvedValue(true);
	render(GroupCard, props({ onAddMember }));
	await search('  PiErOoT  ');
	expect(screen.getAllByText('pieroot')).toHaveLength(2);
	for (const user of [firstUser, secondUser]) {
		const row = within(candidate(user.id));
		expect(row.getByText(user.email)).toBeTruthy();
		expect(row.getByText(user.id)).toBeTruthy();
		expect(row.getByText(user.domain_id)).toBeTruthy();
	}
	await fireEvent.click(within(candidate(secondUser.id)).getByRole('button', { name: '추가' }));
	expect(onAddMember).toHaveBeenCalledExactlyOnceWith(secondUser.id);
	await waitFor(() => expect((screen.getByRole('searchbox') as HTMLInputElement).value).toBe(''));
});

it('matches trimmed case-insensitive email, full UUID and domain without matching only by name', async () => {
	render(GroupCard, props());
	for (const query of [`  ${secondUser.email.toUpperCase()}  `, secondUser.id.toUpperCase(), ' HOME-SECOND ']) {
		await search(query);
		expect(screen.queryByText(firstUser.id)).toBeNull();
		expect(screen.getByText(secondUser.id)).toBeTruthy();
	}
	await search('unmatched');
	expect(screen.getByText('일치하는 사용자가 없습니다')).toBeTruthy();
});

it('excludes only the existing member UUID and keeps a same-name user from another domain selectable', async () => {
	render(GroupCard, props({ members: [{ ...firstUser, identity_read_only: true }] }));
	await search('pieroot');
	const memberRow = screen.getByText(firstUser.id).closest('li')!;
	expect(within(memberRow).getByText(firstUser.email)).toBeTruthy();
	expect(within(memberRow).getByText(firstUser.domain_id)).toBeTruthy();
	expect(within(memberRow).queryByRole('button', { name: '추가' })).toBeNull();
	expect(within(candidate(secondUser.id)).getByRole('button', { name: '추가' })).toBeTruthy();
	expect(screen.getAllByRole('button', { name: '추가' })).toHaveLength(1);
});

it('states missing email and unavailable member home domain honestly', async () => {
	render(GroupCard, props({
		members: [{ ...firstUser, email: '', domain_id: null, identity_read_only: false }],
		allUsers: [{ ...secondUser, email: '' }],
	}));
	await search('pieroot');
	expect(screen.getAllByText('이메일 미등록')).toHaveLength(2);
	expect(screen.getByText('도메인 미확인')).toBeTruthy();
});

it('keeps matches beyond the eighth result reachable instead of silently slicing them away', async () => {
	const users = Array.from({ length: 12 }, (_, index) => ({ ...firstUser, id: `candidate-${index}`, email: `person-${index}@example.test` }));
	const onAddMember = vi.fn().mockResolvedValue(true);
	render(GroupCard, props({ allUsers: users, onAddMember }));
	await search('pieroot');
	expect(screen.getAllByRole('button', { name: '추가' })).toHaveLength(12);
	await fireEvent.click(within(candidate('candidate-11')).getByRole('button', { name: '추가' }));
	expect(onAddMember).toHaveBeenCalledExactlyOnceWith('candidate-11');
});

it('never offers stale candidates or a no-match state while lookup is pending or failed and exposes retry', async () => {
	const onRetryUsers = vi.fn().mockResolvedValue(undefined);
	const view = render(GroupCard, props({ members: [{ ...firstUser, identity_read_only: false }], usersLoading: true, onRetryUsers }));
	await search('pieroot');
	expect(screen.getByText('추가 가능한 사용자 확인 중...')).toBeTruthy();
	expect(screen.getByText(firstUser.email)).toBeTruthy();
	expect(screen.queryByText('일치하는 사용자가 없습니다')).toBeNull();
	expect(screen.queryByRole('button', { name: '추가' })).toBeNull();
	await view.rerender({ usersLoading: false, usersError: 'identity_native_denied' });
	expect(screen.getByText('identity_native_denied')).toBeTruthy();
	expect((screen.getByRole('searchbox', { name: '사용자 검색' }) as HTMLInputElement).value).toBe('pieroot');
	expect(screen.queryByText(secondUser.id)).toBeNull();
	expect(screen.queryByText('일치하는 사용자가 없습니다')).toBeNull();
	expect(screen.getByText(firstUser.email)).toBeTruthy();
	await fireEvent.click(screen.getByRole('button', { name: '사용자 목록 다시 조회' }));
	expect(onRetryUsers).toHaveBeenCalledOnce();
	await view.rerender({ usersError: '', allUsers: [secondUser] });
	expect((screen.getByRole('searchbox', { name: '사용자 검색' }) as HTMLInputElement).value).toBe('pieroot');
	expect(screen.getByText(secondUser.id)).toBeTruthy();
	expect(screen.queryByText('일치하는 사용자가 없습니다')).toBeNull();
});

it('preserves the new source search when a previous source add settles late', async () => {
	const request = Promise.withResolvers<boolean>();
	const view = render(GroupCard, props({ userDomainId: 'home-first', sourceGeneration: 1, onAddMember: vi.fn(() => request.promise) }));
	await search(firstUser.email);
	await fireEvent.click(within(candidate(firstUser.id)).getByRole('button', { name: '추가' }));
	await view.rerender({ userDomainId: 'home-second', sourceGeneration: 2 });
	await search(secondUser.email);
	request.resolve(true);
	await tick();
	await waitFor(() => expect((screen.getByRole('searchbox', { name: '사용자 검색' }) as HTMLInputElement).value).toBe(secondUser.email));
});

