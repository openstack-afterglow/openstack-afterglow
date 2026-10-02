import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { tick } from 'svelte';
import { get } from 'svelte/store';
import type { Writable } from 'svelte/store';

vi.mock('$app/environment', () => ({ browser: true }));
vi.mock('$app/stores', async () => {
	// vi.mock factories run before static imports initialize; resolve the real store module inside the factory.
	const { writable } = await import('svelte/store');
	return { page: writable({ url: new URL('http://localhost/admin/chat/quotas'), data: {} }) };
});

import { page } from '$app/stores';
import { auth } from '$lib/stores/auth';
import { initSiteConfig, siteConfig } from '$lib/config/site';
import { betaFeatures, DEFAULT_BETA_FEATURES } from '$lib/stores/betaFeatures';
import { sidebarExpanded, sidebarOpen } from '$lib/stores/sidebar';
import { buildMockupSession } from '$lib/mockup/contracts';
import type { MockupSession } from '$lib/mockup/contracts';
import AdminSidebar from '../AdminSidebar.svelte';
import Sidebar from '../Sidebar.svelte';

type PageState = { url: URL; data: { mockup?: MockupSession } };
const mockPage = page as unknown as Writable<PageState>;

async function navigate(pathname: string, data: PageState['data'] = {}) {
	mockPage.set({ url: new URL(pathname, 'http://localhost'), data });
	await tick();
}
beforeEach(() => {
	mockPage.set({ url: new URL('http://localhost/admin/chat/quotas'), data: {} });
	initSiteConfig({ services: { chat: false, k3s: false, zun: false, waygate: false, manila: false, trove: false, swift: false } });
	betaFeatures.set({ ...DEFAULT_BETA_FEATURES });
	sidebarOpen.close();
	sidebarExpanded.open();
	auth.set({
		token: 'token', refreshToken: null, accessExpiresAt: null,
		userId: 'u-admin', username: 'admin', projectId: 'project-1', projectName: 'Project',
		availableProjects: [], roles: ['admin'], isSystemAdmin: true, federated: false
	});
});

afterEach(() => {
	cleanup();
	sidebarOpen.close();
	sidebarExpanded.open();
	betaFeatures.set({ ...DEFAULT_BETA_FEATURES });
	siteConfig.update((current) => ({ ...current, services: { ...current.services, chat: false, k3s: false, zun: false, waygate: false, manila: false, trove: false, swift: false } }));
});

async function openGlobalNavigation(...groups: string[]) {
	sidebarOpen.open();
	await tick();
	const drawer = within(screen.getByRole('dialog', { name: '전체 메뉴' }));
	for (const name of groups) {
		const group = drawer.getByRole('button', { name });
		if (group.getAttribute('aria-expanded') !== 'true') await fireEvent.click(group);
	}
	return drawer;
}

describe('administrator contextual sidebar expansion', () => {
	it('keeps selected administrator routes reachable in the rail without changing mode or auth', async () => {
		initSiteConfig({ services: { chat: true } });
		await navigate('/admin/chat/tools/tool-1');
		const authBefore = get(auth);
		render(AdminSidebar);
		await tick();
		const panel = within(screen.getByRole('complementary', { name: '페이지 메뉴' }));
		expect(panel.getByRole('heading').textContent).toBe('도구 설정');
		expect(panel.getByRole('link', { name: '도구 설정' }).getAttribute('aria-current')).toBe('page');
		const toggle = panel.getByRole('button', { name: '서비스 메뉴 접기' });
		toggle.focus();
		await fireEvent.click(toggle);
		expect(panel.getByRole('button', { name: '서비스 메뉴 펼치기' })).toBe(toggle);
		expect(toggle.getAttribute('aria-expanded')).toBe('false');
		expect(panel.getByRole('link', { name: '도구 설정' }).getAttribute('aria-current')).toBe('page');
		expect(panel.getByRole('link', { name: '모델 설정' }).getAttribute('href')).toBe('/admin/chat/models');
		expect(document.activeElement).toBe(toggle);
		await fireEvent.click(toggle);
		expect(toggle.getAttribute('aria-expanded')).toBe('true');
		expect(screen.queryByRole('dialog', { name: '전체 메뉴' })).toBeNull();
		const navigation = within(screen.getByRole('navigation', { name: '현재 서비스' }));
		expect(navigation.getByRole('link', { name: '도구 설정' }).getAttribute('aria-current')).toBe('page');
		expect(navigation.getByRole('link', { name: '모델 설정' }).getAttribute('href')).toBe('/admin/chat/models');
		expect(get(auth)).toEqual(authBefore);
		expect(get(page).url.pathname).toBe('/admin/chat/tools/tool-1');
	});
});

describe('administrator global navigation', () => {
	it('keeps other destinations out of the contextual panel until the global drawer opens', async () => {
		initSiteConfig({ services: { chat: true } });
		const authBefore = get(auth);
		render(AdminSidebar);
		await tick();
		expect(screen.getByRole('link', { name: '사용자 쿼터' }).getAttribute('aria-current')).toBe('page');
		expect(screen.queryByRole('link', { name: '전체 인스턴스' })).toBeNull();

		const drawer = await openGlobalNavigation('Compute');
		expect(drawer.getByRole('link', { name: '전체 인스턴스' }).getAttribute('href')).toBe('/admin/instances');
		await fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
		expect(screen.queryByRole('link', { name: '전체 인스턴스' })).toBeNull();
		expect(screen.getByRole('link', { name: '사용자 쿼터' }).getAttribute('aria-current')).toBe('page');
		expect(get(auth)).toEqual(authBefore);
	});

	it('makes all administration destinations reachable from the global drawer', async () => {
		initSiteConfig({ services: { chat: true, zun: true, k3s: true, waygate: true, manila: true, trove: true, swift: true } });
		betaFeatures.update(current => ({ ...current, keyManager: true }));
		await navigate('/admin');
		render(AdminSidebar);
		await tick();
		const drawer = await openGlobalNavigation('Compute', '스토리지', '네트워크', '컨테이너', 'Lumen', 'Key Manager', '모니터링', '시스템', 'Identity');
		for (const [label, href] of [
			['개요', '/admin'],
			['전체 인스턴스', '/admin/instances'], ['Flavor', '/admin/flavors'],
			['이미지', '/admin/images'], ['하이퍼바이저', '/admin/hypervisors'],
			['전체 볼륨', '/admin/volumes'], ['파일 스토리지', '/admin/file-storage'],
			['DB 인스턴스', '/admin/database-instances'], ['Object Storage', '/admin/object-storage'],
			['토폴로지', '/admin/topology'], ['네트워크', '/admin/networks'],
			['Floating IP', '/admin/floating-ips'], ['라우터', '/admin/routers'],
			['로드밸런서', '/admin/loadbalancers'], ['포트', '/admin/ports'], ['Waygate', '/admin/waygate'],
			['전체 컨테이너', '/admin/containers'], ['Drover', '/admin/drover'],
			['클러스터 템플릿', '/admin/drover/templates'],
			['Lumen', '/admin/chat'], ['채팅 통계', '/admin/chat/stats'],
			['사용자 쿼터', '/admin/chat/quotas'], ['모델 설정', '/admin/chat/models'], ['도구 설정', '/admin/chat/tools'],
			['Palimpsest', '/admin/libraries'], ['프로젝트 쿼터', '/admin/secrets'],
			['통합 모니터링', '/admin/monitoring'], ['노드', '/admin/monitoring/node'],
			['MySQL', '/admin/monitoring/mysql'], ['ProxySQL', '/admin/monitoring/proxysql'],
			['HAProxy', '/admin/monitoring/haproxy'], ['RabbitMQ', '/admin/monitoring/rabbitmq'],
			['Memcached', '/admin/monitoring/memcached'], ['etcd', '/admin/monitoring/etcd'],
			['Libvirt', '/admin/monitoring/libvirt'], ['OpenStack', '/admin/monitoring/openstack'], ['Ceph', '/admin/monitoring/ceph'],
			['서비스 상태', '/admin/services'], ['운영 이벤트', '/admin/events'],
			['고아 리소스', '/admin/orphans'], ['Notion 연동', '/admin/notion'],
			['공지 관리', '/admin/announcements'], ['기본 설정', '/admin/settings'],
			['사용자', '/admin/users'], ['프로젝트', '/admin/projects'], ['쿼터', '/admin/quotas'],
			['그룹', '/admin/groups'], ['역할', '/admin/roles'], ['시스템 관리자', '/admin/system-admins'],
		]) {
			expect(drawer.getByRole('link', { name: label }).getAttribute('href')).toBe(href);
		}
		expect(drawer.getByRole('link', { name: '개요' }).getAttribute('aria-current')).toBe('page');
	});

	it('closes the drawer on route changes and replaces the contextual destinations', async () => {
		initSiteConfig({ services: { chat: true } });
		render(AdminSidebar);
		await tick();
		await openGlobalNavigation();
		await navigate('/admin/users/user-1');
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(screen.getByRole('link', { name: '사용자' }).getAttribute('aria-current')).toBe('page');
		expect(screen.getByRole('link', { name: '프로젝트' }).getAttribute('href')).toBe('/admin/projects');
		expect(screen.queryByRole('link', { name: '사용자 쿼터' })).toBeNull();
	});
});

describe('administrator contextual navigation ownership', () => {
	it.each([
		['/admin/drover', 'Drover', '/admin/drover', '클러스터 템플릿'],
		['/admin/drover/templates/template-1', '클러스터 템플릿', '/admin/drover/templates', 'Drover'],
		['/admin/chat', 'Lumen', '/admin/chat', '채팅 통계'],
		['/admin/chat/stats', '채팅 통계', '/admin/chat/stats', '사용자 쿼터'],
		['/admin/chat/quotas/user-1', '사용자 쿼터', '/admin/chat/quotas', '채팅 통계'],
		['/admin/chat/models/model-1', '모델 설정', '/admin/chat/models', '도구 설정'],
		['/admin/chat/tools/tool-1', '도구 설정', '/admin/chat/tools', '모델 설정'],
		['/admin/waygate/vpn-1', 'Waygate', '/admin/waygate', '네트워크'],
		['/admin/flavors/flavor-1', 'Flavor', '/admin/flavors', '전체 인스턴스'],
		['/admin/monitoring/proxysql', 'ProxySQL', '/admin/monitoring/proxysql', 'MySQL'],
		['/admin/projects/project-1', '프로젝트', '/admin/projects', '사용자'],
	])('selects the longest visible route and its siblings at %s', async (path, label, href, sibling) => {
		initSiteConfig({ services: { zun: true, k3s: true, chat: true, waygate: true } });
		await navigate(path);
		render(AdminSidebar);
		await tick();
		const link = screen.getByRole('link', { name: label });
		expect(link.getAttribute('href')).toBe(href);
		expect(link.getAttribute('aria-current')).toBe('page');
		expect(screen.getByRole('link', { name: sibling }).getAttribute('aria-current')).toBeNull();
		expect(screen.getAllByRole('link').filter(link => link.getAttribute('aria-current') === 'page')).toEqual([link]);
		expect(screen.queryByRole('link', { name: '개요' })).toBeNull();
		const drawer = await openGlobalNavigation();
		const globalLink = drawer.getByRole('link', { name: label });
		expect(globalLink.getAttribute('aria-current')).toBe('page');
		expect(drawer.getAllByRole('link').filter(link => link.getAttribute('aria-current') === 'page')).toEqual([globalLink]);
	});

	it.each(['/admin/libraries', '/admin/libraries/build-123'])('keeps standalone Palimpsest selected at %s', async path => {
		await navigate(path);
		render(AdminSidebar);
		await tick();
		const link = screen.getByRole('link', { name: 'Palimpsest' });
		expect(link.getAttribute('href')).toBe('/admin/libraries');
		expect(link.getAttribute('aria-current')).toBe('page');
		expect(screen.queryByRole('link', { name: '전체 인스턴스' })).toBeNull();
	});

	it('does not assign lookalike routes to a contextual group', async () => {
		initSiteConfig({ services: { k3s: true, chat: true } });
		await navigate('/admin/chatty');
		render(AdminSidebar);
		await tick();
		expect(screen.queryByRole('link', { name: 'Lumen' })).toBeNull();
		const drawer = await openGlobalNavigation();
		expect(drawer.getAllByRole('link').filter(link => link.getAttribute('aria-current') === 'page')).toEqual([]);
	});
});

describe('administrator navigation visibility gates', () => {
	it.each([
		[{ zun: false, k3s: true }, '/admin/drover/templates', '클러스터 템플릿', ['전체 컨테이너'], ['Drover', '클러스터 템플릿']],
		[{ zun: true, k3s: false }, '/admin/containers', '전체 컨테이너', ['Drover', '클러스터 템플릿'], ['전체 컨테이너']],
	] as const)('preserves independent container service gates with %j', async (services, path, activeLabel, hiddenLabels, visibleLabels) => {
		initSiteConfig({ services });
		await navigate(path);
		render(AdminSidebar);
		await tick();
		expect(screen.getByRole('link', { name: activeLabel }).getAttribute('aria-current')).toBe('page');
		for (const label of hiddenLabels) expect(screen.queryByRole('link', { name: label })).toBeNull();
		const drawer = await openGlobalNavigation();
		for (const label of hiddenLabels) expect(drawer.queryByRole('link', { name: label })).toBeNull();
		for (const label of visibleLabels) {
			const href = label === 'Drover' ? '/admin/drover' : label === '클러스터 템플릿' ? '/admin/drover/templates' : '/admin/containers';
			expect(drawer.getByRole('link', { name: label }).getAttribute('href')).toBe(href);
		}
	});

	it('removes disabled service destinations without hiding the remaining groups', async () => {
		await navigate('/admin/networks');
		render(AdminSidebar);
		await tick();
		expect(screen.getByRole('link', { name: '네트워크' }).getAttribute('aria-current')).toBe('page');
		expect(screen.queryByRole('link', { name: 'Waygate' })).toBeNull();
		const drawer = await openGlobalNavigation('스토리지', '네트워크');
		for (const label of ['전체 컨테이너', 'Drover', '클러스터 템플릿', 'Lumen', '채팅 통계', '사용자 쿼터', '모델 설정', '도구 설정', 'Waygate', '파일 스토리지', 'DB 인스턴스', 'Object Storage']) {
			expect(drawer.queryByRole('link', { name: label })).toBeNull();
		}
		expect(drawer.queryByRole('button', { name: 'Lumen' })).toBeNull();
		expect(drawer.queryByRole('button', { name: '컨테이너' })).toBeNull();
		expect(drawer.getByRole('link', { name: '전체 볼륨' }).getAttribute('href')).toBe('/admin/volumes');
		expect(drawer.getByRole('link', { name: '네트워크' }).getAttribute('href')).toBe('/admin/networks');
	});

	it('reacts to beta preference changes without exposing a gated contextual route', async () => {
		await navigate('/admin/secrets/project-1');
		render(AdminSidebar);
		await tick();
		expect(screen.queryByRole('link', { name: '프로젝트 쿼터' })).toBeNull();
		let drawer = await openGlobalNavigation();
		expect(drawer.queryByRole('link', { name: '프로젝트 쿼터' })).toBeNull();
		expect(drawer.queryByRole('button', { name: 'Key Manager' })).toBeNull();
		await fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
		betaFeatures.update(current => ({ ...current, keyManager: true }));
		await tick();
		expect(screen.getByRole('link', { name: '프로젝트 쿼터' }).getAttribute('aria-current')).toBe('page');
		drawer = await openGlobalNavigation();
		expect(drawer.getByRole('link', { name: '프로젝트 쿼터' }).getAttribute('href')).toBe('/admin/secrets');
	});

	it('uses the admin mockup allowlist while overriding service and beta preferences', async () => {
		initSiteConfig({ services: { chat: true, k3s: true, waygate: true } });
		await navigate('/admin/secrets', { mockup: buildMockupSession('admin') });
		render(AdminSidebar);
		await tick();
		expect(screen.getByRole('link', { name: '프로젝트 쿼터' }).getAttribute('aria-current')).toBe('page');
		const drawer = await openGlobalNavigation('컨테이너', '네트워크', '모니터링', 'Identity');
		expect(drawer.getByRole('link', { name: '전체 컨테이너' }).getAttribute('href')).toBe('/admin/containers');
		expect(drawer.getByRole('link', { name: '프로젝트 쿼터' }).getAttribute('href')).toBe('/admin/secrets');
		for (const label of ['Drover', '클러스터 템플릿', 'Lumen', '모델 설정', 'Waygate', 'ProxySQL', '프로젝트']) {
			expect(drawer.queryByRole('link', { name: label })).toBeNull();
		}
		expect(drawer.queryByRole('button', { name: 'Lumen' })).toBeNull();
		expect(screen.queryByTitle('사용자 모드로 전환')).toBeNull();
	});
});

describe('responsive sidebar current-mode controls', () => {
	it('shows user mode while linking the dashboard sidebar to admin mode', async () => {
		await navigate('/dashboard');
		render(Sidebar);
		await tick();
		await openGlobalNavigation();

		const link = screen.getByTitle('관리자 모드로 전환');
		expect(link.textContent).toContain('사용자 모드');
		expect(link.getAttribute('href')).toBe('/admin');
		expect(link.getAttribute('aria-label')).toBe('현재 사용자 모드, 관리자 모드로 전환');
	});

	it('shows admin mode while linking the admin sidebar to user mode', async () => {
		await navigate('/admin');
		render(AdminSidebar);
		await tick();
		await openGlobalNavigation();

		const link = screen.getByTitle('사용자 모드로 전환');
		expect(link.textContent).toContain('관리자 모드');
		expect(link.getAttribute('href')).toBe('/dashboard');
		expect(link.getAttribute('aria-label')).toBe('현재 관리자 모드, 사용자 모드로 전환');
	});
});
