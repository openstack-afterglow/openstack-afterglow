import { describe, expect, it } from 'vitest';
import { renderMarkdown } from '../chatMarkdown';

describe('renderMarkdown', () => {
	it('마크다운 강조를 렌더한다', () => {
		const html = renderMarkdown('**굵게** _기울임_');
		expect(html).toContain('<strong>굵게</strong>');
		expect(html).toContain('<em>기울임</em>');
	});

	it('<script> 를 제거한다 (XSS 방어)', () => {
		const html = renderMarkdown('안녕<script>alert(1)</script>');
		expect(html).not.toContain('<script');
		expect(html).toContain('안녕');
	});

	it('javascript: 링크를 제거한다', () => {
		const html = renderMarkdown('[클릭](javascript:alert(1))');
		expect(html).not.toContain('javascript:');
	});

	it('onerror 등 이벤트 핸들러 속성을 제거한다', () => {
		const html = renderMarkdown('<img src=x onerror=alert(1)>');
		expect(html).not.toContain('onerror');
	});

	it('코드 블록을 language 클래스와 함께 pre>code 로 렌더한다', () => {
		const html = renderMarkdown('```js\nconst a = 1;\n```');
		expect(html).toContain('<pre>');
		expect(html).toContain('<code');
		expect(html).toContain('language-js');
	});
});

describe('registered source Markdown', () => {
	const asset_id = 'e83a2892-41f0-4ca2-a453-4e23118f32ba';
	const url = `source://assets/${asset_id}`;
	const citation = { source_kind: 'asset', asset_id, url };
	it('allows only an exact registered upload and renders a local authenticated source page', () => {
		const html = renderMarkdown(`[File](${url})`, { citations: [citation] });
		expect(html).toContain(`href=\"/lumen/sources/assets/${asset_id}\"`);
		expect(html).not.toContain('source://');
		expect(renderMarkdown(`[File](${url})`)).not.toContain('href=');
		expect(renderMarkdown(`[File](${url})`, { citations: [{ ...citation, asset_id: 'foreign' }] })).not.toContain('href=');
	});
	it('does not broaden DOMPurify schemes or custom image protocols', () => {
		const html = renderMarkdown(`[bad](source://tools/delete) ![file](${url}) [js](javascript:alert%281%29)`, { citations: [citation] });
		expect(html).not.toContain('source:');
		expect(html).not.toContain('javascript:');
		expect(renderMarkdown('[Web](https://example.org)')).toContain('href=\"https://example.org\"');
	});
	it('keys cached rendering by registered source ownership and removes its sanitizer hook', () => {
		const content = `[File](${url})`;
		expect(renderMarkdown(content, { cache: true, citations: [citation] })).toContain('href=');
		expect(renderMarkdown(content, { cache: true })).not.toContain('href=');
		expect(renderMarkdown(content, { citations: [citation] })).toContain('href=');
		expect(renderMarkdown(content)).not.toContain('href=');
	});
});
