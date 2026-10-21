import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { api, confirmDialog } = vi.hoisted(() => ({
	api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
	confirmDialog: vi.fn()
}));
vi.mock('$lib/api/client', () => ({ api, ApiError: class ApiError extends Error { constructor(public status: number, message: string) { super(message); } } }));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token', userId: 'actor', domainId: 'domain-a', domainName: 'Domain A', isDomainManager: true, isSystemAdmin: false }),
	authReady: writable(true), projectSwitching: writable(false)
}));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog }));
import { auth, authReady } from '$lib/stores/auth';
import { ApiError } from '$lib/api/client';
import DomainIamConsole from '../DomainIamConsole.svelte';
import IamUsers from '../IamUsers.svelte';
import IamLogin from '../IamLogin.svelte';
import IamProjects from '../IamProjects.svelte';
import IamInvitations from '../IamInvitations.svelte';
import IamRecovery from '../IamRecovery.svelte';

const session = { token: () => 'token', userId: 'actor', domainId: 'domain-a', isCurrent: () => true, canSubmit: () => true };
const user = { id: 'user-a', name: 'Alice', email: 'alice@example.com', enabled: true, domain_id: 'domain-a', protected: false };
const provider = { id: 'provider-a', domain_id: 'domain-a', name: 'Corporate SSO', kind: 'oidc', federation_token_type: 'id_token', token_endpoint_auth_method: 'client_secret_basic', verified: true, verified_revision: 3, verified_at: '2026-10-15T00:00:00Z', enabled: true, issuer_url: 'https://issuer.example.com', client_id: 'public-client', scopes: ['openid', 'email'], keystone_idp_id: 'idp', keystone_protocol_id: 'openid', authorization_url: 'https://issuer.example.com/authorize', token_url: 'https://issuer.example.com/token', api_url: null, client_secret_configured: true, revision: 3, created_at: '', updated_at: '' };
const policy = { domain_id: 'domain-a', password_enabled: true, allowed_email_domains: [], signup_enabled: false, signup_email_domains: [], revision: 7, configured: true, smtp_configured: true, usable_provider_count: 1 };
const project = { id: 'project-a', name: 'Project A', enabled: true, domain_id: 'domain-a' };
const member = { user_id: 'user-a', username: 'Alice', email: 'alice@example.com', is_owner: false, is_manager: false, roles: ['custom_reader'], direct_role_ids: ['role-a'], effective_role_ids: ['role-a'], external_role_ids: [], source: 'direct' };
const catalog = { is_owner: false, can_manage_owners: false, roles: [{ id: 'role-a', name: 'custom_reader', area: 'custom', grade: 'reader', implied_role_ids: [], inherited_role_ids: [] }] };
const invitation = { id: 4, domain_id: 'domain-a', email: 'invitee@example.com', project_id: 'project-a', project_name: 'Project A', role_ids: ['role-a'], status: 'pending', expires_at: '2099-01-01T00:00:00Z', created_at: '', accepted_at: null };
function deferred<T>() { let resolve!: (value: T) => void; let reject!: (cause: Error) => void; const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }
function fixture(path: string) {
	if (path.endsWith('/context')) return { domain_id: 'domain-a', domain_name: 'Domain A', is_domain_manager: true };
	if (path.includes('/projects/creators?')) return { domain_id: 'domain-a', role: { id: 'creator-role', name: 'project_creator' }, users: [] };
	if (path.endsWith('/eligible-users')) return [user];
	if (path.endsWith('/ownership')) return { project_id: path.split('/').at(-2), owner_user_id: 'actor', status: 'unique', owners: [{ user_id: 'actor', name: 'Owner', source: 'direct' }], can_transfer: false, can_delete: false, transfer_operation: null };
	if (path.endsWith('/users')) return { items: [user] };
	if (path.endsWith('/projects')) return { items: [project] };
	if (path.endsWith('/assignable-roles')) return catalog;
	if (path.endsWith('/members')) return { items: [member] };
	if (path.endsWith('/invitations')) return { items: [invitation] };
	if (path.endsWith('/login-policy')) return policy;
	if (path.endsWith('/providers')) return { items: [provider] };
	throw new Error(`Unexpected path: ${path}`);
}
afterEach(cleanup);
beforeEach(() => {
	vi.resetAllMocks();
	auth.set({ token: 'token', userId: 'actor', domainId: 'domain-a', domainName: 'Domain A', isDomainManager: true, isSystemAdmin: false } as never);
	authReady.set(true);
	api.get.mockImplementation((path: string) => Promise.resolve(fixture(path)));
	confirmDialog.mockResolvedValue(true);
});

describe('server-verified IAM identity boundary', () => {
	it('does not fetch private rows before the server verifies the manager', async () => {
		const pending = deferred<unknown>(); api.get.mockReturnValue(pending.promise);
		render(DomainIamConsole);
		await waitFor(() => expect(api.get).toHaveBeenCalledTimes(1));
		expect(screen.queryByText('Alice')).toBeNull();
		pending.resolve({ domain_id: 'domain-a', domain_name: 'Domain A', is_domain_manager: false });
		await screen.findByText('현재 도메인의 관리 권한이 확인되지 않았습니다.');
		expect(api.get).toHaveBeenCalledTimes(1);
	});

	it('does not verify user IAM for system-only authority and rejects a system-only server context', async () => {
		auth.update(state => ({ ...state, isDomainManager: false, isSystemAdmin: true }));
		const first = render(DomainIamConsole);
		await screen.findByText('현재 도메인의 관리 권한이 확인되지 않았습니다.');
		expect(api.get).not.toHaveBeenCalled();
		first.unmount();
		auth.update(state => ({ ...state, isDomainManager: true }));
		api.get.mockResolvedValue({ domain_id: 'domain-a', domain_name: 'Domain A', is_domain_manager: false, is_system_admin: true });
		render(DomainIamConsole);
		await screen.findByText('현재 도메인의 관리 권한이 확인되지 않았습니다.');
		expect(api.get).toHaveBeenCalledOnce();
		expect(screen.queryByText('Alice')).toBeNull();
	});

	it('removes verified console and secret-bearing actions when manager is revoked while system admin stays true', async () => {
		auth.update(state => ({ ...state, isSystemAdmin: true }));
		render(DomainIamConsole);
		await screen.findByText('Alice');
		await fireEvent.click(screen.getByRole('button', { name: '사용자 및 비밀번호 편집' }));
		await fireEvent.input(screen.getByLabelText('새 비밀번호 (선택)'), { target: { value: 'must-not-survive-revocation' } });
		auth.update(state => ({ ...state, isDomainManager: false }));
		await screen.findByText('현재 도메인의 관리 권한이 확인되지 않았습니다.');
		expect(screen.queryByText('Alice')).toBeNull();
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(api.patch).not.toHaveBeenCalled();
	});
	it('rejects a server context for a different domain rather than creating a picker', async () => {
		api.get.mockResolvedValue({ domain_id: 'foreign', domain_name: 'Foreign', is_domain_manager: true });
		render(DomainIamConsole);
		await screen.findByText('서버의 도메인이 로그인한 도메인과 다릅니다. 다시 로그인해 주세요.');
		expect(screen.queryByRole('combobox')).toBeNull();
		expect(api.get).toHaveBeenCalledTimes(1);
	});
	it('fences A to B to A identity transitions even before effects flush', async () => {
		const old = deferred<unknown>(); let reads = 0;
		api.get.mockImplementation((path: string) => path.endsWith('/context') && ++reads === 1 ? old.promise : Promise.resolve(fixture(path)));
		render(DomainIamConsole);
		await waitFor(() => expect(reads).toBe(1));
		auth.update(state => ({ ...state, domainId: 'domain-b' }));
		auth.update(state => ({ ...state, domainId: 'domain-a' }));
		await screen.findByText('Alice');
		old.resolve({ domain_id: 'domain-a', domain_name: 'Obsolete Domain Name', is_domain_manager: true });
		await waitFor(() => expect(screen.queryByText('Obsolete Domain Name')).toBeNull());
		expect(screen.getByText('Alice')).toBeTruthy();
	});
	it('keeps drafts during a focus check and clears them after confirmed revocation', async () => {
		render(DomainIamConsole); await screen.findByText('Alice');
		await fireEvent.click(screen.getByRole('button', { name: '사용자 및 비밀번호 편집' }));
		await fireEvent.input(screen.getByLabelText('새 비밀번호 (선택)'), { target: { value: 'never-retain-this' } });
		const pending = deferred<unknown>(); api.get.mockReturnValue(pending.promise);
		await fireEvent.focus(window);
		expect((screen.getByLabelText('새 비밀번호 (선택)') as HTMLInputElement).value).toBe('never-retain-this');
		expect((screen.getByRole('button', { name: '저장' }) as HTMLButtonElement).disabled).toBe(true);
		pending.reject(new ApiError(403, 'revoked'));
		await screen.findByText('현재 도메인의 관리 권한이 확인되지 않았습니다.');
		expect(screen.queryByText('Alice')).toBeNull(); expect(screen.queryByRole('dialog')).toBeNull();
		expect(api.patch).not.toHaveBeenCalled();
	});
	it('preserves provider drafts and write-only secrets after a successful background focus check', async () => {
		render(DomainIamConsole); await screen.findByText('Alice');
		await fireEvent.click(screen.getByRole('button', { name: '로그인 정책 및 제공자' }));
		await screen.findByText('Corporate SSO');
		await fireEvent.click(screen.getByRole('button', { name: '편집' }));
		const dialog = screen.getByRole('dialog');
		await fireEvent.input(screen.getByLabelText(/^이름/), { target: { value: 'Draft SSO' } });
		await fireEvent.input(screen.getByLabelText('클라이언트 비밀'), { target: { value: 'copied-from-idp-console' } });
		const pending = deferred<unknown>(); api.get.mockImplementation((path: string) => path.endsWith('/context') ? pending.promise : Promise.resolve(fixture(path)));
		await fireEvent.focus(window);
		expect(screen.getByRole('dialog')).toBe(dialog);
		expect((screen.getByRole('button', { name: '저장' }) as HTMLButtonElement).disabled).toBe(true);
		expect((screen.getByLabelText(/^이름/) as HTMLInputElement).disabled).toBe(false);
		pending.resolve({ domain_id: 'domain-a', domain_name: 'Domain A', is_domain_manager: true });
		await waitFor(() => expect((screen.getByRole('button', { name: '저장' }) as HTMLButtonElement).disabled).toBe(false));
		expect(screen.getByRole('dialog')).toBe(dialog);
		expect((screen.getByLabelText(/^이름/) as HTMLInputElement).value).toBe('Draft SSO');
		expect((screen.getByLabelText('클라이언트 비밀') as HTMLInputElement).value).toBe('copied-from-idp-console');
		expect(api.patch).not.toHaveBeenCalled();
	});
	it('does not retire an already accepted user write during a successful focus recheck', async () => {
		const accepted = deferred<unknown>(); api.patch.mockReturnValue(accepted.promise);
		render(DomainIamConsole); await screen.findByText('Alice');
		await fireEvent.click(screen.getByRole('button', { name: '사용자 및 비밀번호 편집' }));
		await fireEvent.click(screen.getByRole('button', { name: '저장' }));
		await fireEvent.focus(window);
		accepted.resolve(user);
		await screen.findByText('변경을 저장했습니다.');
		expect(api.patch).toHaveBeenCalledTimes(1);
		expect(screen.queryByRole('dialog')).toBeNull();
	});
	it('keeps drafts across access-token rotation and sends later writes with the rotated token', async () => {
		api.patch.mockResolvedValue(user);
		render(DomainIamConsole); await screen.findByText('Alice');
		await fireEvent.click(screen.getByRole('button', { name: '사용자 및 비밀번호 편집' }));
		const dialog = screen.getByRole('dialog');
		await fireEvent.input(screen.getByLabelText(/^이름/), { target: { value: 'Rotated draft' } });
		auth.update(state => ({ ...state, token: 'rotated-token' }));
		expect(screen.getByRole('dialog')).toBe(dialog);
		await fireEvent.click(screen.getByRole('button', { name: '저장' }));
		expect(api.patch).toHaveBeenCalledWith('/api/v1/iam/users/user-a', { name: 'Rotated draft', email: user.email, enabled: true }, 'rotated-token', undefined, { replayOnUnauthorized: false });
	});
	it('does not publish a user-list response received after logout', async () => {
		const pending = deferred<unknown>(); api.get.mockImplementation((path: string) => path.endsWith('/users') ? pending.promise : Promise.resolve(fixture(path)));
		render(DomainIamConsole); await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
		authReady.set(false); pending.resolve({ items: [user] });
		await screen.findByText('현재 도메인의 관리 권한이 확인되지 않았습니다.');
		expect(screen.queryByText('Alice')).toBeNull();
	});
});

describe('user and provider secret lifecycles', () => {
	it('clears a submitted password on failure, preserves non-secret edits and allows retry without password', async () => {
		const pending = deferred<unknown>(); api.patch.mockReturnValue(pending.promise);
		render(IamUsers, { session, onDenied: vi.fn() }); await screen.findByText('Alice');
		await fireEvent.click(screen.getByRole('button', { name: '사용자 및 비밀번호 편집' }));
		await fireEvent.input(screen.getByLabelText(/^이름/), { target: { value: 'Updated' } });
		await fireEvent.input(screen.getByLabelText('새 비밀번호 (선택)'), { target: { value: 'private-password' } });
		await fireEvent.click(screen.getByRole('button', { name: '저장' }));
		expect((screen.getByLabelText('새 비밀번호 (선택)') as HTMLInputElement).value).toBe('');
		expect((screen.getByRole('button', { name: '저장' }) as HTMLButtonElement).disabled).toBe(true);
		pending.reject(new Error('update failed')); await screen.findByText('update failed');
		expect((screen.getByLabelText(/^이름/) as HTMLInputElement).value).toBe('Updated');
		api.patch.mockResolvedValue(user); await fireEvent.click(screen.getByRole('button', { name: '저장' }));
		expect(api.patch.mock.calls[1][1]).toEqual({ name: 'Updated', email: user.email, enabled: true });
	});
	it('disables protected-user editing without granting system-admin authority', async () => {
		api.get.mockResolvedValue({ items: [{ ...user, protected: true }] });
		render(IamUsers, { session, onDenied: vi.fn() }); await screen.findByText('Alice');
		expect((screen.getByRole('button', { name: '사용자 및 비밀번호 편집' }) as HTMLButtonElement).disabled).toBe(true);
		expect(api.patch).not.toHaveBeenCalled();
	});
	it.each(['foreign-home', 'account'])('shows joined %s identities without creation or credential authority', async home => {
		api.get.mockResolvedValue({ items: [{ ...user, domain_id: home }] });
		render(IamUsers, { session, onDenied: vi.fn() });
		await screen.findByText('Alice');
		expect(screen.getByText(home)).toBeTruthy();
		expect(screen.queryByRole('button', { name: '사용자 생성' })).toBeNull();
		expect(api.post).not.toHaveBeenCalled();
		expect((screen.getByRole('button', { name: '사용자 및 비밀번호 편집' }) as HTMLButtonElement).disabled).toBe(true);
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(api.patch).not.toHaveBeenCalled();
	});
	it('omits untouched provider secrets, sends revision, and clears newly entered secrets on error', async () => {
		const pending = deferred<unknown>(); api.patch.mockReturnValueOnce(pending.promise);
		render(IamLogin, { session, onDenied: vi.fn() }); await screen.findByText('Corporate SSO');
		await fireEvent.click(screen.getByRole('button', { name: '편집' }));
		expect((screen.getByLabelText('클라이언트 비밀') as HTMLInputElement).value).toBe('');
		await fireEvent.input(screen.getByLabelText('클라이언트 비밀'), { target: { value: 'private-secret' } });
		await fireEvent.click(screen.getByRole('button', { name: '저장' }));
		expect(api.patch.mock.calls[0][1]).toMatchObject({ client_secret: 'private-secret', revision: 3 });
		expect((screen.getByLabelText('클라이언트 비밀') as HTMLInputElement).value).toBe('');
		pending.reject(new Error('provider failed')); await screen.findByText('provider failed');
		api.patch.mockResolvedValue(provider); await fireEvent.click(screen.getByRole('button', { name: '저장' }));
		expect(api.patch.mock.calls[1][1]).not.toHaveProperty('client_secret');
	});
	it('sends only changed provider fields so a name edit does not alter verified security settings', async () => {
		api.patch.mockResolvedValue(provider);
		render(IamLogin, { session, onDenied: vi.fn() }); await screen.findByText('Corporate SSO');
		await fireEvent.click(screen.getByRole('button', { name: '편집' }));
		await fireEvent.input(screen.getByLabelText(/^이름/), { target: { value: 'Renamed SSO' } });
		await fireEvent.click(screen.getByRole('button', { name: '저장' }));
		expect(api.patch.mock.calls[0][1]).toEqual({ revision: 3, name: 'Renamed SSO' });
	});
	it('requires a replacement secret before changing a provider token destination', async () => {
		render(IamLogin, { session, onDenied: vi.fn() }); await screen.findByText('Corporate SSO');
		await fireEvent.click(screen.getByRole('button', { name: '편집' }));
		await fireEvent.input(screen.getByLabelText(/^OIDC 발급자 URL/), { target: { value: 'https://new-issuer.example.com' } });
		expect((screen.getByLabelText(/^클라이언트 비밀/) as HTMLInputElement).required).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: '저장' }));
		expect(api.patch).not.toHaveBeenCalled();
	});
	it('saves both email controls and password/signup flags with current policy revision', async () => {
		api.put.mockResolvedValue(policy); render(IamLogin, { session, onDenied: vi.fn() }); await screen.findByText('Corporate SSO');
		await fireEvent.input(screen.getByLabelText('로그인 허용 이메일 도메인'), { target: { value: 'example.com, research.org' } });
		await fireEvent.input(screen.getByLabelText('회원가입 허용 이메일 도메인'), { target: { value: 'research.org' } });
		await fireEvent.click(screen.getByLabelText('이메일 인증 회원가입 허용'));
		await fireEvent.click(screen.getByRole('button', { name: '로그인 정책 저장' }));
		expect(api.put).toHaveBeenCalledWith('/api/v1/iam/login-policy', { password_enabled: true, signup_enabled: true, allowed_email_domains: ['example.com', 'research.org'], signup_email_domains: ['research.org'], revision: 7 }, 'token', undefined, { replayOnUnauthorized: false });
	});
	it('fences provider deletion through an awaited confirmation after unmount', async () => {
		const decision = deferred<boolean>(); confirmDialog.mockReturnValue(decision.promise);
		const view = render(IamLogin, { session, onDenied: vi.fn() }); await screen.findByText('Corporate SSO');
		await fireEvent.click(screen.getByRole('button', { name: '삭제' })); view.unmount(); decision.resolve(true);
		await Promise.resolve(); expect(api.delete).not.toHaveBeenCalled();
	});
});

describe('project grant and invitation boundaries', () => {
	it('uses the server owner-management ceiling, not manager status or a role name', async () => {
		api.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/members') ? { items: [{ ...member, is_owner: true, is_manager: true }] } : fixture(path)));
		render(IamProjects, { session, onDenied: vi.fn() }); await screen.findByText('Alice');
		expect((screen.getByRole('button', { name: '역할 편집' }) as HTMLButtonElement).disabled).toBe(true);
		expect((screen.getByRole('button', { name: '멤버 제거' }) as HTMLButtonElement).disabled).toBe(true);
		expect(screen.getByText('마지막 유효 소유자 보호')).toBeTruthy();
	});
	it('discards a project response after another project has been selected', async () => {
		const pending = deferred<unknown>();
		api.get.mockImplementation((path: string) => {
			if (path.endsWith('/projects')) return Promise.resolve({ items: [project, { ...project, id: 'project-b', name: 'Project B' }] });
			if (path.includes('/project-a/members')) return pending.promise;
			if (path.includes('/project-b/members')) return Promise.resolve({ items: [{ ...member, user_id: 'bob', username: 'Bob' }] });
			return Promise.resolve(fixture(path));
		});
		render(IamProjects, { session, onDenied: vi.fn() });
		await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/v1/iam/projects/project-a/members', 'token', undefined, { refresh: true }));
		await fireEvent.change(screen.getByLabelText('프로젝트'), { target: { value: 'project-b' } }); await screen.findByText('Bob');
		pending.resolve({ items: [member] }); await Promise.resolve();
		expect(screen.queryByText('Alice')).toBeNull();
	});
	it('assigns actual server role IDs and never a hardcoded role-name grant', async () => {
		api.put.mockResolvedValue({}); render(IamProjects, { session, onDenied: vi.fn() }); await screen.findByText('Alice');
		await fireEvent.click(screen.getByRole('button', { name: '역할 편집' }));
		await fireEvent.click(screen.getByRole('button', { name: '역할 저장' }));
		expect(api.put).toHaveBeenCalledWith('/api/v1/iam/projects/project-a/members/user-a/roles', { role_ids: ['role-a'] }, 'token', undefined, { replayOnUnauthorized: false });
	});
	it('sends selected invitation role IDs and publishes email delivery failures without success', async () => {
		api.post.mockRejectedValue(new Error('smtp delivery failed'));
		render(IamInvitations, { session, onDenied: vi.fn() }); await screen.findByText('invitee@example.com');
		await fireEvent.input(screen.getByLabelText(/^이메일/), { target: { value: 'new@example.com' } });
		await fireEvent.change(screen.getByLabelText('추가 프로젝트 (선택)'), { target: { value: 'project-a' } });
		await waitFor(() => expect((screen.getByRole('button', { name: '초대 역할 선택' }) as HTMLButtonElement).disabled).toBe(false));
		await fireEvent.click(screen.getByRole('button', { name: '초대 역할 선택' }));
		await fireEvent.click(screen.getByRole('checkbox', { name: /custom_reader/ }));
		await fireEvent.click(screen.getByRole('button', { name: '역할 저장' }));
		await fireEvent.click(screen.getByRole('button', { name: '초대 이메일 발송' }));
		await screen.findByText('smtp delivery failed'); expect(screen.queryByText('초대 이메일을 발송했습니다.')).toBeNull();
		expect(api.post).toHaveBeenCalledWith('/api/v1/iam/invitations', { email: 'new@example.com', project_id: 'project-a', role_ids: ['role-a'] }, 'token', undefined, { replayOnUnauthorized: false });
	});
	it('sends domain membership invitations without requiring an additional project or role catalog', async () => {
		api.post.mockResolvedValue(invitation);
		render(IamInvitations, { session, onDenied: vi.fn() }); await screen.findByText('invitee@example.com');
		expect(screen.queryByRole('button', { name: '초대 역할 선택' })).toBeNull();
		await fireEvent.input(screen.getByLabelText(/^이메일/), { target: { value: 'joined@example.com' } });
		await fireEvent.click(screen.getByRole('button', { name: '초대 이메일 발송' }));
		expect(api.post).toHaveBeenCalledWith('/api/v1/iam/invitations', { email: 'joined@example.com' }, 'token', undefined, { replayOnUnauthorized: false });
		expect(api.get.mock.calls.some(([path]) => String(path).endsWith('/assignable-roles'))).toBe(false);
	});
	it('makes only pending invitations revocable and fences confirmation after unmount', async () => {
		api.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/invitations') ? { items: [invitation, { ...invitation, id: 5, email: 'done@example.com', status: 'accepted' }] } : fixture(path)));
		const decision = deferred<boolean>(); confirmDialog.mockReturnValue(decision.promise);
		const view = render(IamInvitations, { session, onDenied: vi.fn() }); await screen.findByText('done@example.com');
		const done = screen.getByText('done@example.com').closest('tr')!;
		expect((within(done).getByRole('button', { name: '초대 취소' }) as HTMLButtonElement).disabled).toBe(true);
		const pending = screen.getByText('invitee@example.com').closest('tr')!;
		await fireEvent.click(within(pending).getByRole('button', { name: '초대 취소' })); view.unmount(); decision.resolve(true);
		await Promise.resolve(); expect(api.delete).not.toHaveBeenCalled();
	});
});

describe('partial enrollment recovery and localized refusals', () => {
	it('reverts a partial operation only after confirmation and reports success after the verified 204', async () => {
		const operation = { ...invitation, id: 9, kind: 'managed_create', user_id: 'new-user', recovery_required: true, status: 'recovery_required', email: 'partial@example.com' };
		api.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/operations') ? { items: [operation] } : fixture(path)));
		api.delete.mockResolvedValue(undefined);
		render(IamRecovery, { session, onDenied: vi.fn() }); await screen.findByText('partial@example.com');
		expect(screen.getByText('복구 필요')).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: '되돌리기' }));
		await screen.findByText('작업을 되돌렸습니다.');
		expect(api.delete).toHaveBeenCalledWith('/api/v1/iam/operations/9', 'token', undefined, { replayOnUnauthorized: false });
	});
	it('keeps an unverified compensation failure visible without claiming recovery', async () => {
		const operation = { ...invitation, id: 9, kind: 'invite', user_id: null, recovery_required: true, status: 'granting', email: 'partial@example.com' };
		api.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/operations') ? { items: [operation] } : fixture(path)));
		api.delete.mockRejectedValue(Object.assign(new ApiError(503, 'native unavailable'), { code: 'unavailable' }));
		render(IamRecovery, { session, onDenied: vi.fn() }); await screen.findByText('partial@example.com');
		await fireEvent.click(screen.getByRole('button', { name: '되돌리기' }));
		await screen.findByText('서비스를 일시적으로 사용할 수 없습니다. 잠시 후 다시 시도하세요.');
		expect(screen.queryByText('작업을 되돌렸습니다.')).toBeNull();
		expect(screen.getByText('partial@example.com')).toBeTruthy();
	});
	it('shows a localized last-login-method refusal instead of backend English text', async () => {
		api.patch.mockRejectedValue(Object.assign(new ApiError(409, "This is the domain's last usable login method"), { code: 'last_login_method' }));
		render(IamLogin, { session, onDenied: vi.fn() }); await screen.findByText('Corporate SSO');
		await fireEvent.click(screen.getByRole('button', { name: '비활성화' }));
		await screen.findByText('사용 가능한 마지막 로그인 방법입니다. 먼저 비밀번호 로그인을 켜거나 다른 검증된 제공자를 준비하세요.');
		expect(screen.queryByText("This is the domain's last usable login method")).toBeNull();
	});
});
