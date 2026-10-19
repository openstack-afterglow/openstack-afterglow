import { beforeEach, expect, vi } from 'vitest';
import { get, type Writable } from 'svelte/store';
import type { PermissionState } from '$lib/stores/servicePermissions';
import { acceptAuthVerification, auth, getAuthVerificationEpoch, projectSwitching, setAuth, type AuthState } from '$lib/stores/auth';
import { refreshAuthState } from '$lib/utils/authSession';

vi.mock('$lib/stores/servicePermissions', async () => {
	// The hoisted mock factory runs before static imports are initialized.
	const { writable } = await import('svelte/store');
	return {
		serviceCapabilities: writable<(leaf: string) => boolean>(() => false),
		serviceDenials: writable<(leaf: string) => boolean>(() => false),
		projectPermissions: writable({ permissions: null, loading: false, error: '' })
	};
});
import { serviceCapabilities, serviceDenials, projectPermissions } from '$lib/stores/servicePermissions';

// Component fixtures stand in for completed /auth/me verification, never a grant
// subscription. Call this after replacing an actor; raw replacements stay unverified.
export function setVerifiedLumenActor(state: AuthState): void {
	auth.set(state);
	expect(acceptAuthVerification(getAuthVerificationEpoch(), {})).toBe(true);
}

// Native refresh continues an already verified logical session. Keep the mapper's
// exact result so setAuth, not this fixture, decides whether readiness survives.
export function refreshLumenAuth(token: string): void {
	const current = get(auth);
	setAuth(refreshAuthState({
		token,
		user_id: current.userId!,
		username: current.username!,
		project_id: current.projectId!,
		project_name: current.projectName!,
		expires_at: current.accessExpiresAt === null ? null : new Date(current.accessExpiresAt * 1000).toISOString(),
		roles: current.roles,
		is_system_admin: current.isSystemAdmin,
		can_write: current.canWrite,
		domain_id: current.domainId,
		domain_name: current.domainName,
		identity_domain_id: current.identityDomainId,
		identity_domain_name: current.identityDomainName,
		is_domain_manager: current.isDomainManager,
		available_domains: current.availableDomains,
		can_create_domain: current.canCreateDomain,
	}, current));
}

const leaves = ['inventory_reader', 'history_reader', 'chat_user', 'images_user', 'audio_user', 'tools_user', 'assets_editor', 'agents_editor', 'mcp_editor', 'keys_editor', 'history_editor', 'resources_admin'].map((leaf) => `lumen-${leaf}`);
export function grantLumen(...grants: string[]) {
	const allowed = new Set(grants);
	(serviceCapabilities as Writable<(leaf: string) => boolean>).set((leaf) => allowed.has(leaf));
	(serviceDenials as Writable<(leaf: string) => boolean>).set((leaf) => !allowed.has(leaf));
	(projectPermissions as Writable<PermissionState>).set({ permissions: null, loading: false, error: '' });
}
export function pendingLumen(error = '') {
	(serviceCapabilities as Writable<(leaf: string) => boolean>).set(() => false);
	(serviceDenials as Writable<(leaf: string) => boolean>).set(() => false);
	(projectPermissions as Writable<PermissionState>).set({ permissions: null, loading: !error, error });
}
beforeEach(() => {
	projectSwitching.set(false);
	grantLumen(...leaves);
});
