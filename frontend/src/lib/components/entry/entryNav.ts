import { t } from '$lib/i18n/ns/public-entry';

export interface EntryNavLink { label: string; href: string }

/**
 * Landing section links. The landing passes `''` (in-page anchors); other entry surfaces pass `'/'`, so the
 * bar is the same everywhere and a scene never rebuilds it. Call inside `$derived` so the locale is tracked.
 */
export function entryNavLinks(base: '' | '/'): EntryNavLink[] {
	return [
		{ label: t('landing.story.nav.compute'), href: `${base}#capabilities` },
		{ label: t('landing.story.nav.gateway'), href: `${base}#workflow` },
		{ label: t('landing.story.nav.kubernetes'), href: `${base}#work` },
		{ label: t('landing.story.nav.onprem'), href: `${base}#contact` },
		{ label: t('landing.nav.docs'), href: '/docs' },
	];
}
