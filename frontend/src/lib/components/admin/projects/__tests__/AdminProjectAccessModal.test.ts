import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { auth } from '$lib/stores/auth';

const mocks = vi.hoisted(() => ({
	get: vi.fn(),
	post: vi.fn(),
	delete: vi.fn(),
}));

vi.mock('$lib/api/client', () => ({
	api: mocks,
	ApiError: class ApiError extends Error {},
}));

import AdminProjectAccessModal from '../AdminProjectAccessModal.svelte';

const project = {
	id: 'p1',
	name: 'agent',
	description: '',
	enabled: true,
	domain_id: null,
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
	return render(AdminProjectAccessModal, { project, onClose: vi.fn() });
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
			if (url === '/api/v1/admin/projects/p1/members') return Promise.resolve(members);
			if (url === '/api/v1/admin/users?limit=100') {
				return Promise.resolve({ items: [{ id: 'u1', name: 'dustywindow' }, { id: 'u2', name: 'pieroot' }] });
			}
			if (url === '/api/v1/admin/roles') return Promise.resolve(roles);
			if (url === '/api/v1/admin/groups') return Promise.resolve([{ id: 'g1', name: 'AGENT', description: '' }]);
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
			federated: false,
		});
	});

	it('adds a user as reader with one click', async () => {
		renderModal();
		await screen.findByRole('button', { name: 'dustywindow reader로 추가' });

		await fireEvent.click(screen.getByRole('button', { name: 'dustywindow reader로 추가' }));

		await waitFor(() => expect(mocks.post).toHaveBeenCalledWith(
			'/api/v1/admin/roles/assign',
			{ user_id: 'u1', project_id: 'p1', role_id: 'r-reader' },
			'token',
			'admin-project',
		));
		expect(screen.queryByRole('dialog', { name: /역할 선택/ })).toBeNull();
		expect(mocks.get.mock.calls.filter(([url]) => url === '/api/v1/admin/projects/p1/members')).toHaveLength(2);
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
			'/api/v1/admin/roles/assign',
			{ user_id: 'u2', project_id: 'p1', role_id: 'r-member' },
			'token',
			'admin-project',
		));
		await fireEvent.click(within(dialog).getByRole('checkbox', { name: 'admin' }));
		await waitFor(() => expect(mocks.delete).toHaveBeenCalledWith(
			'/api/v1/admin/roles/assign?user_id=u2&project_id=p1&role_id=r-admin',
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
			'/api/v1/admin/roles/assign-group',
			{ group_id: 'g1', project_id: 'p1', role_id: 'r-reader' },
			'token',
			'admin-project',
		));
	});

	it('fails closed when the reader role is missing', async () => {
		roles = defaultRoles.filter((role) => role.name !== 'reader');
		renderModal();
		await screen.findByRole('status');
		expect(screen.getByRole('status').textContent).toContain('reader 역할을 찾을 수 없어 멤버를 추가할 수 없습니다');
		expect((screen.getByRole('button', { name: 'dustywindow reader로 추가' }) as HTMLButtonElement).disabled).toBe(true);
	});

	it('removes every role assigned to a principal', async () => {
		renderModal();
		await screen.findByRole('button', { name: 'pieroot 제거' });
		await fireEvent.click(screen.getByRole('button', { name: 'pieroot 제거' }));

		await waitFor(() => expect(mocks.delete).toHaveBeenCalledWith(
			'/api/v1/admin/roles/assign?user_id=u2&project_id=p1&role_id=r-admin',
			'token',
			'admin-project',
		));
		expect(mocks.delete).toHaveBeenCalledWith(
			'/api/v1/admin/roles/assign?user_id=u2&project_id=p1&role_id=r-reader',
			'token',
			'admin-project',
		);
	});
});
