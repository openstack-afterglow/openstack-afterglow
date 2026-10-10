import { derived, readable } from 'svelte/store';
import { auth, authReady, projectSwitching } from './auth';
import { t } from '$lib/i18n/ns/account';
import { api } from '$lib/api/client';

export interface ProjectPermissions {
	is_owner: boolean;
	is_manager: boolean;
	can_write: boolean;
	service_permissions: Record<string, string[]>;
}
export interface PermissionState {
	permissions: ProjectPermissions | null;
	loading: boolean;
	error: string;
}
const empty: PermissionState = { permissions: null, loading: false, error: '' };
let refresh: (() => Promise<void>) | null = null;

// Never hydrate service authority from local storage or projected role names.
export const projectPermissions = readable<PermissionState>(empty, (set) => {
	let generation = 0;
	let current: { token: string; projectId: string; userId: string | null } | null = null;
	async function load() {
		const scope = current;
		if (!scope) return;
		const request = ++generation;
		set({ permissions: null, loading: true, error: '' });
		try {
			const permissions = await api.get<ProjectPermissions>('/api/v1/projects/current/permissions', scope.token, scope.projectId, { refresh: true });
			if (current === scope && request === generation) set({ permissions, loading: false, error: '' });
		} catch (error) {
			if (current === scope && request === generation) set({ permissions: null, loading: false, error: error instanceof Error ? error.message : t('projectSettings.permissionsFailed') });
		}
	}
	refresh = load;
	const unsubscribe = derived([auth, authReady, projectSwitching], ([state, ready, switching]) =>
		ready && !switching && state.token && state.projectId
			? { token: state.token, projectId: state.projectId, userId: state.userId } : null
	).subscribe((scope) => {
		if (scope && current && scope.token === current.token && scope.projectId === current.projectId && scope.userId === current.userId) return;
		current = scope;
		++generation;
		set(empty);
		if (scope) void load();
	});
	return () => { current = null; ++generation; refresh = null; unsubscribe(); };
});

export async function refreshProjectPermissions(): Promise<void> { await refresh?.(); }

const serviceAuthority = derived(
	[projectPermissions, auth, authReady, projectSwitching],
	([state, identity, ready, switching]) => {
		const active = ready && !switching && !!identity.token && !!identity.projectId && !state.loading && !state.error && state.permissions !== null;
		const leaves = new Set(Object.values(state.permissions?.service_permissions ?? {}).flat());
		return {
			can: (leaf: string): boolean => active && leaves.has(leaf),
			denied: (leaf: string): boolean => active && !leaves.has(leaf),
		};
	}
);
export const serviceCapabilities = derived(serviceAuthority, (state) => state.can);
// Unavailable permission checks disable actions, but are not evidence of revocation.
export const serviceDenials = derived(serviceAuthority, (state) => state.denied);
export const isProjectOwner = derived(projectPermissions, (state) => !state.loading && !state.error && state.permissions?.is_owner === true);
export const canManageProject = derived(
	[projectPermissions, auth, authReady, projectSwitching],
	([state, identity, ready, switching]) => ready && !switching && !!identity.token && !!identity.projectId && !state.loading && !state.error && state.permissions !== null &&
		(identity.isSystemAdmin === true || state.permissions?.is_owner === true || state.permissions?.is_manager === true)
);
