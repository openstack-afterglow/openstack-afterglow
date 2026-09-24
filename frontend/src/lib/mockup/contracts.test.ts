// @vitest-environment node
import { describe, expect, it } from 'vitest';

import { ADMIN_ALLOWED_PATHS, getMockupHomePath, isMockupPathAllowed } from './contracts';

const ADMIN_TOUR_PATHS = [
	'/admin/instances',
	'/admin/volumes',
	'/admin/libraries',
	'/admin/topology',
	'/admin/containers',
	'/admin/secrets',
	'/admin/monitoring',
	'/admin/services',
	'/admin/users',
] as const;

describe('administrator mockup route contract', () => {
	it('allows only the administrator landing page and the nine guided-tour sections', () => {
		expect(ADMIN_ALLOWED_PATHS).toEqual(['/', '/login', '/admin', ...ADMIN_TOUR_PATHS]);
		expect(getMockupHomePath('admin')).toBe('/admin');
		for (const path of ADMIN_TOUR_PATHS) expect(isMockupPathAllowed('admin', path)).toBe(true);
	});

	it.each([
		'/dashboard',
		'/admin/instances/mock-instance-1',
		'/admin/volumes/mock-admin-volume-available',
		'/admin/services/compute',
		'/admin/users/mock-user-1',
		'/admin/instances-near-prefix',
	])('rejects unsupported and near-prefix path %s', (path) => {
		expect(isMockupPathAllowed('admin', path)).toBe(false);
	});
});

describe('tutorial OAuth consent route contract', () => {
	it('allows the local consent handoff without widening administrator routes', () => {
		expect(isMockupPathAllowed('on', '/oauth/mcp/authorize')).toBe(true);
		expect(isMockupPathAllowed('admin', '/oauth/mcp/authorize')).toBe(false);
	});
});
