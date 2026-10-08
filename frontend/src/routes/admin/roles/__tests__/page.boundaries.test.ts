import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import { tick } from 'svelte';
import type { AuthState } from '$lib/stores/auth';
import type { ManagedRole } from '$lib/components/admin/roles/types';

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: mocks, ApiError: class ApiError extends Error {} }));
vi.mock('$lib/stores/auth', () => ({
	auth: writable<AuthState>({ token: null, refreshToken: null, accessExpiresAt: null, userId: null, username: null,
		projectId: null, projectName: null, availableProjects: [], roles: [], isSystemAdmin: false, federated: false }),
	authReady: writable(true), projectSwitching: writable(false)
}));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({ createAutoRefresh: () => ({ active: false, intervalSeconds: 60, intervalOptions: [30, 60] }) }));

vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: vi.fn() }));
import { auth, authReady, projectSwitching } from '$lib/stores/auth';
import Page from '../+page.svelte';
import { confirmDialog } from '$lib/stores/confirm.svelte';

const admin: AuthState = { token: 'admin-token', refreshToken: null, accessExpiresAt: null, userId: 'admin', username: 'admin',
	projectId: 'project-a', projectName: 'A', availableProjects: [], roles: ['admin'], isSystemAdmin: true, federated: false };
function role(id: string, changes: Partial<ManagedRole> = {}): ManagedRole {
	return { id, name: id, description: '', domain_id: null, protected: false, system_only: false,
		implied_role_ids: [], inherited_role_ids: [], parent_role_ids: [], ...changes };
}

beforeEach(() => {
	vi.resetAllMocks();
	auth.set(admin); authReady.set(true); projectSwitching.set(false);
	vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('role dashboard authorization and stale responses', () => {
	it('does not fetch or expose catalog/creation controls for ordinary or unverified auth', async () => {
		auth.set({ ...admin, isSystemAdmin: false });
		render(Page);
		await screen.findByText('시스템 관리자 권한이 필요합니다');
		expect(screen.queryByRole('button', { name: '역할 만들기' })).toBeNull();
		expect(mocks.get).not.toHaveBeenCalled();
		authReady.set(false); auth.set(admin);
		await tick();
		expect(screen.queryByRole('searchbox', { name: '역할 검색' })).toBeNull();
		expect(mocks.get).not.toHaveBeenCalled();
	});

	it('clears open sensitive details on demotion and ignores an older outstanding catalog response', async () => {
		const pending = Promise.withResolvers<ManagedRole[]>();
		mocks.get.mockResolvedValueOnce([role('secret-role')]).mockReturnValueOnce(pending.promise);
		render(Page);
		await screen.findAllByRole('button', { name: 'secret-role 역할 상세' });
		await fireEvent.click(screen.getAllByRole('button', { name: 'secret-role 역할 상세' })[0]);
		await screen.findByRole('dialog', { name: 'secret-role 역할 상세' });
		await fireEvent.click(screen.getByTitle('지금 새로고침'));
		auth.set({ ...admin, isSystemAdmin: false });
		await tick();
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(document.body.textContent).not.toContain('secret-role');
		pending.resolve([role('late-secret')]);
		await tick(); await tick();
		expect(document.body.textContent).not.toContain('late-secret');
		expect(screen.getByText('시스템 관리자 권한이 필요합니다')).toBeTruthy();
	});

	it('never repaints a new project scope with an old successful response', async () => {
		const old = Promise.withResolvers<ManagedRole[]>();
		mocks.get.mockReturnValueOnce(old.promise).mockResolvedValueOnce([role('project-b-role')]);
		render(Page);
		await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(1));
		auth.set({ ...admin, projectId: 'project-b' });
		await screen.findAllByRole('button', { name: 'project-b-role 역할 상세' });
		old.resolve([role('project-a-secret')]);
		await tick(); await tick();
		expect(document.body.textContent).not.toContain('project-a-secret');
		expect(screen.getAllByRole('button', { name: 'project-b-role 역할 상세' }).length).toBeGreaterThan(0);
	});

	it('keeps search/view controls and old details after refresh failure, but fences mutations until recovery', async () => {
		mocks.get.mockResolvedValueOnce([role('custom-role')]).mockRejectedValueOnce(new Error('provider unavailable'));
		render(Page);
		await screen.findAllByRole('button', { name: 'custom-role 역할 상세' });
		await fireEvent.click(screen.getAllByRole('button', { name: 'custom-role 역할 상세' })[0]);
		await fireEvent.click(screen.getByTitle('지금 새로고침'));
		await screen.findByText(/provider unavailable/);
		const detail = within(screen.getByRole('dialog', { name: 'custom-role 역할 상세' }));
		expect((detail.getByRole('button', { name: '이름·설명 편집' }) as HTMLButtonElement).disabled).toBe(true);
		expect((detail.getByRole('button', { name: '역할 삭제' }) as HTMLButtonElement).disabled).toBe(true);
		expect(screen.getByRole('searchbox', { name: '역할 검색' })).toBeTruthy();
		expect(screen.getByRole('button', { name: '상속 트리' })).toBeTruthy();
		mocks.get.mockResolvedValueOnce([role('custom-role')]);
		await fireEvent.click(screen.getByRole('button', { name: '다시 시도' }));
		await waitFor(() => expect((detail.getByRole('button', { name: '이름·설명 편집' }) as HTMLButtonElement).disabled).toBe(false));
	});

	it('does not re-open a modal or publish mutation success after auth identity changes', async () => {
		const pending = Promise.withResolvers<ManagedRole>();
		mocks.get.mockResolvedValue([]); mocks.post.mockReturnValueOnce(pending.promise);
		render(Page);
		await waitFor(() => expect((screen.getByRole('button', { name: '역할 만들기' }) as HTMLButtonElement).disabled).toBe(false));
		await fireEvent.click(screen.getByRole('button', { name: '역할 만들기' }));
		await fireEvent.input(screen.getByRole('textbox', { name: /^영역/ }), { target: { value: 'new' } });
		await fireEvent.input(screen.getByRole('textbox', { name: /^등급/ }), { target: { value: 'role' } });
		await fireEvent.click(screen.getByRole('button', { name: '만들기' }));
		auth.set({ ...admin, token: 'other-admin-token', userId: 'other-admin' });
		await tick();
		pending.resolve(role('new-role'));
		await tick(); await tick();
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(screen.queryByText('역할을 만들었습니다.')).toBeNull();
		expect(screen.queryByText('new-role')).toBeNull();
	});

	it('shows disabled reasons for privilege aliases and preserves checked removals separately from indirect inheritance', async () => {
		const roles = [role('admin', { protected: true, system_only: true }), role('member', { protected: true, implied_role_ids: ['custom'], inherited_role_ids: ['custom', 'reader'] }),
			role('custom', { implied_role_ids: ['reader'], inherited_role_ids: ['reader'] }), role('reader', { protected: true }),
			role('admin-alias', { system_only: true, implied_role_ids: ['admin'], inherited_role_ids: ['admin'] })];
		mocks.get.mockResolvedValue(roles);
		render(Page);
		await screen.findAllByRole('button', { name: 'member 역할 상세' });
		await fireEvent.click(screen.getAllByRole('button', { name: 'member 역할 상세' })[0]);
		const detail = within(screen.getByRole('dialog', { name: 'member 역할 상세' }));
		expect((detail.getByRole('checkbox', { name: 'admin-alias 직접 상속' }) as HTMLInputElement).disabled).toBe(true);
		expect(detail.getAllByText(/선택 불가:.*높은/).length).toBeGreaterThan(0);
		expect((detail.getByRole('checkbox', { name: 'custom 직접 상속' }) as HTMLInputElement).checked).toBe(true);
		expect((detail.getByRole('checkbox', { name: 'reader 직접 상속' }) as HTMLInputElement).checked).toBe(false);
		expect(detail.getByText('간접 상속됨 · 직접 연결은 없음')).toBeTruthy();
		expect(detail.getByRole('heading', { name: '간접 상속 (1) · 읽기 전용' })).toBeTruthy();
	});

	it('preserves underscore roles and applies presets only after explicit confirmation, then reads the actual DAG', async () => {
		const confirmed = Promise.withResolvers<boolean>();
		vi.mocked(confirmDialog).mockReturnValueOnce(confirmed.promise);
		const existing = role('owner-id', { name: 'project_owner' });
		const fresh = role('chat-id', { name: 'lumen-chat_user' });
		let catalogs = 0;
		mocks.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/presets') ? {
			roles: [{ name: fresh.name, description: 'chat', area: 'lumen-chat', grade: 'user', parent: 'lumen_user' }], project_roles: [], implications: [{ prior: 'lumen_user', implied: fresh.name }]
		} : ++catalogs === 1 ? [existing] : [existing, fresh]));
		mocks.post.mockResolvedValue({ created_roles: [fresh.name], created_implications: [], roles: [existing, fresh] });
		render(Page);
		await screen.findAllByRole('button', { name: 'project_owner 역할 상세' });
		await fireEvent.click(screen.getByRole('button', { name: '역할 프리셋 미리보기' }));
		const preview = await screen.findByRole('dialog', { name: '역할 프리셋 미리보기' });
		await fireEvent.click(within(preview).getByRole('button', { name: '프리셋 적용' }));
		expect(mocks.post).not.toHaveBeenCalled();
		expect(confirmDialog).toHaveBeenCalledTimes(1);
		confirmed.resolve(true);
		await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/v1/admin/roles/presets/apply', {}, 'admin-token', 'project-a'));
		await waitFor(() => expect(catalogs).toBe(2));
		await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
		expect(document.body.textContent).toContain('project_owner');
		expect(document.body.textContent).toContain('lumen-chat_user');
		vi.mocked(confirmDialog).mockResolvedValueOnce(true);
		mocks.post.mockResolvedValueOnce({ created_roles: [], created_implications: [], roles: [existing, fresh] });
		await fireEvent.click(screen.getByRole('button', { name: '역할 프리셋 미리보기' }));
		await fireEvent.click(within(await screen.findByRole('dialog', { name: '역할 프리셋 미리보기' })).getByRole('button', { name: '프리셋 적용' }));
		await waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(2));
		await waitFor(() => expect(catalogs).toBe(3));
		await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
		expect(document.body.textContent).toContain('project_owner');
		expect(document.body.textContent).toContain('lumen-chat_user');
	});
});
