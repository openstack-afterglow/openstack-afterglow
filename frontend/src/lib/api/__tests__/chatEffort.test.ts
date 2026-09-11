import { describe, expect, it } from 'vitest';
import { effortLabel, effortOptionsFor, normalizeEffort } from '../chatEffort';

describe('effortOptionsFor', () => {
	it('reasoning 미지원이면 빈 배열', () => {
		expect(effortOptionsFor({ reasoning: false })).toEqual([]);
		expect(effortOptionsFor(null)).toEqual([]);
		expect(effortOptionsFor(undefined)).toEqual([]);
	});
	it('model options 앞에 auto와 none을 제공한다', () => {
		expect(
			effortOptionsFor({
				reasoning: true,
				reasoning_options: [{ type: 'effort', values: ['low', 'xhigh', 'max', 'ultra', 'vendor_extra'] }]
			})
		).toEqual(['auto', 'none', 'low', 'xhigh', 'max', 'ultra']);
	});
	it('effort 목록이 없거나 toggle뿐인 모델은 auto/none만 제공한다', () => {
		expect(effortOptionsFor({ reasoning: true })).toEqual(['auto', 'none']);
		expect(effortOptionsFor({ reasoning: true, reasoning_options: [{ type: 'toggle', values: [] }] })).toEqual([
			'auto',
			'none'
		]);
	});
});

describe('effortLabel', () => {
	it('한국어 라벨 매핑', () => {
		expect(effortLabel('auto')).toBe('자동');
		expect(effortLabel('none')).toBe('없음');
		expect(effortLabel('max')).toBe('최대');
		expect(effortLabel('ultra')).toBe('울트라');
	});
	it('매핑 없으면 원문', () => {
		expect(effortLabel('weird')).toBe('weird');
	});
});

describe('normalizeEffort', () => {
	const caps = { reasoning: true, reasoning_options: [{ type: 'effort', values: ['low', 'high'] }] };
	it('유효 effort 는 유지', () => {
		expect(normalizeEffort('high', caps)).toBe('high');
	});
	it('모델에 없는 effort는 auto로 정규화한다', () => {
		expect(normalizeEffort('medium', caps)).toBe('auto');
	});
	it('null/빈값은 auto다', () => {
		expect(normalizeEffort(null, caps)).toBe('auto');
		expect(normalizeEffort('', caps)).toBe('auto');
	});
});
