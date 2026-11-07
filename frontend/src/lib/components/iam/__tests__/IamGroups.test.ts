import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { api, confirmDialog } = vi.hoisted(() => ({ api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() }, confirmDialog: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api, ApiError: class ApiError extends Error { constructor(public status: number, message: string, public code?: string) { super(message); } } }));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog }));
import { ApiError } from '$lib/api/client';
import { t } from '$lib/i18n/ns/domain-iam-groups';
import type { IamGroup, IamGroupMember, IamUser } from '$lib/api/domainIam';
import IamGroups from '../IamGroups.svelte';

const team: IamGroup = { id: 'team', name: 'Team', description: 'Builders', domain_id: 'domain-a', member_count: 1, protected: false, sso_mapped: false };
const operators: IamGroup = { id: 'operators', name: 'Operators', description: '', domain_id: 'domain-a', member_count: 0, protected: true, sso_mapped: false };
const engineering: IamGroup = { id: 'engineering', name: 'Engineering', description: 'SSO', domain_id: 'domain-a', member_count: 0, protected: false, sso_mapped: true };
const alice: IamGroupMember = { id: 'alice', name: 'Alice', email: 'alice@example.com', enabled: true, domain_id: 'domain-a', protected: false, identity_read_only: false };
const bob: IamUser = { id: 'bob', name: 'Bob', email: 'bob@example.com', enabled: true, domain_id: 'domain-a', protected: false };
const carol: IamUser = { ...bob, id: 'carol', name: 'Carol', enabled: false };
let rows: IamGroup[] = [];
let members: IamGroupMember[] = [];
let current = true;
const session = { token: () => 'token', userId: 'actor', domainId: 'domain-a', isCurrent: () => current, canSubmit: () => current };

function fixture(path: string) {
	if (path === '/api/v1/iam/groups') return { items: rows };
	if (path === '/api/v1/iam/groups/team/members') return { items: members };
	if (path === '/api/v1/iam/users') return { items: [alice, bob, carol] };
	throw new Error(`Unexpected path: ${path}`);
}
const slideOver = () => screen.getAllByRole('dialog').at(-1)!;
const row = (name: string) => screen.getByText(name, { selector: 'span' }).closest('tr')!;

afterEach(cleanup);
beforeEach(() => {
	vi.resetAllMocks();
	current = true; rows = [team, operators]; members = [alice];
	api.get.mockImplementation((path: string) => Promise.resolve(fixture(path)));
});

describe('domain manager group table', () => {
	it('lists domain groups with member counts and keeps protected groups read-only', async () => {
		render(IamGroups, { session, onDenied: vi.fn() });
		await screen.findByText('Team', { selector: 'span' });
		expect(within(row('Team')).getByText('Builders')).toBeTruthy();
		expect(within(row('Team')).getByText('1')).toBeTruthy();
		for (const label of [t('edit'), t('members'), t('delete')]) expect((within(row('Team')).getByRole('button', { name: label }) as HTMLButtonElement).disabled).toBe(false);
		expect(within(row('Operators')).getByText(t('protected'))).toBeTruthy();
		expect((within(row('Operators')).getByRole('button', { name: t('edit') }) as HTMLButtonElement).disabled).toBe(true);
		expect((within(row('Operators')).getByRole('button', { name: t('delete') }) as HTMLButtonElement).disabled).toBe(true);
		expect((within(row('Operators')).getByRole('button', { name: t('members') }) as HTMLButtonElement).disabled).toBe(false);
		expect(screen.queryByText(/domain-a/)).toBeNull();
	});

	it('keeps an SSO-mapped group name and existence fixed while its description stays editable', async () => {
		rows = [team, engineering];
		render(IamGroups, { session, onDenied: vi.fn() });
		await screen.findByText('Engineering', { selector: 'span' });
		expect(within(row('Engineering')).getByText(t('ssoMapped'))).toBeTruthy();
		expect((within(row('Engineering')).getByRole('button', { name: t('delete') }) as HTMLButtonElement).disabled).toBe(true);
		await fireEvent.click(within(row('Engineering')).getByRole('button', { name: t('edit') }));
		const panel = slideOver();
		expect((within(panel).getByRole('textbox', { name: new RegExp(t('name')) }) as HTMLInputElement).disabled).toBe(true);
		expect((within(panel).getByRole('textbox', { name: t('description') }) as HTMLTextAreaElement).disabled).toBe(false);
	});

	it('creates a group from the modal and refreshes the table', async () => {
		api.post.mockImplementation(async () => { const created = { ...team, id: 'new', name: 'Release crew', description: 'Ships', member_count: 0 }; rows = [...rows, created]; return created; });
		render(IamGroups, { session, onDenied: vi.fn() });
		await screen.findByText('Team', { selector: 'span' });
		await fireEvent.click(screen.getByRole('button', { name: t('create') }));
		const dialog = screen.getByRole('dialog');
		await fireEvent.input(within(dialog).getByRole('textbox', { name: new RegExp(t('name')) }), { target: { value: '  Release crew ' } });
		await fireEvent.input(within(dialog).getByRole('textbox', { name: t('description') }), { target: { value: 'Ships' } });
		await fireEvent.click(within(dialog).getByRole('button', { name: t('createSubmit') }));
		await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/v1/iam/groups', { name: 'Release crew', description: 'Ships' }, 'token', undefined, { replayOnUnauthorized: false }));
		await screen.findByText('Release crew', { selector: 'span' });
		await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
	});

	it('maps a duplicate name to a localized error without revoking the page', async () => {
		const onDenied = vi.fn();
		api.post.mockRejectedValue(new ApiError(409, 'domain_group_name_exists'));
		render(IamGroups, { session, onDenied });
		await screen.findByText('Team', { selector: 'span' });
		await fireEvent.click(screen.getByRole('button', { name: t('create') }));
		const dialog = screen.getByRole('dialog');
		await fireEvent.input(within(dialog).getByRole('textbox', { name: new RegExp(t('name')) }), { target: { value: 'team' } });
		await fireEvent.click(within(dialog).getByRole('button', { name: t('createSubmit') }));
		expect(await within(dialog).findByText(t('errorNameExists'))).toBeTruthy();
		expect(onDenied).not.toHaveBeenCalled();
	});

	it('edits name and description in the right slide-in', async () => {
		api.patch.mockImplementation(async () => { rows = [{ ...team, name: 'Renamed' }, operators]; return rows[0]; });
		render(IamGroups, { session, onDenied: vi.fn() });
		await screen.findByText('Team', { selector: 'span' });
		await fireEvent.click(within(row('Team')).getByRole('button', { name: t('edit') }));
		const panel = slideOver();
		expect(within(panel).getByText(t('editTitle', { name: 'Team' }))).toBeTruthy();
		await fireEvent.input(within(panel).getByRole('textbox', { name: new RegExp(t('name')) }), { target: { value: 'Renamed' } });
		await fireEvent.click(within(panel).getByRole('button', { name: t('save') }));
		await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/api/v1/iam/groups/team', { name: 'Renamed' }, 'token', undefined, { replayOnUnauthorized: false }));
		await screen.findByText('Renamed', { selector: 'span' });
		expect(screen.getByText(t('saved'))).toBeTruthy();
	});

	it('adds and removes members from the members slide-in', async () => {
		api.put.mockImplementation(async () => { members = [alice, { ...bob, identity_read_only: false }]; });
		api.delete.mockImplementation(async () => { members = [{ ...bob, identity_read_only: false }]; });
		confirmDialog.mockResolvedValue(true);
		render(IamGroups, { session, onDenied: vi.fn() });
		await screen.findByText('Team', { selector: 'span' });
		await fireEvent.click(within(row('Team')).getByRole('button', { name: t('members') }));
		const panel = slideOver();
		await within(panel).findByText('Alice');
		const select = within(panel).getByRole('combobox', { name: t('user') }) as HTMLSelectElement;
		// Existing members and disabled accounts are not offered.
		expect([...select.options].map(option => option.value)).toEqual(['', 'bob']);
		await fireEvent.change(select, { target: { value: 'bob' } });
		await fireEvent.click(within(panel).getByRole('button', { name: t('add') }));
		await waitFor(() => expect(api.put).toHaveBeenCalledWith('/api/v1/iam/groups/team/members/bob', {}, 'token', undefined, { replayOnUnauthorized: false }));
		await within(panel).findByText('Bob');
		const aliceRow = within(panel).getByText('Alice').closest('tr')!;
		await fireEvent.click(within(aliceRow).getByRole('button', { name: t('remove') }));
		expect(confirmDialog).toHaveBeenCalledWith(t('removeConfirm', { user: 'Alice', group: 'Team' }), { confirmLabel: t('remove') });
		await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/api/v1/iam/groups/team/members/alice', 'token', undefined, { replayOnUnauthorized: false }));
		await waitFor(() => expect(within(panel).queryByText('Alice')).toBeNull());
	});

	it('deletes a group only after confirmation', async () => {
		api.delete.mockImplementation(async () => { rows = [operators]; });
		confirmDialog.mockResolvedValueOnce(false).mockResolvedValueOnce(true);
		render(IamGroups, { session, onDenied: vi.fn() });
		await screen.findByText('Team', { selector: 'span' });
		await fireEvent.click(within(row('Team')).getByRole('button', { name: t('delete') }));
		expect(api.delete).not.toHaveBeenCalled();
		await fireEvent.click(within(row('Team')).getByRole('button', { name: t('delete') }));
		await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/api/v1/iam/groups/team', 'token', undefined, { replayOnUnauthorized: false }));
		await waitFor(() => expect(screen.queryByText('Team', { selector: 'span' })).toBeNull());
	});
});
