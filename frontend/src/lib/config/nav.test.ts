// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { DEFAULT_BETA_FEATURES } from '$lib/stores/betaFeatures';
import { adminNavSections, allNavItems, isNavSectionActive } from './nav';
import { initLocale } from '$lib/i18n/runtime.svelte';

beforeEach(() => initLocale('ko'));
afterEach(() => initLocale('ko'));

describe('allNavItems service inheritance', () => {
	it('preserves section service gates for flattened user routes', () => {
		const items = allNavItems(false, DEFAULT_BETA_FEATURES);
		const byHref = new Map(items.map(item => [item.href, item]));

		expect(byHref.get('/dashboard/file-storage')?.service).toBe('manila');
		expect(byHref.get('/dashboard/database/instances')?.service).toBe('trove');
		expect(byHref.get('/dashboard/object-storage/buckets')?.service).toBe('swift');
		expect(byHref.get('/dashboard/compute/instances')?.service).toBeNull();
	});

	it('includes volume and database backups while keeping snapshots gated by default', () => {
		const hrefs = allNavItems(false, DEFAULT_BETA_FEATURES).map(item => item.href);

		expect(hrefs).toContain('/dashboard/volumes/backups');
		expect(hrefs).toContain('/dashboard/database/backups');
		expect(hrefs).not.toContain('/dashboard/volumes/snapshots');
	});

	it('keeps explicit item service gates for admin routes', () => {
		const items = allNavItems(true, DEFAULT_BETA_FEATURES);
		const fileStorage = items.find(item => item.href === '/admin/file-storage');

		expect(fileStorage?.service).toBe('manila');
	});


	it('keeps service gates on both primary and secondary service links', () => {
		const byHref = new Map(allNavItems(true, DEFAULT_BETA_FEATURES).map((item) => [item.href, item]));
		for (const href of ['/admin/drover', '/admin/drover/templates']) {
			expect(byHref.get(href)?.service).toBe('k3s');
		}
		for (const href of ['/admin/chat', '/admin/chat/stats', '/admin/chat/quotas', '/admin/chat/models', '/admin/chat/tools']) {
			expect(byHref.get(href)?.service).toBe('chat');
		}
		expect(byHref.get('/admin/libraries')?.service).toBeNull();
		expect(byHref.get('/admin/waygate')?.service).toBe('waygate');
	});

  it.each([
    ['/admin/drover', '/admin/containers'],
    ['/admin/drover/templates', '/admin/containers'],
    ['/admin/drover/cluster-1', '/admin/containers'],
    ['/admin/chat/stats/daily', '/admin/chat'],
    ['/admin/libraries/123', '/admin/libraries'],
    ['/admin/waygate', '/admin/topology'],
  ])('activates only the owning section for %s', (path, owner) => {
    expect(adminNavSections.filter(section => isNavSectionActive(section, path)).map(section => section.prefix)).toEqual([owner]);
  });

  it.each(['/admin/droverish', '/admin/chatty', '/admin/libraries-old', '/admin/waygate-extra'])('does not activate a section for a lookalike route %s', path => {
    expect(adminNavSections.some(section => isNavSectionActive(section, path))).toBe(false);
  });

	it('retains catalog keys and stable routes while flattened labels follow each locale', () => {
		for (const [locale, instances, compute, packages] of [
			['ko', '인스턴스', 'Compute', '프로젝트 패키지'],
			['en', 'Instances', 'Compute', 'Project packages'],
			['ja', 'インスタンス', 'コンピュート', 'プロジェクトパッケージ'],
			['zh-CN', '实例', '计算', '项目软件包'],
		] as const) {
			initLocale(locale);
			const byHref = new Map(allNavItems(false, DEFAULT_BETA_FEATURES).map(item => [item.href, item]));
			expect(byHref.get('/dashboard/compute/instances')).toMatchObject({ label: instances, labelKey: 'items.instances', section: compute, sectionKey: 'sections.compute' });
			expect(byHref.get('/palimpsest/packages')).toMatchObject({ label: packages, labelKey: 'items.projectPackages', section: 'Palimpsest', service: null });
		}
	});
});
