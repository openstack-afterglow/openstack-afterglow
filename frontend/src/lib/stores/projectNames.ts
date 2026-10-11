import { writable } from 'svelte/store';
import { api } from '$lib/api/client';
import { getActiveMockupProfile } from '$lib/mockup/transport';
import { getMockupRevision, onMockupRevisionChange } from '$lib/mockup/state';
import type { MockupProfileId } from '$lib/mockup/contracts';

export interface ProjectNamesScope {
	token?: string;
	projectId?: string;
	userId?: string;
	mockProfile: MockupProfileId | null;
	mockRevision: number;
}


export interface ProjectNamesResult {
	names: ReadonlyMap<string, string>;
	failed: boolean;
}
const nameMap = writable<Map<string, string>>(new Map());
let generation = 0;
let currentScope: ProjectNamesScope | null = null;
let currentScopeKey: string | null = null;
let settledValue: Map<string, string> | null = null;
let inFlight: { scopeKey: string; promise: Promise<ProjectNamesResult> } | null = null;

function scopeKey(scope: ProjectNamesScope): string {
	return JSON.stringify([
		scope.token ?? null,
		scope.projectId ?? null,
		scope.userId ?? null,
		scope.mockProfile,
		scope.mockRevision,
	]);
}

function scope(token?: string, projectId?: string, userId?: string): ProjectNamesScope {
	return {
		token,
		projectId,
		userId,
		mockProfile: getActiveMockupProfile(),
		mockRevision: getMockupRevision(),
	};
}

function clearInFlight(requestGeneration: number, requestedScopeKey: string): void {
	if (generation === requestGeneration && inFlight?.scopeKey === requestedScopeKey) {
		inFlight = null;
	}
}

async function loadResult(token?: string, projectId?: string, userId?: string): Promise<ProjectNamesResult> {
	const requestedScope = scope(token, projectId, userId);
	const requestedScopeKey = scopeKey(requestedScope);
	if (currentScopeKey === requestedScopeKey && settledValue) return { names: new Map(settledValue), failed: false };
	if (inFlight?.scopeKey === requestedScopeKey) {
		return inFlight.promise.then((value) => ({ ...value, names: new Map(value.names) }));
	}

	generation += 1;
	const requestGeneration = generation;
	currentScope = requestedScope;
	currentScopeKey = requestedScopeKey;
	settledValue = null;
	inFlight = null;
	nameMap.set(new Map());

	const promise = (async () => {
		try {
			const data = await api.get<Array<{ id: string; name: string }>>(
				'/api/v1/admin/projects/names',
				token,
				projectId,
			);
			const loaded = new Map(data.map((project) => [project.id, project.name]));
			if (
				generation === requestGeneration
				&& currentScopeKey === requestedScopeKey
				&& scopeKey(scope(token, projectId, userId)) === requestedScopeKey
			) {
				settledValue = loaded;
				nameMap.set(new Map(loaded));
			}
			return { names: loaded, failed: false };
		} catch {
			return { names: new Map<string, string>(), failed: true };
		} finally {
			clearInFlight(requestGeneration, requestedScopeKey);
		}
	})();
	inFlight = { scopeKey: requestedScopeKey, promise };
	return promise.then((value) => ({ ...value, names: new Map(value.names) }));
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
	scope,
	invalidate,
};

onMockupRevisionChange(() => projectNames.invalidate());
