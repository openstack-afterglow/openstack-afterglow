import { get, writable } from 'svelte/store';
import { auth } from './auth';
import { api } from '$lib/api/client';
import { getActiveMockupProfile } from '$lib/mockup/transport';
import { getMockupRevision, onMockupRevisionChange } from '$lib/mockup/state';
import type { MockupProfileId } from '$lib/mockup/contracts';

export interface ProjectNamesScope {
	token?: string;
	projectId?: string;
	userId?: string;
	authority?: string;
	mockProfile: MockupProfileId | null;
	mockRevision: number;
}


export interface ProjectNamesResult {
	names: ReadonlyMap<string, string>;
	failed: boolean;
}
export interface AdminProjectName { id: string; name: string; domain_id?: string }
interface ProjectDirectoryResult extends ProjectNamesResult { projects: readonly AdminProjectName[]; error?: unknown }
const METADATA_TTL_MS = 30_000;
let settledAt = 0;
const nameMap = writable<Map<string, string>>(new Map());
let generation = 0;
let currentScope: ProjectNamesScope | null = null;
let currentScopeKey: string | null = null;
let settledValue: ProjectDirectoryResult | null = null;
let inFlight: { scopeKey: string; promise: Promise<ProjectDirectoryResult> } | null = null;

function scopeKey(scope: ProjectNamesScope): string {
	return JSON.stringify([
		scope.token ?? null,
		scope.projectId ?? null,
		scope.userId ?? null,
		scope.authority ?? null,
		scope.mockProfile,
		scope.mockRevision,
	]);
}

function scope(token?: string, projectId?: string, userId?: string): ProjectNamesScope {
	const state = get(auth);
	return {
		token,
		projectId,
		userId: userId ?? state.userId ?? undefined,
		authority: JSON.stringify([state.sessionId, state.identityDomainId, state.domainId, state.isSystemAdmin, state.isDomainManager]),
		mockProfile: getActiveMockupProfile(),
		mockRevision: getMockupRevision(),
	};
}

function clearInFlight(requestGeneration: number, requestedScopeKey: string): void {
	if (generation === requestGeneration && inFlight?.scopeKey === requestedScopeKey) {
		inFlight = null;
	}
}

async function loadDirectory(token?: string, projectId?: string, userId?: string, refresh = false): Promise<ProjectDirectoryResult> {
	const requestedScope = scope(token, projectId, userId);
	const requestedScopeKey = scopeKey(requestedScope);
	const copy = (value: ProjectDirectoryResult): ProjectDirectoryResult => ({ ...value, names: new Map(value.names), projects: value.projects.map(project => ({ ...project })) });
	if (!refresh && currentScopeKey === requestedScopeKey && settledValue && Date.now() - settledAt < METADATA_TTL_MS) return copy(settledValue);
	if (!refresh && inFlight?.scopeKey === requestedScopeKey) return inFlight.promise.then(copy);

	generation += 1;
	const requestGeneration = generation;
	currentScope = requestedScope;
	currentScopeKey = requestedScopeKey;
	settledValue = null;
	inFlight = null;
	nameMap.set(new Map());

	const promise = (async () => {
		try {
			const data = refresh
				? await api.get<AdminProjectName[]>('/api/v1/admin/projects/names', token, projectId, { refresh: true })
				: await api.get<AdminProjectName[]>('/api/v1/admin/projects/names', token, projectId);
			const loaded = new Map(data.map((project) => [project.id, project.name]));
			if (
				generation === requestGeneration
				&& currentScopeKey === requestedScopeKey
				&& scopeKey(scope(token, projectId, userId)) === requestedScopeKey
			) {
				settledValue = { names: loaded, projects: data.map(project => ({ ...project })), failed: false };
				settledAt = Date.now();
				nameMap.set(new Map(loaded));
			}
			return { names: loaded, projects: data, failed: false };
		} catch (error) {
			return { names: new Map<string, string>(), projects: [], failed: true, error };
		} finally {
			clearInFlight(requestGeneration, requestedScopeKey);
		}
	})();
	inFlight = { scopeKey: requestedScopeKey, promise };
	return promise.then(copy);
}

async function loadResult(token?: string, projectId?: string, userId?: string): Promise<ProjectNamesResult> {
	const { names, failed } = await loadDirectory(token, projectId, userId);
	return { names, failed };
}

async function loadMetadata(token?: string, projectId?: string, userId?: string, refresh = false) {
	const { projects, failed, error } = await loadDirectory(token, projectId, userId, refresh);
	return { projects, failed, error };
}

async function load(token?: string, projectId?: string): Promise<ReadonlyMap<string, string>> {
	return (await loadResult(token, projectId)).names;
}

function invalidate(targetScope?: ProjectNamesScope): void {
	if (!currentScope || !currentScopeKey) return;
	if (targetScope && scopeKey(targetScope) !== currentScopeKey) return;
	generation += 1;
	currentScope = null;
	currentScopeKey = null;
	settledValue = null;
	inFlight = null;
	nameMap.set(new Map());
}

export const projectNames = {
	subscribe: nameMap.subscribe,
	load,
	loadResult,
	loadMetadata,
	scope,
	invalidate,
};

onMockupRevisionChange(() => projectNames.invalidate());

let observedAuthority: string | undefined;
auth.subscribe(state => {
	const next = JSON.stringify([state.sessionId, state.userId, state.identityDomainId, state.domainId, state.projectId, state.isSystemAdmin, state.isDomainManager, !!state.token]);
	if (observedAuthority === next) return;
	observedAuthority = next;
	projectNames.invalidate();
});
