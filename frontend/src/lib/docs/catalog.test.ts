import { describe, expect, it } from 'vitest';
import type { DocsLocale } from './locales';
import { createDocSearchIndex, getDocGuides, searchDocGuides } from './catalog';

const nativeSnapshotQueries: { locale: DocsLocale; query: string }[] = [
	{ locale: 'ko', query: 'Cinder 스냅샷' },
	{ locale: 'en', query: 'Cinder snapshot' },
	{ locale: 'ja', query: 'Cinder スナップショット' },
	{ locale: 'zh-CN', query: 'Cinder 快照' },
];

const nativePersonalMcpKeyQueries: { locale: DocsLocale; query: string }[] = [
	{ locale: 'ko', query: '개인 키 Authorization' },
	{ locale: 'en', query: 'personal key Authorization' },
	{ locale: 'ja', query: '個人キー Authorization' },
	{ locale: 'zh-CN', query: '个人密钥 Authorization' },
];

describe('localized documentation search', () => {
	it.each(nativeSnapshotQueries)('finds Cinder from $locale native operation terms', async ({ locale, query }) => {
		const index = createDocSearchIndex(await getDocGuides(locale));
		expect(searchDocGuides(query, index).map(({ slug }) => slug)).toContain('cinder');
		expect(searchDocGuides(`${query} nonexistent-operation-zzzz`, index)).toEqual([]);
	});

	it.each(nativePersonalMcpKeyQueries)('finds the personal MCP connector guide from $locale native terms', async ({ locale, query }) => {
		const guides = await getDocGuides(locale);
		const index = createDocSearchIndex(guides);
		expect(guides.filter(({ slug }) => slug === 'mcp')).toHaveLength(1);
		expect(searchDocGuides(query, index).map(({ slug }) => slug)).toContain('mcp');
		expect(searchDocGuides(`${query} nonexistent-operation-zzzz`, index)).toEqual([]);
	});

	it.each(nativePersonalMcpKeyQueries)('provides the same usable HTTP example in $locale', async ({ locale }) => {
		const guide = (await getDocGuides(locale)).find(({ slug }) => slug === 'mcp')!;
		const commands = guide.sections.flatMap((section) => section.commands ?? []);
		const sourceCommands = (await getDocGuides('ko')).find(({ slug }) => slug === 'mcp')!
			.sections.flatMap((section) => section.commands ?? []);
		expect(commands.map(({ code }) => code)).toEqual(sourceCommands.map(({ code }) => code));
		const config = JSON.parse(guide.sections.find(({ id }) => id === 'http-config')!.commands![0].code);
		expect(config.mcpServers['my-stream-server']).toEqual({
			type: 'http',
			url: 'https://cloud.dmslab.re.kr/mcp',
			headers: { Authorization: 'Bearer <personal key>' },
		});
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
