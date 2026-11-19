import { derived } from 'svelte/store';
import { auth, type AuthState } from './auth';

/**
 * The Personal domain has no credit pool, so dashboard chat and Studios cannot be
 * billed there. This is a presentation hint only; Lumen remains authoritative.
 */
export function isPersonalWorkspace(state: Pick<AuthState, 'domainId' | 'availableDomains'>): boolean {
	return !!state.domainId && state.availableDomains?.find(row => row.id === state.domainId)?.kind === 'personal';
}

export const personalWorkspace = derived(auth, isPersonalWorkspace);
