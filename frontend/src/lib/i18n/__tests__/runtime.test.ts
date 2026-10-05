import { afterEach, describe, expect, it } from 'vitest';
import { LOCALE_COOKIE, resolveLocale } from '../locales';
import { defineMessages, getLocale, initLocale, intlLocale, setLocale } from '../runtime.svelte';

const source = {
	greeting: '안녕하세요, {name}님',
	onlyKorean: '한국어 원문',
	results: '{count}개 결과',
	broken: '정상 원문',
	rich: '<strong>{name}</strong>을 삭제합니다',
};

const t = defineMessages<typeof source>('sample', {
	'../messages/ko/sample.json': source,
	'../messages/en/sample.json': {
		greeting: 'Hello, {name}',
		results: '{count, plural, one {# result} other {# results}}',
		broken: 'Valid English',
		rich: 'Delete <strong>{name}</strong>',
	},
	'../messages/ja/sample.json': {
		greeting: 'こんにちは、{name}さん',
		broken: '{name, plural, one {壊れた}}',
		rich: '<strong>{name}</strong>を削除します',
	},
});

afterEach(() => {
	initLocale('ko');
	document.cookie = `${LOCALE_COOKIE}=; path=/; max-age=0`;
	document.documentElement.lang = '';
});

describe('i18n runtime', () => {
	it('accepts supported cookie values and falls back for missing or untrusted values', () => {
		for (const locale of ['ko', 'en', 'ja', 'zh-CN'] as const) expect(resolveLocale(locale)).toBe(locale);
		for (const value of [undefined, null, '', 'zh-TW', 'en-US', 'JA', '<script>']) {
			expect(resolveLocale(value)).toBe('ko');
		}
	});

	it('renders the Korean source by default', () => {
		expect(getLocale()).toBe('ko');
		expect(t('greeting', { name: '지민' })).toBe('안녕하세요, 지민님');
		expect(intlLocale()).toBe('ko-KR');
	});

	it('falls back from Japanese to English and then to the Korean source', () => {
		initLocale('ja');
		expect(t('greeting', { name: 'Aki' })).toBe('こんにちは、Akiさん');
		expect(t('results', { count: 2 })).toBe('2 results');
		expect(t('onlyKorean')).toBe('한국어 원문');
	});

	it('skips an invalid translation instead of breaking the page', () => {
		initLocale('ja');
		expect(t('broken')).toBe('Valid English');
	});

	it('uses the plural rules of the language the message is written in', () => {
		initLocale('en');
		expect(t('results', { count: 1 })).toBe('1 result');
		initLocale('ko');
		expect(t('results', { count: 1 })).toBe('1개 결과');
	});

	it('returns namespace:key for an unknown key', () => {
		expect(t('missing' as keyof typeof source)).toBe('sample:missing');
	});

	it('keeps values as text when building rich segments', () => {
		initLocale('en');
		expect(t.rich('rich', { name: '<img src=x onerror=alert(1)>' })).toEqual([
			{ type: 'text', value: 'Delete ' },
			{ type: 'element', tag: 'strong', children: [{ type: 'text', value: '<img src=x onerror=alert(1)>' }] },
		]);
		expect(t('rich', { name: 'db' })).toBe('Delete <strong>db</strong>');
	});

	it('persists the choice for SSR and updates the document language', () => {
		setLocale('zh-CN');
		expect(getLocale()).toBe('zh-CN');
		expect(document.cookie).toContain(`${LOCALE_COOKIE}=zh-CN`);
		expect(document.documentElement.lang).toBe('zh-CN');
		expect(t('greeting', { name: 'Li' })).toBe('Hello, Li');
	});
});
