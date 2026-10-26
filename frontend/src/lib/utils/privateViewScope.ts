import { get, readable } from 'svelte/store';
import { auth, authReady, projectSwitching } from '$lib/stores/auth';
import { observedProjectPermissions } from '$lib/stores/servicePermissions';

/** A mounted workspace lifetime, not a bearer-token or permission-check lifetime. */
export function createPrivateViewScope() {
	return readable(0, (set) => {
		let revision = 0;
		let owner: string | undefined;
		let authority: string | undefined;
		let switching = false;
		let permissions: string | undefined;
		const stopAuth = auth.subscribe((state) => {
			const next = JSON.stringify([state.sessionId, state.userId, state.identityDomainId, state.domainId, state.projectId, !!state.token]);
			if (next !== owner) {
				if (owner !== undefined) set(++revision);
				owner = next;
				permissions = undefined;
				authority = undefined;
			}
			if (!get(authReady)) return;
			const nextAuthority = JSON.stringify([state.isSystemAdmin, state.isDomainManager, state.canWrite, [...(state.roles ?? [])].sort()]);
			if (authority !== undefined && nextAuthority !== authority) set(++revision);
			authority = nextAuthority;
		});
		const stopReady = authReady.subscribe((ready) => {
			if (!ready) return;
			const state = get(auth);
			const next = JSON.stringify([state.isSystemAdmin, state.isDomainManager, state.canWrite, [...(state.roles ?? [])].sort()]);
			if (authority !== undefined && next !== authority) set(++revision);
			authority = next;
		});
		const stopSwitch = projectSwitching.subscribe((next) => {
			// The entry edge catches A -> B -> A even before Svelte flushes.
			if (next && !switching) set(++revision);
			switching = next;
		});
		const stopPermissions = observedProjectPermissions.subscribe((state) => {
			// A routine background revalidation must not destroy drafts/sockets.
			// A changed authoritative result must retire the old private view.
			if (state.loading || state.error || !state.permissions) return;
			const value = state.permissions;
			const next = JSON.stringify([
				value.is_owner, value.is_manager, value.can_write,
				Object.entries(value.service_permissions).sort(([a], [b]) => a.localeCompare(b))
					.map(([service, leaves]) => [service, [...leaves].sort()]),
				Object.entries(value.service_permission_errors ?? {}).sort(([a], [b]) => a.localeCompare(b)),
			]);
			if (permissions !== undefined && next !== permissions) set(++revision);
			permissions = next;
		});
		return () => { stopAuth(); stopReady(); stopSwitch(); stopPermissions(); };
	});
}
