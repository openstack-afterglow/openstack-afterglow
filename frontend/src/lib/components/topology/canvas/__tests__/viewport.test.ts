import { describe, expect, it } from 'vitest';
import { K_MAX, K_MIN } from '../topologyLayout';
import { createViewport } from '../viewport.svelte';

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

	it('fitBounds 는 bounds 를 뷰포트 가운데에 맞추고 toScreen 은 toCanvas 의 역함수다', () => {
		const v = createViewport();
		v.fitBounds({ x: 100, y: 100, w: 400, h: 200 }, 1000, 600, 40);
		expect(v.k).toBe(1.25);
		expect(v.toScreen(300, 200)).toEqual({ x: 500, y: 300 });
		const p = v.toCanvas(123, 456);
		expect(v.toScreen(p.x, p.y).x).toBeCloseTo(123);
		expect(v.toScreen(p.x, p.y).y).toBeCloseTo(456);
	});
});
