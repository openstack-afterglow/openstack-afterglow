import { goto } from '$app/navigation';
import { derived, get } from 'svelte/store';
import { api } from '$lib/api/client';
import { auth, authReady, logoutInProgress, projectSwitching, setAuth, clearAuth } from '$lib/stores/auth';
import { cloudShell } from '$lib/stores/cloudShell.svelte';
import { toast } from '$lib/stores/toast';
import type { AvailableDomain, SessionTokenResponse } from '$lib/types/auth';
import { domainAuthState, sessionScopeKey } from './authSession';
import { takePendingInvitationPath } from './domainLogin';
import { postAuthDestination } from './mcpConsent';
import { t } from '$lib/i18n/ns/domain-iam';

/** A successful DELETE must never leave the browser using its deleted native scope. */
export async function continueAfterProjectDeletion(projectId: string, domainId: string): Promise<void> {
	const original = get(auth);
	if (original.projectId !== projectId || original.domainId !== domainId || !original.token
		|| !get(authReady) || get(logoutInProgress) || get(projectSwitching)) return;
	const owner = sessionScopeKey(original);
	let retired = false;
	let ownsSwitch = false;
	// This owner intentionally outlives the deleted project's mounted settings/console.
	const unsubscribe = derived([auth, authReady, logoutInProgress, projectSwitching], ([state, ready, loggingOut, switching]) => ({ state, ready, loggingOut, switching })).subscribe(({ state, ready, loggingOut, switching }) => {
		if (sessionScopeKey(state) !== owner || !ready || loggingOut || (switching && !ownsSwitch) || (ownsSwitch && !switching) || !state.token) retired = true;
	});
	const current = () => !retired && sessionScopeKey(get(auth)) === owner && get(authReady) && !get(logoutInProgress);
	const options = { replayOnUnauthorized: false, suppressAuthRedirect: true, cache: 'no-store' as const };
	try {
		await cloudShell.close('project-switch', { keepDock: false });
		if (!current()) return;
		const domains = await api.get<AvailableDomain[]>('/api/v1/auth/domains', get(auth).token!, undefined, { refresh: true, suppressAuthRedirect: true });
		if (!current()) return;
		if (!Array.isArray(domains) || !domains.some(row => row.id === domainId)) throw new Error('Deleted project domain is unavailable');
		ownsSwitch = true;
		projectSwitching.set(true);
		const response = await api.post<SessionTokenResponse>('/api/v1/auth/token/domain', { domain_id: domainId }, get(auth).token!, undefined, options);
		if (!current()) return;
		const next = domainAuthState(response, { ...get(auth), availableDomains: domains }, domainId);
		if (next.projectId === projectId) throw new Error('Deleted project scope returned');
		const destination = takePendingInvitationPath() ?? postAuthDestination(next.projectId ? '/dashboard' : '/select-project');
		setAuth(next);
		await goto(destination);
	} catch {
		if (!current()) return;
		// Keystone may revoke the old scoped token with the project. Never pretend
		// that token is unscoped or replay DELETE; reauthentication is then required.
		clearAuth();
		toast.error(t('deletedRescopeFailed'));
		await goto('/login');
	} finally {
		unsubscribe();
		if (ownsSwitch) projectSwitching.set(false);
	}
}
