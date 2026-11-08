import { describe, expect, it, beforeEach } from 'vitest';
import { ApiError } from '$lib/api/errors';
import { mockIdentity } from './identity';
import { getMockupState, resetMockupState } from './state';

type Report = { project_id: string; can_delete: boolean; resources: { kind: string; count: number }[] };
const none = new URLSearchParams();

function names(): string[] {
	return (mockIdentity('GET', '/api/v1/iam/projects', none, null, 'on') as { items: { name: string; domain_id: string }[] }).items.map((item) => item.name);
}
function create(name: string, domain = 'mock-domain'): { id: string; name: string } {
	return mockIdentity('POST', '/api/v1/projects', none, { name, description: 'qa', domain_id: domain }, 'on') as { id: string; name: string };
}

describe('mockIdentity project lifecycle', () => {
	beforeEach(() => resetMockupState());

	it('grants organization project management for the tutorial domain only', () => {
		expect(mockIdentity('GET', '/api/v1/projects/capabilities', new URLSearchParams('domain_id=mock-domain'), null, 'on')).toEqual({ domain_id: 'mock-domain', domain_kind: 'organization', is_domain_manager: true, can_create_project: true });
		expect(() => mockIdentity('GET', '/api/v1/projects/capabilities', new URLSearchParams('domain_id=other'), null, 'on')).toThrow(ApiError);
	});

	it('lists a created project and exposes it in the shared project list', () => {
		const before = names();
		const project = create(' qa-team ');
		expect(project.name).toBe('qa-team');
		expect(names()).toEqual([...before, 'qa-team']);
		expect(getMockupState().projects.some((item) => item.id === project.id)).toBe(true);
	});

	it('rejects empty, reserved, duplicate and foreign-domain creation', () => {
		create('qa-team');
		for (const [name, domain, status] of [['  ', 'mock-domain', 422], ['Default', 'mock-domain', 409], ['QA-TEAM', 'mock-domain', 409], ['other', 'foreign', 403]] as const) {
			try { create(name, domain); throw new Error('accepted'); }
			catch (cause) { expect(cause instanceof ApiError && cause.status).toBe(status); }
		}
		expect(names().filter((name) => name.toLowerCase() === 'qa-team')).toHaveLength(1);
	});

	it('reports a created project empty and deletes it', () => {
		const { id } = create('qa-team');
		const report = mockIdentity('GET', `/api/v1/projects/${encodeURIComponent(id)}/deletion-check`, none, null, 'on') as Report;
		expect(report.project_id).toBe(id);
		expect(report.can_delete).toBe(true);
		expect(report.resources.every((row) => row.count === 0)).toBe(true);
		mockIdentity('DELETE', `/api/v1/projects/${encodeURIComponent(id)}`, none, null, 'on');
		expect(names()).not.toContain('qa-team');
		expect(() => mockIdentity('DELETE', `/api/v1/projects/${encodeURIComponent(id)}`, none, null, 'on')).toThrow(ApiError);
	});

	it('refuses to delete the selected project that still owns resources', () => {
		const selected = getMockupState().selectedProjectId;
		const report = mockIdentity('GET', `/api/v1/projects/${selected}/deletion-check`, none, null, 'on') as Report;
		expect(report.can_delete).toBe(false);
		expect(() => mockIdentity('DELETE', `/api/v1/projects/${selected}`, none, null, 'on')).toThrow(ApiError);
		expect(getMockupState().projects.some((item) => item.id === selected)).toBe(true);
	});

	it('returns undefined for unowned paths and the admin profile', () => {
		expect(mockIdentity('GET', '/api/v1/projects/current/permissions', none, null, 'on')).toBeUndefined();
		expect(mockIdentity('GET', '/api/v1/projects/mock-project-1/members', none, null, 'on')).toBeUndefined();
		expect(mockIdentity('GET', '/api/v1/iam/projects', none, null, 'admin')).toBeUndefined();
	});
});
