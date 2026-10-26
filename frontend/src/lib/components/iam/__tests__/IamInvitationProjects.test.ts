import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { api } = vi.hoisted(() => ({ api: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }));
vi.mock('$lib/api/client', () => ({ api, ApiError: class ApiError extends Error { constructor(public status: number, message: string) { super(message); } } }));
import IamInvitations from '../IamInvitations.svelte';
import { t } from '$lib/i18n/ns/domain-iam';
import { t as tc } from '$lib/i18n/ns/common';

const session = { token: () => 'token', userId: 'manager', domainId: 'domain-a', isCurrent: () => true, canSubmit: () => true };
const projects = [{ id: 'project-a', name: 'Project A' }, { id: 'project-b', name: 'Project B' }];
async function open() {
	render(IamInvitations, { session, onDenied: vi.fn() });
	await waitFor(() => expect((screen.getByRole('button', { name: t('sendInvite') }) as HTMLButtonElement).disabled).toBe(false));
	await fireEvent.input(screen.getByLabelText(new RegExp(t('email'))), { target: { value: 'invitee@example.com' } });
	await fireEvent.click(screen.getByRole('button', { name: t('sendInvite') }));
	return within(screen.getByRole('dialog'));
}
beforeEach(() => {
	vi.resetAllMocks();
	api.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/projects') ? { items: projects } : path.endsWith('/invitations') ? { items: [] } : { roles: [
		{ id: path.includes('project-a') ? 'reader-a' : 'reader-b', name: 'project_reader', area: 'project', grade: 'reader' },
		{ id: 'owner', name: 'project_owner', area: 'project', grade: 'owner' },
		{ id: 'admin', name: 'admin', area: 'legacy' }
	] }));
});
afterEach(cleanup);

describe('multi-project invitation modal', () => {
	it('keeps email entry alone, cancels without sending and drops the cancelled selection', async () => {
		const modal = await open();
		expect(api.post).not.toHaveBeenCalled();
		await fireEvent.click(modal.getByRole('checkbox', { name: /Project A/ }));
		await modal.findByRole('checkbox', { name: 'project_reader' });
		await fireEvent.click(modal.getByRole('button', { name: tc('actions.cancel') }));
		expect(api.post).not.toHaveBeenCalled();
		expect(screen.queryByRole('dialog')).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: t('sendInvite') }));
		expect((within(screen.getByRole('dialog')).getByRole('checkbox', { name: /Project A/ }) as HTMLInputElement).checked).toBe(false);
	});
	it('submits two projects with individual role IDs exactly once while a final request is pending', async () => {
		const sent = Promise.withResolvers<unknown>(); api.post.mockReturnValue(sent.promise);
		const modal = await open();
		await fireEvent.click(modal.getByRole('checkbox', { name: /Project A/ }));
		await fireEvent.click(await modal.findByRole('checkbox', { name: 'project_reader' }));
		await fireEvent.click(modal.getByRole('checkbox', { name: /Project B/ }));
		await waitFor(() => expect(modal.getAllByRole('checkbox', { name: 'project_reader' })).toHaveLength(2));
		await fireEvent.click(modal.getAllByRole('checkbox', { name: 'project_reader' })[1]);
		expect(modal.queryByRole('checkbox', { name: 'project_owner' })).toBeNull();
		expect(modal.queryByRole('checkbox', { name: 'admin' })).toBeNull();
		const send = modal.getByRole('button', { name: t('inviteProjectsSend') });
		await fireEvent.click(send); await fireEvent.click(send);
		expect(api.post).toHaveBeenCalledExactlyOnceWith('/api/v1/iam/invitations', { email: 'invitee@example.com', projects: [{ project_id: 'project-a', role_ids: ['reader-a'] }, { project_id: 'project-b', role_ids: ['reader-b'] }] }, 'token', undefined, { replayOnUnauthorized: false });
		sent.resolve({});
		await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
	});
	it('rejects final send after scope invalidation before unmount and clears the private draft on unmount', async () => {
		let current = true;
		const view = render(IamInvitations, { session: { ...session, isCurrent: () => current }, onDenied: vi.fn() });
		await waitFor(() => expect((screen.getByRole('button', { name: t('sendInvite') }) as HTMLButtonElement).disabled).toBe(false));
		await fireEvent.input(screen.getByLabelText(new RegExp(t('email'))), { target: { value: 'private@example.com' } });
		await fireEvent.click(screen.getByRole('button', { name: t('sendInvite') }));
		current = false;
		await fireEvent.click(screen.getByRole('button', { name: t('inviteProjectsSend') }));
		expect(api.post).not.toHaveBeenCalled();
		view.unmount();
		render(IamInvitations, { session, onDenied: vi.fn() });
		expect((screen.getByLabelText(new RegExp(t('email'))) as HTMLInputElement).value).toBe('');
		expect(screen.queryByRole('dialog')).toBeNull();
	});
});
