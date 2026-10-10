import { describe, expect, it } from 'vitest';
import { FIT_K_MAX, K_MAX, K_MIN, fitTransform } from '../topologyLayout';
import { createViewport, easeEmphasized, interpolateView } from '../viewport.svelte';

describe('createViewport', () => {
	it('초기값과 set/panBy', () => {
		const v = createViewport();
		expect(v.view).toEqual({ panX: 0, panY: 0, k: 1 });
		v.set({ panX: 5, panY: 6, k: 0.5 });
		v.panBy(10, -6);
		expect(v.view).toEqual({ panX: 15, panY: 0, k: 0.5 });
		expect(createViewport({ k: 2 }).view).toEqual({ panX: 0, panY: 0, k: 2 });
	});

	it('zoomAt 은 커서 아래 캔버스 점을 고정하고 zoomBy 는 뷰포트 중심 기준이다', () => {
		const v = createViewport({ panX: 40, panY: 30, k: 1 });
		const before = v.toCanvas(200, 100);
		v.zoomAt(200, 100, 1.5);
		expect(v.k).toBe(1.5);
		expect(v.toCanvas(200, 100).x).toBeCloseTo(before.x);
		expect(v.toCanvas(200, 100).y).toBeCloseTo(before.y);
		const c = v.toCanvas(400, 300);
		v.zoomBy(1.2, 800, 600);
		expect(v.k).toBeCloseTo(1.8);
		expect(v.toCanvas(400, 300).x).toBeCloseTo(c.x);
		v.zoomBy(100, 800, 600);
		expect(v.k).toBe(K_MAX);
		v.zoomBy(0.0001, 800, 600);
		expect(v.k).toBe(K_MIN);
	});

	it('맞춤 뷰를 적용하면 toScreen 은 toCanvas 의 역함수다', () => {
		const v = createViewport();
		v.set(fitTransform({ x: 100, y: 100, w: 400, h: 200 }, 1000, 600, 40, K_MIN, FIT_K_MAX));
		expect(v.k).toBe(1.25);
		expect(v.toScreen(300, 200)).toEqual({ x: 500, y: 300 });
		const p = v.toCanvas(123, 456);
		expect(v.toScreen(p.x, p.y).x).toBeCloseTo(123);
		expect(v.toScreen(p.x, p.y).y).toBeCloseTo(456);
	});
});

describe('카메라 전환 보간', () => {
	it('양 끝은 정확히 출발·도착 뷰이고, 중간에는 뷰포트 중심 아래 월드 점이 직선으로 옮겨진다', () => {
		const from = { panX: 0, panY: 0, k: 1 };
		const to = { panX: -300, panY: -100, k: 2 };
		expect(interpolateView(from, to, 0, 800, 600)).toEqual(from);
		expect(interpolateView(from, to, 1, 800, 600)).toEqual(to);
		const mid = interpolateView(from, to, 0.5, 800, 600);
		// 배율은 로그 공간 중간(√2), 중심 아래 월드 점은 (400,300)→(350,200) 의 중간
		expect(mid.k).toBeCloseTo(Math.SQRT2);
		expect((400 - mid.panX) / mid.k).toBeCloseTo(375);
		expect((300 - mid.panY) / mid.k).toBeCloseTo(250);
	});

	it('emphasized 곡선은 0→1 단조 증가이고 앞쪽이 빠르다(CSS cubic-bezier(0.2, 0, 0, 1))', () => {
		expect(easeEmphasized(0)).toBe(0);
		expect(easeEmphasized(1)).toBe(1);
		let prev = 0;
		for (let i = 1; i <= 20; i++) {
			const v = easeEmphasized(i / 20);
			expect(v).toBeGreaterThanOrEqual(prev);
			prev = v;
		}
		expect(easeEmphasized(0.5)).toBeGreaterThan(0.8);
	});
});
