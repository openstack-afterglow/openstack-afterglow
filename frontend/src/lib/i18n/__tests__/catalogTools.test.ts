// @vitest-environment node
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import {
	exportCsv,
	importCsv,
	loadCatalogs,
	loadReviews,
	markReviewed,
	parseCsv,
	reviewState,
	validateCatalogs,
	writeCatalogs,
	type Catalogs,
	type ReviewManifests,
} from '../../../../scripts/i18n-core.mjs';
import { findHardcodedText } from '../../../../scripts/i18n-scan.mjs';

type Messages = Record<string, string>;

function catalogs(ko: Messages, en: Messages, ja: Messages = en, zh: Messages = en): Catalogs {
	return {
		namespaces: ['demo'],
		messages: { ko: { demo: ko }, en: { demo: en }, ja: { demo: ja }, 'zh-CN': { demo: zh } },
		modules: ['demo'],
		loadErrors: [],
	};
}

const emptyReviews = (): ReviewManifests => ({ en: {}, ja: {}, 'zh-CN': {} });

const codes = (data: Catalogs) =>
	validateCatalogs(data)
		.filter((finding) => finding.level === 'error')
		.map((finding) => `${finding.code}:${finding.locale ?? '-'}:${finding.key ?? ''}`);

describe('catalog validation', () => {
	it('accepts complete, equivalent translations', () => {
		expect(codes(catalogs({ 'list.title': '{count}개 인스턴스' }, { 'list.title': '{count, plural, one {# instance} other {# instances}}' }))).toEqual([]);
	});

	it('reports missing, extra and empty translations', () => {
		const data = catalogs({ a: '가', b: '나' }, { a: 'A', extra: 'X' }, { a: 'A', b: ' ' });
		expect(codes(data)).toEqual(['extra-key:en:extra', 'missing-key:en:b', 'empty-message:ja:b', 'extra-key:zh-CN:extra', 'missing-key:zh-CN:b']);
	});

	it('rejects changed placeholders, markup, syntax errors and leftover Korean', () => {
		const data = catalogs(
			{ greet: '{name}님 환영합니다', bold: '<strong>{count}</strong>개', plural: '{count}개' },
			{ greet: 'Welcome {user}', bold: '{count} selected', plural: '{count, plural, one {#}}' },
			{ greet: '{name}님', bold: '<strong>{count}</strong>件', plural: '{count}件' },
		);
		expect(codes(data)).toEqual([
			'argument-mismatch:en:greet',
			'tag-mismatch:en:bold',
			'syntax:en:plural',
			'untranslated-hangul:ja:greet',
			'argument-mismatch:zh-CN:greet',
			'tag-mismatch:zh-CN:bold',
			'syntax:zh-CN:plural',
		]);
	});

	it('rejects crossed markup and tags split across different ICU render paths', () => {
		const data = catalogs(
			{ nested: '<strong><em>내용</em></strong>', branch: '{choice, select, yes {<strong>예</strong>} other {아니오}}' },
			{ nested: '<strong><em>Body</strong></em>', branch: '{choice, select, yes {<strong>Yes} other {No</strong>}}' },
			{ nested: '<strong><em>Body</em></strong>', branch: '{choice, select, yes {<strong>Yes</strong>} other {No}}' },
			{ nested: '<strong><em>Body</em></strong>', branch: '{choice, select, yes {<strong>Yes</strong>} other {No}}' },
		);
		expect(codes(data)).toEqual(['rich-structure:en:nested', 'rich-structure:en:branch']);
	});

	it('preserves custom snippets, correlated selectors and literal model hints', () => {
		const message = '{choice, select, yes {<link><strong>} other {<link>}}{name}{choice, select, yes {</strong></link>} other {</link>}} <model>';
		expect(codes(catalogs({ body: message }, { body: message }))).toEqual([]);
	});

	it('reports invalid Korean source markup before it can be reviewed', () => {
		const data = catalogs({ body: '<strong><em>내용</strong></em>' }, { body: '<strong><em>Body</em></strong>' });
		const reviews = emptyReviews();
		expect(codes(data)).toEqual(['rich-structure:ko:body']);
		expect(() => markReviewed(data, reviews, 'ja', 'demo')).toThrow(Error);
		expect(reviews.ja).toEqual({});
	});

	it('requires a namespace module and catalogs for every locale', () => {
		const data = catalogs({ a: '가' }, { a: 'A' });
		data.modules = [];
		delete data.messages.ja.demo;
		expect(codes(data)).toEqual(['missing-module:-:', 'missing-namespace:ja:']);
	});
});

describe('review status and spreadsheet exchange', () => {
	it('refuses corrupted markup before importing or approving any row', () => {
		const source = '<strong><em>내용</em></strong>';
		const data = catalogs({ body: source }, { body: '<strong><em>Body</em></strong>' });
		const reviews = emptyReviews();
		const csv = `namespace,key,source_ko,translation\r\ndemo,body,${source},<strong><em>Body</strong></em>`;
		expect(importCsv(data, reviews, 'ja', csv, { markReviewed: true }))
			.toMatchObject({ updated: 0, errors: [expect.stringMatching(/closing tag/)] });
		expect(data.messages.ja.demo.body).toBe('<strong><em>Body</em></strong>');
		expect(reviews.ja).toEqual({});
	});

	it.each([
		['namespace,key,source_ko,translation,status', 'demo,save,저장,Save, please,draft'],
		['namespace,key,source_ko,translation', 'demo,save,저장'],
		['namespace,key,source_ko,translation,translation', 'demo,save,저장,Save,Other'],
	])('rejects ragged records or duplicate headers: %s / %s', (header, row) => {
		const data = catalogs({ save: '저장' }, { save: 'Save' }, { save: '保存' });
		const reviews = emptyReviews();
		expect(importCsv(data, reviews, 'ja', `${header}\r\n${row}`, { markReviewed: true }))
			.toMatchObject({ updated: 0, errors: [expect.stringMatching(/CSV/)] });
		expect(data.messages.ja.demo.save).toBe('保存');
		expect(reviews.ja).toEqual({});
	});

	it('does not approve invalid translations or partially mark a namespace', () => {
		const data = catalogs({ save: '저장', greet: '{name}님' }, { save: 'Save', greet: 'Hello {name}' }, { save: '保存', greet: 'こんにちは{user}' });
		const reviews = emptyReviews();
		expect(() => markReviewed(data, reviews, 'ja', 'demo')).toThrow(/greet/);
		expect(reviews.ja).toEqual({});
		expect(reviewState(data, reviews, 'ja', 'demo', 'save')).toBe('draft');
		expect(markReviewed(data, reviews, 'ja', 'demo', ['save'])).toBe(1);
		expect(reviewState(data, reviews, 'ja', 'demo', 'save')).toBe('reviewed');
		expect(reviewState(data, reviews, 'ja', 'demo', 'greet')).toBe('draft');
	});

	it.each(['"Save', 'sa"ve', '"Save"oops'])('rejects malformed CSV without changing translations or reviews: %s', (translation) => {
		const data = catalogs({ save: '저장' }, { save: 'Save' }, { save: '保存' });
		const reviews = emptyReviews();
		const result = importCsv(data, reviews, 'ja', `namespace,key,source_ko,translation\r\ndemo,save,저장,${translation}`, { markReviewed: true });
		expect(result).toMatchObject({ updated: 0, errors: [expect.stringMatching(/Invalid CSV/)] });
		expect(data.messages.ja.demo.save).toBe('保存');
		expect(reviews.ja).toEqual({});
	});

	it('moves a translation from draft to reviewed and back to outdated when the source changes', () => {
		const data = catalogs({ save: '저장' }, { save: 'Save' });
		const reviews = emptyReviews();
		expect(reviewState(data, reviews, 'ja', 'demo', 'save')).toBe('draft');
		expect(markReviewed(data, reviews, 'ja', 'demo')).toBe(1);
		expect(reviewState(data, reviews, 'ja', 'demo', 'save')).toBe('reviewed');
		data.messages.ko.demo.save = '저장하기';
		expect(reviewState(data, reviews, 'ja', 'demo', 'save')).toBe('outdated');
	});

	it('round-trips quotes, commas, newlines and meaningful whitespace in a reviewed CSV', () => {
		const data = catalogs(
			{ body: '삭제하면 "복구"할 수 없습니다,\n계속할까요?', other: '{name} 저장' },
			{ body: 'Deleting cannot be "undone",\ncontinue?', other: 'Save {name}' },
		);
		const reviews = emptyReviews();
		const csv = exportCsv(data, reviews, 'ja');
		expect(parseCsv(csv)[1].slice(0, 3)).toEqual(['demo', 'body', '삭제하면 "복구"할 수 없습니다,\n계속할까요?']);

		const edited = csv.replace('"Deleting cannot be ""undone"",\ncontinue?",draft', '"  削除すると「元に戻せません」。\n続行しますか？\n ",draft');
		expect(importCsv(data, reviews, 'ja', edited, { markReviewed: true })).toEqual({ errors: [], updated: 2 });
		expect(data.messages.ja.demo.body).toBe('  削除すると「元に戻せません」。\n続行しますか？\n ');
		expect(reviewState(data, reviews, 'ja', 'demo', 'body')).toBe('reviewed');

		const before = { ...data.messages.ja.demo };
		const invalid = edited.replace('削除すると', '消すと').replace(',Save {name},draft', ',Save {title},draft');
		expect(importCsv(data, reviews, 'ja', invalid).errors).toEqual(['line 3: demo:other must use {name}']);
		expect(data.messages.ja.demo).toEqual(before);
	});

	it('rejects rows whose Korean source changed after export', () => {
		const data = catalogs({ save: '저장' }, { save: 'Save' });
		const reviews = emptyReviews();
		const csv = exportCsv(data, reviews, 'ja');
		data.messages.ko.demo.save = '저장하기';
		expect(importCsv(data, reviews, 'ja', csv.replace(',Save,Save,draft', ',Save,保存,draft'))).toEqual({
			errors: ['line 2: demo:save Korean source changed since export; export again'],
			updated: 0,
		});
		expect(data.messages.ja.demo.save).toBe('Save');
	});
});

describe('catalog and review loading safety', () => {
	it('does not overwrite recoverable catalog bytes or approve partial loads', async () => {
		const dir = await mkdtemp(join(tmpdir(), 'afterglow-i18n-load-'));
		const originalKo = JSON.stringify({ a: '가', b: '나' });
		const brokenJa = '{"a":"Existing A","b":"Keep this translation"';
		try {
			await mkdir(join(dir, 'messages', 'ko'), { recursive: true });
			await mkdir(join(dir, 'messages', 'en'), { recursive: true });
			await mkdir(join(dir, 'messages', 'ja'), { recursive: true });
			await mkdir(join(dir, 'review'), { recursive: true });
			await writeFile(join(dir, 'messages', 'ko', 'demo.json'), originalKo);
			await writeFile(join(dir, 'messages', 'en', 'demo.json'), JSON.stringify({ a: 'A', b: 'B' }));
			await writeFile(join(dir, 'messages', 'ja', 'demo.json'), brokenJa);
			const data = await loadCatalogs(dir);
			const reviews = emptyReviews();
			expect(importCsv(data, reviews, 'ja', 'namespace,key,source_ko,translation\ndemo,a,가,New value'))
				.toMatchObject({ updated: 0, errors: [expect.stringMatching(/invalid-json.*ja\/demo/)] });
			expect(data.messages.ja.demo).toBeUndefined();
			expect(() => markReviewed(data, reviews, 'en', 'demo')).toThrow(/invalid-json/);
			expect(reviews.en).toEqual({});
			await expect(writeCatalogs(data, reviews, dir)).rejects.toThrow(/invalid-json/);
			expect(await readFile(join(dir, 'messages', 'ja', 'demo.json'), 'utf8')).toBe(brokenJa);
			expect(await readFile(join(dir, 'messages', 'ko', 'demo.json'), 'utf8')).toBe(originalKo);
		} finally {
			await rm(dir, { recursive: true, force: true });
		}
	});

	it.each(['{', '[]', '{"demo:save":23}'])('does not turn an existing malformed review manifest into empty approvals: %s', async (text) => {
		const dir = await mkdtemp(join(tmpdir(), 'afterglow-i18n-review-'));
		try {
			await mkdir(join(dir, 'review'), { recursive: true });
			await writeFile(join(dir, 'review', 'ja.json'), text);
			await expect(loadReviews(dir)).rejects.toThrow(/ja\.json/);
		} finally {
			await rm(dir, { recursive: true, force: true });
		}
	});

	it('allows missing manifests but propagates existing-file read failures', async () => {
		const dir = await mkdtemp(join(tmpdir(), 'afterglow-i18n-review-io-'));
		try {
			expect(await loadReviews(dir)).toEqual(emptyReviews());
			await mkdir(join(dir, 'review', 'ja.json'), { recursive: true });
			await expect(loadReviews(dir)).rejects.toThrow(/ja\.json/);
		} finally {
			await rm(dir, { recursive: true, force: true });
		}
	});
});

describe('hard-coded text scanner', () => {
	it('ignores comments but finds strings, templates and markup text', () => {
		const script = [
			'// 주석은 무시',
			"const url = 'https://example.com'; const label = '저장'; /* 블록 주석 */",
			'const tpl = `${count}개 ${fn(/["]/.test(x) ? "a" : "b")}`;',
			'const ratio = total / 2; // 나눗셈 뒤 주석',
		].join('\n');
		expect(findHardcodedText(script, 'x.ts').map((hit) => hit.line)).toEqual([2, 3]);

		const component = [
			'<script lang="ts">',
			'\t// 스크립트 주석',
			"\tconst title = '제목';",
			'</script>',
			'<!-- 마크업 주석 -->',
			'<p title="도움말">{title}</p>',
			'<style>',
			'\t/* 스타일 주석 */',
			'</style>',
		].join('\n');
		expect(findHardcodedText(component, 'x.svelte').map((hit) => hit.line)).toEqual([3, 6]);
	});
});
