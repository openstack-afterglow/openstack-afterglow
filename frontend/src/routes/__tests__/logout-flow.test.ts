import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const repoRoot = resolve(__dirname, '../../..');
const readSource = (path: string) => readFileSync(resolve(repoRoot, path), 'utf8');

const layoutSource = readSource('src/routes/+layout.svelte');
const selectProjectSource = readSource('src/routes/select-project/+page.svelte');
const loginRouteSource = readSource('src/routes/login/+page.svelte');
const loginComponentSource = readSource('src/lib/components/auth/LoginPage.svelte');
const securitySectionSource = readSource('src/lib/components/account/SecuritySection.svelte');
const loginSource = `${loginRouteSource}\n${loginComponentSource}`;

describe('logout flow source contracts', () => {
	it('keeps confirmed real-session logout on the login page with history replacement in both logged-in exit points', () => {
		for (const source of [layoutSource, selectProjectSource]) {
			expect(source).toContain("confirmDialog('로그아웃하시겠습니까?')");
			expect(source).toContain("mockLogout ? '/login?tutorial=off' : '/login'");
			expect(source).toContain("toast.success('정상적으로 로그아웃 되었습니다.')");
		}
	});

	it('keeps logout completion UI out of the login page source', () => {
		expect(loginSource).not.toContain('logged_out');
		expect(loginSource).not.toContain('<Alert tone="success">로그아웃되었습니다.</Alert>');
	});


	it('sends last-session deletion and logout-all from security settings to the login page', () => {
		expect(securitySectionSource).toContain("await goto('/login', { replaceState: true })");
		expect(securitySectionSource).toContain("goto('/login', { replaceState: true }).finally(() => logoutInProgress.set(false))");
		expect(securitySectionSource).not.toContain("goto('/')");
		expect(securitySectionSource).toContain('logoutInProgress.set(true);');
	});

	it('clears mock auth before routing explicit logout to the login page', () => {
		for (const source of [layoutSource, selectProjectSource]) {
			expect(source).toContain('const mockLogout = isMockAuthActive();');
			expect(source).toContain('exitMockAuth();');
			expect(source).toContain('clearAuth();');
			expect(source).toContain("mockLogout ? '/login?tutorial=off' : '/login'");
		}
	});


	it('fences new refreshes and revokes the latest token before explicit logout', () => {
		for (const source of [layoutSource, selectProjectSource]) {
			expect(source).toContain('const pendingRefresh = beginSessionRevocation();');
			expect(source).toContain('await pendingRefresh;');
			expect(source).toContain('const logoutToken = $auth.token;');
			expect(source).toContain('endSessionRevocation();');
			expect(source).toContain("await api.post('/api/v1/auth/logout', {}, logoutToken");
		}
		expect(securitySectionSource).toContain('const pendingRefresh = beginSessionRevocation();');
		expect(securitySectionSource).toContain('await pendingRefresh;');
		expect(securitySectionSource).toContain('const logoutToken = $auth.token;');
		expect(securitySectionSource).toContain("await api.post('/api/v1/auth/logout-all', {}, logoutToken ?? undefined, projectId);");
		expect(securitySectionSource).toContain('endSessionRevocation();');
	});
	it('keeps the layout logout guard suppressed during redirect and renders toast outside the logged-in confirm block', () => {
		expect(layoutSource).toContain('if (!$logoutInProgress && !$isLoggedIn');
		expect(layoutSource).toContain("goto('/login', { replaceState: true });");

		const loggedInBlockStart = layoutSource.indexOf('{#if $isLoggedIn}');
		const confirmDialogIndex = layoutSource.indexOf('<ConfirmDialog />');
		const loggedInBlockEnd = layoutSource.indexOf('{/if}', confirmDialogIndex);
		const toastIndex = layoutSource.indexOf('<Toast />');

		expect(loggedInBlockStart).toBeGreaterThan(-1);
		expect(confirmDialogIndex).toBeGreaterThan(loggedInBlockStart);
		expect(loggedInBlockEnd).toBeGreaterThan(confirmDialogIndex);
		expect(toastIndex).toBeGreaterThan(loggedInBlockEnd);
	});
});
