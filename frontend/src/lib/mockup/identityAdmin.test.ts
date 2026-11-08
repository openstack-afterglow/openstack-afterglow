import { beforeEach, describe, expect, it } from 'vitest';
import { ApiError } from '$lib/api/errors';
import type { ApplicationCredential, ApplicationCredentialIssued } from '$lib/types/adminCredential';
import { mockIdentityAdmin } from './identityAdmin';
import { getMockupState, resetMockupState } from './state';

const TOKENS = '/api/v1/auth/mcp-tokens';
const CREDS = '/api/v1/admin/application-credentials';
const DOMAIN = new URLSearchParams({ domain_id: 'mock-domain' });
const inMonths = (months: number) => new Date(Date.now() + months * 30 * 86_400_000).toISOString();
const token = (overrides: Record<string, unknown> = {}) => ({ name: 'tutorial-agent', access_level: 'read', project_scope: 'selected', project_ids: ['mock-project-1'], expires_at: inMonths(1), ...overrides });
const credential = (overrides: Record<string, unknown> = {}) => ({ name: 'tutorial-deploy', description: '', role_ids: ['mock-role-member'], ...overrides });

function tutorial(method: string, path: string, body: unknown = null) {
	return mockIdentityAdmin(method, path, new URLSearchParams(), body, 'on', 'mock-project-1');
}
function admin(method: string, path: string, body: unknown = null, params = DOMAIN) {
	return mockIdentityAdmin(method, path, params, body, 'admin');
}
function codeOf(run: () => unknown): string | undefined {
	try { run(); } catch (error) { if (error instanceof ApiError) return error.code ?? `status-${error.status}`; throw error; }
	return undefined;
}
function statusOf(run: () => unknown): number | undefined {
	try { run(); } catch (error) { if (error instanceof ApiError) return error.status; throw error; }
	return undefined;
}

beforeEach(() => resetMockupState());

describe('mockIdentityAdmin personal MCP keys', () => {
	it('issues a key once with its secret, then revokes only that key', () => {
		const issued = tutorial('POST', TOKENS, token({ name: '  tutorial-agent  ' })) as { id: string; token: string; name: string; projects: { id: string }[]; owner_project_id: string; status: string };
		expect(issued).toMatchObject({ name: 'tutorial-agent', owner_project_id: 'mock-project-1', status: 'active', projects: [{ id: 'mock-project-1' }] });
		expect(issued.token).toMatch(/^sk-afgl-mock-/);
		const state = getMockupState();
		expect(state.mcpAccess.personalTokens.find((item) => item.id === issued.id)).not.toHaveProperty('token');
		expect(tutorial('DELETE', `${TOKENS}/${issued.id}`)).toEqual({});
		expect(state.mcpAccess.personalTokens.find((item) => item.id === issued.id)?.status).toBe('revoked');
		expect(state.mcpAccess.personalTokens.find((item) => item.id === 'mock-mcp-token-lumen')?.status).toBe('active');
		expect(statusOf(() => tutorial('DELETE', `${TOKENS}/${issued.id}`))).toBe(404);
		expect(statusOf(() => tutorial('DELETE', `${TOKENS}/unknown`))).toBe(404);
	});

	it('allows repeated names like the real API and supports all/current/non-expiring scopes', () => {
		const first = tutorial('POST', TOKENS, token({ name: 'Lumen' })) as { id: string };
		const all = tutorial('POST', TOKENS, token({ name: 'Lumen', project_scope: 'all', project_ids: [], non_expiring: true, expires_at: undefined })) as { id: string; projects: unknown[]; expires_at: string | null };
		expect(all.id).not.toBe(first.id);
		expect(all.projects).toHaveLength(getMockupState().projects.length);
		expect(all.expires_at).toBeNull();
		expect(tutorial('POST', TOKENS, { name: 'current', access_level: 'manage' })).toMatchObject({ project_scope: 'current', project_ids: ['mock-project-1'] });
	});

	it('rejects invalid input the way the backend does', () => {
		for (const [payload, status] of [
			[token({ name: '' }), 422], [token({ name: '   ' }), 400], [token({ name: 'x'.repeat(101) }), 422],
			[token({ access_level: 'admin' }), 422], [token({ non_expiring: true }), 422], [token({ non_expiring: 'yes' }), 422],
			[token({ expires_at: '2020-01-01T00:00:00Z' }), 400], [token({ expires_at: inMonths(14) }), 400], [token({ expires_at: '2027-01-01T00:00:00' }), 400],
			[token({ project_scope: 'domain' }), 422], [token({ project_ids: [] }), 400], [token({ project_ids: ['mock-project-1', 'mock-project-1'] }), 400],
			[token({ project_ids: ['not-a-member'] }), 400], [token({ project_scope: 'all', project_ids: ['mock-project-1'] }), 400],
			[token({ project_scope: 'current', project_ids: ['mock-project-2'] }), 400],
		] as const) expect(statusOf(() => tutorial('POST', TOKENS, payload)), JSON.stringify(payload)).toBe(status);
		expect(getMockupState().mcpAccess.personalTokens).toHaveLength(1);
	});

	it('caps active personal keys per issuing project', () => {
		for (let index = 0; index < 9; index += 1) tutorial('POST', TOKENS, token({ name: `key-${index}` }));
		expect(statusOf(() => tutorial('POST', TOKENS, token()))).toBe(409);
	});

	it('leaves list, Lumen default, verify, consent and other profiles to the transport', () => {
		expect(tutorial('GET', TOKENS)).toBeUndefined();
		expect(tutorial('DELETE', `${TOKENS}/lumen-default`)).toBeUndefined();
		expect(tutorial('PUT', `${TOKENS}/mock-mcp-token-lumen/lumen-default`)).toBeUndefined();
		expect(tutorial('POST', `${TOKENS}/verify`, { token: 'x' })).toBeUndefined();
		expect(tutorial('POST', '/api/v1/auth/mcp-oauth/consents/ticket/approve', {})).toBeUndefined();
		expect(mockIdentityAdmin('POST', TOKENS, new URLSearchParams(), token(), 'admin')).toBeUndefined();
	});
});

describe('mockIdentityAdmin application credentials', () => {
	it('serves the caller context and lists only the selected user', () => {
		expect(admin('GET', `${CREDS}/context`)).toMatchObject({ domain_id: 'mock-domain', user_id: 'mock-admin-1', project_id: 'mock-admin-project', roles: expect.arrayContaining([{ id: 'mock-role-member', name: 'member' }]) });
		expect((admin('GET', CREDS) as { items: ApplicationCredential[] }).items.map((item) => item.name)).toEqual(['ci-deploy']);
		expect((admin('GET', CREDS, null, new URLSearchParams({ domain_id: 'mock-domain', user_id: 'mock-user-2' })) as { items: unknown[] }).items).toEqual([]);
	});

	it('creates a credential with a one-time secret, rejects duplicates and deletes only it', () => {
		const created = admin('POST', CREDS, credential({ expires_at: inMonths(2), role_ids: ['mock-role-member', 'mock-role-member'] })) as ApplicationCredentialIssued;
		expect(created).toMatchObject({ name: 'tutorial-deploy', user_id: 'mock-admin-1', project_id: 'mock-admin-project', domain_id: 'mock-domain', unrestricted: false, roles: [{ id: 'mock-role-member', name: 'member' }] });
		expect(created.secret).toMatch(/^mock-app-cred-secret-/);
		expect(admin('GET', `${CREDS}/${created.id}`)).not.toHaveProperty('secret');
		expect(codeOf(() => admin('POST', CREDS, credential()))).toBe('credential_conflict');
		admin('DELETE', `${CREDS}/${created.id}`);
		expect((admin('GET', CREDS) as { items: ApplicationCredential[] }).items.map((item) => item.id)).toEqual(['mock-app-cred-1']);
		expect(codeOf(() => admin('DELETE', `${CREDS}/${created.id}`))).toBe('credential_not_found');
	});

	it('rejects invalid input, foreign roles, domains and users with credential codes', () => {
		for (const payload of [
			credential({ name: '' }), credential({ role_ids: [] }), credential({ role_ids: ['bad id'] }), credential({ description: 'x'.repeat(4097) }),
			credential({ expires_at: '2020-01-01T00:00:00Z' }), credential({ expires_at: '2027-01-01T00:00:00' }), credential({ unrestricted: true }), null,
		]) expect(codeOf(() => admin('POST', CREDS, payload)), JSON.stringify(payload)).toBe('credential_invalid_input');
		expect(codeOf(() => admin('POST', CREDS, credential({ role_ids: ['mock-role-owner'] })))).toBe('credential_scope_denied');
		expect(codeOf(() => admin('GET', CREDS, null, new URLSearchParams()))).toBe('credential_invalid_input');
		expect(codeOf(() => admin('GET', CREDS, null, new URLSearchParams({ domain_id: 'other-domain' })))).toBe('credential_not_found');
		expect(codeOf(() => admin('GET', CREDS, null, new URLSearchParams({ domain_id: 'mock-domain', user_id: 'stranger' })))).toBe('credential_scope_denied');
		expect((admin('GET', CREDS) as { items: unknown[] }).items).toHaveLength(1);
	});

	it('ignores other paths, methods and the tutorial profile', () => {
		expect(admin('GET', '/api/v1/admin/user-credentials')).toBeUndefined();
		expect(admin('PATCH', `${CREDS}/mock-app-cred-1`, {})).toBeUndefined();
		expect(admin('GET', '/api/v1/admin/users')).toBeUndefined();
		expect(mockIdentityAdmin('GET', CREDS, DOMAIN, null, 'on')).toBeUndefined();
	});
});
