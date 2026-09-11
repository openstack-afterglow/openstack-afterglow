// 스파크라인 좌표 계산. rx/tx 를 같은 축에 올리는 계약과 표본 1개 처리를 고정한다.
import { describe, expect, it } from 'vitest';
import { sparkPoints } from '../canvasHelpers';

describe('sparkPoints', () => {
	it('빈 입력은 빈 문자열 — 호출부가 "데이터 없음"을 0 과 구분해야 한다', () => {
		expect(sparkPoints([], 100, 30, 0)).toBe('');
	});

	it('표본이 1개면 가로선이 되도록 두 점을 낸다 (polyline 은 점 1개로 아무것도 안 그린다)', () => {
		const pts = sparkPoints([50], 100, 30, 100).split(' ');
		expect(pts).toHaveLength(2);
		expect(pts[0]).toBe('0,15');
		expect(pts[1]).toBe('100,15');
	});

	it('첫 점은 x=0, 마지막 점은 x=w 로 폭을 꽉 채운다', () => {
		const pts = sparkPoints([1, 2, 3], 100, 30, 3).split(' ');
		expect(pts).toHaveLength(3);
		expect(pts[0].startsWith('0,')).toBe(true);
		expect(pts[2].startsWith('100,')).toBe(true);
		expect(pts[1].startsWith('50,')).toBe(true);
	});

	it('y 는 위가 큰 값 — peak 는 0, 0 은 바닥(h)', () => {
		expect(sparkPoints([100, 0], 10, 40, 100)).toBe('0,0 10,40');
	});

	it('peak 를 공유하면 두 계열의 높이가 비교 가능하다', () => {
		const peak = 100;
		const rx = sparkPoints([100], 10, 40, peak);
		const tx = sparkPoints([50], 10, 40, peak);
		expect(rx).toBe('0,0 10,0');
		expect(tx).toBe('0,20 10,20');
	});

	it('peak 가 0 이면 0 으로 나누지 않고 바닥선을 낸다', () => {
		expect(sparkPoints([0, 0], 10, 40, 0)).toBe('0,40 10,40');
	});

	it('peak 를 넘는 값은 위쪽으로 잘린다 (그래프 밖으로 나가지 않는다)', () => {
		expect(sparkPoints([200], 10, 40, 100)).toBe('0,0 10,0');
	});
});
