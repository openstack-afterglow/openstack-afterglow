import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { auth } from '$lib/stores/auth';
import { ApiError } from '$lib/api/client';

const mocks = vi.hoisted(() => ({
	get: vi.fn(),
	post: vi.fn(),
	delete: vi.fn(),
}));

vi.mock('$lib/api/client', () => ({
	api: mocks,
	ApiError: class ApiError extends Error { constructor(_status: number, message: string) { super(message); } },
}));

import AdminProjectAccessModal from '../AdminProjectAccessModal.svelte';

const project = {
	id: 'p1',
	name: 'agent',
	description: '',
	enabled: true,
	domain_id: 'domain-a',
	created_at: null,
};

const defaultRoles = [
	{ id: 'r-lb', name: 'load-balancer_member' },
	{ id: 'r-admin', name: 'admin' },
	{ id: 'r-reader', name: 'reader' },
	{ id: 'r-member', name: 'member' },
];

let members: Array<Record<string, unknown>>;
let roles: Array<{ id: string; name: string }>;

function renderModal() {
	return render(AdminProjectAccessModal, { project, domainId: 'domain-a', onClose: vi.fn() });
}

describe('AdminProjectAccessModal', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		members = [
			{ user_id: 'u2', user_name: 'pieroot', role_id: 'r-admin', role_name: 'admin', type: 'user' },
			{ user_id: 'u2', user_name: 'pieroot', role_id: 'r-reader', role_name: 'reader', type: 'user' },
			{ user_id: 'group:g1', user_name: '[그룹] AGENT', role_id: 'r-member', role_name: 'member', type: 'group', group_id: 'g1' },
		];
		roles = defaultRoles;
		mocks.get.mockImplementation((url: string) => {
			if (url === '/api/v1/admin/projects/p1/members?domain_id=domain-a') return Promise.resolve(members);
			if (url === '/api/v1/admin/domains/domain-a/members') {
				return Promise.resolve({ domain_id: 'domain-a', items: [{ id: 'u1', name: 'dustywindow', domain_id: 'personal-home' }, { id: 'u2', name: 'pieroot', domain_id: 'domain-a' }] });
			}
			if (url === '/api/v1/admin/roles?domain_id=domain-a') return Promise.resolve(roles);
			if (url === '/api/v1/admin/groups?domain_id=domain-a') return Promise.resolve([{ id: 'g1', name: 'AGENT', description: '', domain_id: 'domain-a' }]);
			throw new Error(`Unexpected GET ${url}`);
		});
		mocks.post.mockResolvedValue({ status: 'assigned' });
		mocks.delete.mockResolvedValue({ status: 'revoked' });
		auth.set({
			token: 'token',
			refreshToken: null,
			accessExpiresAt: null,
			userId: 'admin',
			username: 'admin',
			projectId: 'admin-project',
			projectName: 'Admin',
			availableProjects: [],
			roles: ['admin'],
			isSystemAdmin: true,
			federated: false, domainId: 'domain-1', domainName: 'Domain', isDomainManager: false,
		});
	});

	it('adds an explicitly joined foreign-home user as reader with one click', async () => {
		renderModal();
		await screen.findByRole('button', { name: 'dustywindow reader로 추가' });

		await fireEvent.click(screen.getByRole('button', { name: 'dustywindow reader로 추가' }));

		await waitFor(() => expect(mocks.post).toHaveBeenCalledWith(
			'/api/v1/admin/roles/assign?domain_id=domain-a',
			{ user_id: 'u1', project_id: 'p1', role_id: 'r-reader', domain_id: 'domain-a' },
			'token',
			'admin-project',
		));
		expect(screen.queryByRole('dialog', { name: /역할 선택/ })).toBeNull();
		expect(mocks.get.mock.calls.filter(([url]) => url === '/api/v1/admin/projects/p1/members?domain_id=domain-a')).toHaveLength(2);
	});

	it('groups a principal roles into one row and marks existing users assigned', async () => {
		renderModal();
		await screen.findByRole('button', { name: 'pieroot 권한' });

		expect(screen.getAllByRole('button', { name: 'pieroot 권한' })).toHaveLength(1);
		const row = screen.getByRole('button', { name: 'pieroot 권한' }).parentElement?.parentElement as HTMLElement;
		expect(within(row).getByText('admin')).toBeTruthy();
		expect(within(row).getByText('reader')).toBeTruthy();
		expect(screen.getByText('할당됨')).toBeTruthy();
		expect(screen.queryByRole('button', { name: 'pieroot reader로 추가' })).toBeNull();
	});

	it('locks reader and immediately toggles other user roles', async () => {
		renderModal();
		await screen.findByRole('button', { name: 'pieroot 권한' });
		await fireEvent.click(screen.getByRole('button', { name: 'pieroot 권한' }));

		const dialog = screen.getByRole('dialog', { name: 'pieroot — 세부 권한' });
		expect(within(dialog).getByRole('checkbox', { name: 'reader' })).toMatchObject({ checked: true, disabled: true });
		expect(within(dialog).getByRole('checkbox', { name: 'admin' })).toMatchObject({ checked: true, disabled: false });
		expect(within(dialog).getByRole('checkbox', { name: 'member' })).toMatchObject({ checked: false });
		expect(within(dialog).getAllByRole('checkbox').map((checkbox) => checkbox.getAttribute('aria-label') ?? checkbox.parentElement?.textContent?.trim())).toEqual([
			'reader',
			'member',
			'admin',
			'load-balancer_member',
		]);

		await fireEvent.click(within(dialog).getByRole('checkbox', { name: 'member' }));
		await waitFor(() => expect(mocks.post).toHaveBeenCalledWith(
			'/api/v1/admin/roles/assign?domain_id=domain-a',
			{ user_id: 'u2', project_id: 'p1', role_id: 'r-member', domain_id: 'domain-a' },
			'token',
			'admin-project',
		));
		await fireEvent.click(within(dialog).getByRole('checkbox', { name: 'admin' }));
		await waitFor(() => expect(mocks.delete).toHaveBeenCalledWith(
			'/api/v1/admin/roles/assign?project_id=p1&role_id=r-admin&user_id=u2&domain_id=domain-a',
			'token',
			'admin-project',
		));
	});

	it('routes group principals through group role endpoints', async () => {
		renderModal();
		await screen.findByRole('button', { name: '[그룹] AGENT 권한' });
		await fireEvent.click(screen.getByRole('button', { name: '[그룹] AGENT 권한' }));
		await fireEvent.click(screen.getByRole('checkbox', { name: 'reader' }));

		await waitFor(() => expect(mocks.post).toHaveBeenCalledWith(
			'/api/v1/admin/roles/assign-group?domain_id=domain-a',
			{ group_id: 'g1', project_id: 'p1', role_id: 'r-reader', domain_id: 'domain-a' },
			'token',
			'admin-project',
		));
	});

	it('announces saving the reader role on a group until the request settles', async () => {
		const request = Promise.withResolvers<unknown>();
		mocks.post.mockReturnValueOnce(request.promise);
		renderModal();
		await fireEvent.click(await screen.findByRole('button', { name: '[그룹] AGENT 권한' }));
		const dialog = screen.getByRole('dialog', { name: '[그룹] AGENT — 세부 권한' });
		await fireEvent.click(within(dialog).getByRole('checkbox', { name: 'reader' }));
		expect(within(dialog).getByRole('status').textContent).toContain('저장 중...');
		members.push({ user_id: 'group:g1', user_name: '[그룹] AGENT', role_id: 'r-reader', role_name: 'reader', type: 'group', group_id: 'g1' });
		request.resolve({ status: 'assigned' });
		await waitFor(() => expect(within(dialog).queryByText('저장 중...')).toBeNull());
		expect(within(dialog).getByRole('checkbox', { name: 'reader' })).toMatchObject({ checked: true, disabled: true });
	});

	it('fails closed when the reader role is missing', async () => {
		roles = defaultRoles.filter((role) => role.name !== 'reader');
		renderModal();
		const warning = await screen.findByText('reader 역할을 찾을 수 없어 멤버를 추가할 수 없습니다. Keystone 역할 목록을 확인하세요.');
		expect(warning.closest('[role="status"]')).toBeTruthy();
		expect((screen.getByRole('button', { name: 'dustywindow reader로 추가' }) as HTMLButtonElement).disabled).toBe(true);
	});

	it('removes every role assigned to a principal', async () => {
		renderModal();
		await screen.findByRole('button', { name: 'pieroot 제거' });
		await fireEvent.click(screen.getByRole('button', { name: 'pieroot 제거' }));

		await waitFor(() => expect(mocks.delete).toHaveBeenCalledWith(
			'/api/v1/admin/roles/assign?project_id=p1&role_id=r-admin&user_id=u2&domain_id=domain-a',
			'token',
			'admin-project',
		));
		expect(mocks.delete).toHaveBeenCalledWith(
			'/api/v1/admin/roles/assign?project_id=p1&role_id=r-reader&user_id=u2&domain_id=domain-a',
			'token',
			'admin-project',
		);
	});
	it('rejects a membership catalog for another working domain', async () => {
		mocks.get.mockImplementation((url: string) => {
			if (url === '/api/v1/admin/domains/domain-a/members') return Promise.resolve({ domain_id: 'domain-b', items: [{ id: 'foreign', name: 'Foreign user', domain_id: 'domain-b' }] });
			if (url.includes('/roles?')) return Promise.resolve(defaultRoles);
			return Promise.resolve([]);
		});
		renderModal();
		expect(await screen.findByRole('alert')).toBeTruthy();
		expect(screen.queryByText('Foreign user')).toBeNull();
		expect(mocks.post).not.toHaveBeenCalled();
	});

	it('ignores a late old-domain catalog and preserves a native denial', async () => {
		const first = Promise.withResolvers<unknown>();
		mocks.get.mockImplementation(() => first.promise);
		const view = renderModal();
		await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(4));
		mocks.get.mockRejectedValue(new ApiError(403, 'identity_domain_mismatch'));
		await view.rerender({ project: { ...project, domain_id: 'domain-b' }, domainId: 'domain-b', onClose: vi.fn() });
		expect(await screen.findByText('identity_domain_mismatch')).toBeTruthy();
		first.resolve([]);
		await Promise.resolve();
		expect(screen.getByText('identity_domain_mismatch')).toBeTruthy();
		expect(screen.queryByRole('button', { name: 'dustywindow reader로 추가' })).toBeNull();
	});

	it('stops a multi-role removal when its captured scope unmounts', async () => {
		const pending = Promise.withResolvers<unknown>();
		mocks.delete.mockReturnValueOnce(pending.promise);
		const view = renderModal();
		await fireEvent.click(await screen.findByRole('button', { name: 'pieroot 제거' }));
		expect(mocks.delete).toHaveBeenCalledOnce();
		view.unmount();
		pending.resolve({ status: 'revoked' });
		await Promise.resolve();
		await Promise.resolve();
		expect(mocks.delete).toHaveBeenCalledOnce();
		expect(mocks.get).toHaveBeenCalledTimes(4);
	});

});
