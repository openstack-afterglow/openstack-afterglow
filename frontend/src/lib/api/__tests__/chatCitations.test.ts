// @vitest-environment node
import { describe, expect, it } from 'vitest';
import {
	aggregateCitations,
	citationDomain,
	citationLabel,
	normalizeCitations
} from '../chatCitations';

describe('citationDomain', () => {
	it('호스트에서 www 제거', () => {
		expect(citationDomain('https://www.example.com/path')).toBe('example.com');
		expect(citationDomain('https://en.wikipedia.org/wiki/X')).toBe('en.wikipedia.org');
	});
	it('파싱 실패 시 앞부분', () => {
		expect(citationDomain('not a url')).toBe('not a url');
	});
});

describe('citationLabel', () => {
	it('title 우선', () => {
		expect(citationLabel({ source_kind: 'web', url: 'https://a.com', title: 'A 제목' })).toBe('A 제목');
	});
	it('title 없으면 도메인', () => {
		expect(citationLabel({ source_kind: 'web', url: 'https://www.a.com/x' })).toBe('a.com');
	});
});

describe('normalizeCitations', () => {
	it('url 있는 항목만, 방어적', () => {
		expect(normalizeCitations([{ url: 'https://a.com', title: 'A' }, { title: 'no url' }, null, 5])).toEqual([
			{ source_kind: 'web', url: 'https://a.com', title: 'A', snippet: null }
		]);
	});
	it('배열 아니면 빈 목록', () => {
		expect(normalizeCitations(undefined)).toEqual([]);
	});
	it('javascript:·data: 등 비-http 스킴은 제거(XSS 방어)', () => {
		expect(
			normalizeCitations([
				{ url: 'javascript:alert(1)' },
				{ url: 'data:text/html,x' },
				{ url: 'https://ok.com', title: 'OK' }
			])
		).toEqual([{ source_kind: 'web', url: 'https://ok.com', title: 'OK', snippet: null }]);
	});

	it('LiteLLM document citations retain their index without a fabricated URL', () => {
		expect(
			normalizeCitations([
				{ source_kind: 'document', document_index: 2, title: '운영 가이드', snippet: '문서의 근거' }
			])
		).toEqual([
			{ source_kind: 'document', document_index: 2, title: '운영 가이드', snippet: '문서의 근거' }
		]);
	});
});

describe('aggregateCitations', () => {
	it('url 기준 중복 제거 + 등장 순서 보존', () => {
		const agg = aggregateCitations([
			{ citations: [{ url: 'https://a.com', title: 'A' }] },
			{ citations: [{ url: 'https://b.com' }, { url: 'https://a.com', title: 'A' }] }
		]);
		expect(agg.map((c) => c.url)).toEqual(['https://a.com', 'https://b.com']);
	});
	it('더 풍부한 항목으로 업그레이드(title/snippet 보완)', () => {
		const agg = aggregateCitations([
			{ citations: [{ url: 'https://a.com' }] },
			{ citations: [{ url: 'https://a.com', title: 'A', snippet: 's' }] }
		]);
		expect(agg[0]).toEqual({ source_kind: 'web', url: 'https://a.com', title: 'A', snippet: 's' });
	});
});
