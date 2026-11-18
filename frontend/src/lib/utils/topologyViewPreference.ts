// 사용자 토폴로지만 그리드를 제공한다. 관리자 기본값은 캔버스로 유지한다.
export type TopologyView = 'lane' | 'canvas';
export type UserTopologyView = TopologyView | 'grid';

export const TOPOLOGY_VIEW_STORAGE_KEY = 'topology.view';
export const DEFAULT_TOPOLOGY_VIEW: TopologyView = 'canvas';

export function isTopologyView(v: unknown): v is TopologyView {
	return v === 'lane' || v === 'canvas';
}

/** SSR 과 저장소 접근 예외에서도 안전하게 기본값을 돌려준다. */
export function readTopologyView(): TopologyView;
export function readTopologyView(defaultView: 'grid'): UserTopologyView;
export function readTopologyView(defaultView: UserTopologyView = DEFAULT_TOPOLOGY_VIEW): UserTopologyView {
	try {
		if (typeof localStorage === 'undefined') return defaultView;
		const v = localStorage.getItem(TOPOLOGY_VIEW_STORAGE_KEY);
		return isTopologyView(v) ? v : defaultView;
	} catch {
		return defaultView;
	}
}

export function writeTopologyView(v: UserTopologyView): void {
	try {
		if (typeof localStorage === 'undefined') return;
		localStorage.setItem(TOPOLOGY_VIEW_STORAGE_KEY, v);
	} catch {
		// 저장 실패는 무시(세션 동안 메모리 상태만 유지)
	}
}
