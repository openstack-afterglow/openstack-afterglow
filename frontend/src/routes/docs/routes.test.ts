import { describe, expect, it } from 'vitest';
import { getDocGuides } from '$lib/docs/catalog';
import { docsMessages, type DocsLocale } from '$lib/docs/locales';
import type { DocGuide } from '$lib/docs/types';
import { load as loadLayout } from './+layout';
import { load as loadIndex } from './+page';
import { load as loadArticle } from './[slug]/+page';

const locales: DocsLocale[] = ['ko', 'en', 'ja', 'zh-CN'];

describe('localized MCP documentation routes', () => {
	it.each(locales)('exposes the MCP guide through navigation, hub and article in %s', async (locale) => {
		const url = new URL(`/docs/mcp${locale === 'ko' ? '' : `?lang=${locale}`}`, 'https://cloud.example.test');
		const layout = await loadLayout({ url } as Parameters<typeof loadLayout>[0]) as {
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
		expect(article.guide.title.trim()).not.toBe('');
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
