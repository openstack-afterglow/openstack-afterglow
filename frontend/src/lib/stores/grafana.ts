import { writable } from 'svelte/store';
import { api } from '$lib/api/client';
import { getActiveMockupProfile } from '$lib/mockup/transport';
import { getMockupRevision, onMockupRevisionChange } from '$lib/mockup/state';
import type { MockupProfileId } from '$lib/mockup/contracts';

export type GrafanaDashboardKey = 'node' | 'rabbitmq' | 'mysqld' | 'proxysql' | 'memcached' | 'etcd' | 'haproxy' | 'libvirt' | 'openstack' | 'ceph' | 'instance-cpu' | 'instance-gpu';

export interface GrafanaContext {
	grafanaUrl: string;
	dashboards: Record<GrafanaDashboardKey, string>;
}

interface GrafanaScope {
	token?: string;
	projectId?: string;
	mockProfile: MockupProfileId | null;
	mockRevision: number;
}

interface GrafanaContextStore {
	ctx: GrafanaContext | null;
	loading: boolean;
	error: boolean;
}

const store = writable<GrafanaContextStore>({ ctx: null, loading: false, error: false });
let generation = 0;
let currentScopeKey: string | null = null;
let settledContext: GrafanaContext | null = null;
let hasSettledContext = false;
let inFlight: { scopeKey: string; promise: Promise<GrafanaContext | null> } | null = null;

function keyForScope(scope: GrafanaScope): string {
	return JSON.stringify([
		scope.token ?? null,
		scope.projectId ?? null,
		scope.mockProfile,
		scope.mockRevision,
	]);
}

function copyContext(context: GrafanaContext | null): GrafanaContext | null {
	return context ? { ...context, dashboards: { ...context.dashboards } } : null;
}

function currentScopeKeyFor(token?: string, projectId?: string): string {
	return keyForScope({
		token,
		projectId,
		mockProfile: getActiveMockupProfile(),
		mockRevision: getMockupRevision(),
	});
}

function clearInFlight(requestGeneration: number, requestedScopeKey: string): void {
	if (generation === requestGeneration && inFlight?.scopeKey === requestedScopeKey) {
		inFlight = null;
	}
}

export async function loadGrafanaContext(
	token: string | undefined,
	projectId: string | undefined,
): Promise<GrafanaContext | null> {
	const requestedScopeKey = currentScopeKeyFor(token, projectId);
	if (currentScopeKey === requestedScopeKey && hasSettledContext) return copyContext(settledContext);
	if (inFlight?.scopeKey === requestedScopeKey) {
		return inFlight.promise.then(copyContext);
	}

	generation += 1;
	const requestGeneration = generation;
	currentScopeKey = requestedScopeKey;
	settledContext = null;
	hasSettledContext = false;
	inFlight = null;
	store.set({ ctx: null, loading: true, error: false });

	const promise = (async () => {
		try {
			const dashData = await api.get<{ grafana_url: string; dashboards: Record<string, string> }>(
				'/api/v1/grafana/dashboards',
				token,
				projectId,
			);
			const context = dashData.grafana_url
				? {
					grafanaUrl: dashData.grafana_url.replace(/\/$/, ''),
					dashboards: { ...dashData.dashboards } as Record<GrafanaDashboardKey, string>,
				}
				: null;
			if (
				generation === requestGeneration
				&& currentScopeKey === requestedScopeKey
				&& currentScopeKeyFor(token, projectId) === requestedScopeKey
			) {
				settledContext = context;
				hasSettledContext = true;
				store.set({ ctx: copyContext(context), loading: false, error: false });
			}
			return context;
		} catch {
			if (
				generation === requestGeneration
				&& currentScopeKey === requestedScopeKey
				&& currentScopeKeyFor(token, projectId) === requestedScopeKey
			) {
				hasSettledContext = false;
				store.set({ ctx: null, loading: false, error: true });
			}
			return null;
		} finally {
			clearInFlight(requestGeneration, requestedScopeKey);
		}
	})();
	inFlight = { scopeKey: requestedScopeKey, promise };
	return promise.then(copyContext);
}

export function invalidateGrafanaContext(): void {
	generation += 1;
	currentScopeKey = null;
	settledContext = null;
	hasSettledContext = false;
	inFlight = null;
	store.set({ ctx: null, loading: false, error: false });
}

export const grafanaStore = { subscribe: store.subscribe };

onMockupRevisionChange(invalidateGrafanaContext);
