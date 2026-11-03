import { beforeEach, describe, expect, it, vi } from 'vitest';
import { writable } from 'svelte/store';
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'fresh-token', federated: true, sessionId: 'fresh-session', userId: 'user', identityDomainId: 'home', projectId: null, domainId: 'home' }) }));
import { auth } from '$lib/stores/auth';
import { freshLoginDestination, postAuthDestination, storeMcpConsentTicket, pendingMcpConsentTicket, storePasswordCreateContinuation, storeLumenSourceContinuation, clearMcpConsentTicket, beginClaudeGatewayAuthorization, clearClaudeGatewayAuthorization } from '../mcpConsent';
import { storePendingInvitation, takePendingInvitationPath } from '../domainLogin';

beforeEach(() => {
	sessionStorage.clear();
	auth.update(state => ({ ...state, token: 'fresh-token', federated: true, sessionId: 'fresh-session', userId: 'user', identityDomainId: 'home', projectId: null, domainId: 'home' }));
});
describe('fresh established login continuation', () => {
	it('goes straight to an established project without explicit intent', () => {
		expect(freshLoginDestination('/dashboard')).toBe('/dashboard');
	});
	it.each(['/select-domain', '/select-project'])('retains every intent until a project is established at %s', target => {
		storePendingInvitation('i'.repeat(32)); storeMcpConsentTicket('m'.repeat(32));
		storePasswordCreateContinuation('p'.repeat(32));
		expect(freshLoginDestination(target)).toBe(target);
		expect(takePendingInvitationPath()).toBe(`/invitations/${'i'.repeat(32)}`);
		expect(pendingMcpConsentTicket()).toBe('m'.repeat(32));
		auth.update(state => ({ ...state, token: 'rotated-token', domainId: 'workspace', projectId: 'selected-project' }));
		expect(postAuthDestination('/dashboard')).toBe(`/recover/${'p'.repeat(32)}?reauthenticated=1`);
	});
	it('resumes invitation once before the preserved MCP continuation', () => {
		storePendingInvitation('i'.repeat(32)); storeMcpConsentTicket('m'.repeat(32));
		expect(freshLoginDestination('/dashboard')).toBe(`/invitations/${'i'.repeat(32)}`);
		expect(takePendingInvitationPath()).toBeNull();
		expect(freshLoginDestination('/dashboard')).toBe('/oauth/mcp/authorize');
		expect(pendingMcpConsentTicket()).toBe('m'.repeat(32));
	});
	it('retains recovery behind invitation and resumes it before MCP exactly once', () => {
		storePendingInvitation('i'.repeat(32)); storeMcpConsentTicket('m'.repeat(32));
		expect(storePasswordCreateContinuation('p'.repeat(32))).toBe(true);
		expect(freshLoginDestination('/dashboard')).toBe(`/invitations/${'i'.repeat(32)}`);
		expect(sessionStorage.getItem('afterglow_password_create_continuation')).toContain('p'.repeat(32));
		expect(postAuthDestination('/dashboard')).toBe(`/recover/${'p'.repeat(32)}?reauthenticated=1`);
		expect(sessionStorage.getItem('afterglow_password_create_continuation')).toBeNull();
		expect(freshLoginDestination('/dashboard')).toBe('/oauth/mcp/authorize');
	});
	it('does not mark an existing-session return as freshly reauthenticated', () => {
		storePasswordCreateContinuation('p'.repeat(32));
		expect(postAuthDestination('/dashboard')).toBe(`/recover/${'p'.repeat(32)}`);
		expect(sessionStorage.getItem('afterglow_password_create_continuation')).toBeNull();
	});
	it.each(['sessionId', 'userId', 'identityDomainId'] as const)('does not reuse deferred freshness after %s replacement', field => {
		storePasswordCreateContinuation('p'.repeat(32));
		expect(freshLoginDestination('/select-project')).toBe('/select-project');
		auth.update(state => ({ ...state, [field]: 'replacement' }));
		expect(postAuthDestination('/dashboard')).toBe(`/recover/${'p'.repeat(32)}`);
	});
	it('does not reuse expired deferred freshness', () => {
		storePasswordCreateContinuation('p'.repeat(32));
		freshLoginDestination('/select-domain');
		const key = 'afterglow_password_create_continuation';
		const value = JSON.parse(sessionStorage.getItem(key)!);
		sessionStorage.setItem(key, JSON.stringify({ ...value, freshUntil: Date.now() - 1 }));
		expect(postAuthDestination('/dashboard')).toBe(`/recover/${'p'.repeat(32)}`);
	});
	it.each([
		'not-json',
		JSON.stringify({ token: '../unsafe', expiresAt: Date.now() + 10000 }),
		JSON.stringify({ token: 'p'.repeat(32), expiresAt: 1 }),
		JSON.stringify({ token: 'p'.repeat(32), expiresAt: Date.now() + 3600000 }),
	])('deletes malformed or expired proof without resuming it', value => {
		sessionStorage.setItem('afterglow_password_create_continuation', value);
		expect(freshLoginDestination('/dashboard')).toBe('/dashboard');
		expect(sessionStorage.getItem('afterglow_password_create_continuation')).toBeNull();
	});
});

describe('source-only login continuation', () => {
	const path = '/lumen/sources/runs/run-1/citation-1';
	it('retains a source through project selection and consumes it exactly once', () => {
		expect(storeLumenSourceContinuation(path)).toBe(true);
		expect(freshLoginDestination('/select-project')).toBe('/select-project');
		auth.update(state => ({ ...state, projectId: 'selected-project' }));
		expect(postAuthDestination('/dashboard')).toBe(path);
		expect(postAuthDestination('/dashboard')).toBe('/dashboard');
	});
	it('preserves invitation, recovery, MCP and Claude continuation priorities ahead of sources', () => {
		storeLumenSourceContinuation(path);
		storePendingInvitation('i'.repeat(32));
		storePasswordCreateContinuation('p'.repeat(32));
		storeMcpConsentTicket('m'.repeat(32));
		beginClaudeGatewayAuthorization();
		expect(freshLoginDestination('/dashboard')).toBe(`/invitations/${'i'.repeat(32)}`);
		expect(postAuthDestination('/dashboard')).toBe(`/recover/${'p'.repeat(32)}?reauthenticated=1`);
		expect(postAuthDestination('/dashboard')).toBe('/oauth/mcp/authorize');
		clearMcpConsentTicket();
		expect(postAuthDestination('/dashboard')).toBe('/oauth/claude/authorize');
		clearClaudeGatewayAuthorization();
		auth.update(state => ({ ...state, projectId: 'selected-project' }));
		expect(postAuthDestination('/dashboard')).toBe(path);
	});
	it('rejects invalid or expired source intent without broadening login redirects', () => {
		for (const value of ['https://evil.example', '//evil.example', '/dashboard', '/lumen/sources/runs/../private', '/lumen/sources/runs/run-1/%2e%2e', `${path}\n`]) expect(storeLumenSourceContinuation(value)).toBe(false);
		storeLumenSourceContinuation(path);
		const key = 'afterglow_lumen_source_continuation';
		sessionStorage.setItem(key, JSON.stringify({ path, expiresAt: Date.now() - 1 }));
		expect(postAuthDestination('/dashboard')).toBe('/dashboard');
		expect(sessionStorage.getItem(key)).toBeNull();
	});
});
