import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { get } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '$lib/api/client';
import { auth, logoutInProgress, projectSwitching } from '$lib/stores/auth';

const mocks = vi.hoisted(() => ({ get: vi.fn(), delete: vi.fn(), scope: vi.fn(), invalidate: vi.fn() }));
vi.mock('$lib/api/client', () => ({
	api: { get: mocks.get, delete: mocks.delete },
	ApiError: class ApiError extends Error {
		status: number;
		constructor(status: number, message: string) { super(message); this.status = status; }
	},
}));
vi.mock('$lib/stores/projectNames', () => ({ projectNames: { scope: mocks.scope, invalidate: mocks.invalidate } }));

import AdminProjectDeleteModal from '../AdminProjectDeleteModal.svelte';

const initialAuth = get(auth);
const project = { id: 'p1', name: 'demo', description: '', enabled: true, domain_id: null, created_at: null };
const otherProject = { ...project, id: 'p2', name: 'other' };
const emptyResource = { kind: 'instances', service: 'compute', status: 'ok', count: 0, samples: [], reason: null };
const remainingResource = { ...emptyResource, count: 1, samples: [{ id: 'vm-1', name: 'web-1', status: 'SHUTOFF' }] };
const unavailableResource = { ...emptyResource, status: 'unavailable', count: null, reason: 'resource_check_failed' };
const emptyReport = (target = project.id) => ({
	project_id: target, checked_at: '2026-10-08T00:00:00Z', can_delete: true, resources: [{ ...emptyResource }],
});
const blockedReport = () => ({ ...emptyReport(), can_delete: false, resources: [remainingResource] });
const unknownReport = () => ({ ...emptyReport(), can_delete: false, resources: [unavailableResource] });
const deleteButton = () => screen.getByRole('button', { name: '삭제' }) as HTMLButtonElement;
const recheckButton = () => screen.getByRole('button', { name: '리소스 다시 확인' }) as HTMLButtonElement;
function openModal() {
	const props = { project, onClose: vi.fn(), onSuccess: vi.fn() };
	return { ...render(AdminProjectDeleteModal, props), props };
}
async function waitUntilReady() {
	await waitFor(() => expect(deleteButton().disabled).toBe(false));
}

beforeEach(() => {
	vi.resetAllMocks();
	mocks.get.mockResolvedValue(emptyReport());
	mocks.delete.mockResolvedValue({ status: 'deleted' });
	mocks.scope.mockImplementation((token: string, projectId: string) => ({ token, projectId }));
	logoutInProgress.set(false);
	projectSwitching.set(false);
	auth.set({ ...initialAuth, token: 'token', userId: 'admin', projectId: 'admin-project', isSystemAdmin: true });
});
afterEach(() => {
	cleanup();
	auth.set(initialAuth);
	logoutInProgress.set(false);
	projectSwitching.set(false);
});

describe('AdminProjectDeleteModal resource inspection', () => {
	it('opens with a fresh abortable check and never enables deletion while loading', async () => {
		const pending = Promise.withResolvers<unknown>();
		mocks.get.mockReturnValueOnce(pending.promise);
		openModal();
		await screen.findByText('프로젝트 리소스를 확인하는 중...');
		expect(deleteButton().disabled).toBe(true);
		expect(recheckButton().disabled).toBe(true);
		expect(screen.queryByText(/확인 가능한 프로젝트 리소스가 모두 비어/)).toBeNull();
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/admin/projects/p1/deletion-check', 'token', 'admin-project', {
			refresh: true, signal: expect.any(AbortSignal),
		});
		await fireEvent.click(deleteButton());
		expect(mocks.delete).not.toHaveBeenCalled();
		pending.resolve(emptyReport());
		await waitUntilReady();
		expect(await screen.findByText(/삭제 요청 시 서버가 리소스를 다시 확인/)).toBeTruthy();
	});

	it('shows positive counts and bounded names/IDs and blocks deletion', async () => {
		mocks.get.mockResolvedValue({ ...blockedReport(), resources: [{
			...remainingResource, count: 8,
			samples: Array.from({ length: 8 }, (_, i) => ({ id: `vm-${i}`, name: `web-${i}`, payload: 'not-for-display' })),
		}] });
		openModal();
		const list = await screen.findByRole('list', { name: '프로젝트 리소스 확인 결과' });
		expect(within(list).getByText('인스턴스')).toBeTruthy();
		expect(within(list).getByText('8개')).toBeTruthy();
		expect(within(list).getByText(/web-0/)).toBeTruthy();
		expect(within(list).getByText('vm-4')).toBeTruthy();
		expect(within(list).queryByText('vm-5')).toBeNull();
		expect(screen.queryByText('not-for-display')).toBeNull();
		expect(deleteButton().disabled).toBe(true);
	});

	it('does not render secret contents or names from an inventory sample', async () => {
		mocks.get.mockResolvedValue({ ...blockedReport(), resources: [{ ...remainingResource, kind: 'secrets', service: 'key_manager',
			samples: [{ id: 'secret-uuid', name: 'sensitive-name', payload: 'secret-value' }] }] });
		openModal();
		expect(await screen.findByText('secret-uuid')).toBeTruthy();
		expect(screen.queryByText(/sensitive-name|secret-value/)).toBeNull();
	});

	it('shows unavailable inventory as unknown, not zero, and supports a fresh recheck', async () => {
		mocks.get.mockResolvedValueOnce(unknownReport()).mockResolvedValueOnce(emptyReport());
		openModal();
		const list = await screen.findByRole('list', { name: '프로젝트 리소스 확인 결과' });
		expect(within(list).getAllByText(/확인 불가/).length).toBeGreaterThan(0);
		expect(within(list).queryByText('0개')).toBeNull();
		expect(deleteButton().disabled).toBe(true);
		await fireEvent.click(recheckButton());
		await waitUntilReady();
		expect(mocks.get).toHaveBeenCalledTimes(2);
		expect(mocks.get.mock.calls[1][3]).toMatchObject({ refresh: true });
	});

	it('explains administrator authority and target-project verification blockers without showing zero', async () => {
		mocks.get.mockResolvedValue({ ...unknownReport(), resources: [
			{ ...unavailableResource, kind: 'object_containers', service: 'object_store', reason: 'project_scope_unverified' },
			{ ...unavailableResource, reason: 'admin_authority_unverified' },
		] });
		openModal();
		const list = await screen.findByRole('list', { name: '프로젝트 리소스 확인 결과' });
		expect(within(list).getByText(/관리자 범위에서 확인 불가/).textContent).toContain('대상 프로젝트에 admin 역할이 있는 관리자 계정');
		expect(within(list).getByText(/OpenStack admin 권한을 확인할 수 없음/).textContent).toContain('관리자 프로젝트로 전환');
		expect(within(list).queryByText('0개')).toBeNull();
		expect(deleteButton().disabled).toBe(true);
		await fireEvent.click(deleteButton());
		expect(mocks.delete).not.toHaveBeenCalled();
	});

	it('displays failed initial inspection with an actionable retry', async () => {
		mocks.get.mockRejectedValueOnce(new Error('connection failed')).mockResolvedValueOnce(emptyReport());
		openModal();
		expect(await screen.findByRole('alert')).toHaveProperty('textContent', expect.stringContaining('리소스 확인에 실패했습니다'));
		expect(deleteButton().disabled).toBe(true);
		await fireEvent.click(recheckButton());
		await waitUntilReady();
	});

	it('uses safe fallback labels for unknown kinds/services', async () => {
		mocks.get.mockResolvedValue({ ...blockedReport(), resources: [{ ...remainingResource, kind: 'future_kind', service: 'future_service' }] });
		openModal();
		expect(await screen.findByText('기타 리소스')).toBeTruthy();
		expect(screen.getByText('기타 서비스')).toBeTruthy();
		expect(deleteButton().disabled).toBe(true);
	});

	it('distinguishes confirmed absent optional services from failed inspection', async () => {
		mocks.get.mockResolvedValue({ ...emptyReport(), resources: [emptyResource, {
			...unavailableResource, kind: 'shares', service: 'share', status: 'skipped', reason: 'service_not_present',
		}] });
		openModal();
		await waitUntilReady();
		expect(screen.getByText('서비스 미설치')).toBeTruthy();
	});

	it.each([
		['different target', { ...emptyReport(), project_id: 'wrong' }],
		['missing inventory', { ...emptyReport(), resources: [] }],
		['positive forged can_delete', { ...emptyReport(), resources: [remainingResource] }],
		['unknown forged can_delete', { ...emptyReport(), resources: [unavailableResource] }],
		['unknown status', { ...emptyReport(), resources: [{ ...emptyResource, status: 'unknown' }] }],
		['unexplained skip', { ...emptyReport(), resources: [{ ...unavailableResource, status: 'skipped', reason: 'unknown' }] }],
	])('fails closed for %s', async (_label, value) => {
		mocks.get.mockResolvedValue(value);
		openModal();
		await waitFor(() => expect(screen.queryByText('프로젝트 리소스를 확인하는 중...')).toBeNull());
		expect(deleteButton().disabled).toBe(true);
	});

	it('disables deletion immediately during refresh rather than reusing the old empty report', async () => {
		const refresh = Promise.withResolvers<unknown>();
		mocks.get.mockResolvedValueOnce(emptyReport()).mockReturnValueOnce(refresh.promise);
		openModal();
		await waitUntilReady();
		await fireEvent.click(recheckButton());
		expect(deleteButton().disabled).toBe(true);
		refresh.resolve(blockedReport());
		await screen.findByText('vm-1');
		expect(deleteButton().disabled).toBe(true);
	});

	it('aborts and fences a late report when the modal closes', async () => {
		const pending = Promise.withResolvers<unknown>();
		mocks.get.mockReturnValueOnce(pending.promise);
		const view = openModal();
		await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(1));
		const signal = mocks.get.mock.calls[0][3].signal as AbortSignal;
		await fireEvent.keyDown(document, { key: 'Escape' });
		expect(view.props.onClose).toHaveBeenCalledOnce();
		expect(signal.aborted).toBe(true);
		await view.rerender({ ...view.props, project: null });
		pending.resolve(emptyReport());
		await tick();
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(mocks.delete).not.toHaveBeenCalled();
	});

	it('ignores a late old-target report while the new target check is pending', async () => {
		const first = Promise.withResolvers<unknown>();
		const second = Promise.withResolvers<unknown>();
		mocks.get.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
		const view = openModal();
		await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(1));
		const firstSignal = mocks.get.mock.calls[0][3].signal as AbortSignal;
		await view.rerender({ ...view.props, project: otherProject });
		expect(firstSignal.aborted).toBe(true);
		first.resolve(emptyReport());
		await tick();
		expect(deleteButton().disabled).toBe(true);
		expect(screen.queryByText(/확인 가능한 프로젝트 리소스가 모두 비어/)).toBeNull();
		second.resolve(emptyReport('p2'));
		await waitUntilReady();
	});

	it.each(['token', 'project', 'user', 'logout', 'switching', 'admin'])('fences inspection on %s auth scope changes', async (change) => {
		const first = Promise.withResolvers<unknown>();
		const second = Promise.withResolvers<unknown>();
		mocks.get.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
		openModal();
		await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(1));
		const signal = mocks.get.mock.calls[0][3].signal as AbortSignal;
		if (change === 'token') auth.update((value) => ({ ...value, token: 'new-token' }));
		if (change === 'project') auth.update((value) => ({ ...value, projectId: 'new-admin-project' }));
		if (change === 'user') auth.update((value) => ({ ...value, userId: 'other-user' }));
		if (change === 'logout') logoutInProgress.set(true);
		if (change === 'switching') projectSwitching.set(true);
		if (change === 'admin') auth.update((value) => ({ ...value, isSystemAdmin: false }));
		await tick();
		expect(signal.aborted).toBe(true);
		first.resolve(emptyReport());
		await tick();
		expect(deleteButton().disabled).toBe(true);
		expect(mocks.delete).not.toHaveBeenCalled();
	});

	it('guards double-click and dismissal during DELETE and invalidates only the captured names scope', async () => {
		const deletion = Promise.withResolvers<unknown>();
		mocks.delete.mockReturnValueOnce(deletion.promise);
		const view = openModal();
		await waitUntilReady();
		const button = deleteButton();
		await fireEvent.click(button);
		await fireEvent.click(button);
		await fireEvent.keyDown(document, { key: 'Escape' });
		await fireEvent.click(screen.getByRole('button', { name: '취소' }));
		expect(mocks.delete).toHaveBeenCalledOnce();
		expect(mocks.delete).toHaveBeenCalledWith('/api/v1/admin/projects/p1', 'token', 'admin-project');
		expect(view.props.onClose).not.toHaveBeenCalled();
		expect(recheckButton().disabled).toBe(true);
		expect(mocks.scope).toHaveBeenCalledWith('token', 'admin-project');
		deletion.resolve({ status: 'deleted' });
		await waitFor(() => expect(view.props.onSuccess).toHaveBeenCalledOnce());
		expect(view.props.onClose).toHaveBeenCalledOnce();
		expect(mocks.invalidate.mock.calls).toEqual([[{ token: 'token', projectId: 'admin-project' }], [{ token: 'token', projectId: 'admin-project' }]]);
	});

	it('does not call old-target success/close callbacks after the modal target changes during DELETE', async () => {
		const deletion = Promise.withResolvers<unknown>();
		mocks.delete.mockReturnValueOnce(deletion.promise);
		const view = openModal();
		await waitUntilReady();
		await fireEvent.click(deleteButton());
		mocks.get.mockResolvedValue(emptyReport('p2'));
		const nextClose = vi.fn();
		const nextSuccess = vi.fn();
		await view.rerender({ project: otherProject, onClose: nextClose, onSuccess: nextSuccess });
		await waitUntilReady();
		deletion.resolve({ status: 'deleted' });
		await tick();
		expect(view.props.onClose).not.toHaveBeenCalled();
		expect(view.props.onSuccess).not.toHaveBeenCalled();
		expect(nextClose).not.toHaveBeenCalled();
		expect(nextSuccess).not.toHaveBeenCalled();
		expect(deleteButton().disabled).toBe(false);
	});

	it('fences DELETE callbacks during logout', async () => {
		const deletion = Promise.withResolvers<unknown>();
		mocks.delete.mockReturnValueOnce(deletion.promise);
		const view = openModal();
		await waitUntilReady();
		await fireEvent.click(deleteButton());
		logoutInProgress.set(true);
		await tick();
		deletion.resolve({ status: 'deleted' });
		await tick();
		expect(view.props.onClose).not.toHaveBeenCalled();
		expect(view.props.onSuccess).not.toHaveBeenCalled();
		expect(deleteButton().disabled).toBe(true);
	});

	it.each([
		[409, 'project_has_resources', blockedReport(), '최종 확인에서 남은 리소스가 발견되어'],
		[503, 'project_resource_check_failed', unknownReport(), '서버의 최종 리소스 확인을 완료할 수 없어'],
	])('keeps final server refusal %s readable and applies the embedded report', async (status, code, check, message) => {
		mocks.delete.mockRejectedValue(new ApiError(status, JSON.stringify({ code, message: 'safe server message', check })));
		const view = openModal();
		await waitUntilReady();
		await fireEvent.click(deleteButton());
		await screen.findByText(new RegExp(message));
		expect(deleteButton().disabled).toBe(true);
		expect(screen.queryByText(/"code"/)).toBeNull();
		expect(mocks.get).toHaveBeenCalledOnce();
		expect(view.props.onClose).not.toHaveBeenCalled();
		expect(view.props.onSuccess).not.toHaveBeenCalled();
		await fireEvent.keyDown(document, { key: 'Escape' });
		expect(view.props.onClose).toHaveBeenCalledOnce();
	});

	it('never treats an embedded refusal report claiming can_delete as a new permission to delete', async () => {
		mocks.delete.mockRejectedValue(new ApiError(409, JSON.stringify({ code: 'project_has_resources', check: emptyReport() })));
		openModal();
		await waitUntilReady();
		await fireEvent.click(deleteButton());
		await screen.findByText(/최종 확인에서 남은 리소스가 발견되어/);
		expect(deleteButton().disabled).toBe(true);
		await fireEvent.click(recheckButton());
		await waitUntilReady();
	});

	it.each([
		['malformed JSON', '{invalid'],
		['missing report', JSON.stringify({ code: 'project_resource_check_failed' })],
		['wrong target report', JSON.stringify({ code: 'project_has_resources', check: emptyReport('other') })],
	])('rechecks final refusal with %s rather than rendering raw JSON', async (_label, message) => {
		const refresh = Promise.withResolvers<unknown>();
		mocks.get.mockResolvedValueOnce(emptyReport()).mockReturnValueOnce(refresh.promise);
		mocks.delete.mockRejectedValue(new ApiError(503, message));
		openModal();
		await waitUntilReady();
		await fireEvent.click(deleteButton());
		await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(2));
		expect(deleteButton().disabled).toBe(true);
		expect(screen.queryByText(message, { exact: true })).toBeNull();
		refresh.resolve(unknownReport());
		await waitFor(() => expect(recheckButton().disabled).toBe(false));
		expect(deleteButton().disabled).toBe(true);
	});

	it('renders a readable ordinary failure and requires another inspection before retrying deletion', async () => {
		mocks.delete.mockRejectedValue(new ApiError(500, 'Identity service unavailable'));
		openModal();
		await waitUntilReady();
		await fireEvent.click(deleteButton());
		expect(await screen.findByText('Identity service unavailable')).toBeTruthy();
		expect(deleteButton().disabled).toBe(true);
		await fireEvent.click(recheckButton());
		await waitUntilReady();
		expect(screen.queryByText('Identity service unavailable')).toBeNull();
	});

	it.each(['cancel', 'scrim'])('allows %s dismissal while resource inspection is pending', async (route) => {
		const pending = Promise.withResolvers<unknown>();
		mocks.get.mockReturnValueOnce(pending.promise);
		const view = openModal();
		await waitFor(() => expect(mocks.get).toHaveBeenCalledOnce());
		const signal = mocks.get.mock.calls[0][3].signal as AbortSignal;
		await fireEvent.click(screen.getByRole('button', { name: route === 'cancel' ? '취소' : '대화상자 닫기' }));
		expect(view.props.onClose).toHaveBeenCalledOnce();
		expect(signal.aborted).toBe(true);
		pending.resolve(emptyReport());
		await tick();
		expect(mocks.delete).not.toHaveBeenCalled();
	});

	it('aborts inspection on unmount and ignores its eventual response', async () => {
		const pending = Promise.withResolvers<unknown>();
		mocks.get.mockReturnValueOnce(pending.promise);
		const view = openModal();
		await waitFor(() => expect(mocks.get).toHaveBeenCalledOnce());
		const signal = mocks.get.mock.calls[0][3].signal as AbortSignal;
		view.unmount();
		expect(signal.aborted).toBe(true);
		pending.resolve(emptyReport());
		await tick();
		expect(view.props.onSuccess).not.toHaveBeenCalled();
		expect(view.props.onClose).not.toHaveBeenCalled();
	});

	it('shows a localized failure instead of object-shaped generic API error JSON', async () => {
		mocks.delete.mockRejectedValue(new ApiError(500, JSON.stringify({ detail: 'internal provider failure' })));
		openModal();
		await waitUntilReady();
		await fireEvent.click(deleteButton());
		expect(await screen.findByText('삭제 실패')).toBeTruthy();
		expect(screen.queryByText(/internal provider failure/)).toBeNull();
		expect(deleteButton().disabled).toBe(true);
	});

});
