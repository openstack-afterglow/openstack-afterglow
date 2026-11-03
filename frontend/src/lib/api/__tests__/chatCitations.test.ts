// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { marked } from 'marked';
import {
	aggregateCitations,
	citationDomain,
	citationHref,
	copyMarkdownWithCitations,
	isPortableCitationHttpUrl,
	isSafeCitationHttpUrl,
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
	it('keeps distinct registered datasource observations even when their external URL is the same', () => {
		const first = { type: 'citation', source_kind: 'data_source', source_id: 'observation-one', citation_id: 'observation-one', url: 'https://metrics.example/dataset', snippet: '3 running VMs', observed_at: '2026-11-03T00:00:00Z' };
		const second = { ...first, source_id: 'observation-two', citation_id: 'observation-two', snippet: '5 running VMs', observed_at: '2026-11-03T00:01:00Z' };
		const observed = aggregateCitations([{ parts: [first, second] }]);
		expect(observed.map(({ source_id, snippet, observed_at }) => ({ source_id, snippet, observed_at }))).toEqual([
			{ source_id: first.source_id, snippet: first.snippet, observed_at: first.observed_at },
			{ source_id: second.source_id, snippet: second.snippet, observed_at: second.observed_at }
		]);
		expect(aggregateCitations([{ citations: [{ ...first, url: undefined }] }, { parts: [first] }])).toMatchObject([{ source_id: first.source_id, url: first.url }]);
	});
});

describe('portable registered sources', () => {
	const assetId = 'e83a2892-41f0-4ca2-a453-4e23118f32ba';
	it('retains canonical identities and provenance for every new source kind', () => {
		for (const source_kind of ['data_source', 'tool_result', 'user_input', 'asset']) {
			const citation = { source_kind, citation_id: 'c1', source_id: 'source-1', asset_id: assetId, observed_at: '2026-11-02T00:00:00Z', provenance: { tool_name: 'search' }, title: 'Evidence', snippet: 'Observed result' };
			expect(normalizeCitations([citation])).toEqual([citation]);
		}
	});
	it('intercepts only the exact registered uploaded-asset fallback', () => {
		const citation = { source_kind: 'asset' as const, asset_id: assetId, url: `source://assets/${assetId}` };
		expect(citationHref(citation)).toBe(`/lumen/sources/assets/${assetId}`);
		expect(normalizeCitations([{ ...citation, asset_id: 'another' }, { ...citation, source_kind: 'tool_result', source_id: 's1' }, { ...citation, url: `${citation.url}?token=secret` }])).toEqual([]);
	});
	it('preserves raw Markdown and adds only missing absolute canonical source links', () => {
		const content = '**Answer**\n\n[Existing](https://example.org/article)';
		const copied = copyMarkdownWithCitations(content, [
			{ source_kind: 'web', url: 'https://example.org/article' },
			{ source_kind: 'tool_result', source_id: 's1', url: 'https://console.example/lumen/sources/runs/run-1/c1', title: 'Result [1]' },
			{ source_kind: 'asset', asset_id: assetId, url: `source://assets/${assetId}`, title: 'Uploaded file' }
		]);
		expect(copied.startsWith(content)).toBe(true);
		expect(copied.split('https://example.org/article')).toHaveLength(2);
		expect(copied).toContain(String.raw`[Result \[1\]](<https://console.example/lumen/sources/runs/run-1/c1>)`);
		expect(copied).toContain(`[Uploaded file](<source://assets/${assetId}>)`);
	});
	it('never appends object-store signed URLs or invents a public origin', () => {
		expect(copyMarkdownWithCitations('Answer', [
			{ source_kind: 'asset', asset_id: assetId, url: 'https://objects.example/file?X-Amz-Signature=secret' },
			{ source_kind: 'document', document_index: 0, title: 'Input' },
			{ source_kind: 'web', url: 'https://objects.example/file?X-Goog-Signature=secret' }
		])).toBe('Answer');
	});
	it('never merges distinct registered non-web sources by a missing document index', () => {
		expect(aggregateCitations([{ citations: [
			{ source_kind: 'tool_result', source_id: 's1', title: 'First' },
			{ source_kind: 'tool_result', source_id: 's2', title: 'Second' }
		] }])).toHaveLength(2);
	});
	it.each(['-2', '?version=2'])('keeps a distinct registered source when an existing destination only shares its prefix: %s', async (suffix) => {
		const url = 'https://example.org/article';
		const content = `[Different observation](${url}${suffix})`;
		const copied = copyMarkdownWithCitations(content, [{ source_kind: 'web', url }]);
		const html = await marked.parse(copied);
		const destinations = [...html.matchAll(/\bhref=(["'])(.*?)\1/g)].map((match) => match[2]);
		expect(destinations).toEqual([url + suffix, url]);
		expect(copied.startsWith(content)).toBe(true);
	});
	it.each([
		'[Existing](https://example.org/article)',
		'[Existing][source]\n\n[source]: https://example.org/article',
		'<https://example.org/article>',
		'https://example.org/article'
	])('preserves existing exact Markdown destinations without adding another source link: %s', (content) => {
		expect(copyMarkdownWithCitations(content, [{ source_kind: 'web', url: 'https://example.org/article' }])).toBe(content);
	});
	it('does not mistake a URL inside code for a portable source link', async () => {
		const url = 'https://example.org/article';
		const content = `Example: \`${url}\``;
		const copied = copyMarkdownWithCitations(content, [{ source_kind: 'web', url }]);
		const html = await marked.parse(copied);
		expect([...html.matchAll(/\bhref=(["'])(.*?)\1/g)].map((match) => match[2])).toEqual([url]);
		expect(copied.startsWith(content)).toBe(true);
	});
});

it('restores all canonical citation parts without requiring a legacy citations projection', () => {
	const parts = Array.from({ length: 40 }, (_, index) => ({ type: 'citation', citation_id: `c${index}`, source_kind: 'web', url: `https://example.org/${index}` }));
	expect(aggregateCitations([{ parts }])).toHaveLength(40);
	expect(aggregateCitations([{ citations: [parts[0]], parts }])).toHaveLength(40);
});

it('copies canonical external data-source record URLs unchanged', () => {
	const url = 'https://git.example/org/repo/blob/main/data.csv';
	expect(copyMarkdownWithCitations('Observed dataset.', [{ source_kind: 'data_source', source_id: 'record-1', title: 'Dataset', url }])).toContain(`[Dataset](<${url}>)`);
	expect(copyMarkdownWithCitations('Observed dataset.', [{ source_kind: 'data_source', source_id: 'record-1', title: 'Dataset', url: `${url}?X-Amz-Signature=secret` }])).not.toContain('secret');
});

it.each(['temp_url_sig', 'temp_url_expires', 'token', 'access_token', 'api_key', 'authorization'])('does not export a bearer-bearing %s source URL', (key) => {
	expect(copyMarkdownWithCitations('Answer', [{ source_kind: 'data_source', source_id: 's1', url: `https://objects.example/private?${key}=secret` }])).toBe('Answer');
});

describe('portable source credential parameters', () => {
	const source = (url: string) => ({ source_kind: 'data_source' as const, citation_id: 'c1', source_id: 'record-1', title: 'Dataset', url });
	it.each([
		'#access_token=secret', '#id_token=secret', '#refresh_token=secret',
		'#ACCESS%5fTOKEN=secret', '#/callback?access_token=secret', '#/callback?client_secret=secret',
		'#access_token=secret?foo=bar', '#private_token=secret', '?client_secret=secret',
		'?private_token=secret', '?temp_url_sig=secret&temp_url_expires=123',
		'#temp_url_sig=secret', '?X-Amz-Credential=secret', '#X-Goog-Signature=secret',
		'?api-key=secret', '?api%2Dkey=secret', '#api-key=secret', '#/callback?api-key=secret'
	])('never renders or appends credential-bearing URL parameters %s', (suffix) => {
		const citation = source(`https://git.example/data.csv${suffix}`);
		expect(isPortableCitationHttpUrl(citation.url)).toBe(false);
		expect(citationHref(citation)).toBeNull();
		expect(normalizeCitations([citation])).toEqual([]);
		expect(copyMarkdownWithCitations('**Answer**', [citation])).toBe('**Answer**');
	});
	it.each([
		'#section', '?q=password+reset', '?q=password+reset#section', '#/document?section=overview',
		'#note=access_token%3Dnot-a-parameter', '#access%255ftoken=not-a-recognized-key',
		'?q=access_token%3Ddocumentation', '??token=not-a-recognized-key'
	])('keeps ordinary queries, anchors and once-decoded parameter names unchanged: %s', (suffix) => {
		const citation = source(`https://git.example/data.csv${suffix}`);
		expect(isPortableCitationHttpUrl(citation.url)).toBe(true);
		expect(citationHref(citation)).toBe(citation.url);
		expect(copyMarkdownWithCitations('**Answer**', [citation])).toContain(`[Dataset](<${citation.url}>)`);
	});
	it('rejects query or fragment field overflow, including empty fields, like native parse_qsl', () => {
		for (const delimiter of ['?', '#']) {
			expect(isPortableCitationHttpUrl(`https://git.example/data.csv${delimiter}${Array.from({ length: 129 }, () => 'q=x').join('&')}`)).toBe(false);
			expect(isPortableCitationHttpUrl(`https://git.example/data.csv${delimiter}q=x${'&'.repeat(128)}`)).toBe(false);
			expect(isPortableCitationHttpUrl(`https://git.example/data.csv${delimiter}${Array.from({ length: 128 }, () => 'q=x').join('&')}`)).toBe(true);
		}
	});
	it('does not reject fresh signed download transport URLs while excluding them from citations', () => {
		const url = 'https://objects.example/file?X-Amz-Signature=temporary';
		expect(isSafeCitationHttpUrl(url)).toBe(true);
		expect(isPortableCitationHttpUrl(url)).toBe(false);
	});
});

it.each(['auth'])('keeps legacy %s copy-only exclusions outside the native source-link policy', (key) => {
	const citation = { source_kind: 'data_source' as const, source_id: 's1', url: `https://example.org/document?${key}=public` };
	expect(isPortableCitationHttpUrl(citation.url)).toBe(true);
	expect(citationHref(citation)).toBe(citation.url);
	expect(normalizeCitations([citation])).toHaveLength(1);
	expect(copyMarkdownWithCitations('Answer', [citation])).toBe('Answer');
});

it.each(['#authorization', '#token', '#key', '#api-key', '#access_token', '#/callback?token'])('preserves the bare document anchor %s without treating it as a credential assignment', (fragment) => {
	const url = `https://example.org/document${fragment}`;
	const citation = { source_kind: 'data_source' as const, source_id: 's1', title: 'Document section', url };
	expect(isPortableCitationHttpUrl(url)).toBe(true);
	expect(citationHref(citation)).toBe(url);
	expect(copyMarkdownWithCitations('Answer', [citation])).toContain(`[Document section](<${url}>)`);
});
