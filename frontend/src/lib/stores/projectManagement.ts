import { derived, readable } from 'svelte/store';
import { auth, authReady, logoutInProgress, projectSwitching } from './auth';
import { api } from '$lib/api/client';
import { sessionScopeKey } from '$lib/utils/authSession';

export interface ProjectManagementCapability {
	domain_id: string;
	domain_kind: 'personal' | 'organization' | 'legacy';
	is_domain_manager: boolean;
	can_create_project: boolean;
}
export interface ProjectManagementScope {
	domainId: string;
	userId: string;
	token: () => string;
}
export interface ProjectManagementState {
	scope: ProjectManagementScope | null;
	capability: ProjectManagementCapability | null;
	checking: boolean;
	error: string;
}
const empty: ProjectManagementState = { scope: null, capability: null, checking: false, error: '' };
let refresh: (() => Promise<void>) | null = null;

// User navigation and the project console share one current, non-persisted read.
// Role names and system-admin status never imply organization project authority.
export const projectManagement = readable<ProjectManagementState>(empty, set => {
	let scope: ProjectManagementScope | null = null;
	let owner = '';
	let token = '';
	let capability: ProjectManagementCapability | null = null;
	let generation = 0;
	async function load() {
		const target = scope;
		if (!target) return;
		const pending = ++generation;
		set({ scope: target, capability, checking: true, error: '' });
		try {
			const result = await api.get<ProjectManagementCapability>(`/api/v1/projects/capabilities?domain_id=${encodeURIComponent(target.domainId)}`, target.token(), undefined, { cache: 'no-store', suppressAuthRedirect: true });
			if (scope !== target || generation !== pending) return;
			if (result.domain_id !== target.domainId || !['organization', 'legacy', 'personal'].includes(result.domain_kind) || typeof result.is_domain_manager !== 'boolean' || typeof result.can_create_project !== 'boolean') throw new Error('Invalid project capability response');
			capability = result;
			set({ scope: target, capability, checking: false, error: '' });
		} catch (cause) {
			if (scope !== target || generation !== pending) return;
			capability = null;
			set({ scope: target, capability: null, checking: false, error: cause instanceof Error ? cause.message : 'Project capability unavailable' });
		}
	}
	refresh = load;
	const unsubscribe = derived([auth, authReady, logoutInProgress, projectSwitching], ([state, ready, loggingOut, switching]) => ({ state, active: ready && !loggingOut && !switching })).subscribe(({ state, active }) => {
		const next = active && state.token && state.userId && state.domainId ? JSON.stringify([sessionScopeKey(state), state.isDomainManager]) : '';
		token = next ? state.token! : '';
		if (next === owner) return;
		owner = next; generation++; capability = null;
		scope = next ? { domainId: state.domainId!, userId: state.userId!, token: () => token } : null;
		set({ ...empty, scope });
		if (scope) void load();
	});
	const focus = () => { void load(); };
	const visible = () => { if (document.visibilityState === 'visible') focus(); };
	if (typeof window !== 'undefined') { window.addEventListener('focus', focus); document.addEventListener('visibilitychange', visible); }
	return () => {
		unsubscribe(); scope = null; generation++; refresh = null;
		if (typeof window !== 'undefined') { window.removeEventListener('focus', focus); document.removeEventListener('visibilitychange', visible); }
	};
});
export const canManageOrganizationProjects = derived(projectManagement, state => !state.checking && !state.error && !!state.scope && !!state.capability && state.capability.domain_kind !== 'personal' && (state.capability.is_domain_manager || state.capability.can_create_project));
export async function refreshProjectManagement(): Promise<void> { await refresh?.(); }
