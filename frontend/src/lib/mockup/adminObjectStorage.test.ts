import { beforeEach, describe, expect, it } from 'vitest';
import { ApiError } from '$lib/api/errors';
import type { SwiftContainer } from '$lib/types/common';
import { mockAdminObjectStorage } from './adminObjectStorage';
import { buildMockAuth } from './auth';
import { getMockupState, resetMockupState } from './state';

const none = new URLSearchParams();
// The admin page sends its signed-in $auth.projectId with every bucket mutation.
const pageProject = buildMockAuth('admin', '/admin').projectId!;
const admin = (method: string, path: string, body: unknown = null, project?: string, params = none) => mockAdminObjectStorage(method, path, params, body, 'admin', project);
const inventory = (params = none) => (admin('GET', '/api/v1/admin/object-storage', null, undefined, params) as { items: SwiftContainer[] }).items;

describe('mockAdminObjectStorage', () => {
	beforeEach(() => resetMockupState());

	it('creates a bucket in the page project and soft deletes only it', () => {
		const tenant = getMockupState().selectedProjectId;
		expect(inventory()).toEqual([expect.objectContaining({ name: 'sample-artifacts', project_id: tenant })]);
		admin('POST', '/api/v1/object-storage', { name: 'tut-bucket' }, pageProject);
		expect(inventory()).toEqual([
			expect.objectContaining({ name: 'sample-artifacts', project_id: tenant }),
			expect.objectContaining({ name: 'tut-bucket', project_id: pageProject, project_name: 'Admin Demo Project' }),
		]);
		admin('DELETE', '/api/v1/object-storage/tut-bucket', null, pageProject);
		const [sample, created] = inventory();
		expect(sample.is_deleted).toBeUndefined();
		expect(created).toMatchObject({ name: 'tut-bucket', project_id: pageProject, is_deleted: true });
		expect(getMockupState().objectContainers.map((item) => item.name)).toEqual(['sample-artifacts']);
		expect(() => admin('DELETE', '/api/v1/object-storage/tut-bucket', null, pageProject)).toThrow(ApiError);
	});

	it('refuses duplicates, foreign accounts and foreign domains', () => {
		admin('POST', '/api/v1/object-storage', { name: 'tut-bucket' }, pageProject);
		expect(() => admin('POST', '/api/v1/object-storage', { name: 'tut-bucket' }, pageProject)).toThrow(ApiError);
		expect(() => admin('POST', '/api/v1/object-storage', { name: 'other-bucket' }, 'foreign')).toThrow(ApiError);
		expect(() => admin('DELETE', '/api/v1/object-storage/sample-artifacts', null, getMockupState().selectedProjectId)).toThrow(ApiError);
		expect(inventory(new URLSearchParams({ project_id: pageProject })).map((item) => item.name)).toEqual(['tut-bucket']);
		expect(inventory(new URLSearchParams({ project_id: 'foreign' }))).toEqual([]);
		expect(() => inventory(new URLSearchParams({ domain_id: 'other' }))).toThrow(ApiError);
	});

	it('ignores other profiles and paths', () => {
		expect(mockAdminObjectStorage('POST', '/api/v1/object-storage', none, { name: 'x-bucket' }, 'on', pageProject)).toBeUndefined();
		expect(admin('GET', '/api/v1/object-storage')).toBeUndefined();
		expect(admin('DELETE', '/api/v1/object-storage/trash/containers/sample-artifacts')).toBeUndefined();
	});
});
