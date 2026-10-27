// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { DEFAULT_BETA_FEATURES } from '$lib/stores/betaFeatures';
import { adminNavSections, allNavItems, isNavSectionActive } from './nav';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { isProjectAgnosticPath } from './routes';

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

	it('keeps Aodh and Gnocchi as ungated monitoring siblings in all four locales', () => {
		for (const [locale, aodh, gnocchi] of [
			['ko', 'Aodh 알람', 'Gnocchi 서비스'],
			['en', 'Aodh alarms', 'Gnocchi service'],
			['ja', 'Aodh アラーム', 'Gnocchi サービス'],
			['zh-CN', 'Aodh 告警', 'Gnocchi 服务'],
		] as const) {
			initLocale(locale);
			const items = allNavItems(true, DEFAULT_BETA_FEATURES);
			expect(items.find(item => item.href === '/admin/monitoring/aodh')).toMatchObject({ label: aodh, sectionKey: 'sections.monitoring', service: null });
			expect(items.find(item => item.href === '/admin/monitoring/gnocchi')).toMatchObject({ label: gnocchi, sectionKey: 'sections.monitoring', service: null });
			expect(adminNavSections.filter(section => isNavSectionActive(section, '/admin/monitoring/aodh/settings')).map(section => section.prefix)).toEqual(['/admin/monitoring']);
		}
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
    ['/admin/application-credentials', '/admin/users'],
    ['/admin/user-credentials', '/admin/users'],
  ])('activates only the owning section for %s', (path, owner) => {
    expect(adminNavSections.filter(section => isNavSectionActive(section, path)).map(section => section.prefix)).toEqual([owner]);
  });

  it.each(['/admin/droverish', '/admin/chatty', '/admin/libraries-old', '/admin/waygate-extra'])('does not activate a section for a lookalike route %s', path => {
    expect(adminNavSections.some(section => isNavSectionActive(section, path))).toBe(false);
  });

  it('exposes both credential destinations only in administrator Identity navigation', () => {
    const adminItems = allNavItems(true, DEFAULT_BETA_FEATURES);
    const userItems = allNavItems(false, DEFAULT_BETA_FEATURES);
    for (const href of ['/admin/application-credentials', '/admin/user-credentials']) {
      expect(adminItems.find(item => item.href === href)).toMatchObject({ sectionKey: 'sections.identity', service: null });
      expect(userItems.some(item => item.href === href)).toBe(false);
    }
  });

  it('separates manager-only user navigation from fresh project-management navigation', () => {
    expect(allNavItems(false, DEFAULT_BETA_FEATURES).some(item => item.href.startsWith('/dashboard/iam'))).toBe(false);
    const manager = allNavItems(false, DEFAULT_BETA_FEATURES, { domainManager: true, projectManagement: true });
    expect(manager.find(item => item.href === '/dashboard/iam/users')).toMatchObject({ labelKey: 'items.iamUsers', capability: 'domainManager' });
    expect(manager.find(item => item.href === '/dashboard/iam/projects')).toMatchObject({ labelKey: 'items.iamProjects', capability: 'projectManagement' });
    const creator = allNavItems(false, DEFAULT_BETA_FEATURES, { domainManager: false, projectManagement: true });
    expect(creator.some(item => item.href === '/dashboard/iam/users')).toBe(false);
    expect(creator.some(item => item.href === '/dashboard/iam/projects')).toBe(true);
    expect(creator.some(item => item.href.startsWith('/admin'))).toBe(false);
    expect(allNavItems(true, DEFAULT_BETA_FEATURES).find(item => item.href === '/admin/domains')).toMatchObject({ sectionKey: 'sections.identity' });
  });

	it('localizes both IAM sibling destinations across all supported locales', () => {
		for (const [locale, users, projects] of [
			['ko', '사용자 관리', '프로젝트 관리'], ['en', 'User management', 'Project management'],
			['ja', 'ユーザー管理', 'プロジェクト管理'], ['zh-CN', '用户管理', '项目管理'],
			['bn', 'ব্যবহারকারী পরিচালনা', 'প্রকল্প পরিচালনা'], ['ms', 'Pengurusan pengguna', 'Pengurusan projek'],
			['nb', 'Brukeradministrasjon', 'Prosjektadministrasjon'], ['sw', 'Usimamizi wa watumiaji', 'Usimamizi wa miradi'],
			['vi', 'Quản lý người dùng', 'Quản lý dự án'],
		] as const) {
			initLocale(locale);
			const items = allNavItems(false, DEFAULT_BETA_FEATURES, { domainManager: true, projectManagement: true });
			expect(items.find(item => item.href === '/dashboard/iam/users')?.label).toBe(users);
			expect(items.find(item => item.href === '/dashboard/iam/projects')?.label).toBe(projects);
		}
	});

	it('keeps domain selection in the resource dialog rather than the navigation catalog', () => {
		const items = allNavItems(false, DEFAULT_BETA_FEATURES);
		expect(items.some(item => item.href === '/select-domain')).toBe(false);
		expect(items.some(item => item.href === '/dashboard/iam')).toBe(false);
		expect(items.some(item => item.href.startsWith('/admin'))).toBe(false);
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

describe('project-independent authenticated routes', () => {
	it.each(['/select-domain', '/select-project', '/dashboard/iam', '/dashboard/iam/users', '/dashboard/iam/projects'])('does not require a selected project for %s', (path) => {
		expect(isProjectAgnosticPath(path, false)).toBe(true);
	});
	it.each(['/admin', '/admin/domains'])('keeps the project exemption on %s system-admin-only', (path) => {
		expect(isProjectAgnosticPath(path, false)).toBe(false);
		expect(isProjectAgnosticPath(path, true)).toBe(true);
	});
	it.each(['/select-domain-other', '/dashboard/iam-other', '/dashboard/compute/instances'])('does not exempt lookalike or project-bound route %s', (path) => {
		expect(isProjectAgnosticPath(path, false)).toBe(false);
	});
});
