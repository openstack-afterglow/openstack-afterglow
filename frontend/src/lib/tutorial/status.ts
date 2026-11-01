/**
 * 사용자별 튜토리얼(투어) 진행 이력 — 서버 기록 + 프론트 강조 판정.
 *
 * - 로그인 후 한 번 loadTutorialStatuses() 로 서버 이력을 받아 스토어에 채운다.
 * - 기록이 없는 투어는 "미체험" → 해당 페이지의 튜토리얼 버튼을 강조한다.
 * - 투어 완주(engine 의 'afterglow:tour-complete' 이벤트) → 'completed' 기록.
 * - 사용자가 강조를 무시('나중에') → 'dismissed' 기록. 어느 쪽이든 기록되면 강조 해제.
 */
import { get, writable } from 'svelte/store';

import { api } from '$lib/api/client';
import { auth } from '$lib/stores/auth';
import { sessionScopeKey } from '$lib/utils/authSession';

import type { TourId } from './tours';

export type TutorialStatus = 'completed' | 'dismissed';
export type TutorialStatusMap = Partial<Record<TourId, TutorialStatus>>;

export const tutorialStatuses = writable<TutorialStatusMap>({});
// 서버 이력 조회가 최소 1회 성공했는지. 초대 팝오버는 이 값이 true 된 뒤에만 띄워
// 로드 전 빈 맵({}) 상태에서 이미 완료/무시한 사용자에게 초대가 깜빡이는 것을 막는다.
export const tutorialStatusesLoaded = writable(false);

let loadedOwner: string | null = null;
let loadingOwner: string | null = null;
let loadGeneration = 0;
let mutationVersion = 0;
const mutations = new Map<TourId, { version: number; status: TutorialStatus; pending: boolean }>();

let previousOwner = '';
auth.subscribe(state => {
	const owner = JSON.stringify([!!state.token, sessionScopeKey(state)]);
	if (owner === previousOwner) return;
	previousOwner = owner;
	loadGeneration++;
	loadedOwner = null;
	loadingOwner = null;
	mutations.clear();
	tutorialStatuses.set({});
	tutorialStatusesLoaded.set(false);
});

/** Display-only history is loaded once per logical login and exact scope. */
export async function loadTutorialStatuses(force = false): Promise<void> {
	const state = get(auth);
	const { token } = state;
	if (!token) return;
	const owner = sessionScopeKey(state);
	if (!force && (loadedOwner === owner || loadingOwner === owner)) return;

	const generation = ++loadGeneration;
	const startingMutation = mutationVersion;
	const pendingAtStart = new Set<number>();
	const pendingStatuses: TutorialStatusMap = {};
	for (const [tour, mutation] of mutations) {
		if (!mutation.pending) continue;
		pendingAtStart.add(mutation.version);
		pendingStatuses[tour] = mutation.status;
	}
	loadedOwner = null;
	loadingOwner = owner;
	tutorialStatuses.set(pendingStatuses);
	tutorialStatusesLoaded.set(false);

	try {
		const res = await api.get<{ statuses: Record<string, TutorialStatus> }>(
			'/api/v1/tutorials/status',
			token,
		);
		if (generation !== loadGeneration || sessionScopeKey(get(auth)) !== owner || !get(auth).token) return;
		const statuses = { ...(res?.statuses ?? {}) } as TutorialStatusMap;
		for (const [tour, mutation] of mutations) {
			if (mutation.version > startingMutation || pendingAtStart.has(mutation.version)) statuses[tour] = mutation.status;
		}
		tutorialStatuses.set(statuses);
		loadedOwner = owner;
		tutorialStatusesLoaded.set(true);
	} catch {
		if (generation !== loadGeneration || sessionScopeKey(get(auth)) !== owner || !get(auth).token) return;
		loadedOwner = null;
		tutorialStatusesLoaded.set(false);
	} finally {
		if (generation === loadGeneration) loadingOwner = null;
	}
}

/** 특정 투어 상태를 기록. 낙관적으로 스토어를 먼저 갱신해 강조를 즉시 해제한다. */
export async function recordTutorialStatus(tour: TourId, status: TutorialStatus): Promise<void> {
	const { token } = get(auth);
	const mutation = { version: ++mutationVersion, status, pending: !!token };
	mutations.set(tour, mutation);
	tutorialStatuses.update((m) => ({ ...m, [tour]: status }));
	if (!token) return;
	try {
		await api.post(`/api/v1/tutorials/${tour}/status`, { status }, token);
	} catch {
		// best-effort: 낙관값 유지, 다음 로드에서 서버값으로 정합.
	} finally {
		mutation.pending = false;
	}
}

// 투어 완주 이벤트 수신 → completed 기록(버튼/URL 재개 등 모든 완료 경로 공통 처리).
if (typeof window !== 'undefined') {
	window.addEventListener('afterglow:tour-complete', (event) => {
		const tourId = (event as CustomEvent).detail?.tourId as TourId | undefined;
		if (tourId) void recordTutorialStatus(tourId, 'completed');
	});
}
