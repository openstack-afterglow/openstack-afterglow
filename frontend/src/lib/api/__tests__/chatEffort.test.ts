// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { effortForModel, effortLabel, effortOptionsFor, normalizeEffort } from '../chatEffort';

describe('effortOptionsFor', () => {
	it('reasoning 미지원이면 빈 배열', () => {
		expect(effortOptionsFor({ reasoning: false })).toEqual([]);
		expect(effortOptionsFor(null)).toEqual([]);
		expect(effortOptionsFor(undefined)).toEqual([]);
	});
	const listed = {
		reasoning: true,
		reasoning_options: [
			{
				type: 'effort',
				values: ['low', 'xhigh', 'max', 'ultra', 'vendor_extra']
			}
		]
	};
	it('Lumen이 none을 지원한다고 알리면 auto 다음에 none을 제공한다', () => {
		expect(effortOptionsFor(listed, true)).toEqual(['auto', 'none', 'low', 'xhigh', 'max', 'ultra']);
		expect(
			effortOptionsFor(
				{
					reasoning: true,
					reasoning_options: [{ type: 'toggle', values: [] }]
				},
				true
			)
		).toEqual(['auto', 'none']);
	});
	it('none 지원이 false이거나 없으면(gpt-5, o3, 구버전 Lumen) none을 숨긴다', () => {
		expect(effortOptionsFor(listed, false)).toEqual(['auto', 'low', 'xhigh', 'max', 'ultra']);
		expect(effortOptionsFor(listed)).toEqual(['auto', 'low', 'xhigh', 'max', 'ultra']);
		expect(effortOptionsFor({ reasoning: true }, undefined)).toEqual(['auto']);
	});
	it('reasoning 미지원이면 none 지원 값과 무관하게 빈 배열', () => {
		expect(effortOptionsFor({ reasoning: false }, true)).toEqual([]);
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
	const caps = {
		reasoning: true,
		reasoning_options: [{ type: 'effort', values: ['low', 'high'] }]
	};
	it('유효 effort 는 유지', () => {
		expect(normalizeEffort('high', caps)).toBe('high');
	});
	it('모델에 없는 effort는 auto로 정규화한다', () => {
		expect(normalizeEffort('medium', caps)).toBe('auto');
	});
	it('모델이 none을 지원하지 않으면 none을 auto로 정규화한다', () => {
		expect(normalizeEffort('none', caps, true)).toBe('none');
		expect(normalizeEffort('none', caps, false)).toBe('auto');
		expect(normalizeEffort('none', caps)).toBe('auto');
	});
	it('null/빈값은 auto다', () => {
		expect(normalizeEffort(null, caps)).toBe('auto');
		expect(normalizeEffort('', caps)).toBe('auto');
	});
});

describe('effortForModel', () => {
	const models = [
		{
			model_name: 'gpt-5.1',
			reasoning_none_supported: true,
			capabilities: {
				reasoning: true,
				reasoning_options: [{ type: 'effort', values: ['none', 'low', 'high'] }]
			}
		},
		{
			model_name: 'gpt-5',
			reasoning_none_supported: false,
			capabilities: {
				reasoning: true,
				reasoning_options: [{ type: 'effort', values: ['minimal', 'low', 'high'] }]
			}
		}
	];
	it('재생성 대상 모델이 none을 지원하지 않으면 auto로 보낸다', () => {
		expect(effortForModel('none', models, 'gpt-5.1')).toBe('none');
		expect(effortForModel('none', models, 'gpt-5')).toBe('auto');
		expect(effortForModel('high', models, 'gpt-5')).toBe('high');
	});
	it('목록에 없는 모델은 auto로 보낸다', () => {
		expect(effortForModel('none', models, 'unknown')).toBe('auto');
		expect(effortForModel('low', models, undefined)).toBe('auto');
	});
});
