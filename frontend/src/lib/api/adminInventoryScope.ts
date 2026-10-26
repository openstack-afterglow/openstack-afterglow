import { get } from 'svelte/store';
import { api } from './client';
import { adminInventoryScope, type AdminInventoryFilter } from '$lib/stores/adminInventoryScope';

// Only these project-owned observation reads accept the independent admin filter.
// Detail, IAM, metadata and mutation URLs deliberately retain their native contract.
const INVENTORY_PATHS: Record<string, true> = {
	'/api/v1/admin/all-instances': true,
	'/api/v1/admin/instances/health': true,
	'/api/v1/admin/all-volumes': true,
	'/api/v1/admin/volumes/status-summary': true,
	'/api/v1/admin/overview/domains': true,
	'/api/v1/admin/all-ports': true,
	'/api/v1/admin/all-networks': true,
	'/api/v1/admin/all-routers': true,
	'/api/v1/admin/all-floating-ips': true,
	'/api/v1/admin/all-subnets': true,
	'/api/v1/admin/topology': true,
	'/api/v1/admin/all-containers': true,
	'/api/v1/admin/all-file-storages': true,
	'/api/v1/admin/all-loadbalancers': true,
	'/api/v1/admin/images': true,
	'/api/v1/admin/key-manager/project-quotas': true,
	'/api/v1/admin/database-instances': true,
	'/api/v1/admin/object-storage': true,
	'/api/v1/admin/events': true,
	'/api/v1/admin/events/stats': true,
	'/api/v1/chat/admin/stats': true,
	'/api/v1/chat/admin/stats/users': true,
	'/api/v1/chat/admin/stats/timeseries': true,
};
export function adminInventoryPath(path: string, scope: AdminInventoryFilter): string {
	const [pathname, query = ''] = path.split('?');
	if (!INVENTORY_PATHS[pathname] || (!scope.domainId && !scope.projectId)) return path;
	const params = new URLSearchParams(query);
	if (scope.domainId) params.set('domain_id', scope.domainId);
	if (scope.projectId) params.set('project_id', scope.projectId);
	return `${pathname}?${params}`;
}

export function createAdminInventoryApi(base = api) {
	const scope = get(adminInventoryScope);
	const scoped = !!(scope.domainId || scope.projectId);
	let alive = true;
	const isCurrent = () => alive && get(adminInventoryScope).revision === scope.revision;
	const assertCurrent = () => {
		if (!isCurrent()) throw new DOMException('Aborted', 'AbortError');
	};
	const accept = async <T>(promise: Promise<T>): Promise<T> => {
		const result = await promise;
		assertCurrent();
		return result;
	};
	return {
		...base,
		scoped,
		filter: scope,
		isCurrent,
		dispose: () => { alive = false; },
		get: <T>(path: string, ...args: OmitFirst<Parameters<typeof api.get>>): Promise<T> => {
			assertCurrent();
			// Stored timeseries are cluster aggregates, never project/domain observations.
			if (scoped && path.startsWith('/api/v1/admin/timeseries/')) return Promise.reject(new DOMException('Aborted', 'AbortError'));
			return accept(base.get<T>(adminInventoryPath(path, scope), ...args));
		},
		prefetch: (path: string, ...args: OmitFirst<Parameters<typeof api.prefetch>>) => {
			assertCurrent();
			return base.prefetch(adminInventoryPath(path, scope), ...args);
		},
		post: <T>(...args: Parameters<typeof api.post>): Promise<T> => { assertCurrent(); return accept(base.post<T>(...args)); },
		put: <T>(...args: Parameters<typeof api.put>): Promise<T> => { assertCurrent(); return accept(base.put<T>(...args)); },
		patch: <T>(...args: Parameters<typeof api.patch>): Promise<T> => { assertCurrent(); return accept(base.patch<T>(...args)); },
		delete: <T>(...args: Parameters<typeof api.delete>): Promise<T> => { assertCurrent(); return accept(base.delete<T>(...args)); },
	};
}
type OmitFirst<T extends unknown[]> = T extends [unknown, ...infer Rest] ? Rest : never;
