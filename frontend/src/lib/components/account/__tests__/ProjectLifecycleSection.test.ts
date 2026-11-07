import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
const { api, confirmDialog, projectNames, continueDeletion } = vi.hoisted(() => ({
	api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
	confirmDialog: vi.fn(), projectNames: { scope: vi.fn(), invalidate: vi.fn() }, continueDeletion: vi.fn()
}));
vi.mock('$lib/api/client', () => ({ api, ApiError: class ApiError extends Error { constructor(public status: number, message: string) { super(message); } } }));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token', userId: 'actor', projectId: 'project-a', domainId: 'domain-a', isSystemAdmin: false }),
	logoutInProgress: writable(false), projectSwitching: writable(false)
}));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog }));
vi.mock('$lib/stores/projectNames', () => ({ projectNames }));
vi.mock('$lib/utils/projectDeletionContinuation', () => ({ continueAfterProjectDeletion: continueDeletion }));
import { ApiError } from '$lib/api/client';
import ProjectLifecycleSection from '../ProjectLifecycleSection.svelte';
const project = { id: 'project-a', name: 'Project A', description: '', domain_id: 'domain-a', enabled: true, created_at: null };
const joined = { id: 'joined', name: 'Joined user', email: 'joined@example.com', domain_id: 'foreign-home', enabled: true };
const ownership = { project_id: 'project-a', status: 'unique', owner_user_id: 'actor', owners: [{ user_id: 'actor', name: 'Current owner', source: 'direct' }], can_transfer: true, can_delete: true, transfer_operation: null };
const resource = { kind: 'child_projects', service: 'identity', status: 'ok', count: 0, samples: [], reason: null };
const proof = { project_id: 'project-a', checked_at: '2026-10-16T00:00:00Z', can_delete: true, resources: [resource] };
let valid = true; let allowed = true;
const session = { token: () => 'token', userId: 'actor', domainId: 'domain-a', isCurrent: () => valid, canSubmit: () => valid && allowed };
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(yes => { resolve = yes; }); return { promise, resolve }; }
function fixture(path: string) {
	if (path.endsWith('/eligible-users')) return [joined];
	if (path.endsWith('/ownership')) return ownership;
	if (path.endsWith('/deletion-check')) return proof;
	if (path.endsWith('/iam/users')) return { items: [{ ...joined, protected: false }] };
	throw new Error(`Unexpected path: ${path}`);
}
function lifecycle() { return render(ProjectLifecycleSection, { session, project, callerProject: 'project-a', onChanged: vi.fn(), onDeleted: vi.fn() }); }
afterEach(cleanup);
beforeEach(() => { vi.resetAllMocks(); valid = true; allowed = true; api.get.mockImplementation((path: string) => Promise.resolve(fixture(path))); confirmDialog.mockResolvedValue(true); });

describe('explicit project ownership and safe deletion', () => {
	it('only offers the original target after an explicitly settled missing-owner transfer', async () => {
		const operation = { id: 'operation-id', project_id: 'project-a', domain_id: 'domain-a', from_user_id: 'actor', to_user_id: joined.id, status: 'settled', stage: 'reconciled' };
		api.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/ownership') ? { ...ownership, status: 'missing', owner_user_id: null, owners: [], can_delete: false, transfer_operation: operation } : path.endsWith('/eligible-users') ? [joined, { ...joined, id: 'another', name: 'Another user' }] : fixture(path)));
		api.post.mockResolvedValue({ ...ownership, owner_user_id: joined.id, transfer_operation: { ...operation, status: 'completed' } });
		lifecycle(); await screen.findByText(/시스템 관리자가 이전 네이티브 요청의 종료를 확인했습니다/);
		expect((screen.getByLabelText('새 소유자') as HTMLSelectElement).value).toBe(joined.id);
		expect(screen.queryByRole('option', { name: /Another user/ })).toBeNull(); expect(api.post).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: '소유권 이전' }));
		expect(api.post).toHaveBeenCalledWith('/api/v1/projects/project-a/ownership-transfer', { user_id: joined.id }, 'token', 'project-a', { replayOnUnauthorized: false });
	});
	it('keeps an unknown native transfer unresolved even after a fresh ownership read', async () => {
		api.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/ownership') ? { ...ownership, can_transfer: false, can_delete: false, transfer_operation: { id: 'unknown-operation', project_id: 'project-a', domain_id: 'domain-a', from_user_id: 'actor', to_user_id: joined.id, status: 'unknown', stage: 'revoke_unknown' } } : fixture(path)));
		lifecycle(); await screen.findByText(/시스템 관리자가 원래 요청이 모두 종료되었음을/);
		expect(screen.queryByLabelText('새 소유자')).toBeNull(); expect((screen.getByRole('button', { name: '프로젝트 삭제' }) as HTMLButtonElement).disabled).toBe(true);
		expect(api.post).not.toHaveBeenCalled();
	});
	it('does not publish a transfer result after its session owner retires', async () => {
		const pending = deferred<unknown>(); api.post.mockReturnValue(pending.promise);
		const onChanged = vi.fn();
		render(ProjectLifecycleSection, { session, project, callerProject: 'project-a', onChanged, onDeleted: vi.fn() });
		await screen.findByRole('option', { name: 'Joined user · joined@example.com' });
		await fireEvent.change(screen.getByLabelText('새 소유자'), { target: { value: joined.id } });
		await fireEvent.click(screen.getByRole('button', { name: '소유권 이전' }));
		valid = false; pending.resolve({ ...ownership, owner_user_id: joined.id });
		await Promise.resolve(); await Promise.resolve(); expect(onChanged).not.toHaveBeenCalled();
	});
	it('transfers only to a current joined user even when its home domain is foreign, without mutation replay', async () => {
		api.post.mockResolvedValue({ ...ownership, owner_user_id: joined.id });
		lifecycle(); await screen.findByRole('option', { name: 'Joined user · joined@example.com' });
		await fireEvent.change(screen.getByLabelText('새 소유자'), { target: { value: joined.id } });
		await fireEvent.click(screen.getByRole('button', { name: '소유권 이전' }));
		expect(api.post).toHaveBeenCalledWith('/api/v1/projects/project-a/ownership-transfer', { user_id: 'joined' }, 'token', 'project-a', { replayOnUnauthorized: false });
	});
	it.each(['scope', 'submission', 'unmount'])('fences transfer through awaited confirmation on %s changes', async (change) => {
		const decision = deferred<boolean>(); confirmDialog.mockReturnValue(decision.promise);
		const view = lifecycle(); await screen.findByRole('option', { name: 'Joined user · joined@example.com' });
		await fireEvent.change(screen.getByLabelText('새 소유자'), { target: { value: joined.id } });
		await fireEvent.click(screen.getByRole('button', { name: '소유권 이전' }));
		if (change === 'scope') valid = false; else if (change === 'submission') allowed = false; else view.unmount();
		decision.resolve(true); await Promise.resolve(); expect(api.post).not.toHaveBeenCalled();
	});
	it('requires fresh explicit observation before another transfer after an uncertain write', async () => {
		api.post.mockRejectedValue(new Error('native response unavailable'));
		lifecycle(); await screen.findByRole('option', { name: 'Joined user · joined@example.com' });
		await fireEvent.change(screen.getByLabelText('새 소유자'), { target: { value: joined.id } });
		await fireEvent.click(screen.getByRole('button', { name: '소유권 이전' }));
		await screen.findByText('native response unavailable');
		expect((screen.getByRole('button', { name: '소유권 이전' }) as HTMLButtonElement).disabled).toBe(true);
		expect(api.post).toHaveBeenCalledTimes(1);
	});
	it('shows legacy ownership conflicts explicitly rather than enabling implicit owner repair', async () => {
		api.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/ownership') ? { ...ownership, status: 'conflict', owner_user_id: null, can_transfer: false, can_delete: false } : fixture(path)));
		lifecycle(); await screen.findByText(/기존 소유권 충돌/);
		expect(screen.queryByLabelText('새 소유자')).toBeNull();
		expect((screen.getByRole('button', { name: '프로젝트 삭제' }) as HTMLButtonElement).disabled).toBe(true);
	});
	it.each([{ status: 'ok', count: 1 }, { status: 'unavailable', count: null }])('blocks deletion when the proof contains $status / $count', async (row) => {
		api.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/deletion-check') ? { ...proof, resources: [{ ...resource, ...row }] } : fixture(path)));
		lifecycle(); await fireEvent.click(await screen.findByRole('button', { name: '프로젝트 삭제' }));
		await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/v1/projects/project-a/deletion-check', 'token', 'project-a', { refresh: true, signal: expect.any(AbortSignal) }));
		const dialog = screen.getByRole('dialog'); await within(dialog).findByText('하위 프로젝트');
		expect((within(dialog).getByRole('button', { name: '삭제' }) as HTMLButtonElement).disabled).toBe(true);
		expect(api.delete).not.toHaveBeenCalled();
	});
	it('uses the user deletion endpoint and displays the backend final resource refusal without replay', async () => {
		api.delete.mockRejectedValue(new ApiError(409, JSON.stringify({ code: 'project_has_resources', check: { ...proof, can_delete: false, resources: [{ ...resource, count: 1 }] } })));
		lifecycle(); await fireEvent.click(await screen.findByRole('button', { name: '프로젝트 삭제' }));
		const dialog = screen.getByRole('dialog'); const remove = within(dialog).getByRole('button', { name: '삭제' }) as HTMLButtonElement;
		await waitFor(() => expect(remove.disabled).toBe(false)); await fireEvent.click(remove);
		expect(api.delete).toHaveBeenCalledWith('/api/v1/projects/project-a', 'token', 'project-a', { replayOnUnauthorized: false });
		await waitFor(() => expect(remove.disabled).toBe(true)); expect(api.delete).toHaveBeenCalledTimes(1);
	});
	it('hands a successful active deletion to the fenced scope continuation', async () => {
		api.delete.mockResolvedValue(undefined);
		lifecycle(); await fireEvent.click(await screen.findByRole('button', { name: '프로젝트 삭제' }));
		const dialog = screen.getByRole('dialog'); const remove = within(dialog).getByRole('button', { name: '삭제' }) as HTMLButtonElement;
		await waitFor(() => expect(remove.disabled).toBe(false)); await fireEvent.click(remove);
		await waitFor(() => expect(continueDeletion).toHaveBeenCalledWith('project-a', 'domain-a'));
	});
	it('offers ownership transfer but no deletion when the host hides deletion', async () => {
		render(ProjectLifecycleSection, { session, project, callerProject: 'project-a', showDelete: false, onChanged: vi.fn(), onDeleted: vi.fn() });
		await screen.findByLabelText('새 소유자');
		expect(screen.queryByRole('button', { name: '프로젝트 삭제' })).toBeNull();
		expect(screen.queryByText(/Default는 삭제할 수 없습니다/)).toBeNull();
	});
});
