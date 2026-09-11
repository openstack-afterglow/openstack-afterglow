// 토폴로지 뷰(레인 | 캔버스) 선택을 localStorage 에 보관한다. 기본값은 캔버스.
export type TopologyView = 'lane' | 'canvas';

export const TOPOLOGY_VIEW_STORAGE_KEY = 'topology.view';
export const DEFAULT_TOPOLOGY_VIEW: TopologyView = 'canvas';

export function isTopologyView(v: unknown): v is TopologyView {
	return v === 'lane' || v === 'canvas';
}

/** SSR 과 저장소 접근 예외에서도 안전하게 기본값을 돌려준다. */
export function readTopologyView(): TopologyView {
	try {
		if (typeof localStorage === 'undefined') return DEFAULT_TOPOLOGY_VIEW;
		const v = localStorage.getItem(TOPOLOGY_VIEW_STORAGE_KEY);
		return isTopologyView(v) ? v : DEFAULT_TOPOLOGY_VIEW;
	} catch {
		return DEFAULT_TOPOLOGY_VIEW;
	}
}

export function writeTopologyView(v: TopologyView): void {
	try {
		if (typeof localStorage === 'undefined') return;
		localStorage.setItem(TOPOLOGY_VIEW_STORAGE_KEY, v);
	} catch {
		// 저장 실패는 무시(세션 동안 메모리 상태만 유지)
	}
}
