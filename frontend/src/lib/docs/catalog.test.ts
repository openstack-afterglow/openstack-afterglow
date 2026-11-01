import { describe, expect, it } from 'vitest';
import type { DocsLocale } from './locales';
import { createDocSearchIndex, getDocGuides, searchDocGuides } from './catalog';
import type { DocGuide } from './types';
import { translateDocGuide } from './translate';

const nativeSnapshotQueries: { locale: DocsLocale; query: string }[] = [
	{ locale: 'ko', query: 'Cinder 스냅샷' },
	{ locale: 'en', query: 'Cinder snapshot' },
	{ locale: 'ja', query: 'Cinder スナップショット' },
	{ locale: 'zh-CN', query: 'Cinder 快照' },
	{ locale: 'sw', query: 'Cinder nakala za muda' },
	{ locale: 'nb', query: 'Cinder øyeblikksbilde' },
	{ locale: 'ms', query: 'Cinder petikan' },
	{ locale: 'vi', query: 'Cinder bản chụp nhanh' },
	{ locale: 'bn', query: 'Cinder স্ন্যাপশট' },
];

const nativePersonalMcpKeyQueries: { locale: DocsLocale; query: string }[] = [
	{ locale: 'ko', query: '개인 키 Authorization' },
	{ locale: 'en', query: 'personal key Authorization' },
	{ locale: 'ja', query: '個人キー Authorization' },
	{ locale: 'zh-CN', query: '个人密钥 Authorization' },
	{ locale: 'sw', query: 'ufunguo binafsi Authorization' },
	{ locale: 'nb', query: 'personlig nøkkel Authorization' },
	{ locale: 'ms', query: 'kunci peribadi Authorization' },
	{ locale: 'vi', query: 'khóa cá nhân Authorization' },
	{ locale: 'bn', query: 'ব্যক্তিগত কী Authorization' },
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

describe('document hierarchy content', () => {
	const guide: DocGuide = {
		slug: 'hierarchy-example', name: 'Guide', title: 'Guide', summary: 'Guide', category: 'start',
		keywords: [], prerequisites: [], related: [], consoleLinks: [],
		sections: [{
			id: 'roles', title: 'Roles', hierarchy: {
				title: 'Hierarchy', description: 'Conditional access', relation: 'includes',
				levels: [{ role: 'example_owner', alsoIncludes: ['native_writer'] }, { role: 'example_reader' }],
			},
		}],
	};

	it('finds graph-only descriptions and side branches while requiring every search term', () => {
		const index = createDocSearchIndex([guide]);
		expect(searchDocGuides('conditional native_WRITER', index).map(({ slug }) => slug)).toEqual(['hierarchy-example']);
		expect(searchDocGuides('Hierarchy example_reader', index).map(({ slug }) => slug)).toEqual(['hierarchy-example']);
		expect(searchDocGuides('conditional absent-role', index)).toEqual([]);
	});

	it('localizes graph prose without treating exact roles or side branches as translation keys', () => {
		const translated = translateDocGuide(guide, {
			Guide: 'Anleitung', Roles: 'Rollen', Hierarchy: 'Hierarchie',
			'Conditional access': 'Bedingter Zugriff', includes: 'enthält',
		});
		expect(translated.sections[0].hierarchy).toEqual({
			title: 'Hierarchie', description: 'Bedingter Zugriff', relation: 'enthält',
			levels: [{ role: 'example_owner', alsoIncludes: ['native_writer'] }, { role: 'example_reader' }],
		});
		expect(searchDocGuides('Zugriff native_writer', createDocSearchIndex([translated])).map(({ slug }) => slug)).toEqual(['hierarchy-example']);
	});

	it('rejects missing graph explanations instead of displaying an untranslated authority caveat', () => {
		expect(() => translateDocGuide(guide, { Guide: 'Anleitung', Roles: 'Rollen', Hierarchy: 'Hierarchie', includes: 'enthält' }))
			.toThrow('Missing documentation translation: hierarchy-example: Conditional access');
	});
});
