import { describe, expect, it } from 'vitest';
import { docsContentHref, docsHref, docsLanguageHref, docsLocaleFromUrl } from './locales';
import { LOCALES } from '$lib/i18n/locales';

const origin = 'https://cloud.example.com';

describe('documentation language navigation', () => {
	it.each(LOCALES)('keeps the article, section and reader context when switching to %s', (locale) => {
		const source = new URL('/docs/manila?lang=en&tutorial=on&reader=shared#access-rules', origin);
		const next = new URL(docsLanguageHref(source, locale), origin);
		expect(next.pathname).toBe('/docs/manila');
		expect(next.hash).toBe('#access-rules');
		expect(next.searchParams.get('lang')).toBe(locale);
		expect(next.searchParams.get('tutorial')).toBe('on');
		expect(next.searchParams.get('reader')).toBe('shared');
		expect(source.searchParams.get('lang')).toBe('en');
	});

	it('explicit Korean overrides a saved foreign preference without losing section context', () => {
		const next = new URL(docsLanguageHref(new URL('/docs/nova?lang=zh-CN&tutorial=admin#connect', origin), 'ko'), origin);
		expect(next.searchParams.get('lang')).toBe('ko');
		expect(docsLocaleFromUrl(next, 'en')).toBe('ko');
		expect(next.searchParams.get('tutorial')).toBe('admin');
		expect(next.hash).toBe('#connect');
	});

	it('guide navigation carries language/tutorial but not an unrelated section', () => {
		const source = new URL('/docs/nova?lang=en&tutorial=on#connect', origin);
		const next = new URL(docsHref('neutron', 'en', source), origin);
		expect(next.pathname).toBe('/docs/neutron');
		expect(next.searchParams.get('lang')).toBe('en');
		expect(next.searchParams.get('tutorial')).toBe('on');
		expect(next.hash).toBe('');
	});

	it('body documentation links retain their own target/query/fragment and tutorial context', () => {
		const source = new URL('/docs/getting-started?lang=ja&tutorial=on', origin);
		const next = new URL(docsContentHref('/docs/waygate?view=reference#clients', 'ja', source), origin);
		expect(next.pathname).toBe('/docs/waygate');
		expect(next.hash).toBe('#clients');
		expect(next.searchParams.get('view')).toBe('reference');
		expect(next.searchParams.get('lang')).toBe('ja');
		expect(next.searchParams.get('tutorial')).toBe('on');
	});

	it.each(['/docs-admin', '/dashboard/compute/instances?section=details', 'https://docs.openstack.org/nova/latest/'])('does not rewrite non-documentation destination %s', (href) => {
		expect(docsContentHref(href, 'zh-CN', new URL('/docs?lang=zh-CN', origin))).toBe(href);
	});

	it.each(LOCALES)('selects supported %s independent of query ordering', (locale) => {
		expect(docsLocaleFromUrl(new URL(`/docs/nova?tutorial=on&lang=${locale}`, origin))).toBe(locale);
	});

	it.each(LOCALES)('inherits saved %s when no language selector is present', (locale) => {
		expect(docsLocaleFromUrl(new URL('/docs/nova', origin), locale)).toBe(locale);
	});

	it.each(['ja-JP', 'en-US', 'unknown', 'en\" onload=alert(1)'])('unsupported selector %s cannot become a document language', (value) => {
		const url = new URL('/docs', origin);
		url.searchParams.set('lang', value);
		expect(docsLocaleFromUrl(url)).toBe('ko');
		expect(docsLocaleFromUrl(url, 'vi')).toBe('vi');
		expect(docsLocaleFromUrl(url, 'zh-CN')).toBe('zh-CN');
	});
});
