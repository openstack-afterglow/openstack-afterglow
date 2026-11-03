import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { tick } from 'svelte';
import { get } from 'svelte/store';
import { acceptAuthVerification, auth, authReady, getAuthVerificationEpoch, projectSwitching, setAuth } from '$lib/stores/auth';
import { refreshAuthState } from '$lib/utils/authSession';
import type { RegisteredChatSource } from '$lib/api/chatSources';
import { ApiError } from '$lib/api/errors';
const mocks = vi.hoisted(() => ({ source: vi.fn(), asset: vi.fn(), download: vi.fn() }));
vi.mock('$lib/api/chatSources', () => ({ getRegisteredChatSource: mocks.source, getChatSourceAsset: mocks.asset, getChatSourceDownloadLink: mocks.download }));
vi.mock('$lib/stores/servicePermissions', async () => {
	const { writable } = await import('svelte/store');
	// Vitest hoists this factory before static store imports are initialized.
	return { observedProjectPermissions: writable({ permissions: null, loading: false, error: '' }) };
});
import ChatSourcePage from '../ChatSourcePage.svelte';

const assetId = 'e83a2892-41f0-4ca2-a453-4e23118f32ba';
function actor(projectId = 'project-1') {
	auth.set({ token: 'token', refreshToken: null, accessExpiresAt: null, userId: 'user-1', username: 'tester', projectId, projectName: projectId, availableProjects: [], roles: [], isSystemAdmin: false, federated: false, domainId: 'domain-1', domainName: 'Domain', identityDomainId: 'domain-1', identityDomainName: 'Domain', isDomainManager: false });
	expect(acceptAuthVerification(getAuthVerificationEpoch(), {})).toBe(true);
}
beforeEach(() => {
	vi.clearAllMocks();
	projectSwitching.set(false);
	actor();
	mocks.asset.mockResolvedValue({ id: assetId, name: 'Uploaded guide.pdf', mime_type: 'application/pdf', size_bytes: 42 });
	mocks.source.mockResolvedValue({ type: 'citation', citation_id: 'c1', source_kind: 'web', url: 'https://example.org/guide', title: 'Registered guide', snippet: 'Observed evidence' });
	mocks.download.mockResolvedValue('https://objects.example/file?signature=fresh');
});
describe('ChatSourcePage', () => {
	it('loads registered evidence but never opens an external resource automatically', async () => {
		const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
		render(ChatSourcePage, { runId: 'run-1', citationId: 'c1' });
		expect(await screen.findByText('Observed evidence')).toBeTruthy();
		expect(screen.getByRole('link', { name: /원문 열기/ }).getAttribute('href')).toBe('https://example.org/guide');
		expect(click).not.toHaveBeenCalled();
		expect(mocks.download).not.toHaveBeenCalled();
		click.mockRestore();
	});
	it('requests a fresh signed URL only on explicit download and never renders the signature', async () => {
		const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
		const view = render(ChatSourcePage, { assetId });
		const button = await screen.findByRole('button', { name: 'Uploaded guide.pdf 다운로드' });
		expect(mocks.download).not.toHaveBeenCalled();
		await fireEvent.click(button);
		await waitFor(() => expect(click).toHaveBeenCalledTimes(1));
		expect(mocks.download).toHaveBeenCalledWith(assetId, expect.objectContaining({ token: 'token', projectId: 'project-1' }));
		expect(view.container.innerHTML).not.toContain('signature=fresh');
		click.mockRestore();
	});
	it('discards same-tick project-switch ABA responses and aborts the retired request', async () => {
		const pending = Promise.withResolvers<RegisteredChatSource>();
		mocks.source.mockReturnValueOnce(pending.promise);
		const view = render(ChatSourcePage, { runId: 'run-1', citationId: 'c1' });
		await waitFor(() => expect(mocks.source).toHaveBeenCalledTimes(1));
		const firstSignal = mocks.source.mock.calls[0][2].signal;
		projectSwitching.set(true);
		projectSwitching.set(false);
		pending.resolve({ type: 'citation', citation_id: 'c1', source_kind: 'web', url: 'https://example.org/old', title: 'Retired private title', snippet: 'Retired private evidence' });
		await tick();
		expect(firstSignal.aborted).toBe(true);
		expect(view.queryByText('Retired private title')).toBeNull();
		expect(view.queryByText('Retired private evidence')).toBeNull();
	});
	it('never opens a late signed URL after a scope-switch ABA', async () => {
		const pending = Promise.withResolvers<string>();
		mocks.download.mockReturnValueOnce(pending.promise);
		const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
		render(ChatSourcePage, { assetId });
		await fireEvent.click(await screen.findByRole('button', { name: 'Uploaded guide.pdf 다운로드' }));
		await waitFor(() => expect(mocks.download).toHaveBeenCalledTimes(1));
		projectSwitching.set(true); projectSwitching.set(false);
		pending.resolve('https://objects.example/file?signature=retired');
		await tick();
		expect(click).not.toHaveBeenCalled();
		click.mockRestore();
	});
	it('preserves settled source evidence during an ordinary same-owner bearer renewal', async () => {
		render(ChatSourcePage, { runId: 'run-1', citationId: 'c1' });
		await screen.findByText('Observed evidence');
		const state = get(auth);
		setAuth(refreshAuthState({ token: 'renewed', user_id: state.userId!, username: state.username!, project_id: state.projectId!, project_name: state.projectName!, expires_at: null, roles: state.roles, is_system_admin: false, domain_id: state.domainId, identity_domain_id: state.identityDomainId, identity_domain_name: state.identityDomainName, is_domain_manager: false }, state));
		await tick();
		expect(screen.getByText('Observed evidence')).toBeTruthy();
		expect(mocks.source).toHaveBeenCalledTimes(1);
	});
	it('shows a bounded generic error, never raw upstream bodies, and offers explicit reload', async () => {
		mocks.source.mockRejectedValueOnce(new Error('Authorization: secret upstream HTML'));
		const view = render(ChatSourcePage, { runId: 'run-1', citationId: 'c1' });
		await screen.findByRole('alert');
		expect(view.container.textContent).not.toContain('secret upstream');
		await fireEvent.click(screen.getByRole('button', { name: '출처 다시 불러오기' }));
		expect(await screen.findByText('Observed evidence')).toBeTruthy();
	});
});

it('shows expired historical evidence without suggesting a replacement-data retry', async () => {
	mocks.source.mockRejectedValueOnce(new ApiError(410, 'private archived snapshot reference'));
	render(ChatSourcePage, { runId: 'run-1', citationId: 'c1' });
	expect(await screen.findByText(/보관된 출처 기록이 만료되었거나 삭제/)).toBeTruthy();
	expect(screen.queryByRole('button', { name: '출처 다시 불러오기' })).toBeNull();
	expect(screen.queryByText('private archived snapshot reference')).toBeNull();
	expect(mocks.source).toHaveBeenCalledTimes(1);
});

it('keeps current-scope denial distinct from expired historical evidence', async () => {
	mocks.source.mockRejectedValueOnce(new ApiError(403, 'private current scope'));
	render(ChatSourcePage, { runId: 'run-1', citationId: 'c1' });
	expect(await screen.findByText(/현재 계정과 프로젝트에는 이 출처를 볼 권한/)).toBeTruthy();
	expect(screen.queryByRole('button', { name: '출처 다시 불러오기' })).toBeNull();
});

it.each([404, 409])('shows an unavailable asset for HTTP %s without issuing a download link', async (status) => {
	mocks.asset.mockRejectedValueOnce(new ApiError(status, 'asset unavailable'));
	render(ChatSourcePage, { assetId });
	expect(await screen.findByText(/이 파일은 삭제되었거나 다운로드할 준비/)).toBeTruthy();
	expect(mocks.download).not.toHaveBeenCalled();
});

it('offers the canonical external data-source record without opening a stable-page loop', async () => {
	const url = 'https://git.example/org/repo/blob/main/data.csv';
	mocks.source.mockResolvedValueOnce({ type: 'citation', citation_id: 'c1', source_kind: 'data_source', source_id: 'record-1', title: 'Dataset', url });
	const view = render(ChatSourcePage, { runId: 'run-1', citationId: 'c1' });
	expect((await screen.findByRole('link', { name: /원문 열기/ })).getAttribute('href')).toBe(url);
	view.unmount();
	mocks.source.mockResolvedValueOnce({ type: 'citation', citation_id: 'c1', source_kind: 'tool_result', source_id: 'tool-1', title: 'Tool result', url: 'https://console.example/lumen/sources/runs/run-1/c1' });
	render(ChatSourcePage, { runId: 'run-1', citationId: 'c1' });
	await screen.findByText('Tool result');
	expect(screen.queryByRole('link', { name: /원문 열기/ })).toBeNull();
});

it('reloads after a same-tick readiness ABA without publishing the retired request', async () => {
	const pending = Promise.withResolvers<RegisteredChatSource>();
	mocks.source.mockReturnValueOnce(pending.promise);
	const view = render(ChatSourcePage, { runId: 'run-1', citationId: 'c1' });
	await waitFor(() => expect(mocks.source).toHaveBeenCalledTimes(1));
	const firstSignal = mocks.source.mock.calls[0][2].signal;
	authReady.set(false); authReady.set(true);
	pending.resolve({ type: 'citation', citation_id: 'c1', source_kind: 'web', url: 'https://example.org/retired', title: 'Retired readiness response' });
	await waitFor(() => expect(mocks.source).toHaveBeenCalledTimes(2));
	expect(firstSignal.aborted).toBe(true);
	expect(await screen.findByText('Observed evidence')).toBeTruthy();
	expect(view.queryByText('Retired readiness response')).toBeNull();
	expect(mocks.source.mock.calls[1][2].signal.aborted).toBe(false);
});
