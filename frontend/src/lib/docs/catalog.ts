import type { DocGuide } from './types';
import type { DocsLocale } from './locales';
import { translateDocGuide } from './translate';
import { gettingStarted } from './gettingStarted';
import { coreGuides } from './coreGuides';
import { platformGuides } from './platformGuides';
import { additionalGuides } from './additionalGuides';

export const docGuides: DocGuide[] = [gettingStarted, ...coreGuides, ...additionalGuides, ...platformGuides];

export interface DocSearchIndex {
	guides: DocGuide[];
	entries: { guide: DocGuide; text: string }[];
}

export function createDocSearchIndex(guides: DocGuide[]): DocSearchIndex {
	return {
		guides,
		entries: guides.map((guide) => ({
			guide,
			text: [
				guide.name, guide.title, guide.summary, ...guide.keywords, ...guide.prerequisites,
				...guide.consoleLinks.flatMap((link) => [link.label, link.description ?? '']),
				...(guide.externalLinks ?? []).flatMap((link) => [link.label, link.description ?? '']),
				...guide.sections.flatMap((section) => [
					section.title, ...(section.paragraphs ?? []), ...(section.bullets ?? []),
					...(section.steps ?? []).flatMap((step) => [
						step.title, ...step.text, step.command?.label ?? '', step.command?.code ?? '',
						...(step.links ?? []).flatMap((link) => [link.label, link.description ?? '']),
					]),
					...(section.commands ?? []).flatMap((command) => [command.label, command.code]),
					...(section.links ?? []).flatMap((link) => [link.label, link.description ?? '']),
					section.callout?.title ?? '', section.callout?.text ?? '',
				]),
			].join(' ').normalize('NFC').toLowerCase(),
		})),
	};
}

export function searchDocGuides(query: string, index: DocSearchIndex): DocGuide[] {
	const terms = query.normalize('NFC').toLowerCase().trim().split(/\s+/).filter(Boolean);
	if (terms.length === 0) return index.guides;
	return index.entries.filter(({ text }) => terms.every((term) => text.includes(term))).map(({ guide }) => guide);
}

const translationLoaders = {
	en: () => import('./translations/en'),
	ja: () => import('./translations/ja'),
	'zh-CN': () => import('./translations/zh-CN'),
};
const koreanCatalog = Promise.resolve(docGuides);
const catalogs = new Map<DocsLocale, Promise<DocGuide[]>>();

export function getDocGuides(locale: DocsLocale): Promise<DocGuide[]> {
	if (locale === 'ko') return koreanCatalog;
	const existing = catalogs.get(locale);
	if (existing) return existing;
	const catalog = translationLoaders[locale]()
		.then(({ default: translations }) => docGuides.map((guide) => translateDocGuide(guide, translations)));
	catalogs.set(locale, catalog);
	return catalog;
}
