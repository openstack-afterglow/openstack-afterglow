import { get, writable } from 'svelte/store';
import { auth } from './auth';

export interface AdminInventoryFilter {
	domainId: string;
	projectId: string;
	revision: number;
}

// Observation filters never rescope the authenticated workspace or grant authority.
export const adminInventoryScope = writable<AdminInventoryFilter>({ domainId: '', projectId: '', revision: 0 });
export function setAdminInventoryScope(domainId: string, projectId: string): void {
	const current = get(adminInventoryScope);
	if (current.domainId === domainId && current.projectId === projectId) return;
	adminInventoryScope.set({ domainId, projectId, revision: current.revision + 1 });
}

let authority: string | undefined;
auth.subscribe(state => {
	const next = JSON.stringify([state.sessionId, state.userId, state.identityDomainId, state.domainId, state.projectId, state.isSystemAdmin, state.isDomainManager, !!state.token]);
	if (next === authority) return;
	authority = next;
	adminInventoryScope.update(current => ({ domainId: '', projectId: '', revision: current.revision + 1 }));
});

const INVENTORY_ROUTES: Record<string, true> = {
	instances: true, volumes: true, ports: true, networks: true, routers: true,
	'floating-ips': true, subnets: true, topology: true, 'database-instances': true,
	containers: true, 'file-storage': true, 'object-storage': true, secrets: true,
	loadbalancers: true, images: true,
};
export function hasAdminInventoryScope(pathname: string): boolean {
	const parts = pathname.split('/').filter(Boolean);
	return parts.length === 2 && parts[0] === 'admin' && INVENTORY_ROUTES[parts[1]] === true;
}
