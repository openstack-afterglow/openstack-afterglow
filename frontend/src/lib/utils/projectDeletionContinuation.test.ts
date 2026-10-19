import { beforeEach, describe, expect, it, vi } from 'vitest';
import { get, writable } from 'svelte/store';
const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), goto: vi.fn(), close: vi.fn(), error: vi.fn(), invitation: vi.fn(), destination: vi.fn() }));
vi.mock('$app/navigation', () => ({ goto: mocks.goto }));
vi.mock('$lib/api/client', () => ({ api: { get: mocks.get, post: mocks.post } }));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({}), authReady: writable(true), logoutInProgress: writable(false), projectSwitching: writable(false), setAuth: vi.fn(), clearAuth: vi.fn()
}));
vi.mock('$lib/stores/cloudShell.svelte', () => ({ cloudShell: { close: mocks.close } }));
vi.mock('$lib/stores/toast', () => ({ toast: { error: mocks.error } }));
vi.mock('./domainLogin', () => ({ takePendingInvitationPath: mocks.invitation }));
vi.mock('./mcpConsent', () => ({ postAuthDestination: mocks.destination }));
import { auth, authReady, logoutInProgress, projectSwitching, setAuth, clearAuth } from '$lib/stores/auth';
import { continueAfterProjectDeletion } from './projectDeletionContinuation';
const original = { token: 'old-token', userId: 'actor', identityDomainId: 'home', identityDomainName: 'Home', domainId: 'team', domainName: 'Team', projectId: 'deleted', projectName: 'Deleted', sessionId: 'login-session', availableDomains: [{ id: 'team', name: 'Team' }], availableProjects: [{ id: 'deleted', name: 'Deleted' }], federated: true };
const response = { token: 'new-token', user_id: 'actor', domain_id: 'team', domain_name: 'Team', identity_domain_id: 'home', identity_domain_name: 'Home', project_id: 'default', project_name: 'Default', available_domains: [{ id: 'team', name: 'Team' }], roles: ['reader'], is_domain_manager: false };
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(yes => { resolve = yes; }); return { promise, resolve }; }
beforeEach(() => {
	vi.resetAllMocks(); auth.set(original as never); authReady.set(true); logoutInProgress.set(false); projectSwitching.set(false);
	vi.mocked(setAuth).mockImplementation(update => { auth.update(state => ({ ...state, ...update })); });
	vi.mocked(clearAuth).mockImplementation(() => { authReady.set(false); auth.update(state => ({ ...state, token: null, projectId: null })); });
	mocks.close.mockResolvedValue(undefined); mocks.get.mockResolvedValue([{ id: 'team', name: 'Team' }]); mocks.post.mockResolvedValue(response); mocks.goto.mockResolvedValue(undefined);
	mocks.invitation.mockReturnValue(null); mocks.destination.mockImplementation(path => path);
});

describe('successful active-project deletion continuation', () => {
	it('exchanges the deleted scope once and preserves immutable home identity and logical session', async () => {
		await continueAfterProjectDeletion('deleted', 'team');
		expect(mocks.close).toHaveBeenCalledWith('project-switch', { keepDock: false });
		expect(mocks.post).toHaveBeenCalledWith('/api/v1/auth/token/domain', { domain_id: 'team' }, 'old-token', undefined, { replayOnUnauthorized: false, suppressAuthRedirect: true, cache: 'no-store' });
		expect(get(auth)).toMatchObject({ token: 'new-token', projectId: 'default', identityDomainId: 'home', domainId: 'team', sessionId: 'login-session', federated: true, availableProjects: [] });
		expect(mocks.goto).toHaveBeenCalledWith('/dashboard'); expect(get(projectSwitching)).toBe(false);
	});
	it('retains pending invitation navigation after a verified scope replacement', async () => {
		mocks.invitation.mockReturnValue('/invitations/pending-token');
		await continueAfterProjectDeletion('deleted', 'team');
		expect(mocks.goto).toHaveBeenCalledWith('/invitations/pending-token'); expect(mocks.destination).not.toHaveBeenCalled();
	});
	it('clears the dead token and preserves pending intents when native scope exchange fails', async () => {
		mocks.post.mockRejectedValue(new Error('deleted native token'));
		await continueAfterProjectDeletion('deleted', 'team');
		expect(clearAuth).toHaveBeenCalledOnce(); expect(get(auth).token).toBeNull();
		expect(mocks.goto).toHaveBeenCalledWith('/login'); expect(mocks.invitation).not.toHaveBeenCalled(); expect(mocks.destination).not.toHaveBeenCalled();
		expect(mocks.post).toHaveBeenCalledTimes(1); expect(mocks.error).toHaveBeenCalledOnce(); expect(get(projectSwitching)).toBe(false);
	});
	it('rejects a response that reselects the deleted project', async () => {
		mocks.post.mockResolvedValue({ ...response, project_id: 'deleted' });
		await continueAfterProjectDeletion('deleted', 'team');
		expect(clearAuth).toHaveBeenCalledOnce(); expect(mocks.goto).not.toHaveBeenCalledWith('/dashboard');
	});
	it('rejects a response for a different home identity', async () => {
		mocks.post.mockResolvedValue({ ...response, identity_domain_id: 'foreign' });
		await continueAfterProjectDeletion('deleted', 'team');
		expect(clearAuth).toHaveBeenCalledOnce(); expect(mocks.goto).toHaveBeenCalledWith('/login');
	});
	it('permanently retires pending continuation on same-tick A to B to A scope changes', async () => {
		const pending = deferred<unknown>(); mocks.get.mockReturnValue(pending.promise);
		const action = continueAfterProjectDeletion('deleted', 'team');
		await vi.waitFor(() => expect(mocks.get).toHaveBeenCalledOnce());
		auth.update(state => ({ ...state, projectId: 'other' })); auth.update(state => ({ ...state, projectId: 'deleted' }));
		pending.resolve([{ id: 'team', name: 'Team' }]); await action;
		expect(mocks.post).not.toHaveBeenCalled(); expect(mocks.goto).not.toHaveBeenCalled(); expect(clearAuth).not.toHaveBeenCalled();
	});
	it('does not change the session when another project was deleted', async () => {
		await continueAfterProjectDeletion('not-active', 'team');
		expect(mocks.get).not.toHaveBeenCalled(); expect(mocks.close).not.toHaveBeenCalled(); expect(get(auth).token).toBe('old-token');
	});
});
