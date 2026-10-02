/**
 * Supported interface languages.
 *
 * Korean is the source language: every message is authored in `messages/ko/*.json` first and
 * every other locale maps the same keys. English is the pivot reference for translators who do
 * not read Korean, so Japanese and Chinese fall back to English before Korean.
 */
export const LOCALES = ['ko', 'en', 'ja', 'zh-CN'] as const;

export type Locale = (typeof LOCALES)[number];

export const SOURCE_LOCALE: Locale = 'ko';
export const DEFAULT_LOCALE: Locale = 'ko';

/** Readable by SSR so the first HTML response is already in the chosen language. */
export const LOCALE_COOKIE = 'afterglow_locale';
export const LOCALE_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 365;

/** Each language is always shown in its own script so a reader can find it from any UI language. */
export const LOCALE_NATIVE_NAMES: Record<Locale, string> = {
	ko: '한국어',
	en: 'English',
	ja: '日本語',
	'zh-CN': '简体中文',
};

/** Compact label for space-constrained controls. */
export const LOCALE_SHORT_NAMES: Record<Locale, string> = {
	ko: 'KO',
	en: 'EN',
	ja: 'JA',
	'zh-CN': 'ZH',
};

/** BCP 47 tags passed to `Intl.*` formatters. */
export const INTL_LOCALES: Record<Locale, string> = {
	ko: 'ko-KR',
	en: 'en-US',
	ja: 'ja-JP',
	'zh-CN': 'zh-CN',
};

export const FALLBACK_CHAIN: Record<Locale, readonly Locale[]> = {
	ko: ['ko'],
	en: ['en', 'ko'],
	ja: ['ja', 'en', 'ko'],
	'zh-CN': ['zh-CN', 'en', 'ko'],
};

export function isLocale(value: unknown): value is Locale {
	return typeof value === 'string' && (LOCALES as readonly string[]).includes(value);
}

/** Resolves a stored preference; unknown or missing values keep the Korean default. */
export function resolveLocale(value: string | null | undefined): Locale {
	return isLocale(value) ? value : DEFAULT_LOCALE;
}
