import { describe, expect, it } from 'vitest';
import { getDocGuides } from '$lib/docs/catalog';
import { LOCALES } from '$lib/i18n/locales';
import { docsMessages, type DocsLocale } from '$lib/docs/locales';
import type { DocGuide } from '$lib/docs/types';
import { load as loadLayout } from './+layout';
import { load as loadIndex } from './+page';
import { load as loadArticle } from './[slug]/+page';

const locales: readonly DocsLocale[] = LOCALES;

describe('localized MCP documentation routes', () => {
	it.each(locales)('exposes the MCP guide through navigation, hub and article in %s', async (locale) => {
		const url = new URL('/docs/mcp', 'https://cloud.example.test');
		const layout = await loadLayout({ url, parent: async () => ({ locale }) } as Parameters<typeof loadLayout>[0]) as {
			docsLocale: DocsLocale;
			docsNavigationGuides: Pick<DocGuide, 'slug' | 'name' | 'category'>[];
		};
		expect(layout.docsLocale).toBe(locale);
		expect(layout.docsNavigationGuides.filter(({ slug }) => slug === 'mcp')).toHaveLength(1);
		const parent = async () => layout;
		const hub = await loadIndex({ parent } as Parameters<typeof loadIndex>[0]) as { guides: DocGuide[] };
		const article = await loadArticle({ params: { slug: 'mcp' }, parent } as Parameters<typeof loadArticle>[0]) as {
			guide: DocGuide;
			relatedGuides: DocGuide[];
		};
		expect(hub.guides.filter(({ slug }) => slug === 'mcp')).toEqual([article.guide]);
		expect(article.guide.slug).toBe('mcp');
		if (locale !== 'ko') {
			const korean = (await getDocGuides('ko')).find(({ slug }) => slug === 'mcp')!;
			expect(article.guide.title).not.toBe(korean.title);
			expect(article.guide.summary).not.toBe(korean.summary);
		}
		expect(article.relatedGuides.map(({ slug }) => slug)).toContain('lumen');
		const lumen = await loadArticle({ params: { slug: 'lumen' }, parent } as Parameters<typeof loadArticle>[0]) as {
			relatedGuides: DocGuide[];
		};
		expect(lumen.relatedGuides.find(({ slug }) => slug === 'mcp')).toEqual(article.guide);
	});

	it.each(locales)('keeps a localized 404 for an unregistered MCP-like slug in %s', async (locale) => {
		await expect(loadArticle({
			params: { slug: 'mcp-missing' },
			parent: async () => ({ docsLocale: locale }),
		} as Parameters<typeof loadArticle>[0])).rejects.toMatchObject({
			status: 404,
			body: { message: docsMessages[locale].notFound },
		});
	});
});

describe('localized IAM documentation routes', () => {
	it.each(locales)('exposes one fully localized IAM guide with the canonical project graph in %s', async (locale) => {
		const url = new URL('/docs/iam', 'https://cloud.example.test');
		const layout = await loadLayout({ url, parent: async () => ({ locale }) } as Parameters<typeof loadLayout>[0]) as {
			docsLocale: DocsLocale;
			docsNavigationGuides: Pick<DocGuide, 'slug' | 'name' | 'category'>[];
		};
		const parent = async () => layout;
		const hub = await loadIndex({ parent } as Parameters<typeof loadIndex>[0]) as { guides: DocGuide[] };
		const article = await loadArticle({ params: { slug: 'iam' }, parent } as Parameters<typeof loadArticle>[0]) as {
			guide: DocGuide;
			relatedGuides: DocGuide[];
		};
		expect(layout.docsLocale).toBe(locale);
		expect(layout.docsNavigationGuides.filter(({ slug }) => slug === 'iam')).toHaveLength(1);
		expect(hub.guides.filter(({ slug }) => slug === 'iam')).toEqual([article.guide]);
		const graphs = article.guide.sections.flatMap(({ hierarchy }) => hierarchy ? [hierarchy] : []);
		expect(graphs).toHaveLength(1);
		expect(graphs[0].levels).toEqual([
			{ role: 'project_owner' },
			{ role: 'project_admin' },
			{ role: 'project_member', alsoIncludes: ['member'] },
			{ role: 'project_reader', alsoIncludes: ['reader'] },
		]);
		expect(article.relatedGuides.map(({ slug }) => slug)).toEqual(expect.arrayContaining([
			'waygate', 'drover', 'lumen', 'palimpsest',
		]));
		for (const service of ['waygate', 'drover', 'lumen', 'palimpsest']) {
			const serviceGuide = hub.guides.find(({ slug }) => slug === service)!;
			const links = serviceGuide.sections.flatMap(({ links }) => links ?? []);
			expect(links).toContainEqual({ label: article.guide.name, href: `/docs/iam#${service}` });
			expect(article.guide.sections.some(({ id }) => id === service)).toBe(true);
		}
		if (locale !== 'ko') {
			const korean = (await getDocGuides('ko')).find(({ slug }) => slug === 'iam')!;
			expect(article.guide.name).not.toBe(korean.name);
			expect(article.guide.summary).not.toBe(korean.summary);
			expect(graphs[0].description).not.toBe(korean.sections.find(({ hierarchy }) => hierarchy)!.hierarchy!.description);
		}
	});
});
