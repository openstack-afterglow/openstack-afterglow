import { derived, get, readable, type Readable } from 'svelte/store';
import * as authStores from '$lib/stores/auth';

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
	if (!Object.hasOwn(authStores, 'isMockAuthActive') || authStores.isMockAuthActive()) return false;
	if (
		!Object.hasOwn(authStores, 'auth')
		|| !Object.hasOwn(authStores, 'authReady')
		|| !Object.hasOwn(authStores, 'projectSwitching')
		|| !Object.hasOwn(authStores, 'logoutInProgress')
	) return false;
	const state = get(authStores.auth);
	return (
		state.token !== null
		&& state.isSystemAdmin === true
		&& get(authStores.authReady)
		&& !get(authStores.projectSwitching)
		&& !get(authStores.logoutInProgress)
	);
}

/** Single start gate for the button, `?tour=` links and saved-tour resume. */
export function canStartTour(tourId: string): boolean {
	const realAdminTour = Object.hasOwn(REAL_ADMIN_TOUR_IDS, tourId);
	const mockAuth = Object.hasOwn(authStores, 'isMockAuthActive') ? authStores.isMockAuthActive() : true;
	return mockAuth ? !realAdminTour : realAdminTour && isRealAdminSession();
}

/** Reactive presentation gate shared by launchers and route-level layout wrappers. */
export function tourAvailability(tourId: string): Readable<boolean> {
	const stores: Readable<unknown>[] = [];
	if (Object.hasOwn(authStores, 'auth')) stores.push(authStores.auth as Readable<unknown>);
	if (Object.hasOwn(authStores, 'authReady')) stores.push(authStores.authReady as Readable<unknown>);
	if (Object.hasOwn(authStores, 'projectSwitching')) stores.push(authStores.projectSwitching as Readable<unknown>);
	if (Object.hasOwn(authStores, 'logoutInProgress')) stores.push(authStores.logoutInProgress as Readable<unknown>);
	return derived(stores.length > 0 ? stores : readable(null), () => canStartTour(tourId));
}
