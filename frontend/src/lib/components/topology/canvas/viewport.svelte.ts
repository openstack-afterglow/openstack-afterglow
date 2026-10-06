// 팬/줌 상태를 $state 로 보관하는 뷰포트. 수학은 topologyLayout 의 순수 함수에 위임한다.
import { MOTION_EASING } from '$lib/design/tokens';
import { zoomAt as zoomAtPure } from './topologyLayout';
import type { ViewState } from './types';

/**
 * CSS `cubic-bezier(x1, y1, x2, y2)` 와 같은 진행 곡선. rAF 카메라 전환은 CSS 변수를 읽을 수 없어 JS 로 푼다.
 * x(s) 를 Newton 으로 풀고, 기울기가 평평하면 이분법으로 마무리한다.
 */
export function cubicBezierEase(x1: number, y1: number, x2: number, y2: number): (t: number) => number {
	const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
	const cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
	const curveX = (s: number) => ((ax * s + bx) * s + cx) * s;
	const curveY = (s: number) => ((ay * s + by) * s + cy) * s;
	return (t) => {
		if (t <= 0) return 0;
		if (t >= 1) return 1;
		let s = t;
		for (let i = 0; i < 8; i++) {
			const err = curveX(s) - t;
			if (Math.abs(err) < 1e-6) return curveY(s);
			const slope = (3 * ax * s + 2 * bx) * s + cx;
			if (Math.abs(slope) < 1e-6) break;
			s -= err / slope;
		}
		let lo = 0, hi = 1;
		s = t;
		while (hi - lo > 1e-6) {
			if (curveX(s) < t) lo = s;
			else hi = s;
			s = (lo + hi) / 2;
		}
		return curveY(s);
	};
}

/** `--motion-ease-emphasized` 의 JS 구현(MOTION_EASING 과 같은 곡선). */
export const easeEmphasized = (() => {
	const [x1, y1, x2, y2] = (MOTION_EASING.emphasized.match(/-?\d*\.?\d+/g) ?? []).map(Number);
	return cubicBezierEase(x1, y1, x2, y2);
})();

/**
 * 두 뷰 사이의 진행률 t(0…1) 지점. 배율은 로그 공간에서, 위치는 **뷰포트 중심 아래의 월드 좌표**를 직선으로 옮긴다.
 * 팬을 직접 보간하면 배율이 바뀌는 동안 화면이 옆으로 헤엄친다.
 */
export function interpolateView(from: ViewState, to: ViewState, t: number, viewportW: number, viewportH: number): ViewState {
	if (t <= 0) return from;
	if (t >= 1) return to;
	const mx = viewportW / 2, my = viewportH / 2;
	const k = from.k * Math.pow(to.k / from.k, t);
	const fx = (mx - from.panX) / from.k, fy = (my - from.panY) / from.k;
	const tx = (mx - to.panX) / to.k, ty = (my - to.panY) / to.k;
	const cx = fx + (tx - fx) * t, cy = fy + (ty - fy) * t;
	return { k, panX: mx - cx * k, panY: my - cy * k };
}

export class Viewport {
	panX = $state(0);
	panY = $state(0);
	k = $state(1);

	constructor(initial?: Partial<ViewState>) {
		if (initial) this.set({ panX: initial.panX ?? 0, panY: initial.panY ?? 0, k: initial.k ?? 1 });
	}

	get view(): ViewState {
		return { panX: this.panX, panY: this.panY, k: this.k };
	}

	set(view: ViewState): void {
		this.panX = view.panX;
		this.panY = view.panY;
		this.k = view.k;
	}

	/** 화면 좌표 (sx, sy) 아래의 점을 고정한 채 배율을 k2 로 변경(0.35–2.2 클램프). */
	zoomAt(sx: number, sy: number, k2: number): void {
		this.set(zoomAtPure(this.view, sx, sy, k2));
	}

	/** 뷰포트 중심 기준 배율 곱. */
	zoomBy(f: number, viewportW: number, viewportH: number): void {
		this.zoomAt(viewportW / 2, viewportH / 2, this.k * f);
	}

	panBy(dx: number, dy: number): void {
		this.panX += dx;
		this.panY += dy;
	}

	/** 화면 좌표 → 캔버스 좌표. */
	toCanvas(sx: number, sy: number): { x: number; y: number } {
		return { x: (sx - this.panX) / this.k, y: (sy - this.panY) / this.k };
	}

	/** 캔버스 좌표 → 화면 좌표. */
	toScreen(x: number, y: number): { x: number; y: number } {
		return { x: x * this.k + this.panX, y: y * this.k + this.panY };
	}
}

export function createViewport(initial?: Partial<ViewState>): Viewport {
	return new Viewport(initial);
}
