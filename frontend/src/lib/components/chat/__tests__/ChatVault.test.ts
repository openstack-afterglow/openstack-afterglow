import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { get } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { auth, projectSwitching } from '$lib/stores/auth';
import { ApiError } from '$lib/api/errors';
import { grantLumen, setVerifiedLumenActor } from './lumenPermissionFixture';
import ChatVault from '../ChatVault.svelte';
import type { VaultNote } from '$lib/api/chatVault';

const { getJson, post, patch, put } = vi.hoisted(() => ({ getJson: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn() }));
vi.mock('$lib/api/client', async () => ({
	api: { get: getJson, post, patch, put },
	ApiError: (await vi.importActual<{ ApiError: typeof ApiError }>('$lib/api/errors')).ApiError
}));

const base = '/api/v1/chat/vault';
const note: VaultNote = {
	id: 1, kind: 'user_note', slug: 'preferences', title: 'Preferences', content: 'Keep it short.',
	hash: 'a'.repeat(64), scope: 'domain', project_key: null, workspace_id: null, role: null, revision: 1
};
const log: VaultNote = {
	...note, id: 2, kind: 'log', slug: 'investigation', title: 'Investigation',
	content: 'Existing record.', scope: 'global'
};
const workspace = { id: 31, name: 'Research chat' };
const workspaceNote: VaultNote = {
	...note, id: 3, title: 'Imported memory', workspace_id: workspace.id, content: 'Private workspace memory.'
};
const memory = { filename: 'memory.md', content_type: 'text/markdown', content: '# Memory\n\n- Keep it short.\n' };
const netOptions = expect.objectContaining({ cache: 'no-store', replayOnUnauthorized: false, signal: expect.any(AbortSignal) });
const click = (name: string) => fireEvent.click(screen.getByRole('button', { name }));
const change = (label: string, value: string) => fireEvent.input(screen.getByLabelText(label), { target: { value } });

async function selectChatProject() {
	await fireEvent.click(await screen.findByText('도메인 및 전역 노트'));
	await fireEvent.click(await screen.findByRole('option', { name: workspace.name }));
}

beforeEach(() => {
	vi.resetAllMocks();
	setVerifiedLumenActor({
		...get(auth), token: 'token-a', userId: 'user-1', username: 'tester', sessionId: 'session-a',
		identityDomainId: 'home', domainId: 'working-a', projectId: 'project-a'
	});
	getJson.mockImplementation(async (path: string) => {
		const url = new URL(path, 'http://test');
		const inWorkspace = url.searchParams.get('workspace_id') === String(workspace.id);
		switch (url.pathname) {
			case '/api/v1/chat/workspaces': return [workspace];
			case `${base}/notes`: return inWorkspace ? [workspaceNote] : url.searchParams.get('kind') === 'log' ? [log] : [note, log];
			case `${base}/search`: return inWorkspace ? [workspaceNote] : [log];
			case `${base}/document`: return memory;
			case `${base}/notes/1`: return note;
			case `${base}/notes/2`: return log;
			case `${base}/notes/1/revisions`: return [{ revision: 1, title: note.title, content: 'Original text', created_at: '2026-11-19T00:00:00Z' }];
			case `${base}/notes/3`: if (inWorkspace) return workspaceNote; break;
			case `${base}/notes/3/revisions`: if (inWorkspace) return []; break;
			case `${base}/profile`: return { exists: false };
		}
		throw new Error(`Unexpected path: ${path}`);
	});
});
afterEach(() => vi.restoreAllMocks());

describe('ChatVault', () => {
	it('lists kinds and scope, filters, and searches with the selected kind', async () => {
		render(ChatVault);
		expect(await screen.findByRole('button', { name: note.title })).toBeTruthy();
		expect(screen.getByText('현재 도메인')).toBeTruthy();
		expect(screen.getByText('전역')).toBeTruthy();
		await fireEvent.change(screen.getByLabelText('노트 유형'), { target: { value: 'log' } });
		expect(await screen.findByRole('button', { name: log.title })).toBeTruthy();
		expect(screen.queryByRole('button', { name: note.title })).toBeNull();
		await change('Vault 검색', 'incident & proof');
		await click('Vault 검색');
		expect(await screen.findByRole('button', { name: log.title })).toBeTruthy();
		expect(getJson).toHaveBeenCalledWith(`${base}/search?limit=25&kind=log&query=incident+%26+proof`, 'token-a', 'project-a', netOptions);
	});

	it('lists, searches, reads, and edits workspace notes with the selected workspace ID', async () => {
		render(ChatVault);
		await selectChatProject();
		expect(await screen.findByRole('button', { name: workspaceNote.title })).toBeTruthy();
		expect(getJson).toHaveBeenCalledWith('/api/v1/chat/workspaces', 'token-a', 'project-a', netOptions);
		expect(getJson).toHaveBeenCalledWith(`${base}/notes?limit=25&workspace_id=31`, 'token-a', 'project-a', netOptions);
		expect(screen.queryByRole('button', { name: note.title })).toBeNull();
		expect(screen.queryByRole('region', { name: 'memory.md 내용' })).toBeNull();
		await change('Vault 검색', 'imported');
		await click('Vault 검색');
		expect(getJson).toHaveBeenCalledWith(`${base}/search?limit=25&query=imported&workspace_id=31`, 'token-a', 'project-a', netOptions);
		await click(workspaceNote.title);
		expect(await screen.findByText(workspaceNote.content)).toBeTruthy();
		expect(getJson).toHaveBeenCalledWith(`${base}/notes/3?workspace_id=31`, 'token-a', 'project-a', netOptions);
		await click('버전 기록');
		expect(getJson).toHaveBeenCalledWith(`${base}/notes/3/revisions?limit=25&workspace_id=31`, 'token-a', 'project-a', netOptions);
		await click('편집');
		await change('노트 내용', 'Edited workspace memory.');
		patch.mockResolvedValueOnce({ ...workspaceNote, content: 'Edited workspace memory.' });
		await click('변경 저장');
		expect(await screen.findByText('Edited workspace memory.')).toBeTruthy();
		expect(patch).toHaveBeenCalledWith(`${base}/notes/3?workspace_id=31`, {
			content: 'Edited workspace memory.', title: workspaceNote.title, expectedHash: workspaceNote.hash
		}, 'token-a', 'project-a', netOptions);
	});

	it('creates a user note in the selected chat project, never globally', async () => {
		render(ChatVault);
		await selectChatProject();
		await click('노트 만들기');
		const dialog = within(screen.getByRole('dialog', { name: '노트 만들기' }));
		expect(dialog.getByText(`이 노트는 채팅 프로젝트 ${workspace.name}에만 저장됩니다.`)).toBeTruthy();
		expect(dialog.queryByRole('combobox')).toBeNull();
		await fireEvent.input(dialog.getByLabelText('노트 내용'), { target: { value: 'New local note.' } });
		post.mockResolvedValueOnce(workspaceNote);
		await fireEvent.click(dialog.getByRole('button', { name: '노트 만들기' }));
		expect(await screen.findByText(workspaceNote.content)).toBeTruthy();
		expect(post).toHaveBeenCalledWith(`${base}/notes`, {
			kind: 'user_note', mode: 'create', scope: 'domain', workspace_id: 31,
			title: 'New local note.', content: 'New local note.', slug: expect.any(String)
		}, 'token-a', 'project-a', netOptions);
	});

	it('clears the chat project filter when the working domain changes', async () => {
		render(ChatVault);
		await selectChatProject();
		expect(await screen.findByRole('button', { name: workspaceNote.title })).toBeTruthy();
		setVerifiedLumenActor({ ...get(auth), token: 'token-c', domainId: 'working-b', projectId: 'project-c' });
		expect(await screen.findByText('도메인 및 전역 노트')).toBeTruthy();
		expect(await screen.findByRole('button', { name: note.title })).toBeTruthy();
		expect(screen.queryByRole('button', { name: workspaceNote.title })).toBeNull();
		expect(getJson).toHaveBeenCalledWith(`${base}/notes?limit=25`, 'token-c', 'project-c', netOptions);
		expect(getJson).not.toHaveBeenCalledWith(expect.stringContaining('workspace_id='), 'token-c', 'project-c', netOptions);
	});

	it('loads revisions and protects the draft after a hash conflict until explicit reconciliation', async () => {
		render(ChatVault);
		await fireEvent.click(await screen.findByRole('button', { name: note.title }));
		expect(await screen.findByText(note.content)).toBeTruthy();
		await click('버전 기록');
		await fireEvent.click(await screen.findByText(/버전 1/));
		expect(await screen.findByText('Original text')).toBeTruthy();
		await click('편집');
		await change('노트 내용', 'My draft.');
		const newHash = 'b'.repeat(64);
		patch.mockRejectedValueOnce(new ApiError(409, 'hash_mismatch'));
		await click('변경 저장');
		expect(await screen.findByText(/다른 곳에서 이 노트를 변경/)).toBeTruthy();
		expect(patch).toHaveBeenCalledWith(`${base}/notes/1`, { content: 'My draft.', title: note.title, expectedHash: note.hash }, 'token-a', 'project-a', netOptions);
		expect((screen.getByRole('button', { name: '변경 저장' }) as HTMLButtonElement).disabled).toBe(true);
		getJson.mockResolvedValueOnce({ ...note, hash: newHash, content: 'Concurrent edit.' });
		await click('최신 버전 불러오기');
		expect(await screen.findByText('Concurrent edit.')).toBeTruthy();
		await click('초안을 유지하고 직접 병합');
		expect((screen.getByLabelText('노트 내용') as HTMLTextAreaElement).value).toBe('My draft.');
		await change('노트 내용', 'Merged content.');
		patch.mockResolvedValueOnce({ ...note, content: 'Merged content.' });
		await click('변경 저장');
		expect(await screen.findByText('Merged content.')).toBeTruthy();
		expect(patch).toHaveBeenLastCalledWith(`${base}/notes/1`, { content: 'Merged content.', title: note.title, expectedHash: newHash }, 'token-a', 'project-a', netOptions);
	});

	it('only appends a new record for an immutable kind', async () => {
		render(ChatVault);
		await fireEvent.click(await screen.findByRole('button', { name: log.title }));
		await fireEvent.click(await screen.findByRole('button', { name: '기록 추가' }));
		expect(screen.queryByRole('button', { name: '편집' })).toBeNull();
		const body = screen.getByLabelText('추가할 내용') as HTMLTextAreaElement;
		expect(body.value).toBe('');
		await fireEvent.input(body, { target: { value: 'New record.' } });
		post.mockResolvedValueOnce({ ...log, id: 3 });
		await click('기록 추가');
		await waitFor(() => expect(post).toHaveBeenCalledWith(`${base}/notes`, {
			kind: 'log', mode: 'append', scope: 'global', title: log.title, content: 'New record.', slug: expect.any(String)
		}, 'token-a', 'project-a', netOptions));
		expect(patch).not.toHaveBeenCalled();
		expect(screen.getByText(log.content)).toBeTruthy();
	});

	it('defaults to manual user-note creation and explains secret refusal without discarding the draft', async () => {
		render(ChatVault);
		await click('노트 만들기');
		const dialog = within(screen.getByRole('dialog', { name: '노트 만들기' }));
		const body = dialog.getByLabelText('노트 내용') as HTMLTextAreaElement;
		await fireEvent.input(body, { target: { value: 'Synthetic draft.' } });
		post.mockRejectedValueOnce(new ApiError(422, 'secret_detected'));
		await fireEvent.click(dialog.getByRole('button', { name: '노트 만들기' }));
		expect((await dialog.findByRole('alert')).textContent).toMatch(/비밀 정보가 감지/);
		expect(body.value).toBe('Synthetic draft.');
		expect(post).toHaveBeenCalledWith(`${base}/notes`, {
			kind: 'user_note', mode: 'create', scope: 'domain', title: 'Synthetic draft.', content: 'Synthetic draft.', slug: expect.any(String)
		}, 'token-a', 'project-a', netOptions);
		await fireEvent.input(body, { target: { value: 'Safe draft.' } });
		post.mockResolvedValueOnce(note);
		await fireEvent.click(dialog.getByRole('button', { name: '노트 만들기' }));
		expect(await screen.findByText(note.content)).toBeTruthy();
		expect(screen.queryByRole('dialog')).toBeNull();
	});

	it('uses the canonical singleton endpoint when creating a missing profile', async () => {
		render(ChatVault);
		await fireEvent.change(screen.getByLabelText('노트 유형'), { target: { value: 'profile' } });
		await click('프로필 열기');
		await fireEvent.click(await screen.findByRole('button', { name: '편집' }));
		await change('노트 내용', 'Personal profile');
		put.mockResolvedValueOnce({ ...note, kind: 'profile', title: 'Profile', content: 'Personal profile', scope: 'global' });
		await click('변경 저장');
		expect(put).toHaveBeenCalledWith(`${base}/profile`, { content: 'Personal profile', expectedHash: undefined }, 'token-a', 'project-a', netOptions);
		expect(await screen.findByText('Personal profile')).toBeTruthy();
	});

	it('renders, copies and downloads the server-provided Markdown', async () => {
		const writeText = vi.fn().mockResolvedValue(undefined);
		Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
		const createUrl = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:fixture');
		const revokeUrl = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
		const download = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
			expect(this.download).toBe('memory.md');
			expect(this.href).toBe('blob:fixture');
		});
		render(ChatVault);
		expect((await screen.findByRole('region', { name: 'memory.md 내용' })).textContent).toBe(memory.content);
		await click('복사');
		expect(writeText).toHaveBeenCalledWith(memory.content);
		await click('다운로드');
		expect(download).toHaveBeenCalledOnce();
		const [blob] = createUrl.mock.calls[0];
		if (!(blob instanceof Blob)) throw new Error('Expected a Markdown Blob');
		expect(blob.type).toBe('text/markdown;charset=utf-8');
		const reader = new FileReader();
		const { promise, resolve, reject } = Promise.withResolvers<FileReader['result']>();
		reader.onload = () => resolve(reader.result);
		reader.onerror = () => reject(reader.error);
		reader.readAsText(blob);
		await expect(promise).resolves.toBe(memory.content);
		await waitFor(() => expect(revokeUrl).toHaveBeenCalledWith('blob:fixture'));
	});

	it('keeps a draft within one domain, uses the new project, then retires the draft on domain change', async () => {
		render(ChatVault);
		await fireEvent.click(await screen.findByRole('button', { name: note.title }));
		await fireEvent.click(await screen.findByRole('button', { name: '편집' }));
		await change('노트 내용', 'Scope-local draft');
		projectSwitching.set(true);
		setVerifiedLumenActor({ ...get(auth), token: 'token-b', projectId: 'project-b' });
		await waitFor(() => expect(screen.queryByRole('textbox', { name: '노트 내용' })).toBeNull());
		projectSwitching.set(false);
		expect((await screen.findByRole('textbox', { name: '노트 내용' }) as HTMLTextAreaElement).value).toBe('Scope-local draft');
		patch.mockRejectedValueOnce(new ApiError(409, 'hash_mismatch'));
		await click('변경 저장');
		expect(patch).toHaveBeenCalledWith(`${base}/notes/1`, expect.anything(), 'token-b', 'project-b', netOptions);
		setVerifiedLumenActor({ ...get(auth), domainId: 'working-b', projectId: 'project-c' });
		await waitFor(() => expect(screen.queryByRole('textbox', { name: '노트 내용' })).toBeNull());
		expect(await screen.findByRole('button', { name: note.title })).toBeTruthy();
	});

	it('ignores a pending note response after a synchronous domain ABA', async () => {
		render(ChatVault);
		const trigger = await screen.findByRole('button', { name: note.title });
		const pending = Promise.withResolvers<VaultNote>();
		getJson.mockReturnValueOnce(pending.promise);
		await fireEvent.click(trigger);
		expect(getJson).toHaveBeenCalledWith(`${base}/notes/1`, 'token-a', 'project-a', netOptions);
		const original = get(auth);
		setVerifiedLumenActor({ ...original, domainId: 'working-b', projectId: 'project-b' });
		setVerifiedLumenActor(original);
		pending.resolve({ ...note, content: 'Retired note response' });
		expect(await screen.findByRole('button', { name: note.title })).toBeTruthy();
		expect(screen.queryByText('Retired note response')).toBeNull();
		expect(screen.queryByRole('button', { name: '편집' })).toBeNull();
	});

	it('shows notes but no mutation controls to a history reader', async () => {
		grantLumen('lumen-history_reader');
		render(ChatVault);
		await fireEvent.click(await screen.findByRole('button', { name: note.title }));
		expect(await screen.findByText(note.content)).toBeTruthy();
		expect(screen.queryByRole('button', { name: '편집' })).toBeNull();
		expect(screen.queryByRole('button', { name: '노트 만들기' })).toBeNull();
	});

	it('does not load private content without history access', async () => {
		grantLumen();
		render(ChatVault);
		expect(screen.queryByRole('button', { name: '노트 만들기' })).toBeNull();
		expect(getJson).not.toHaveBeenCalled();
	});
});
