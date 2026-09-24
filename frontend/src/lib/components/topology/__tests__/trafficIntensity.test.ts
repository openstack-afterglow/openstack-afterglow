// @vitest-environment node
// 사용량 → 선 굵기·불투명도(연속)와 흐름 점 빈도 계약.
import { describe, expect, it } from 'vitest';
import {
	bpsDecade,
	edgeIntensity,
	flowDotCount,
	flowRate,
	INTENSITY_DECADES,
	INTENSITY_FLOOR_BPS,
	NO_TELEMETRY_STYLE,
} from '../topologyHelpers';

describe('edgeIntensity — 사용량 연속 반영', () => {
	it('앵커 값(1e3/1e5/1e7/1e9)을 지킨다', () => {
		expect(edgeIntensity(1e3)).toEqual({ width: 1.8, opacity: 0.55 });
		expect(edgeIntensity(1e5)).toEqual({ width: 2.7, opacity: 0.7 });
		expect(edgeIntensity(1e7)).toEqual({ width: 3.6, opacity: 0.85 });
		expect(edgeIntensity(1e9)).toEqual({ width: 4.5, opacity: 1.0 });
	});

	it('1 Gbps 에서 포화하고 그 위는 더 굵어지지 않는다', () => {
		expect(edgeIntensity(1e12)).toEqual(edgeIntensity(1e9));
		expect(INTENSITY_FLOOR_BPS * 10 ** INTENSITY_DECADES).toBe(1e9);
	});

	it('NaN·음수도 굵기를 NaN 으로 만들지 않는다 (stroke-width: NaN 이면 선이 사라진다)', () => {
		for (const bad of [NaN, -1, -Infinity]) {
			const { width, opacity } = edgeIntensity(bad);
			expect(Number.isFinite(width), `bps=${bad}`).toBe(true);
			expect(Number.isFinite(opacity), `bps=${bad}`).toBe(true);
		}
		expect(bpsDecade(NaN)).toBe(0);
		expect(Number.isFinite(flowDotCount(NaN, 400))).toBe(true);
	});

	it('**계측된 0 은 계측 없음과 절대 같아 보이지 않는다**', () => {
		// 이것이 이 스케일 교정의 핵심이다. 예전에는 `bps < 1e5` 가 전부
		// {width 1.5, opacity 0.40} 으로 붕괴해 `bps == null` 과 바이트 단위로 동일했고,
		// 실측(2026-09-13) NIC 43개 중 39개가 그 구간이라 **살아 있는 링크 91% 가
		// "계측 없음" 으로 그려졌다.**
		const quiet = edgeIntensity(0);
		expect(quiet.width).toBeGreaterThan(NO_TELEMETRY_STYLE.width);
		expect(quiet.opacity).toBeGreaterThan(NO_TELEMETRY_STYLE.opacity);
		// 하한 미만(1 bps)도 마찬가지로 "없음" 이 아니라 "조용함" 이다
		expect(edgeIntensity(1)).toEqual(quiet);
	});

	it('실환경 분포(중앙값 8.7k ~ 최대 366k)에서 굵기가 실제로 갈린다', () => {
		// 예전 스케일에서는 이 구간이 통째로 바닥값이라 전부 같은 굵기였다.
		const median = edgeIntensity(8_729);
		const busiest = edgeIntensity(365_770);
		expect(busiest.width - median.width).toBeGreaterThan(0.5);
		expect(median.width).toBeGreaterThan(NO_TELEMETRY_STYLE.width);
	});

	it('같은 decade 안에서도 사용량이 커지면 굵어진다(계단이 아니다)', () => {
		const a = edgeIntensity(1.2e6);
		const b = edgeIntensity(4.3e6);
		const c = edgeIntensity(9e6);
		expect(a.width).toBeLessThan(b.width);
		expect(b.width).toBeLessThan(c.width);
		expect(a.opacity).toBeLessThan(b.opacity);
		expect(b.opacity).toBeLessThan(c.opacity);
		for (const s of [a, b, c]) {
			expect(s.width).toBeGreaterThan(3.0);
			expect(s.width).toBeLessThan(3.6);
		}
	});

	it('하한부터 포화까지 **엄격히** 증가한다 (평평한 함수는 통과하면 안 된다)', () => {
		let prevW = 0;
		let prevO = 0;
		for (let e = 3; e <= 9.001; e += 0.25) {
			const { width, opacity } = edgeIntensity(10 ** e);
			expect(width).toBeGreaterThan(prevW);
			expect(opacity).toBeGreaterThan(prevO);
			prevW = width;
			prevO = opacity;
		}
		// 포화 뒤에는 더 오르지 않는다
		expect(edgeIntensity(1e10)).toEqual(edgeIntensity(1e9));
	});
});

describe('flowRate / flowDotCount — 점 빈도', () => {
	it(`bpsDecade 는 0..${INTENSITY_DECADES} 로 포화한다`, () => {
		expect(bpsDecade(INTENSITY_FLOOR_BPS)).toBe(0);
		expect(bpsDecade(1e4)).toBeCloseTo(1, 6);
		expect(bpsDecade(1e9)).toBe(INTENSITY_DECADES);
		expect(bpsDecade(1e20)).toBe(INTENSITY_DECADES);
		expect(bpsDecade(0)).toBe(0);
	});

	it('사용량이 커지면 빈도와 속도가 함께 커진다 (양 끝값은 구간 확대 전과 같다)', () => {
		const lo = flowRate(INTENSITY_FLOOR_BPS);
		const hi = flowRate(1e9);
		expect(lo.freq).toBeLessThan(hi.freq);
		expect(lo.speed).toBe(40);
		expect(hi.speed).toBe(130);
		expect(lo.freq).toBeCloseTo(0.6, 6);
		expect(hi.freq).toBeCloseTo(4.0, 6);
	});

	it('점 개수는 경로가 길수록 늘어 통과 빈도가 길이에 무관하게 유지된다 (production 기본 상한)', () => {
		const bps = 5e6;
		const { freq, speed } = flowRate(bps);
		// **maxPerEdge 를 넘기지 않는다** — production(TopologyCanvas rebuildFlow)은 기본값 8 을 쓴다.
		// 상한에 닿기 전 구간(이 bps 에서는 len ≲ 300)에서만 빈도 보존이 성립한다.
		const lens = [60, 120, 180, 240, 300];
		// 균일 간격 순환이므로 한 지점 통과 빈도 = n · speed / len
		const achieved = lens.map((len) => (flowDotCount(bps, len) * speed) / len);
		// 개수가 정수로 반올림되므로 짧은 경로에서 오차가 크다 — 상대 오차 25% 안이면 된다
		for (const [i, f] of achieved.entries()) {
			expect(f / freq, `len=${lens[i]}`).toBeGreaterThan(0.75);
			expect(f / freq, `len=${lens[i]}`).toBeLessThan(1.25);
		}
		// 개수를 고정하면(예전 방식) 빈도가 길이에 반비례해 10배 벌어진다. 지금은 거의 평평해야 한다
		expect(Math.max(...achieved) / Math.min(...achieved)).toBeLessThan(1.4);
		const fixedCount = 3;
		const fixedAchieved = lens.map((len) => (fixedCount * speed) / len);
		expect(Math.max(...fixedAchieved) / Math.min(...fixedAchieved)).toBeCloseTo(5, 0);
	});

	it('긴 경로에서는 maxPerEdge 가 먼저 걸려 빈도 보존이 깨진다 — 개수가 아니라 속도만 남는다', () => {
		// 이 사실을 숨기면 "빈도 = 사용량" 주장이 실제보다 넓게 들린다.
		const len = 600;
		expect(flowDotCount(1e4, len)).toBe(8);
		expect(flowDotCount(1e9, len)).toBe(8);   // 5 decade 차이가 같은 개수로 붕괴한다
		// 남는 구분은 속도뿐이다
		expect(flowRate(1e9).speed).toBeGreaterThan(flowRate(1e4).speed * 2);
		// 짧은 경로에서는 개수로도 구분된다
		expect(flowDotCount(1e9, 220)).toBeGreaterThan(flowDotCount(1e4, 220));
	});

	it('같은 경로에서 사용량이 커지면 점이 더 많아진다 (상한에 닿기 전 구간)', () => {
		const len = 220;
		const counts = [1e3, 1e5, 1e7, 1e9].map((b) => flowDotCount(b, len));
		expect(Math.max(...counts)).toBeLessThan(8);   // 상한이 결과를 가리지 않는 구간인지 먼저 확인
		for (let i = 1; i < counts.length; i++) expect(counts[i]).toBeGreaterThan(counts[i - 1]);
	});

	it('상한과 하한을 지킨다(성능 예산·최소 가시성)', () => {
		expect(flowDotCount(1e12, 100000, 8)).toBe(8);
		expect(flowDotCount(1e5, 1, 8)).toBe(1);
		expect(flowDotCount(1e5, 0, 8)).toBe(1);
	});
});
