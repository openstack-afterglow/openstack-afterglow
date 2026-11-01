import { browser } from '$app/environment';
import { api } from '$lib/api/client';
import { auth } from '$lib/stores/auth';
import { sessionScopeKey } from '$lib/utils/authSession';
import { writable, get } from 'svelte/store';

export interface Project {
	id: string;
	name: string;
	description?: string;
}

interface ProjectListState {
	projects: Project[];
	loading: boolean;
	loaded: boolean;
}

interface CachedProjectList {
	data: Project[];
	ts: number;
	domainId?: string | null;
	identityDomainId?: string | null;
	projectId?: string | null;
}

export const BROWSER_TTL_MS = 5 * 60 * 1000;

const initialState: ProjectListState = {
	projects: [],
	loading: false,
	loaded: false,
};

const store = writable<ProjectListState>(initialState);
const { subscribe, set, update } = store;

let requestSequence = 0;
let successfulLoad: { owner: string; ts: number } | null = null;
let inFlightRevalidation: { owner: string; promise: Promise<void> } | null = null;
let inFlightRefresh: { owner: string; promise: Promise<void> } | null = null;

function requestOwner(userId: string): string {
	return JSON.stringify([userId, sessionScopeKey(get(auth))]);
}

function storageKey(userId: string): string {
	return `afterglow.projects.${userId}`;
}

function readCache(userId: string): CachedProjectList | null {
	if (!browser) return null;
	try {
		const raw = localStorage.getItem(storageKey(userId));
		if (!raw) return null;
		const cached = JSON.parse(raw) as Partial<CachedProjectList>;
		if (!Array.isArray(cached.data) || typeof cached.ts !== 'number') return null;
		const state = get(auth);
		if ((cached.domainId ?? null) !== state.domainId
			|| (cached.identityDomainId ?? null) !== (state.identityDomainId ?? null)
			|| (cached.projectId ?? null) !== state.projectId) return null;
		return cached as CachedProjectList;
	} catch {
		return null;
	}
}

function writeCache(userId: string, projects: Project[]): void {
	if (!browser) return;
	try {
		const state = get(auth);
		localStorage.setItem(storageKey(userId), JSON.stringify({ data: projects, ts: Date.now(), domainId: state.domainId,
			identityDomainId: state.identityDomainId ?? null, projectId: state.projectId }));
	} catch {
		// localStorage가 비활성화되거나 용량을 초과해도 인메모리 목록은 계속 사용한다.
	}
}

async function fetchAndStore(path: string, token: string, userId: string): Promise<void> {
	const requestId = ++requestSequence;
	update((state) => ({ ...state, loading: true }));
	try {
		const projects = await api.get<Project[]>(path, token);
		if (requestId !== requestSequence) return;
		successfulLoad = { owner: requestOwner(userId), ts: Date.now() };
		set({ projects, loading: false, loaded: true });
		writeCache(userId, projects);
	} catch {
		// SWR 재검증 실패 시 기존 캐시를 유지한다.
	} finally {
		if (requestId === requestSequence) {
			update((state) => ({ ...state, loading: false }));
		}
	}
}

function revalidate(token: string, userId: string): Promise<void> {
	const owner = requestOwner(userId);
	if (inFlightRefresh?.owner === owner) return inFlightRefresh.promise;
	if (inFlightRevalidation?.owner === owner) return inFlightRevalidation.promise;

	const promise = fetchAndStore('/api/v1/auth/projects?cache=true', token, userId).finally(() => {
		if (inFlightRevalidation?.promise === promise) inFlightRevalidation = null;
	});
	inFlightRevalidation = { owner, promise };
	return promise;
}

function prefetch(token: string, userId: string): void {
	const owner = requestOwner(userId);
	if (successfulLoad?.owner === owner && Date.now() - successfulLoad.ts < BROWSER_TTL_MS) return;
	const cached = readCache(userId);
	if (cached && Date.now() - cached.ts < BROWSER_TTL_MS) {
		set({ projects: cached.data, loading: false, loaded: true });
	}
	void revalidate(token, userId);
}

function refresh(token: string, userId: string): Promise<void> {
	const owner = requestOwner(userId);
	if (inFlightRefresh?.owner === owner) return inFlightRefresh.promise;

	const promise = fetchAndStore('/api/v1/auth/projects?refresh=true', token, userId).finally(() => {
		if (inFlightRefresh?.promise === promise) inFlightRefresh = null;
	});
	inFlightRefresh = { owner, promise };
	return promise;
}

function reset(userId?: string): void {
	requestSequence += 1;
	successfulLoad = null;
	inFlightRevalidation = null;
	inFlightRefresh = null;
	set(initialState);
	if (!browser || !userId) return;
	try {
		localStorage.removeItem(storageKey(userId));
	} catch {
		// localStorage 접근 실패는 인메모리 초기화를 막지 않는다.
	}
}

if (browser) {
	let previousUserId: string | null = null;
	let previousOwner = '';
	auth.subscribe(($auth) => {
		const owner = sessionScopeKey($auth);
		if (!$auth.token || owner !== previousOwner) {
			reset(previousUserId ?? undefined);
		}
		previousUserId = $auth.userId;
		previousOwner = owner;
	});
}

export const projectList = {
	subscribe,
	prefetch,
	revalidate,
	refresh,
	reset,
};
