import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { ApiError } from '$lib/api/errors';
import type { AdminDomain } from '$lib/api/domains';
import type { ManagedRole } from '$lib/components/admin/roles/types';
import { mockAdminRolesDomains } from './adminRolesDomains';
import { maybeMockJson } from './transport';
import { resetMockupState } from './state';

// The pages send the tutorial administrator's token and its own project; neither page adds a domain query.
const TOKEN = 'mock-token-admin';
const PROJECT = 'mock-admin-project';
const admin = (method: string, path: string, body: unknown = null) => mockAdminRolesDomains(method, path, body, 'admin');
const roles = () => admin('GET', '/api/v1/admin/roles') as ManagedRole[];
const domains = () => (admin('GET', '/api/v1/admin/domains') as { items: AdminDomain[] }).items;
const status = (call: () => unknown) => {
	try { call(); } catch (error) { return error instanceof ApiError ? error.status : -1; }
	return 0;
};

describe('mockAdminRolesDomains roles', () => {
	beforeEach(() => {
		resetMockupState();
		window.history.replaceState({}, '', '/admin/roles?tutorial=admin');
	});
	afterEach(() => window.history.replaceState({}, '', '/'));

	it('derives the backend catalog flags and links', () => {
		const byName = new Map(roles().map((role) => [role.name, role]));
		expect(byName.get('admin')).toMatchObject({ protected: true, system_only: true, assignable: false, inherited_role_ids: ['mock-role-manager', 'mock-role-member', 'mock-role-reader'] });
		expect(byName.get('reader')).toMatchObject({ protected: true, system_only: false, parent_role_ids: ['mock-role-member'] });
		expect(byName.get('member')?.parent_role_ids).toEqual(['mock-role-manager', 'mock-role-project-member']);
		expect(byName.get('lumen_reader')).toMatchObject({ retired: true, assignable: false, protected: false });
		expect(byName.get('ops-audit_reader')).toMatchObject({ protected: false, retired: false, implied_role_ids: [], parent_role_ids: [] });
	});

	it('creates and deletes the exact role the page sends through the transport', async () => {
		const before = roles();
		// RoleMetadataModal sends the composed name, the description and domain_id null for a global role.
		const created = await maybeMockJson<ManagedRole>('POST', '/api/v1/admin/roles', { name: 'tut-role_viewer', description: '', domain_id: null }, TOKEN, PROJECT) as ManagedRole;
		expect(created).toMatchObject({ name: 'tut-role_viewer', domain_id: null, protected: false, retired: false, system_only: false, implied_role_ids: [], parent_role_ids: [] });
		const listed = await maybeMockJson<ManagedRole[]>('GET', '/api/v1/admin/roles', undefined, TOKEN, PROJECT) as ManagedRole[];
		expect(listed.map((role) => role.id)).toEqual([...before.map((role) => role.id), created.id]);
		// The project access modal reads the same catalog with a domain query.
		expect((await maybeMockJson<ManagedRole[]>('GET', '/api/v1/admin/roles?domain_id=mock-domain', undefined, TOKEN, PROJECT) as ManagedRole[]).map((role) => role.id)).toEqual(listed.map((role) => role.id));
		expect(await maybeMockJson('DELETE', `/api/v1/admin/roles/${encodeURIComponent(created.id)}`, undefined, TOKEN, PROJECT)).toEqual({ status: 'deleted' });
		expect(roles()).toEqual(before);
		expect(status(() => admin('DELETE', `/api/v1/admin/roles/${created.id}`))).toBe(404);
	});

	it('never deletes native, retired, linked or seed roles', async () => {
		expect(status(() => admin('DELETE', '/api/v1/admin/roles/mock-role-reader'))).toBe(409);
		expect(status(() => admin('DELETE', '/api/v1/admin/roles/mock-role-project-member'))).toBe(409);
		expect(admin('DELETE', '/api/v1/admin/roles/mock-role-retired-lumen')).toBeUndefined();
		expect(admin('DELETE', '/api/v1/admin/roles/mock-role-ops-audit')).toBeUndefined();
		await expect(maybeMockJson('DELETE', '/api/v1/admin/roles/mock-role-ops-audit', undefined, TOKEN, PROJECT)).rejects.toMatchObject({ status: 409 });
		await expect(maybeMockJson('DELETE', '/api/v1/admin/roles/mock-role-retired-lumen', undefined, TOKEN, PROJECT)).rejects.toMatchObject({ status: 409 });
		expect(roles()).toHaveLength(7);
	});

	it('validates names like the backend and keeps unsupported role writes fail-closed', async () => {
		expect(status(() => admin('POST', '/api/v1/admin/roles', { name: 'Member', description: '' }))).toBe(409);
		expect(status(() => admin('POST', '/api/v1/admin/roles', { name: 'OPS-AUDIT_reader', description: '' }))).toBe(409);
		expect(status(() => admin('POST', '/api/v1/admin/roles', { name: 'lumen_reader', description: '' }))).toBe(422);
		expect(status(() => admin('POST', '/api/v1/admin/roles', { name: 'no-grade', description: '' }))).toBe(422);
		expect(status(() => admin('POST', '/api/v1/admin/roles', { name: 'tut_role', description: '', extra: true }))).toBe(422);
		expect(status(() => admin('POST', '/api/v1/admin/roles', { name: 'tut-role_viewer', description: '', domain_id: 'missing-domain' }))).toBe(404);
		expect(admin('POST', '/api/v1/admin/roles', { name: 'Tut Role_Viewer', description: '', domain_id: 'mock-domain' })).toMatchObject({ name: 'tut-role_viewer', domain_id: 'mock-domain' });
		await expect(maybeMockJson('PATCH', '/api/v1/admin/roles/mock-role-ops-audit', { description: 'x' }, TOKEN, PROJECT)).rejects.toMatchObject({ status: 409 });
		await expect(maybeMockJson('PUT', '/api/v1/admin/roles/mock-role-ops-audit/implies/mock-role-reader', {}, TOKEN, PROJECT)).rejects.toMatchObject({ status: 409 });
		await expect(maybeMockJson('POST', '/api/v1/admin/roles/presets/apply', {}, TOKEN, PROJECT)).rejects.toMatchObject({ status: 409 });
		expect(mockAdminRolesDomains('GET', '/api/v1/admin/roles', null, 'on')).toBeUndefined();
	});
});

describe('mockAdminRolesDomains domains', () => {
	beforeEach(() => {
		resetMockupState();
		window.history.replaceState({}, '', '/admin/domains?tutorial=admin');
	});
	afterEach(() => window.history.replaceState({}, '', '/'));

	it('creates then disables the exact domain draft the page sends through the transport', async () => {
		expect(domains()).toEqual([{ id: 'mock-domain', name: 'Demo', enabled: true, description: '' }]);
		const created = await maybeMockJson<AdminDomain>('POST', '/api/v1/admin/domains', { name: 'tut-domain', description: '', enabled: true }, TOKEN, PROJECT) as AdminDomain;
		expect(created).toEqual({ id: expect.any(String), name: 'tut-domain', description: '', enabled: true, kind: 'organization' });
		const listed = await maybeMockJson<{ items: AdminDomain[] }>('GET', '/api/v1/admin/domains', undefined, TOKEN, PROJECT) as { items: AdminDomain[] };
		expect(listed.items.map((domain) => domain.name)).toEqual(['Demo', 'tut-domain']);
		// The edit dialog resends the whole draft with enabled cleared.
		const updated = await maybeMockJson<AdminDomain>('PATCH', `/api/v1/admin/domains/${encodeURIComponent(created.id)}`, { name: 'tut-domain', description: '', enabled: false }, TOKEN, PROJECT);
		expect(updated).toMatchObject({ id: created.id, enabled: false });
		expect(domains().find((domain) => domain.id === created.id)?.enabled).toBe(false);
	});

	it('keeps the seed domain unchanged and validates input', async () => {
		expect(admin('PATCH', '/api/v1/admin/domains/mock-domain', { name: 'Demo', description: '', enabled: false })).toBeUndefined();
		await expect(maybeMockJson('PATCH', '/api/v1/admin/domains/mock-domain', { name: 'Demo', description: '', enabled: false }, TOKEN, PROJECT)).rejects.toMatchObject({ status: 409 });
		expect(domains()[0].enabled).toBe(true);
		expect(status(() => admin('PATCH', '/api/v1/admin/domains/missing', { enabled: false }))).toBe(404);
		expect(status(() => admin('POST', '/api/v1/admin/domains', { name: '  ', description: '', enabled: true }))).toBe(422);
		expect(status(() => admin('POST', '/api/v1/admin/domains', { name: 'x'.repeat(65), description: '', enabled: true }))).toBe(422);
		expect(status(() => admin('POST', '/api/v1/admin/domains', { name: 'tut-domain', kind: 'account' }))).toBe(422);
		const created = admin('POST', '/api/v1/admin/domains', { name: 'tut-domain', description: '', enabled: true }) as AdminDomain;
		expect(status(() => admin('PATCH', `/api/v1/admin/domains/${created.id}`, {}))).toBe(422);
		// Compute pool reads under a domain stay with their own handler.
		expect(admin('GET', '/api/v1/admin/domains/mock-domain/compute-pool')).toBeUndefined();
	});
});
