// 팬/줌 상태를 $state 로 보관하는 뷰포트. 수학은 topologyLayout 의 순수 함수에 위임한다.
import { FIT_K_MAX, K_MIN, fitTransform, zoomAt as zoomAtPure } from './topologyLayout';
import type { Rect, ViewState } from './types';

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

	fitBounds(b: Rect, viewportW: number, viewportH: number, pad = 40, kMax = FIT_K_MAX, kMin = K_MIN): void {
		this.set(fitTransform(b, viewportW, viewportH, pad, kMin, kMax));
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
