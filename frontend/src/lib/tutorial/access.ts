import { get } from 'svelte/store';
import { auth, authReady, isMockAuthActive, logoutInProgress, projectSwitching } from '$lib/stores/auth';

/**
 * Tours that act on real administrator authority. They have no tutorial fixtures: the synthetic
 * tutorial admin (`mockup/auth.ts`) carries `isSystemAdmin: true`, so the role flag alone must never open them.
 */
export const REAL_ADMIN_TOUR_IDS: Readonly<Record<string, true>> = {
	'admin-system-admins': true,
	'admin-user-credentials': true,
	'admin-settings': true,
};

/** A live, verified system administrator session (never the tutorial profile). */
export function isRealAdminSession(): boolean {
	if (isMockAuthActive()) return false;
	const state = get(auth);
	return (
		state.token !== null
		&& state.isSystemAdmin === true
		&& get(authReady)
		&& !get(projectSwitching)
		&& !get(logoutInProgress)
	);
}

/** Single start gate for the button, `?tour=` links and saved-tour resume. */
export function canStartTour(tourId: string): boolean {
	const realAdminTour = Object.hasOwn(REAL_ADMIN_TOUR_IDS, tourId);
	return isMockAuthActive() ? !realAdminTour : realAdminTour && isRealAdminSession();
}
