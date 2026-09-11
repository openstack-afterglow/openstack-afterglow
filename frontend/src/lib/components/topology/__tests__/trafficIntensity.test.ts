// 사용량 → 선 굵기·불투명도(연속)와 흐름 점 빈도 계약.
import { describe, expect, it } from 'vitest';
import { bpsDecade, edgeIntensity, flowDotCount, flowRate } from '../topologyHelpers';

describe('edgeIntensity — 사용량 연속 반영', () => {
	it('예전 4단계의 앵커 값(1e5/1e6/1e7/1e8)을 그대로 유지한다', () => {
		expect(edgeIntensity(1e5)).toEqual({ width: 2.0, opacity: 0.65 });
		expect(edgeIntensity(1e6)).toEqual({ width: 2.5, opacity: 0.8 });
		expect(edgeIntensity(1e7)).toEqual({ width: 3.0, opacity: 0.9 });
		expect(edgeIntensity(1e8)).toEqual({ width: 3.5, opacity: 1.0 });
	});

	it('1e5 미만은 바닥값이고 1e8 초과는 포화한다', () => {
		expect(edgeIntensity(0)).toEqual({ width: 1.5, opacity: 0.4 });
		expect(edgeIntensity(9.9e4)).toEqual({ width: 1.5, opacity: 0.4 });
		expect(edgeIntensity(1e12)).toEqual({ width: 3.5, opacity: 1.0 });
	});

	it('같은 단계 안에서도 사용량이 커지면 굵어진다(계단이 아니다)', () => {
		// 예전에는 1e6~1e7 이 전부 폭 2.5 로 같아 10배 차이를 읽을 수 없었다
		const a = edgeIntensity(1.2e6);
		const b = edgeIntensity(4.3e6);
		const c = edgeIntensity(9e6);
		expect(a.width).toBeLessThan(b.width);
		expect(b.width).toBeLessThan(c.width);
		expect(a.opacity).toBeLessThan(b.opacity);
		expect(b.opacity).toBeLessThan(c.opacity);
		for (const s of [a, b, c]) {
			expect(s.width).toBeGreaterThan(2.5);
			expect(s.width).toBeLessThan(3.0);
		}
	});

	it('1e5 이상에서 단조 증가한다', () => {
		let prevW = 0;
		let prevO = 0;
		for (let e = 5; e <= 8.001; e += 0.25) {
			const { width, opacity } = edgeIntensity(10 ** e);
			expect(width).toBeGreaterThanOrEqual(prevW);
			expect(opacity).toBeGreaterThanOrEqual(prevO);
			prevW = width;
			prevO = opacity;
		}
	});
});

describe('flowRate / flowDotCount — 점 빈도', () => {
	it('bpsDecade 는 0..3 으로 포화한다', () => {
		expect(bpsDecade(1e5)).toBe(0);
		expect(bpsDecade(1e6)).toBeCloseTo(1, 6);
		expect(bpsDecade(1e8)).toBe(3);
		expect(bpsDecade(1e20)).toBe(3);
		expect(bpsDecade(0)).toBe(0);
	});

	it('사용량이 커지면 빈도와 속도가 함께 커진다', () => {
		const lo = flowRate(1e5);
		const hi = flowRate(1e8);
		expect(lo.freq).toBeLessThan(hi.freq);
		expect(lo.speed).toBe(40);
		expect(hi.speed).toBe(130);
	});

	it('점 개수는 경로가 길수록 늘어 통과 빈도가 길이에 무관하게 유지된다', () => {
		const bps = 5e6;
		const { freq, speed } = flowRate(bps);
		const lens = [120, 300, 600, 1200];
		// 균일 간격 순환이므로 한 지점 통과 빈도 = n · speed / len
		const achieved = lens.map((len) => (flowDotCount(bps, len, 64) * speed) / len);
		// 개수가 정수로 반올림되므로 짧은 경로에서 오차가 크다 — 상대 오차 25% 안이면 된다
		for (const [i, f] of achieved.entries()) {
			expect(f / freq, `len=${lens[i]}`).toBeGreaterThan(0.75);
			expect(f / freq, `len=${lens[i]}`).toBeLessThan(1.25);
		}
		// 개수를 고정하면(예전 방식) 빈도가 길이에 반비례해 10배 벌어진다. 지금은 거의 평평해야 한다
		expect(Math.max(...achieved) / Math.min(...achieved)).toBeLessThan(1.4);
		const fixedCount = 3;
		const fixedAchieved = lens.map((len) => (fixedCount * speed) / len);
		expect(Math.max(...fixedAchieved) / Math.min(...fixedAchieved)).toBeCloseTo(10, 0);
	});

	it('같은 경로에서 사용량이 커지면 점이 더 많아진다', () => {
		const len = 400;
		const counts = [1e5, 1e6, 1e7, 1e8].map((b) => flowDotCount(b, len, 64));
		for (let i = 1; i < counts.length; i++) expect(counts[i]).toBeGreaterThan(counts[i - 1]);
	});

	it('상한과 하한을 지킨다(성능 예산·최소 가시성)', () => {
		expect(flowDotCount(1e12, 100000, 8)).toBe(8);
		expect(flowDotCount(1e5, 1, 8)).toBe(1);
		expect(flowDotCount(1e5, 0, 8)).toBe(1);
	});
});
