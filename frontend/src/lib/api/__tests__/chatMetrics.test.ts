// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { computeMetrics, estimateTokens, formatMetrics } from '../chatMetrics';

describe('estimateTokens', () => {
	it('4 chars ≈ 1 token 근사', () => {
		expect(estimateTokens(0)).toBe(0);
		expect(estimateTokens(4)).toBe(1);
		expect(estimateTokens(400)).toBe(100);
	});
	it('0 초과면 최소 1', () => {
		expect(estimateTokens(1)).toBe(1);
	});
});

describe('computeMetrics', () => {
	it('firstToken 이 없으면 null', () => {
		expect(computeMetrics(100, null, 5000, false)).toBeNull();
	});
	it('tok/s = tokens / elapsedSeconds', () => {
		const m = computeMetrics(340, 1000, 3000, false);
		expect(m).not.toBeNull();
		expect(m!.seconds).toBeCloseTo(2.0);
		expect(m!.tokPerSec).toBeCloseTo(170);
		expect(m!.approximate).toBe(false);
	});
	it('elapsed 0 이면 0 나눗셈 없이 tokPerSec=0', () => {
		const m = computeMetrics(100, 5000, 5000, true);
		expect(m!.tokPerSec).toBe(0);
	});
	it('tokens 0 이면 tokPerSec=0', () => {
		const m = computeMetrics(0, 1000, 3000, true);
		expect(m!.tokPerSec).toBe(0);
	});
});

describe('formatMetrics', () => {
	it('null 이면 빈 문자열', () => {
		expect(formatMetrics(null)).toBe('');
	});
	it('확정치는 rate·tokens·seconds 를 · 로 연결', () => {
		const s = formatMetrics({ tokens: 340, seconds: 2.0, tokPerSec: 170, approximate: false });
		expect(s).toBe('170 tok/s · 340 tok · 2.0s');
	});
	it('근사치는 ~ 접두 + 소수 1자리', () => {
		const s = formatMetrics({ tokens: 50, seconds: 2.0, tokPerSec: 25, approximate: true });
		expect(s).toBe('~25.0 tok/s · 50 tok · 2.0s');
	});
	it('0 항목은 생략', () => {
		expect(formatMetrics({ tokens: 0, seconds: 0, tokPerSec: 0, approximate: false })).toBe('');
	});
});
