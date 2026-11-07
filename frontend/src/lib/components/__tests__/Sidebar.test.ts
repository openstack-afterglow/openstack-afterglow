import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { get, type Writable } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('$app/environment', () => ({ browser: true }));
vi.mock('$app/stores', async () => {
	// Hoisted factories run before static imports initialize.
	const { writable } = await import('svelte/store');
	return { page: writable({ url: new URL('http://localhost/dashboard'), data: {} }) };
});
vi.mock('$lib/stores/projectManagement', async () => {
	// Hoisted factories run before static imports initialize.
	const { writable } = await import('svelte/store');
	return { canManageOrganizationProjects: writable(false) };
});

import { page } from '$app/stores';
import { initSiteConfig, siteConfig } from '$lib/config/site';
import { auth } from '$lib/stores/auth';
import { canManageOrganizationProjects } from '$lib/stores/projectManagement';
import { betaFeatures, DEFAULT_BETA_FEATURES } from '$lib/stores/betaFeatures';
import { sidebarExpanded, sidebarOpen } from '$lib/stores/sidebar';
import { wizardOpen } from '$lib/stores/wizard';
import { navigationPreferenceKey } from '$lib/stores/navigationPreferences';
import Sidebar from '../Sidebar.svelte';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/nav';
import { t as instanceT } from '$lib/i18n/ns/instance';

const mockPage = page as unknown as Writable<{ url: URL; data: Record<string, unknown> }>;
const initialSiteConfig = get(siteConfig);
const initialAuth = get(auth);
const initialBetaFeatures = get(betaFeatures);
const preferenceKey = navigationPreferenceKey('home', 'sidebar-user', 'user');
const accountDestinations = [
	'/dashboard/account', '/dashboard/account/keypairs', '/dashboard/account/beta',
	'/dashboard/account/sessions', '/dashboard/account/mcp', '/dashboard/account/activity',
];
type LinkScope = Pick<typeof screen, 'queryAllByRole'>;
function queryDestination(scope: LinkScope, href: string) {
	return scope.queryAllByRole('link').find(link => link.getAttribute('href') === href) ?? null;
}
function destination(scope: LinkScope, href: string) {
	const link = queryDestination(scope, href);
	expect(link).not.toBeNull();
	return link!;
}
function activeDestinations(scope: LinkScope) {
	return [...new Set(scope.queryAllByRole('link').filter(link => link.getAttribute('aria-current') === 'page').map(link => link.getAttribute('href')))];
}
function drawer() {
	return within(screen.getByRole('dialog'));
}
function globalServices() {
	return within(drawer().getByRole('navigation', { name: t('accessibility.allServices') }));
}
async function navigate(pathname: string) {
	mockPage.set({ url: new URL(pathname, 'http://localhost'), data: {} });
	return tick();
}
async function expandGlobalSections() {
	const disclosure = drawer().getByRole('button', { name: t('accessibility.allServices') });
	if (disclosure.getAttribute('aria-expanded') === 'false') await fireEvent.click(disclosure);
	for (const button of globalServices().queryAllByRole('button')) {
		if (button.getAttribute('aria-expanded') === 'false') await fireEvent.click(button);
	}
}
async function openCatalog() {
	sidebarOpen.open();
	await tick();
	await expandGlobalSections();
	return drawer();
}
async function openDrawer() {
	sidebarOpen.open();
	await tick();
	return drawer();
}

beforeEach(async () => {
	initLocale('ko');
	localStorage.removeItem(preferenceKey);
	sidebarOpen.close();
	sidebarExpanded.open();
	wizardOpen.set(false);
	auth.set({ ...initialAuth, userId: 'sidebar-user', identityDomainId: 'home', isSystemAdmin: false, isDomainManager: false });
	(canManageOrganizationProjects as Writable<boolean>).set(false);
	betaFeatures.set({ ...DEFAULT_BETA_FEATURES });
	initSiteConfig({ services: {
		magnum: false, zun: false, k3s: false, manila: false,
		trove: false, swift: false, chat: false, waygate: false,
	} });
	await navigate('/dashboard');
});
afterEach(() => {
	cleanup();
	initLocale('ko');
	sidebarOpen.close();
	sidebarExpanded.open();
	wizardOpen.set(false);
	auth.set(initialAuth);
	siteConfig.set(initialSiteConfig);
	betaFeatures.set(initialBetaFeatures);
	localStorage.removeItem(preferenceKey);
	localStorage.removeItem('afterglow.beta.volumeBackups');
	localStorage.removeItem('afterglow.beta.databaseBackups');
});

describe('Sidebar global navigation', () => {
	it.each(['ko', 'en', 'ja', 'zh-CN', 'bn', 'ms', 'nb', 'sw', 'vi'] as const)('keeps Hub first and service categories discoverable without expanding their children in %s', async locale => {
		initLocale(locale);
		localStorage.setItem(preferenceKey, JSON.stringify({ pinned: ['/dashboard/usage', '/dashboard/compute/images'], recent: ['/dashboard/volumes'] }));
		await navigate('/dashboard/compute/instances/instance-1');
		render(Sidebar);
		const menu = await openDrawer();
		const hub = menu.getByRole('navigation', { name: t('sections.hub') });
		const shortcuts = menu.getByRole('region', { name: t('sections.favorites') });
		expect(within(hub).getAllByRole('link').map(link => link.getAttribute('href'))).toEqual(['/dashboard', '/dashboard/usage', '/dashboard/usage-report', '/dashboard/activity', '/dashboard/network/topology']);
		expect(within(hub).queryAllByRole('button')).toEqual([]);
		expect(hub.compareDocumentPosition(shortcuts) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
		expect(within(shortcuts).getAllByRole('link').map(link => link.getAttribute('href'))).toEqual(['/dashboard/compute/images']);
		expect(menu.queryAllByRole('link').filter(link => link.getAttribute('href') === '/dashboard/usage')).toHaveLength(1);
		expect(queryDestination(menu, '/dashboard/compute/instances')).toBeNull();
		expect(queryDestination(menu, '/dashboard/volumes')).toBeNull();
		expect(menu.getByRole('navigation', { name: t('accessibility.allServices') })).toBeTruthy();
		expect(menu.getByRole('button', { name: t('accessibility.allServices') }).getAttribute('aria-expanded')).toBe('true');
		expect(globalServices().getByRole('button', { name: t('sections.compute') }).getAttribute('aria-expanded')).toBe('false');
	});
	it('pins from search and catalog without changing route or expanding search defaults', async () => {
		render(Sidebar);
		const menu = await openDrawer();
		const search = menu.getByRole('searchbox', { name: t('actions.searchServices') });
		await fireEvent.input(search, { target: { value: t('items.images') } });
		const results = within(menu.getByRole('navigation', { name: t('actions.searchServices') }));
		destination(results, '/dashboard/compute/images');
		await fireEvent.click(results.getByRole('button', { name: t('actions.pin', { name: t('items.images') }) }));
		destination(within(menu.getByRole('region', { name: t('sections.favorites') })), '/dashboard/compute/images');
		await fireEvent.input(search, { target: { value: '' } });
		expect(menu.getByRole('navigation', { name: t('accessibility.allServices') })).toBeTruthy();
		await expandGlobalSections();
		await fireEvent.click(globalServices().getByRole('button', { name: t('actions.pin', { name: t('items.instances') }) }));
		expect(JSON.parse(localStorage.getItem(preferenceKey)!).pinned).toEqual(['/dashboard/compute/images', '/dashboard/compute/instances']);
		await fireEvent.click(within(menu.getByRole('region', { name: t('sections.favorites') })).getByRole('button', { name: t('actions.unpin', { name: t('items.images') }) }));
		expect(JSON.parse(localStorage.getItem(preferenceKey)!).pinned).toEqual(['/dashboard/compute/instances']);
		await fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
		const reopened = await openDrawer();
		expect(within(reopened.getByRole('region', { name: t('sections.favorites') })).getAllByRole('link').map(link => link.getAttribute('href'))).toEqual(['/dashboard/compute/instances']);
		expect(reopened.getByRole('navigation', { name: t('accessibility.allServices') })).toBeTruthy();
		expect(get(page).url.pathname).toBe('/dashboard');
	});
	it('restores visible categories and clears search on Escape, backdrop dismissal, and route transitions', async () => {
		render(Sidebar);
		let menu = await openDrawer();
		await fireEvent.click(menu.getByRole('button', { name: t('accessibility.allServices') }));
		await fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
		menu = await openDrawer();
		expect(menu.getByRole('navigation', { name: t('accessibility.allServices') })).toBeTruthy();
		await fireEvent.input(menu.getByRole('searchbox'), { target: { value: t('items.images') } });
		await fireEvent.click(document.querySelector('[data-navigation-backdrop]')!);
		menu = await openDrawer();
		expect((menu.getByRole('searchbox') as HTMLInputElement).value).toBe('');
		await expandGlobalSections();
		await navigate('/dashboard/volumes/volume-1');
		expect(screen.queryByRole('dialog')).toBeNull();
		menu = await openDrawer();
		expect(menu.getByRole('navigation', { name: t('accessibility.allServices') })).toBeTruthy();
		expect(queryDestination(menu, '/dashboard/volumes')).toBeNull();
		expect(destination(within(screen.getByRole('navigation', { name: t('accessibility.currentService') })), '/dashboard/volumes').getAttribute('aria-current')).toBe('page');
	});
	it('filters saved pins through current authority, service and beta gates in saved order', async () => {
		localStorage.setItem(preferenceKey, JSON.stringify({ pinned: ['/dashboard/chat', '/dashboard/iam/users', '/dashboard/secrets', '/dashboard/compute/images', '/dashboard/volumes'], recent: [] }));
		render(Sidebar);
		const menu = await openDrawer();
		const shortcuts = () => within(menu.getByRole('region', { name: t('sections.favorites') })).getAllByRole('link').map(link => link.getAttribute('href'));
		expect(shortcuts()).toEqual(['/dashboard/compute/images', '/dashboard/volumes']);
		initSiteConfig({ services: { chat: true } });
		betaFeatures.update(current => ({ ...current, keyManager: true }));
		auth.update(current => ({ ...current, domainId: 'working', isDomainManager: true }));
		await tick();
		expect(shortcuts()).toEqual(['/dashboard/chat', '/dashboard/iam/users', '/dashboard/secrets', '/dashboard/compute/images', '/dashboard/volumes']);
		initSiteConfig({ services: { chat: false } });
		betaFeatures.set({ ...DEFAULT_BETA_FEATURES });
		auth.update(current => ({ ...current, isDomainManager: false }));
		await tick();
		expect(shortcuts()).toEqual(['/dashboard/compute/images', '/dashboard/volumes']);
	});
	it('retains bounded scroll areas and at most twenty saved pins', async () => {
		initSiteConfig({ services: { magnum: true, zun: true, k3s: true, manila: true, trove: true, swift: true, chat: true, waygate: true } });
		const rendered = render(Sidebar);
		await openCatalog();
		const paths = globalServices().getAllByRole('link').map(link => link.getAttribute('href'));
		expect(paths.length).toBeGreaterThan(20);
		rendered.unmount();
		sidebarOpen.close();
		await tick();
		localStorage.setItem(preferenceKey, JSON.stringify({ pinned: paths, recent: [] }));
		render(Sidebar);
		const menu = await openDrawer();
		expect(within(menu.getByRole('region', { name: t('sections.favorites') })).getAllByRole('link')).toHaveLength(20);
		const fixedArea = document.querySelector('[data-navigation-shortcuts]')!;
		expect(fixedArea.classList.contains('shrink-0')).toBe(true);
		expect(fixedArea.classList.contains('overflow-y-auto')).toBe(true);
		expect(fixedArea.nextElementSibling?.classList.contains('overflow-y-auto')).toBe(true);
	});
	it('keeps tutorial navigation within fixture-backed dashboard routes', async () => {
		mockPage.set({ url: new URL('http://localhost/dashboard?tutorial=on'), data: { mockup: { active: true, profile: 'on' } } });
		render(Sidebar);
		const menu = await openCatalog();
		destination(menu, '/dashboard/compute/instances');
		expect(menu.queryAllByRole('link').filter(link => link.getAttribute('href')?.startsWith('/palimpsest/'))).toEqual([]);
	});
	it.each(['/dashboard', '/dashboard/compute/instances', '/dashboard/volumes', '/dashboard/account'])('keeps VM creation out of shared navigation at %s', async path => {
		await navigate(path);
		render(Sidebar);
		await tick();
		expect(screen.queryByRole('button', { name: instanceT('list.createVmAction') })).toBeNull();
		const menu = await openCatalog();
		expect(menu.queryByRole('button', { name: instanceT('list.createVmAction') })).toBeNull();
		await fireEvent.click(destination(menu, '/dashboard/compute/instances'));
		expect(get(sidebarOpen)).toBe(false);
		expect(get(wizardOpen)).toBe(false);
	});
	it('keeps global service destinations closed until the global menu opens', async () => {
		render(Sidebar);
		await tick();
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(screen.queryByRole('complementary')).toBeNull();
		for (const href of ['/dashboard/compute/instances', '/dashboard/network/topology']) expect(queryDestination(screen, href)).toBeNull();
		const menu = await openCatalog();
		for (const href of ['/dashboard/compute/instances', '/dashboard/network/topology']) destination(menu, href);
	});
	it('makes service and overview destinations reachable in the global drawer', async () => {
		initSiteConfig({ services: { magnum: true, zun: true, k3s: true, manila: true, trove: true, swift: true, chat: true, waygate: true } });
		betaFeatures.set({ ...DEFAULT_BETA_FEATURES, keyManager: true, volumeSnapshots: true, fileStorageSnapshots: true, fileStorageShareNetworks: true, fileStorageSecurityServices: true });
		render(Sidebar);
		const menu = await openCatalog();
		for (const href of [
			'/dashboard', '/dashboard/usage', '/dashboard/usage-report', '/dashboard/activity', '/dashboard/network/topology',
			'/dashboard/compute/instances', '/dashboard/compute/images', '/dashboard/volumes', '/dashboard/volumes/backups', '/dashboard/volumes/snapshots',
			'/dashboard/file-storage', '/dashboard/file-storage/snapshots', '/dashboard/file-storage/networks', '/dashboard/file-storage/security-services',
			'/dashboard/containers/clusters', '/dashboard/containers/instances', '/dashboard/drover', '/dashboard/database/instances', '/dashboard/database/backups',
			'/dashboard/object-storage/buckets', '/dashboard/secrets', '/dashboard/chat', '/dashboard/chat/images', '/dashboard/chat/audio',
			'/dashboard/network/networks', '/dashboard/network/floating-ips', '/dashboard/network/routers', '/dashboard/network/loadbalancers', '/dashboard/network/security-groups', '/dashboard/network/waygate',
		]) destination(menu, href);
	});
	it('preserves project selection and current user-mode semantics in the drawer', async () => {
		auth.update(current => ({ ...current, username: 'alice', projectName: 'Team project', isSystemAdmin: true }));
		render(Sidebar);
		const menu = await openCatalog();
		destination(menu, '/admin');
		expect(menu.getByRole('button', { name: /Team project/ }).getAttribute('aria-haspopup')).toBe('dialog');
		expect(menu.getByText('alice')).toBeTruthy();
		auth.update(current => ({ ...current, isSystemAdmin: false }));
		await tick();
		expect(queryDestination(menu, '/admin')).toBeNull();
	});
	it('separates manager users from server-authorized project management without requiring a selected project', async () => {
		auth.update(current => ({ ...current, token: 'manager-token', domainId: 'working', identityDomainId: 'home', projectId: null, isSystemAdmin: false, isDomainManager: true }));
		(canManageOrganizationProjects as Writable<boolean>).set(true);
		render(Sidebar);
		const menu = await openCatalog();
		expect(menu.getByRole('button', { name: /리소스 선택/ }).getAttribute('aria-haspopup')).toBe('dialog');
		destination(menu, '/dashboard/iam/users');
		destination(menu, '/dashboard/iam/projects');
		destination(menu, '/dashboard/iam/groups');
		expect(queryDestination(menu, '/admin')).toBeNull();
		auth.update(current => ({ ...current, isDomainManager: false, isSystemAdmin: true }));
		await tick();
		expect(queryDestination(menu, '/dashboard/iam/users')).toBeNull();
		expect(queryDestination(menu, '/dashboard/iam/groups')).toBeNull();
		destination(menu, '/dashboard/iam/projects');
		(canManageOrganizationProjects as Writable<boolean>).set(false);
		await tick();
		expect(queryDestination(menu, '/dashboard/iam/projects')).toBeNull();
		destination(menu, '/admin');
	});
});

describe('Sidebar account navigation', () => {
	it.each(accountDestinations)('selects only %s and keeps all account destinations reachable', async href => {
		auth.update(current => ({ ...current, isSystemAdmin: false, isDomainManager: false, projectId: null }));
		await navigate(href);
		render(Sidebar);
		await tick();
		const panel = within(screen.getByRole('complementary'));
		expect(panel.getAllByRole('link').map(link => link.getAttribute('href'))).toEqual(accountDestinations);
		expect(activeDestinations(panel)).toEqual([href]);
		if (href !== '/dashboard/account') {
			await navigate(`${href}/detail-1`);
			expect(activeDestinations(panel)).toEqual([href]);
		}
	});
	it('keeps every account destination accessible in the compact rail without changing identity or route', async () => {
		await navigate('/dashboard/account/sessions');
		const authBefore = get(auth);
		render(Sidebar);
		await tick();
		const panel = within(screen.getByRole('complementary'));
		const toggle = panel.getByRole('button', { name: t('accessibility.collapseServiceMenu') });
		toggle.focus();
		await fireEvent.click(toggle);
		expect(panel.getByRole('button', { name: t('accessibility.expandServiceMenu') })).toBe(toggle);
		expect(document.activeElement).toBe(toggle);
		for (const href of accountDestinations) destination(panel, href);
		expect(activeDestinations(panel)).toEqual(['/dashboard/account/sessions']);
		expect(get(auth)).toEqual(authBefore);
		expect(get(page).url.pathname).toBe('/dashboard/account/sessions');
	});
	it.each([375, 1280])('shows account category while its destinations wait for explicit expansion at %ipx', async width => {
		const previousWidth = window.innerWidth;
		Object.defineProperty(window, 'innerWidth', { configurable: true, value: width });
		try {
			await navigate('/dashboard/account/mcp');
			render(Sidebar);
			sidebarOpen.open();
			await tick();
			const menu = drawer();
			expect(menu.getByRole('navigation', { name: t('accessibility.allServices') })).toBeTruthy();
			for (const href of accountDestinations) expect(queryDestination(menu, href)).toBeNull();
			await expandGlobalSections();
			for (const href of accountDestinations) destination(globalServices(), href);
			expect(activeDestinations(globalServices())).toEqual(['/dashboard/account/mcp']);
			await fireEvent.click(destination(globalServices(), '/dashboard/account/beta'));
			expect(get(sidebarOpen)).toBe(false);
			await navigate('/dashboard/compute/instances');
			expect(destination(screen, '/dashboard/compute/instances').getAttribute('aria-current')).toBe('page');
		} finally {
			Object.defineProperty(window, 'innerWidth', { configurable: true, value: previousWidth });
		}
	});
});

describe('Sidebar navigation ownership', () => {
	it('keeps selected service destinations reachable when collapsed and expands from the same control', async () => {
		await navigate('/dashboard/compute/instances/instance-1');
		const authBefore = get(auth);
		render(Sidebar);
		await tick();
		const panel = within(screen.getByRole('complementary'));
		const toggle = panel.getByRole('button', { name: t('accessibility.collapseServiceMenu') });
		toggle.focus();
		await fireEvent.click(toggle);
		expect(panel.getByRole('button', { name: t('accessibility.expandServiceMenu') })).toBe(toggle);
		expect(toggle.getAttribute('aria-expanded')).toBe('false');
		expect(document.activeElement).toBe(toggle);
		expect(destination(panel, '/dashboard/compute/instances').getAttribute('aria-current')).toBe('page');
		destination(panel, '/dashboard/compute/images');
		await fireEvent.click(toggle);
		expect(toggle.getAttribute('aria-expanded')).toBe('true');
		expect(document.activeElement).toBe(toggle);
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(get(auth)).toEqual(authBefore);
		expect(get(page).url.pathname).toBe('/dashboard/compute/instances/instance-1');
	});
	it('switches locales without replacing chrome or resetting manual navigation state', async () => {
		await navigate('/dashboard/volumes');
		render(Sidebar);
		await tick();
		const panel = document.getElementById('app-service-sidebar')!;
		const toggle = document.getElementById('app-service-sidebar-toggle')!;
		const volumeLink = destination(within(panel), '/dashboard/volumes');
		await fireEvent.click(toggle);
		await openCatalog();
		const menu = document.getElementById('app-navigation-menu')!;
		const volumeGroup = globalServices().getByRole('button', { name: t('sections.volumes') });
		await fireEvent.click(volumeGroup);
		for (const locale of ['ko', 'en', 'ja', 'zh-CN'] as const) {
			initLocale(locale);
			await tick();
			expect(document.getElementById('app-service-sidebar')).toBe(panel);
			expect(document.getElementById('app-navigation-menu')).toBe(menu);
			expect(destination(within(panel), '/dashboard/volumes')).toBe(volumeLink);
			expect(volumeLink.getAttribute('aria-current')).toBe('page');
			expect(toggle.getAttribute('aria-expanded')).toBe('false');
			expect(within(menu).getByRole('button', { name: t('sections.volumes') })).toBe(volumeGroup);
			expect(volumeGroup.getAttribute('aria-expanded')).toBe('false');
			destination(within(menu), '/palimpsest/packages');
			expect(get(page).url.pathname).toBe('/dashboard/volumes');
		}
	});
	it('keeps project settings outside global and service menus', async () => {
		await navigate('/dashboard/project-settings');
		render(Sidebar);
		await tick();
		expect(screen.queryByRole('complementary')).toBeNull();
		const menu = await openCatalog();
		expect(queryDestination(menu, '/dashboard/project-settings')).toBeNull();
	});
	it.each([true, false])('opens parent navigation and restores focus after Escape when expanded=%s', async expanded => {
		await navigate('/dashboard/compute/instances/instance-1');
		if (expanded) sidebarExpanded.open();
		else sidebarExpanded.close();
		const authBefore = get(auth);
		render(Sidebar);
		await tick();
		const parent = screen.getByRole('button', { name: t('accessibility.allServices') });
		parent.focus();
		await fireEvent.click(parent);
		expect(parent.getAttribute('aria-haspopup')).toBe('dialog');
		expect(document.activeElement).toBe(drawer().getByRole('button', { name: t('accessibility.closeAllMenu') }));
		await fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(document.activeElement).toBe(parent);
		expect(get(wizardOpen)).toBe(false);
		expect(get(auth)).toEqual(authBefore);
		expect(get(page).url.pathname).toBe('/dashboard/compute/instances/instance-1');
		expect(get(sidebarExpanded)).toBe(expanded);
	});
	it('keeps the pointer backdrop unfocusable and restores its opener after dismissal', async () => {
		await navigate('/dashboard/compute/instances/instance-1');
		render(Sidebar);
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
		const search = within(dialog).getByRole('searchbox');
		await fireEvent.click(search);
		expect(screen.getByRole('dialog')).toBe(dialog);
		await fireEvent.mouseDown(backdrop);
		expect(document.activeElement).not.toBe(backdrop);
		await fireEvent.mouseUp(backdrop);
		await fireEvent.click(backdrop);
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(get(sidebarOpen)).toBe(false);
		expect(document.activeElement).toBe(opener);
	});
	it('keeps topology standalone rather than showing Network contextual destinations', async () => {
		await navigate('/dashboard/network/topology');
		render(Sidebar);
		await tick();
		expect(screen.queryByRole('complementary')).toBeNull();
		const menu = await openCatalog();
		expect(destination(menu, '/dashboard/network/topology').getAttribute('aria-current')).toBe('page');
	});
	it('switches contextual destinations from standalone topology to the nested Network owner', async () => {
		await navigate('/dashboard/network/topology');
		render(Sidebar);
		await tick();
		await navigate('/dashboard/network/networks/network-1');
		expect(destination(screen, '/dashboard/network/networks').getAttribute('aria-current')).toBe('page');
		destination(screen, '/dashboard/network/floating-ips');
		for (const href of ['/dashboard/network/topology', '/dashboard/compute/instances']) expect(queryDestination(screen, href)).toBeNull();
		await navigate('/dashboard/network/topology');
		expect(screen.queryByRole('complementary')).toBeNull();
		expect(queryDestination(screen, '/dashboard/network/floating-ips')).toBeNull();
	});
	it('owns nested Drover routes outside the container URL prefix', async () => {
		initSiteConfig({ services: { k3s: true } });
		await navigate('/dashboard/drover/cluster-1');
		render(Sidebar);
		await tick();
		expect(destination(screen, '/dashboard/drover').getAttribute('aria-current')).toBe('page');
		for (const href of ['/dashboard/containers/clusters', '/dashboard/containers/instances']) expect(queryDestination(screen, href)).toBeNull();
	});
	it('selects the longest volume destination for backup details and the parent for volume details', async () => {
		await navigate('/dashboard/volumes/backups/backup-1');
		render(Sidebar);
		await tick();
		expect(activeDestinations(screen)).toEqual(['/dashboard/volumes/backups']);
		destination(screen, '/dashboard/volumes');
		await navigate('/dashboard/volumes/volume-1');
		expect(activeDestinations(screen)).toEqual(['/dashboard/volumes']);
		destination(screen, '/dashboard/volumes/backups');
	});
	it('keeps backup destinations available despite obsolete browser opt-outs', async () => {
		localStorage.setItem('afterglow.beta.volumeBackups', 'false');
		localStorage.setItem('afterglow.beta.databaseBackups', 'false');
		initSiteConfig({ services: { trove: true } });
		await navigate('/dashboard/volumes/backups');
		render(Sidebar);
		await tick();
		expect(destination(screen, '/dashboard/volumes/backups').getAttribute('aria-current')).toBe('page');
		destination(await openCatalog(), '/dashboard/database/backups');
	});
	it.each([
		['/dashboard/chat/images/run-1', '/dashboard/chat/images', '/dashboard/chat/audio'],
		['/dashboard/chat/audio/run-1', '/dashboard/chat/audio', '/dashboard/chat/images'],
	])('selects only the longest Studio destination at %s', async (path, href, sibling) => {
		initSiteConfig({ services: { chat: true } });
		await navigate(path);
		render(Sidebar);
		await tick();
		expect(activeDestinations(screen)).toEqual([href]);
		destination(screen, '/dashboard/chat');
		destination(screen, sibling);
		await navigate('/dashboard/chat');
		expect(activeDestinations(screen)).toEqual(['/dashboard/chat']);
		expect(destination(screen, href).getAttribute('aria-current')).toBeNull();
	});
	it('selects usage-report without also activating usage or overview', async () => {
		await navigate('/dashboard/usage-report');
		render(Sidebar);
		const menu = await openCatalog();
		expect(activeDestinations(menu)).toEqual(['/dashboard/usage-report']);
		for (const href of ['/dashboard/usage', '/dashboard']) expect(destination(within(menu.getByRole('navigation', { name: t('sections.hub') })), href).getAttribute('aria-current')).toBeNull();
	});
});

describe('Sidebar service and beta visibility', () => {
	it.each([
		['magnum', '/dashboard/containers/clusters'], ['zun', '/dashboard/containers/instances'], ['k3s', '/dashboard/drover'],
	] as const)('shows the container service when only %s is enabled, without leaking sibling items', async (service, href) => {
		initSiteConfig({ services: { [service]: true } });
		render(Sidebar);
		const menu = await openCatalog();
		destination(menu, href);
		for (const sibling of ['/dashboard/containers/clusters', '/dashboard/containers/instances', '/dashboard/drover'].filter(item => item !== href)) expect(queryDestination(menu, sibling)).toBeNull();
		initSiteConfig({ services: { [service]: false } });
		await tick();
		expect(queryDestination(menu, href)).toBeNull();
	});
	it.each([
		['manila', ['/dashboard/file-storage']], ['trove', ['/dashboard/database/instances', '/dashboard/database/backups']],
		['swift', ['/dashboard/object-storage/buckets']], ['chat', ['/dashboard/chat', '/dashboard/chat/images', '/dashboard/chat/audio']],
		['waygate', ['/dashboard/network/waygate']],
	] as const)('updates global destinations when %s changes without hiding unrelated services', async (service, hrefs) => {
		render(Sidebar);
		const menu = await openCatalog();
		for (const href of hrefs) expect(queryDestination(menu, href)).toBeNull();
		initSiteConfig({ services: { [service]: true } });
		await tick();
		await expandGlobalSections();
		for (const href of hrefs) destination(menu, href);
		initSiteConfig({ services: { [service]: false } });
		await tick();
		for (const href of hrefs) expect(queryDestination(menu, href)).toBeNull();
		destination(menu, '/dashboard/compute/instances');
	});
	it('hides contextual chat destinations when the service is disabled on a Studio route', async () => {
		initSiteConfig({ services: { chat: true } });
		await navigate('/dashboard/chat/images');
		render(Sidebar);
		await tick();
		expect(destination(screen, '/dashboard/chat/images').getAttribute('aria-current')).toBe('page');
		initSiteConfig({ services: { chat: false } });
		await tick();
		for (const href of ['/dashboard/chat', '/dashboard/chat/images', '/dashboard/chat/audio']) expect(queryDestination(screen, href)).toBeNull();
	});
	it('applies section and item beta gates while keeping ordinary destinations available', async () => {
		initSiteConfig({ services: { manila: true } });
		render(Sidebar);
		const menu = await openCatalog();
		const betaDestinations = ['/dashboard/secrets', '/dashboard/volumes/snapshots', '/dashboard/file-storage/snapshots', '/dashboard/file-storage/networks', '/dashboard/file-storage/security-services'];
		for (const href of betaDestinations) expect(queryDestination(menu, href)).toBeNull();
		betaFeatures.set({ ...DEFAULT_BETA_FEATURES, keyManager: true, volumeSnapshots: true, fileStorageSnapshots: true, fileStorageShareNetworks: true, fileStorageSecurityServices: true });
		await tick();
		await expandGlobalSections();
		for (const href of betaDestinations) destination(menu, href);
		initSiteConfig({ services: { manila: false } });
		await tick();
		for (const href of ['/dashboard/file-storage', ...betaDestinations.filter(href => href.startsWith('/dashboard/file-storage/'))]) expect(queryDestination(menu, href)).toBeNull();
		betaFeatures.set({ ...DEFAULT_BETA_FEATURES });
		await tick();
		for (const href of betaDestinations) expect(queryDestination(menu, href)).toBeNull();
		for (const href of ['/dashboard/volumes', '/dashboard/volumes/backups']) destination(menu, href);
	});
});
