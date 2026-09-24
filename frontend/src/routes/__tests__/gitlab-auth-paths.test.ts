// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const loginRouteSource = readFileSync(resolve(__dirname, '../login/+page.svelte'), 'utf8');
const loginComponentSource = readFileSync(resolve(__dirname, '../../lib/components/auth/LoginPage.svelte'), 'utf8');
const loginSource = `${loginRouteSource}\n${loginComponentSource}`;
const callbackSource = readFileSync(resolve(__dirname, '../auth/gitlab/callback/+page.svelte'), 'utf8');

describe('GitLab auth route/API path contract', () => {
	it('keeps browser page routes public while calling the v1 backend API', () => {
		expect(loginSource).toContain("api.get<{ enabled: boolean }>('/api/v1/auth/gitlab/enabled')");
		expect(loginSource).toContain("api.get<{ authorize_url: string }>('/api/v1/auth/gitlab/authorize')");
		expect(callbackSource).toContain("history.replaceState(null, '', '/auth/gitlab/callback')");
		expect(callbackSource).toContain("api.post<LoginResponse>('/api/v1/auth/gitlab/callback', { code, state })");
		expect(callbackSource).toContain('href="/login"');
	});

	it('does not call the UI callback route as a backend API endpoint', () => {
		expect(loginSource).not.toMatch(/api\.(?:get|post)<[^>]*>\('\/auth\/gitlab\//);
		expect(callbackSource).not.toMatch(/api\.(?:get|post)<[^>]*>\('\/auth\/gitlab\//);
	});
	it('routes post-login project selection through the shared helper without prefetching projects', () => {
		expect(callbackSource).toContain('resolvePostLoginProject(data)');
		expect(callbackSource).not.toContain('/api/v1/auth/projects');
	});
});
