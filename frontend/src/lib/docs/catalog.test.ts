import { describe, expect, it } from 'vitest';
import type { DocsLocale } from './locales';
import { createDocSearchIndex, getDocGuides, searchDocGuides } from './catalog';

const nativeSnapshotQueries: { locale: DocsLocale; query: string }[] = [
	{ locale: 'ko', query: 'Cinder 스냅샷' },
	{ locale: 'en', query: 'Cinder snapshot' },
	{ locale: 'ja', query: 'Cinder スナップショット' },
	{ locale: 'zh-CN', query: 'Cinder 快照' },
];

describe('localized documentation search', () => {
	it.each(nativeSnapshotQueries)('finds Cinder from $locale native operation terms', async ({ locale, query }) => {
		const index = createDocSearchIndex(await getDocGuides(locale));
		expect(searchDocGuides(query, index).map(({ slug }) => slug)).toContain('cinder');
		expect(searchDocGuides(`${query} nonexistent-operation-zzzz`, index)).toEqual([]);
	});

	it('normalizes decomposed Korean, case and whitespace while requiring every term', async () => {
		const index = createDocSearchIndex(await getDocGuides('ko'));
		const query = `  cINDER\t${'스냅샷'.normalize('NFD')}  `;
		expect(searchDocGuides(query, index).map(({ slug }) => slug)).toContain('cinder');
		expect(searchDocGuides(`${query} missing-resource-zzzz`, index)).toEqual([]);
	});

	it('searches actual body instructions rather than only service titles', async () => {
		const index = createDocSearchIndex(await getDocGuides('en'));
		expect(searchDocGuides('provisioning_status', index).map(({ slug }) => slug)).toContain('octavia');
		expect(searchDocGuides('DHSS CephFS', index).map(({ slug }) => slug)).toContain('manila');
	});
});
