// 수동 배치 위치의 localStorage 저장. 키는 scope(user|admin) + 프로젝트별로 분리한다.
// localStorage 는 접근 자체가 throw 할 수 있으므로(SSR, 사생활 보호 모드) 모든 호출을 try/catch 로 감싼다.
import type { ManualPositions } from './types';

export type LayoutScope = 'user' | 'admin';

export const LAYOUT_STORAGE_PREFIX = 'topologyCanvas.layout';

export function layoutStorageKey(scope: LayoutScope, projectId: string | null | undefined): string {
	return `${LAYOUT_STORAGE_PREFIX}.${scope}.${projectId || 'all'}`;
}

function storage(): Storage | null {
	try {
		if (typeof localStorage === 'undefined') return null;
		return localStorage;
	} catch {
		return null;
	}
}

function isFiniteNumber(v: unknown): v is number {
	return typeof v === 'number' && Number.isFinite(v);
}

/** 문자열 → 검증된 ManualPositions. 형식이 어긋난 항목은 조용히 버린다. */
export function parseManualPositions(raw: string | null | undefined): ManualPositions {
	if (!raw) return {};
	let parsed: unknown;
	try {
		parsed = JSON.parse(raw);
	} catch {
		return {};
	}
	if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {};
	const out: ManualPositions = {};
	for (const [id, v] of Object.entries(parsed as Record<string, unknown>)) {
		if (!v || typeof v !== 'object') continue;
		const { x, y } = v as { x?: unknown; y?: unknown };
		if (isFiniteNumber(x) && isFiniteNumber(y)) out[id] = { x, y };
	}
	return out;
}

export function loadManualPositions(key: string): ManualPositions {
	try {
		return parseManualPositions(storage()?.getItem(key));
	} catch {
		return {};
	}
}

export function saveManualPositions(key: string, map: ManualPositions): void {
	try {
		const s = storage();
		if (!s) return;
		if (Object.keys(map).length === 0) {
			s.removeItem(key);
			return;
		}
		s.setItem(key, JSON.stringify(map));
	} catch {
		// 저장 실패(quota, 차단)는 기능 저하로만 처리한다
	}
}

export function clearManualPositions(key: string): void {
	try {
		storage()?.removeItem(key);
	} catch {
		// 무시
	}
}
