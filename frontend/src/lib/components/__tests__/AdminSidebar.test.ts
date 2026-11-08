import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { tick } from 'svelte';
import { get, type Writable } from 'svelte/store';
import type * as ResourceSearchModule from '$lib/utils/resourceSearch';

vi.mock('$app/environment', () => ({ browser: true }));
vi.mock('$app/stores', async () => {
	// Hoisted factories run before static imports initialize.
	const { writable } = await import('svelte/store');
	return { page: writable({ url: new URL('http://localhost/admin/chat/quotas'), data: {} }) };
});

const viewport = vi.hoisted(() => ({ mobile: false }));
vi.mock('$lib/utils/mobileViewport', () => ({ mobileViewport: { get current() { return viewport.mobile; } } }));
vi.mock('$lib/utils/resourceSearch', async importOriginal => ({ ...(await importOriginal<typeof ResourceSearchModule>()), loadResourceSearchEntries: vi.fn().mockResolvedValue([]) }));

import { page } from '$app/stores';
import { auth } from '$lib/stores/auth';
import { initSiteConfig, siteConfig } from '$lib/config/site';
import { betaFeatures, DEFAULT_BETA_FEATURES } from '$lib/stores/betaFeatures';
import { sidebarExpanded, sidebarOpen } from '$lib/stores/sidebar';
import { navigationPreferenceKey } from '$lib/stores/navigationPreferences';
import { buildMockupSession, type MockupSession } from '$lib/mockup/contracts';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/nav';
import AdminSidebar from '../AdminSidebar.svelte';
import Sidebar from '../Sidebar.svelte';

type PageState = { url: URL; data: { mockup?: MockupSession } };
type LinkScope = Pick<typeof screen, 'queryAllByRole'>;
const mockPage = page as unknown as Writable<PageState>;
const initialAuth = get(auth);
const preferenceKeys = ['admin', 'user'].map(surface => navigationPreferenceKey('domain-1', 'u-admin', surface));
function queryDestination(scope: LinkScope, href: string) {
	return scope.queryAllByRole('link').find(link => link.getAttribute('href') === href) ?? null;
}
function destination(scope: LinkScope, href: string) {
	const link = queryDestination(scope, href);
	expect(link).not.toBeNull();
	return link!;
}
async function navigate(pathname: string, data: PageState['data'] = {}) {
	mockPage.set({ url: new URL(pathname, 'http://localhost'), data });
	await tick();
}
beforeEach(() => {
	initLocale('ko');
	for (const key of preferenceKeys) localStorage.removeItem(key);
	mockPage.set({ url: new URL('http://localhost/admin/chat/quotas'), data: {} });
	initSiteConfig({ services: { chat: false, k3s: false, zun: false, waygate: false, manila: false, trove: false, swift: false } });
	betaFeatures.set({ ...DEFAULT_BETA_FEATURES });
	sidebarOpen.close();
	sidebarExpanded.open();
	auth.set({
		token: 'token', refreshToken: null, accessExpiresAt: null,
		userId: 'u-admin', username: 'admin', projectId: 'project-1', projectName: 'Project',
		availableProjects: [], roles: ['admin'], isSystemAdmin: true, federated: false,
		domainId: 'domain-1', domainName: 'Domain', identityDomainId: 'domain-1', isDomainManager: false,
	});
});
afterEach(() => {
	cleanup();
	sidebarOpen.close();
	sidebarExpanded.open();
	auth.set(initialAuth);
	for (const key of preferenceKeys) localStorage.removeItem(key);
	betaFeatures.set({ ...DEFAULT_BETA_FEATURES });
	siteConfig.update(current => ({ ...current, services: { ...current.services, chat: false, k3s: false, zun: false, waygate: false, manila: false, trove: false, swift: false } }));
});
async function openCatalog() {
	sidebarOpen.open();
	await tick();
	const menu = within(screen.getByRole('dialog'));
	const disclosure = menu.getByRole('button', { name: t('accessibility.allServices') });
	if (disclosure.getAttribute('aria-expanded') === 'false') await fireEvent.click(disclosure);
	const navigation = within(menu.getByRole('navigation', { name: t('accessibility.allServices') }));
	for (const group of navigation.queryAllByRole('button')) {
		if (group.getAttribute('aria-expanded') === 'false') await fireEvent.click(group);
	}
	return menu;
}

describe('administrator contextual sidebar expansion', () => {
	it('keeps selected administrator routes reachable in the rail without changing mode or auth', async () => {
		initSiteConfig({ services: { chat: true } });
		await navigate('/admin/chat/tools/tool-1');
		const authBefore = get(auth);
		render(AdminSidebar);
		await tick();
		const panel = within(screen.getByRole('complementary'));
		expect(destination(panel, '/admin/chat/tools').getAttribute('aria-current')).toBe('page');
		const toggle = panel.getByRole('button', { name: t('accessibility.collapseServiceMenu') });
		toggle.focus();
		await fireEvent.click(toggle);
		expect(panel.getByRole('button', { name: t('accessibility.expandServiceMenu') })).toBe(toggle);
		expect(toggle.getAttribute('aria-expanded')).toBe('false');
		expect(destination(panel, '/admin/chat/tools').getAttribute('aria-current')).toBe('page');
		destination(panel, '/admin/chat/models');
		expect(document.activeElement).toBe(toggle);
		await fireEvent.click(toggle);
		expect(toggle.getAttribute('aria-expanded')).toBe('true');
		expect(screen.queryByRole('dialog')).toBeNull();
		const navigation = within(screen.getByRole('navigation', { name: t('accessibility.currentService') }));
		expect(destination(navigation, '/admin/chat/tools').getAttribute('aria-current')).toBe('page');
		destination(navigation, '/admin/chat/models');
		expect(get(auth)).toEqual(authBefore);
		expect(get(page).url.pathname).toBe('/admin/chat/tools/tool-1');
	});
	it('opens system information in the existing System sidebar and keeps it selected in the compact rail', async () => {
		await navigate('/admin/system-info');
		render(AdminSidebar);
		await tick();
		const panel = within(screen.getByRole('complementary'));
		const information = destination(panel, '/admin/system-info');
		expect(information.getAttribute('aria-current')).toBe('page');
		expect(information.textContent).toContain(t('items.systemInfo'));
		destination(panel, '/admin/services');
		await fireEvent.click(panel.getByRole('button', { name: t('accessibility.collapseServiceMenu') }));
		expect(destination(panel, '/admin/system-info').getAttribute('aria-current')).toBe('page');
	});
});

describe('administrator global navigation', () => {
	it.each(['backdrop', 'visible close', 'Escape'])('restores administrator opener focus after %s dismissal without focusing the scrim', async dismissal => {
		await navigate('/admin/instances/instance-1');
		render(AdminSidebar);
		await tick();
		const opener = screen.getByRole('button', { name: t('accessibility.allServices') });
		opener.focus();
		await fireEvent.click(opener);
		const dialog = screen.getByRole('dialog');
		const close = within(dialog).getByRole('button', { name: t('accessibility.closeAllMenu') });
		const backdrop = dialog.querySelector<HTMLElement>('[data-navigation-backdrop]')!;
		expect(document.activeElement).toBe(close);
		backdrop.focus();
		expect(document.activeElement).toBe(close);
		await fireEvent.click(within(dialog).getByRole('searchbox'));
		expect(screen.getByRole('dialog')).toBe(dialog);
		if (dismissal === 'backdrop') {
			await fireEvent.mouseDown(backdrop);
			expect(document.activeElement).not.toBe(backdrop);
			await fireEvent.mouseUp(backdrop);
			await fireEvent.click(backdrop);
		} else if (dismissal === 'visible close') {
			await fireEvent.click(close);
		} else {
			await fireEvent.keyDown(dialog, { key: 'Escape' });
		}
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(get(sidebarOpen)).toBe(false);
		expect(document.activeElement).toBe(opener);
	});
	it.each([375, 1280])('keeps administrator Hub and favorites above visible service categories at %ipx', async width => {
		const previousWidth = window.innerWidth;
		const mobile = width < 768;
		Object.defineProperty(window, 'innerWidth', { configurable: true, value: width });
		viewport.mobile = mobile;
		try {
			localStorage.setItem(preferenceKeys[0], JSON.stringify({ pinned: ['/admin', '/docs', '/admin/volumes'], recent: ['/admin/users'] }));
			await navigate('/admin/instances/instance-1');
			render(AdminSidebar);
			sidebarOpen.open();
			await tick();
			let menu = within(screen.getByRole('dialog'));
			const hub = menu.getByRole('navigation', { name: t('sections.hub') });
			const catalogNavigation = menu.getByRole('navigation', { name: t('accessibility.allServices') });
			expect(hub.compareDocumentPosition(catalogNavigation) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
			if (mobile) {
				// Mobile keeps favorites inside the Hub group and lists categories without the all-services disclosure.
				expect(within(hub).getAllByRole('link').map(link => link.getAttribute('href'))).toEqual(['/admin', '/docs', '/admin/volumes']);
				within(hub).getByRole('button', { name: t('actions.unpin', { name: t('items.allVolumes') }) });
				expect(menu.queryByRole('region', { name: t('sections.favorites') })).toBeNull();
				expect(menu.queryByRole('button', { name: t('accessibility.allServices') })).toBeNull();
			} else {
				const shortcuts = menu.getByRole('region', { name: t('sections.favorites') });
				expect(within(hub).getAllByRole('link').map(link => link.getAttribute('href'))).toEqual(['/admin', '/docs']);
				expect(within(hub).queryAllByRole('button')).toEqual([]);
				expect(hub.compareDocumentPosition(shortcuts) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
				expect(within(shortcuts).getAllByRole('link').map(link => link.getAttribute('href'))).toEqual(['/admin/volumes']);
			}
			expect(queryDestination(menu, '/admin/instances')).toBeNull();
			expect(queryDestination(menu, '/admin/users')).toBeNull();
			const catalog = within(catalogNavigation);
			expect(catalog.getByRole('button', { name: t('sections.compute') }).getAttribute('aria-expanded')).toBe('false');
			expect(queryDestination(catalog, '/admin/instances')).toBeNull();
			if (!mobile) await fireEvent.click(menu.getByRole('button', { name: t('accessibility.allServices') }));
			await navigate('/admin/users');
			expect(screen.queryByRole('dialog')).toBeNull();
			sidebarOpen.open();
			await tick();
			menu = within(screen.getByRole('dialog'));
			if (mobile) expect(menu.getByRole('navigation', { name: t('accessibility.allServices') })).toBeTruthy();
			else expect(menu.getByRole('button', { name: t('accessibility.allServices') }).getAttribute('aria-expanded')).toBe('true');
			expect(queryDestination(menu, '/admin/users')).toBeNull();
		} finally {
			Object.defineProperty(window, 'innerWidth', { configurable: true, value: previousWidth });
			viewport.mobile = false;
		}
	});
	it('isolates pinned shortcuts by user and administrator surface and immutable home', async () => {
		localStorage.setItem(preferenceKeys[0], JSON.stringify({ pinned: ['/admin/volumes'], recent: [] }));
		localStorage.setItem(preferenceKeys[1], JSON.stringify({ pinned: ['/dashboard/compute/images'], recent: [] }));
		await navigate('/admin');
		const rendered = render(AdminSidebar);
		sidebarOpen.open();
		await tick();
		let menu = within(screen.getByRole('dialog'));
		destination(within(menu.getByRole('region', { name: t('sections.favorites') })), '/admin/volumes');
		auth.update(current => ({ ...current, domainId: 'working-domain', projectId: 'other-project' }));
		await tick();
		destination(within(menu.getByRole('region', { name: t('sections.favorites') })), '/admin/volumes');
		auth.update(current => ({ ...current, identityDomainId: 'other-home' }));
		await tick();
		expect(menu.queryByRole('region', { name: t('sections.favorites') })).toBeNull();
		auth.update(current => ({ ...current, identityDomainId: 'domain-1', userId: 'other-user' }));
		await tick();
		expect(menu.queryByRole('region', { name: t('sections.favorites') })).toBeNull();
		auth.update(current => ({ ...current, userId: 'u-admin' }));
		await tick();
		destination(within(menu.getByRole('region', { name: t('sections.favorites') })), '/admin/volumes');
		rendered.unmount();
		sidebarOpen.close();
		await navigate('/dashboard');
		render(Sidebar);
		sidebarOpen.open();
		await tick();
		menu = within(screen.getByRole('dialog'));
		expect(within(menu.getByRole('region', { name: t('sections.favorites') })).getAllByRole('link').map(link => link.getAttribute('href'))).toEqual(['/dashboard/compute/images']);
	});
	it('keeps global workspace switching in user navigation and out of administrator navigation', async () => {
		await navigate('/admin');
		const rendered = render(AdminSidebar);
		const adminDrawer = await openCatalog();
		expect(adminDrawer.queryByRole('button', { name: /리소스 선택/ })).toBeNull();
		destination(adminDrawer, '/dashboard');
		rendered.unmount();
		sidebarOpen.close();
		await navigate('/dashboard');
		render(Sidebar);
		const userDrawer = await openCatalog();
		expect(userDrawer.getByRole('button', { name: /리소스 선택/ })).toBeTruthy();
	});
	it('keeps other destinations out of the contextual panel until the global drawer opens', async () => {
		initSiteConfig({ services: { chat: true } });
		const authBefore = get(auth);
		render(AdminSidebar);
		await tick();
		expect(destination(screen, '/admin/chat/quotas').getAttribute('aria-current')).toBe('page');
		expect(queryDestination(screen, '/admin/instances')).toBeNull();
		destination(await openCatalog(), '/admin/instances');
		await fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
		expect(queryDestination(screen, '/admin/instances')).toBeNull();
		expect(destination(screen, '/admin/chat/quotas').getAttribute('aria-current')).toBe('page');
		expect(get(auth)).toEqual(authBefore);
	});
	it('makes all administration destinations reachable from the global drawer', async () => {
		initSiteConfig({ services: { chat: true, zun: true, k3s: true, waygate: true, manila: true, trove: true, swift: true } });
		betaFeatures.update(current => ({ ...current, keyManager: true }));
		await navigate('/admin');
		render(AdminSidebar);
		const menu = await openCatalog();
		for (const href of [
			'/admin', '/admin/instances', '/admin/flavors', '/admin/images', '/admin/hypervisors',
			'/admin/volumes', '/admin/file-storage', '/admin/database-instances', '/admin/object-storage',
			'/admin/topology', '/admin/networks', '/admin/floating-ips', '/admin/routers', '/admin/loadbalancers', '/admin/ports', '/admin/waygate',
			'/admin/containers', '/admin/drover', '/admin/drover/templates', '/admin/chat', '/admin/chat/stats', '/admin/chat/quotas', '/admin/chat/models', '/admin/chat/tools',
			'/admin/libraries', '/admin/secrets', '/admin/monitoring', '/admin/monitoring/node', '/admin/monitoring/aodh', '/admin/monitoring/gnocchi',
			'/admin/monitoring/mysql', '/admin/monitoring/proxysql', '/admin/monitoring/haproxy', '/admin/monitoring/rabbitmq', '/admin/monitoring/memcached',
			'/admin/monitoring/etcd', '/admin/monitoring/libvirt', '/admin/monitoring/openstack', '/admin/monitoring/ceph',
			'/admin/services', '/admin/system-info', '/admin/events', '/admin/orphans', '/admin/notion', '/admin/announcements', '/admin/settings',
			'/admin/users', '/admin/projects', '/admin/quotas', '/admin/groups', '/admin/roles', '/admin/system-admins',
		]) destination(menu, href);
		const hub = within(menu.getByRole('navigation', { name: t('sections.hub') }));
		expect(destination(hub, '/admin').getAttribute('aria-current')).toBe('page');
	});
	it('closes the drawer on route changes and replaces the contextual destinations', async () => {
		initSiteConfig({ services: { chat: true } });
		render(AdminSidebar);
		await openCatalog();
		await navigate('/admin/users/user-1');
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(destination(screen, '/admin/users').getAttribute('aria-current')).toBe('page');
		destination(screen, '/admin/projects');
		expect(queryDestination(screen, '/admin/chat/quotas')).toBeNull();
	});
});

describe('administrator contextual navigation ownership', () => {
	it.each([
		['/admin/drover', '/admin/drover', '/admin/drover/templates'],
		['/admin/drover/templates/template-1', '/admin/drover/templates', '/admin/drover'],
		['/admin/chat', '/admin/chat', '/admin/chat/stats'],
		['/admin/chat/stats', '/admin/chat/stats', '/admin/chat/quotas'],
		['/admin/chat/quotas/user-1', '/admin/chat/quotas', '/admin/chat/stats'],
		['/admin/chat/models/model-1', '/admin/chat/models', '/admin/chat/tools'],
		['/admin/chat/tools/tool-1', '/admin/chat/tools', '/admin/chat/models'],
		['/admin/waygate/vpn-1', '/admin/waygate', '/admin/networks'],
		['/admin/flavors/flavor-1', '/admin/flavors', '/admin/instances'],
		['/admin/monitoring/proxysql', '/admin/monitoring/proxysql', '/admin/monitoring/mysql'],
		['/admin/monitoring/aodh', '/admin/monitoring/aodh', '/admin/monitoring/gnocchi'],
		['/admin/monitoring/aodh/settings', '/admin/monitoring/aodh', '/admin/monitoring/gnocchi'],
		['/admin/monitoring/gnocchi', '/admin/monitoring/gnocchi', '/admin/monitoring/aodh'],
		['/admin/projects/project-1', '/admin/projects', '/admin/users'],
	])('selects the longest visible route and its siblings at %s', async (path, href, sibling) => {
		initSiteConfig({ services: { zun: true, k3s: true, chat: true, waygate: true } });
		await navigate(path);
		render(AdminSidebar);
		await tick();
		const link = destination(screen, href);
		expect(link.getAttribute('aria-current')).toBe('page');
		expect(destination(screen, sibling).getAttribute('aria-current')).toBeNull();
		expect(screen.getAllByRole('link').filter(link => link.getAttribute('aria-current') === 'page')).toEqual([link]);
		expect(queryDestination(screen, '/admin')).toBeNull();
		const menu = await openCatalog();
		const navigation = within(menu.getByRole('navigation', { name: t('accessibility.allServices') }));
		const globalLink = destination(navigation, href);
		expect(globalLink.getAttribute('aria-current')).toBe('page');
		expect(navigation.getAllByRole('link').filter(link => link.getAttribute('aria-current') === 'page')).toEqual([globalLink]);
	});
	it.each(['/admin/libraries', '/admin/libraries/build-123'])('keeps standalone Palimpsest selected at %s', async path => {
		await navigate(path);
		render(AdminSidebar);
		await tick();
		expect(destination(screen, '/admin/libraries').getAttribute('aria-current')).toBe('page');
		expect(queryDestination(screen, '/admin/instances')).toBeNull();
	});
	it('does not assign lookalike routes to a contextual group', async () => {
		initSiteConfig({ services: { k3s: true, chat: true } });
		await navigate('/admin/chatty');
		render(AdminSidebar);
		await tick();
		expect(queryDestination(screen, '/admin/chat')).toBeNull();
		const menu = await openCatalog();
		expect(menu.getAllByRole('link').filter(link => link.getAttribute('aria-current') === 'page')).toEqual([]);
	});
});

describe('administrator navigation visibility gates', () => {
	it.each([
		[{ zun: false, k3s: true }, '/admin/drover/templates', ['/admin/containers'], ['/admin/drover', '/admin/drover/templates']],
		[{ zun: true, k3s: false }, '/admin/containers', ['/admin/drover', '/admin/drover/templates'], ['/admin/containers']],
	] as const)('preserves independent container service gates with %j', async (services, href, hidden, visible) => {
		initSiteConfig({ services });
		await navigate(href);
		render(AdminSidebar);
		await tick();
		expect(destination(screen, href).getAttribute('aria-current')).toBe('page');
		for (const path of hidden) expect(queryDestination(screen, path)).toBeNull();
		const menu = await openCatalog();
		for (const path of hidden) expect(queryDestination(menu, path)).toBeNull();
		for (const path of visible) destination(menu, path);
	});
	it('removes disabled service destinations without hiding the remaining groups', async () => {
		await navigate('/admin/networks');
		render(AdminSidebar);
		await tick();
		expect(destination(screen, '/admin/networks').getAttribute('aria-current')).toBe('page');
		expect(queryDestination(screen, '/admin/waygate')).toBeNull();
		const menu = await openCatalog();
		for (const href of ['/admin/containers', '/admin/drover', '/admin/drover/templates', '/admin/chat', '/admin/chat/stats', '/admin/chat/quotas', '/admin/chat/models', '/admin/chat/tools', '/admin/waygate', '/admin/file-storage', '/admin/database-instances', '/admin/object-storage']) expect(queryDestination(menu, href)).toBeNull();
		for (const key of ['sections.lumen', 'sections.containers'] as const) expect(menu.queryByRole('button', { name: t(key) })).toBeNull();
		for (const href of ['/admin/volumes', '/admin/networks']) destination(menu, href);
	});
	it('reacts to beta preference changes without exposing a gated contextual route', async () => {
		await navigate('/admin/secrets/project-1');
		render(AdminSidebar);
		await tick();
		expect(queryDestination(screen, '/admin/secrets')).toBeNull();
		let menu = await openCatalog();
		expect(queryDestination(menu, '/admin/secrets')).toBeNull();
		expect(menu.queryByRole('button', { name: t('sections.keyManager') })).toBeNull();
		await fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
		betaFeatures.update(current => ({ ...current, keyManager: true }));
		await tick();
		expect(destination(screen, '/admin/secrets').getAttribute('aria-current')).toBe('page');
		menu = await openCatalog();
		destination(menu, '/admin/secrets');
	});
	it('uses the admin mockup allowlist while overriding service and beta preferences', async () => {
		initSiteConfig({ services: { chat: true, k3s: true, waygate: true } });
		await navigate('/admin/secrets', { mockup: buildMockupSession('admin') });
		render(AdminSidebar);
		await tick();
		expect(destination(screen, '/admin/secrets').getAttribute('aria-current')).toBe('page');
		const menu = await openCatalog();
		destination(menu, '/admin/containers');
		destination(menu, '/admin/secrets');
		destination(menu, '/admin/projects');
		for (const href of ['/admin/drover', '/admin/drover/templates', '/admin/chat', '/admin/chat/models', '/admin/waygate', '/admin/monitoring/proxysql', '/dashboard']) expect(queryDestination(menu, href)).toBeNull();
		expect(menu.queryByRole('button', { name: t('sections.lumen') })).toBeNull();
	});
});

describe('responsive sidebar current-mode controls', () => {
	it('links the dashboard sidebar to admin mode', async () => {
		await navigate('/dashboard');
		render(Sidebar);
		destination(await openCatalog(), '/admin');
	});
	it('links the admin sidebar to user mode', async () => {
		await navigate('/admin');
		render(AdminSidebar);
		destination(await openCatalog(), '/dashboard');
	});
});

describe('administrator mobile drawer', () => {
	beforeEach(() => { viewport.mobile = true; });
	afterEach(() => { viewport.mobile = false; });

	it('keeps Hub, combined search and a compact mode switch in the full-screen drawer', async () => {
		await navigate('/admin');
		render(AdminSidebar);
		sidebarOpen.open();
		await tick();
		const menu = within(screen.getByRole('dialog'));
		expect(document.getElementById('app-navigation-menu')!.dataset.navigationLayout).toBe('mobile');
		expect(within(menu.getByRole('navigation', { name: t('sections.hub') })).getAllByRole('link').map(link => link.getAttribute('href'))).toEqual(['/admin', '/docs']);
		expect(menu.queryByRole('searchbox', { name: t('actions.searchServices') })).toBeNull();
		await fireEvent.input(menu.getByRole('searchbox', { name: t('actions.searchAll') }), { target: { value: t('items.topology') } });
		destination(within(menu.getByRole('navigation', { name: t('sections.services') })), '/admin/topology');
		const footer = document.querySelector('#app-navigation-menu [data-navigation-footer="mobile"]') as HTMLElement;
		expect(within(footer).getByText('admin')).toBeTruthy();
		destination(within(footer), '/dashboard');
	});
});
