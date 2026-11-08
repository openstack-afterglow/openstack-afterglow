import { afterEach, describe, expect, it } from 'vitest';
import { get } from 'svelte/store';
import { auth, authReady, enterMockAuth, exitMockAuth, projectSwitching, setLoginAuth } from '$lib/stores/auth';
import { buildMockAuth } from '$lib/mockup/auth';
import { canStartTour, isRealAdminSession } from '../access';

function signInReal(isSystemAdmin: boolean): void {
	exitMockAuth();
	setLoginAuth({ token: 'real-token', userId: 'u1', username: 'real', isSystemAdmin });
	authReady.set(true);
}

afterEach(() => {
	exitMockAuth();
	authReady.set(false);
	projectSwitching.set(false);
});

describe('real administrator tour gate', () => {
	it('refuses the synthetic tutorial admin even though it carries isSystemAdmin', () => {
		enterMockAuth(buildMockAuth('admin', '/admin/system-admins'), 'admin');
		expect(get(auth).isSystemAdmin).toBe(true);
		expect(isRealAdminSession()).toBe(false);
		expect(canStartTour('admin-system-admins')).toBe(false);
		expect(canStartTour('admin-user-credentials')).toBe(false);
		expect(canStartTour('admin-settings')).toBe(false);
	});

	it('opens for a verified real system administrator', () => {
		signInReal(true);
		expect(canStartTour('admin-system-admins')).toBe(true);
	});

	it('refuses a real non-administrator, an unverified session and a project switch', () => {
		signInReal(false);
		expect(canStartTour('admin-settings')).toBe(false);
		signInReal(true);
		authReady.set(false);
		expect(canStartTour('admin-settings')).toBe(false);
		authReady.set(true);
		projectSwitching.set(true);
		expect(canStartTour('admin-settings')).toBe(false);
	});

	it('never restricts ordinary tours, including in the tutorial profile', () => {
		enterMockAuth(buildMockAuth('admin', '/admin/projects'), 'admin');
		expect(canStartTour('admin-projects')).toBe(true);
		expect(canStartTour('vm-create')).toBe(true);
	});

	it('limits every tour outside the tutorial profile to the real administrator tours', () => {
		signInReal(true);
		expect(canStartTour('admin-projects')).toBe(false);
		expect(canStartTour('admin-domains')).toBe(false);
		expect(canStartTour('admin-user-credentials')).toBe(true);
		signInReal(false);
		expect(canStartTour('vm-create')).toBe(false);
	});
});
