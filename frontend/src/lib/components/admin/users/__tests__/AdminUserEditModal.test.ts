import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { auth } from '$lib/stores/auth';
import { ApiError } from '$lib/api/errors';
import { initLocale } from '$lib/i18n/runtime.svelte';
import type { User } from '$lib/types/common';
import ko from '$lib/i18n/messages/ko/admin-identity.json';
import en from '$lib/i18n/messages/en/admin-identity.json';
import ja from '$lib/i18n/messages/ja/admin-identity.json';
import zhCN from '$lib/i18n/messages/zh-CN/admin-identity.json';

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: mocks, ApiError }));

import AdminUserEditModal from '../AdminUserEditModal.svelte';

const alice: User = {
	id: 'a718fbcb-a609-4d3a-986a-9e7d50840b69', name: 'Alice', email: 'alice@example.test',
	enabled: true, domain_id: 'default', default_project_id: null, created_at: null,
};
const bob: User = { ...alice, id: '8b82239e-a0cc-46a3-981f-bfa0e38d5591', name: 'Bob', email: 'bob@example.test' };
const projectId = '91d59d82-5a67-4a45-97a0-2eb58890345c';
const longRole = 'compute_instance_admin_with_an_unbroken_role_name_for_wrapping';
const permissions = {
	items: [
		{ scope_type: 'project', scope_id: projectId, scope_name: 'Research project with a long readable name', roles: [
			{ id: 'role-reader', name: 'reader' }, { id: 'role-compute', name: longRole },
		] },
		{ scope_type: 'project', scope_id: 'a546c3eb-a2ee-440b-8504-90c116842d70', scope_name: 'Deployment', roles: [
			{ id: 'role-member', name: 'member' },
		] },
		{ scope_type: 'domain', scope_id: 'default', scope_name: 'Default', roles: [{ id: 'role-domain', name: 'domain_admin' }] },
		{ scope_type: 'system', scope_id: 'all', scope_name: 'all', roles: [{ id: 'role-system', name: 'system_admin' }] },
	],
	count: 4,
};
const session = {
	jti: 'session-a', origin_ip: '192.0.2.20', last_ip: '192.0.2.21', last_seen: 1780740000,
	blacklisted: false, device_type: 'desktop', os: 'macOS', auth_method: 'password', exp: 1780743600,
};
const sessionResponse = { sessions: [session, { ...session, jti: 'session-blocked', origin_ip: '192.0.2.22', blacklisted: true }], count: 2 };
const emptyPermissions = { items: [], count: 0 };
const emptySessions = { sessions: [], count: 0 };

function deferred<T>() {
	let resolve!: (value: T) => void;
	let reject!: (error: Error) => void;
	const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
	return { promise, resolve, reject };
}

function renderModal(user: User | null = alice, onUpdate = vi.fn().mockResolvedValue(true)) {
	return { ...render(AdminUserEditModal, { user, onUpdate }), onUpdate };
}
function permissionSection() {
	return screen.getByRole('region', { name: '프로젝트 및 범위별 역할' });
}
function sessionSection() {
	return screen.getByRole('region', { name: '활성 세션' });
}

beforeEach(() => {
	vi.resetAllMocks();
	initLocale('ko');
	auth.set({
		token: 'admin-token', refreshToken: null, accessExpiresAt: null, userId: 'admin', username: 'admin',
		projectId: 'admin-project', projectName: 'Admin', availableProjects: [], roles: ['admin'],
		isSystemAdmin: true, federated: false,
	});
	mocks.get.mockImplementation((path: string) => {
		if (path.endsWith('/permissions')) return Promise.resolve(permissions);
		if (path.endsWith('/sessions')) return Promise.resolve(sessionResponse);
		throw new Error(`Unexpected GET ${path}`);
	});
	mocks.post.mockResolvedValue({ revoked_count: 2 });
});
afterEach(() => {
	cleanup();
	initLocale('ko');
});

describe('AdminUserEditModal permissions and sessions', () => {
	it('renders full scope names and IDs, effective role chips, and sessions using the fixed API contract', async () => {
		renderModal();
		await screen.findByText(longRole);
		const grants = within(permissionSection());
		expect(grants.getByText(permissions.items[0].scope_name)).toBeTruthy();
		expect(grants.getByText(`ID: ${projectId}`)).toBeTruthy();
		expect(grants.getByText('ID: a546c3eb-a2ee-440b-8504-90c116842d70')).toBeTruthy();
		expect(grants.getAllByText('프로젝트')).toHaveLength(2);
		expect(grants.getByText('도메인')).toBeTruthy();
		expect(grants.getByText('시스템')).toBeTruthy();
		expect(grants.getByText('ID: default')).toBeTruthy();
		expect(grants.getByText('ID: all')).toBeTruthy();
		const roles = grants.getByRole('list', { name: `${permissions.items[0].scope_name}의 역할` });
		expect(within(roles).getAllByRole('listitem').map((row) => row.textContent?.trim())).toEqual(['reader', longRole]);
		expect(grants.getByText('member')).toBeTruthy();
		expect(grants.getByText('domain_admin')).toBeTruthy();
		expect(grants.getByText('system_admin')).toBeTruthy();
		expect(within(sessionSection()).getByText('192.0.2.20')).toBeTruthy();
		expect(within(sessionSection()).getAllByText('macOS · desktop')).toHaveLength(2);
		expect(within(sessionSection()).getByText('차단')).toBeTruthy();
		expect(mocks.get).toHaveBeenCalledWith(`/api/v1/admin/users/${alice.id}/permissions`, 'admin-token', 'admin-project');
		expect(mocks.get).toHaveBeenCalledWith(`/api/v1/admin/users/${alice.id}/sessions`, 'admin-token', 'admin-project');
		expect(mocks.get).toHaveBeenCalledTimes(2);
	});

	it('keeps each lookup loading independently without showing an empty or zero-grant result', async () => {
		const grants = deferred<typeof permissions>();
		const sessions = deferred<typeof sessionResponse>();
		mocks.get.mockImplementation((path: string) => path.endsWith('/permissions') ? grants.promise : sessions.promise);
		renderModal();
		expect(permissionSection().getAttribute('aria-busy')).toBe('true');
		expect(within(permissionSection()).getByRole('status').textContent).toContain('사용자 역할을 불러오는 중...');
		expect(within(sessionSection()).getByRole('status').textContent).toContain('로딩...');
		expect(screen.queryByText('할당된 유효 역할이 없습니다.')).toBeNull();
		expect(screen.queryByText('활성 세션 없음')).toBeNull();
		sessions.resolve(sessionResponse);
		await screen.findByText('192.0.2.20');
		expect(permissionSection().getAttribute('aria-busy')).toBe('true');
		expect(sessionSection().getAttribute('aria-busy')).toBe('false');
		grants.resolve(permissions);
		await screen.findByText(longRole);
		expect(permissionSection().getAttribute('aria-busy')).toBe('false');
	});

	it('renders empty grants and sessions only after successful empty responses', async () => {
		mocks.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/permissions') ? emptyPermissions : emptySessions));
		renderModal();
		await screen.findByText('할당된 유효 역할이 없습니다.');
		expect(within(sessionSection()).getByText('활성 세션 없음')).toBeTruthy();
		expect(screen.queryByRole('alert')).toBeNull();
		expect(screen.queryByRole('button', { name: '역할 다시 조회' })).toBeNull();
	});

	it.each([
		[new Error('network unavailable'), '사용자 역할을 조회하지 못했습니다.'],
		[new ApiError(503, 'Identity unavailable'), '사용자 역할을 조회하지 못했습니다.'],
		[new ApiError(401, 'Unauthorized'), '사용자 역할을 조회할 권한이 없습니다.'],
		[new ApiError(403, 'Forbidden'), '사용자 역할을 조회할 권한이 없습니다.'],
	])('distinguishes permission lookup failure from no grants and retries only permissions (%s)', async (failure, message) => {
		const retry = deferred<typeof permissions>();
		let attempt = 0;
		mocks.get.mockImplementation((path: string) => {
			if (path.endsWith('/sessions')) return Promise.resolve(sessionResponse);
			return attempt++ === 0 ? Promise.reject(failure) : retry.promise;
		});
		renderModal();
		await screen.findByRole('alert');
		expect(within(permissionSection()).getByRole('alert').textContent).toContain(message);
		expect(screen.queryByText('할당된 유효 역할이 없습니다.')).toBeNull();
		expect(within(sessionSection()).getByText('192.0.2.20')).toBeTruthy();
		const name = screen.getByLabelText('이름') as HTMLInputElement;
		await fireEvent.input(name, { target: { value: 'Unsaved Alice' } });
		await fireEvent.click(screen.getByRole('button', { name: '역할 다시 조회' }));
		expect(within(permissionSection()).getByRole('status')).toBeTruthy();
		expect(within(permissionSection()).queryByRole('alert')).toBeNull();
		expect(screen.queryByText('할당된 유효 역할이 없습니다.')).toBeNull();
		retry.resolve(permissions);
		await screen.findByText(longRole);
		expect(name.value).toBe('Unsaved Alice');
		expect(mocks.get.mock.calls.filter(([path]) => path.endsWith('/sessions'))).toHaveLength(1);
		expect(mocks.get.mock.calls.filter(([path]) => path.endsWith('/permissions'))).toHaveLength(2);
	});

	it('supports permission rendering during a failed session lookup and independently retries sessions', async () => {
		const retry = deferred<typeof sessionResponse>();
		let attempt = 0;
		mocks.get.mockImplementation((path: string) => {
			if (path.endsWith('/permissions')) return Promise.resolve(permissions);
			return attempt++ === 0 ? Promise.reject(new ApiError(403, 'Forbidden')) : retry.promise;
		});
		renderModal();
		await screen.findByText(longRole);
		expect(within(sessionSection()).getByRole('alert').textContent).toContain('세션을 조회하지 못했습니다.');
		expect(within(sessionSection()).queryByText('활성 세션 없음')).toBeNull();
		expect(within(sessionSection()).queryByText('0개')).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: '세션 다시 조회' }));
		expect(within(sessionSection()).getByRole('status')).toBeTruthy();
		expect(within(permissionSection()).getByText(longRole)).toBeTruthy();
		retry.resolve(sessionResponse);
		await screen.findByText('192.0.2.20');
		expect(mocks.get.mock.calls.filter(([path]) => path.endsWith('/permissions'))).toHaveLength(1);
	});

	it('clears loaded roles and sessions immediately when changing the selected user', async () => {
		const view = renderModal();
		await screen.findByText(longRole);
		const grants = deferred<typeof emptyPermissions>();
		const sessions = deferred<typeof emptySessions>();
		mocks.get.mockImplementation((path: string) => path.endsWith('/permissions') ? grants.promise : sessions.promise);
		await view.rerender({ user: bob, onUpdate: view.onUpdate });
		expect(screen.queryByText(longRole)).toBeNull();
		expect(screen.queryByText(`ID: ${projectId}`)).toBeNull();
		expect(screen.queryByText('192.0.2.20')).toBeNull();
		expect((screen.getByLabelText('이름') as HTMLInputElement).value).toBe('Bob');
		expect(mocks.get).toHaveBeenCalledWith(`/api/v1/admin/users/${bob.id}/permissions`, 'admin-token', 'admin-project');
		expect(permissionSection().getAttribute('aria-busy')).toBe('true');
		expect(sessionSection().getAttribute('aria-busy')).toBe('true');
		expect(screen.queryByText('할당된 유효 역할이 없습니다.')).toBeNull();
		grants.resolve(emptyPermissions);
		sessions.resolve(emptySessions);
		await screen.findByText('할당된 유효 역할이 없습니다.');
	});

	it.each(['resolve', 'reject'] as const)('ignores late previous-user permission and session replies (%s)', async (outcome) => {
		const oldGrants = deferred<typeof permissions>();
		const oldSessions = deferred<typeof sessionResponse>();
		const nextGrants = deferred<typeof emptyPermissions>();
		const nextSessions = deferred<typeof emptySessions>();
		mocks.get.mockImplementation((path: string) => {
			const old = path.includes(alice.id);
			return path.endsWith('/permissions') ? (old ? oldGrants.promise : nextGrants.promise) : (old ? oldSessions.promise : nextSessions.promise);
		});
		const view = renderModal();
		await view.rerender({ user: bob, onUpdate: view.onUpdate });
		if (outcome === 'resolve') {
			oldGrants.resolve(permissions);
			oldSessions.resolve(sessionResponse);
		} else {
			oldGrants.reject(new ApiError(403, 'Forbidden'));
			oldSessions.reject(new Error('late failure'));
		}
		await tick();
		expect(screen.queryByText(longRole)).toBeNull();
		expect(screen.queryByText('192.0.2.20')).toBeNull();
		expect(screen.queryByRole('alert')).toBeNull();
		expect(permissionSection().getAttribute('aria-busy')).toBe('true');
		expect(sessionSection().getAttribute('aria-busy')).toBe('true');
		expect(screen.queryByText('할당된 유효 역할이 없습니다.')).toBeNull();
		nextGrants.resolve(emptyPermissions);
		nextSessions.resolve(emptySessions);
		await screen.findByText('할당된 유효 역할이 없습니다.');
		expect(within(sessionSection()).getByText('활성 세션 없음')).toBeTruthy();
	});

	it('ignores old replies after close and reopening the same user', async () => {
		const oldGrants = deferred<typeof permissions>();
		const oldSessions = deferred<typeof sessionResponse>();
		mocks.get.mockImplementation((path: string) => path.endsWith('/permissions') ? oldGrants.promise : oldSessions.promise);
		const view = renderModal();
		await view.rerender({ user: null, onUpdate: view.onUpdate });
		expect(screen.queryByRole('dialog')).toBeNull();
		mocks.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/permissions') ? emptyPermissions : emptySessions));
		await view.rerender({ user: alice, onUpdate: view.onUpdate });
		await screen.findByText('할당된 유효 역할이 없습니다.');
		oldGrants.resolve(permissions);
		oldSessions.resolve(sessionResponse);
		await tick();
		expect(screen.queryByText(longRole)).toBeNull();
		expect(screen.queryByText('192.0.2.20')).toBeNull();
		expect(within(permissionSection()).getByText('할당된 유효 역할이 없습니다.')).toBeTruthy();
	});

	it('keeps update and revoke controls working while permissions fail', async () => {
		mocks.get.mockImplementation((path: string) => path.endsWith('/permissions') ? Promise.reject(new ApiError(403, 'Forbidden')) : Promise.resolve(sessionResponse));
		const onUpdate = vi.fn().mockResolvedValue('Update refused');
		renderModal(alice, onUpdate);
		await screen.findByRole('alert');
		await fireEvent.click(screen.getByRole('button', { name: '전체 세션 강제 폐기 (Keystone 직접 폐기 포함)' }));
		await fireEvent.click(screen.getByRole('button', { name: '확인' }));
		await screen.findByText('세션 2개가 폐기되었습니다.');
		expect(mocks.post).toHaveBeenCalledWith(`/api/v1/admin/users/${alice.id}/revoke-sessions`, {}, 'admin-token', 'admin-project');
		await fireEvent.input(screen.getByLabelText('이름'), { target: { value: 'Alice updated' } });
		await fireEvent.click(screen.getByRole('button', { name: '수정' }));
		await screen.findByText('Update refused');
		expect(onUpdate).toHaveBeenCalledWith(alice.id, { name: 'Alice updated', email: alice.email, password: '', enabled: true });
		onUpdate.mockResolvedValueOnce(true);
		await fireEvent.click(screen.getByRole('button', { name: '수정' }));
		await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
	});

	it('preserves initial focus, keyboard trapping, Escape dismissal and opener focus', async () => {
		const opener = document.createElement('button');
		opener.textContent = 'Open user';
		document.body.append(opener);
		opener.focus();
		try {
			renderModal();
			const dialog = screen.getByRole('dialog', { name: '사용자 수정' });
			const name = screen.getByLabelText('이름');
			await waitFor(() => expect(document.activeElement).toBe(name));
			const update = screen.getByRole('button', { name: '수정' });
			update.focus();
			await fireEvent.keyDown(dialog, { key: 'Tab' });
			expect(document.activeElement).toBe(name);
			await fireEvent.keyDown(dialog, { key: 'Tab', shiftKey: true });
			expect(document.activeElement).toBe(update);
			await fireEvent.keyDown(dialog, { key: 'Escape' });
			await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
			await waitFor(() => expect(document.activeElement).toBe(opener));
		} finally {
			opener.remove();
		}
	});


	it.each([
		['ko', '프로젝트 및 범위별 역할', '활성 세션', '도메인', '시스템', 'ID: '],
		['en', 'Roles by project and scope', 'Active sessions', 'Domain', 'System', 'ID: '],
		['ja', 'プロジェクト・スコープ別のロール', 'アクティブなセッション', 'ドメイン', 'システム', 'ID：'],
		['zh-CN', '按项目和范围显示角色', '活跃会话', '域', '系统', 'ID：'],
	] as const)('renders translated sections without translating resource data (%s)', async (locale, heading, sessionsHeading, domain, system, idPrefix) => {
		initLocale(locale);
		renderModal();
		await screen.findByText(longRole);
		const section = within(screen.getByRole('region', { name: heading }));
		expect(screen.getByRole('region', { name: sessionsHeading })).toBeTruthy();
		expect(section.getByText(domain)).toBeTruthy();
		expect(section.getByText(system)).toBeTruthy();
		expect(section.getByText(permissions.items[0].scope_name)).toBeTruthy();
		expect(section.getByText(`${idPrefix}${projectId}`)).toBeTruthy();
		expect(section.getByText('system_admin')).toBeTruthy();
	});

	it.each([['ko', ko], ['en', en], ['ja', ja], ['zh-CN', zhCN]] as const)(
		'renders localized loading, denial, retry and empty states (%s)', async (locale, messages) => {
			initLocale(locale);
			const grants = deferred<typeof emptyPermissions>();
			const sessions = deferred<typeof emptySessions>();
			mocks.get.mockImplementation((path: string) => path.endsWith('/permissions') ? grants.promise : sessions.promise);
			renderModal();
			expect(screen.getByText(messages['userEdit.permissionsLoading'])).toBeTruthy();
			expect(screen.getByText(messages['userEdit.loading'])).toBeTruthy();
			grants.reject(new ApiError(403, 'Forbidden'));
			sessions.reject(new Error('unavailable'));
			await screen.findByText(messages['userEdit.permissionsUnauthorized']);
			expect(screen.getByText(messages['userEdit.sessionsFailed'])).toBeTruthy();
			expect(screen.queryByText(messages['userEdit.noPermissions'])).toBeNull();
			expect(screen.queryByText(messages['userEdit.noSessions'])).toBeNull();
			mocks.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/permissions') ? emptyPermissions : emptySessions));
			await fireEvent.click(screen.getByRole('button', { name: messages['userEdit.retryPermissions'] }));
			await screen.findByText(messages['userEdit.noPermissions']);
			expect(screen.getByText(messages['userEdit.sessionsFailed'])).toBeTruthy();
			await fireEvent.click(screen.getByRole('button', { name: messages['userEdit.retrySessions'] }));
			await screen.findByText(messages['userEdit.noSessions']);
			expect(screen.queryByRole('alert')).toBeNull();
		},
	);
});
