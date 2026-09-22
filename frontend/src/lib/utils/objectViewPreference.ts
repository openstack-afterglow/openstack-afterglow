// 오브젝트 브라우저 보기(그리드 | 목록) 선택을 localStorage 에 보관한다. 기본값은 그리드.
export type ObjectView = 'grid' | 'list';

export const OBJECT_VIEW_STORAGE_KEY = 'objectBrowser.view';
export const DEFAULT_OBJECT_VIEW: ObjectView = 'grid';

export function isObjectView(v: unknown): v is ObjectView {
	return v === 'grid' || v === 'list';
}

/** SSR 과 저장소 접근 예외에서도 안전하게 기본값을 돌려준다. */
export function readObjectView(): ObjectView {
	try {
		if (typeof localStorage === 'undefined') return DEFAULT_OBJECT_VIEW;
		const v = localStorage.getItem(OBJECT_VIEW_STORAGE_KEY);
		return isObjectView(v) ? v : DEFAULT_OBJECT_VIEW;
	} catch {
		return DEFAULT_OBJECT_VIEW;
	}
}

export function writeObjectView(v: ObjectView): void {
	try {
		if (typeof localStorage === 'undefined') return;
		localStorage.setItem(OBJECT_VIEW_STORAGE_KEY, v);
	} catch {
		// 저장 실패는 무시(세션 동안 메모리 상태만 유지)
	}
}
