import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { get } from 'svelte/store';
import type { Writable } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('$app/environment', () => ({ browser: true }));
vi.mock('$app/stores', async () => {
	// vi.mock is hoisted before static imports initialize, so load the store in its factory.
	const { writable } = await import('svelte/store');
	return { page: writable({ url: new URL('http://localhost/dashboard'), data: {} }) };
});

import { page } from '$app/stores';
import { initSiteConfig, siteConfig } from '$lib/config/site';
import { auth } from '$lib/stores/auth';
import { betaFeatures, DEFAULT_BETA_FEATURES } from '$lib/stores/betaFeatures';
import { sidebarExpanded, sidebarOpen } from '$lib/stores/sidebar';
import { wizardOpen } from '$lib/stores/wizard';
import Sidebar from '../Sidebar.svelte';
import { getTour } from '$lib/tutorial/tours';

// The SvelteKit readable is replaced with a writable store by the mock above.
const mockPage = page as unknown as Writable<{ url: URL; data: Record<string, unknown> }>;
const initialSiteConfig = get(siteConfig);
const initialAuth = get(auth);
const initialBetaFeatures = get(betaFeatures);

function navigate(pathname: string) {
	mockPage.set({ url: new URL(pathname, 'http://localhost'), data: {} });
	return tick();
}

async function expandGlobalSections() {
	const drawer = within(screen.getByRole('dialog', { name: '전체 메뉴' }));
	const navigation = within(drawer.getByRole('navigation', { name: '모든 서비스' }));
	for (const button of navigation.queryAllByRole('button')) {
		if (button.getAttribute('aria-expanded') === 'false') await fireEvent.click(button);
	}
}

async function openGlobalNavigation() {
	sidebarOpen.open();
	await tick();
	const drawer = within(screen.getByRole('dialog', { name: '전체 메뉴' }));
	await expandGlobalSections();
	return drawer;
}

beforeEach(async () => {
	sidebarOpen.close();
	sidebarExpanded.open();
	wizardOpen.set(false);
	auth.set({ ...initialAuth, isSystemAdmin: false });
	betaFeatures.set({ ...DEFAULT_BETA_FEATURES });
	initSiteConfig({ services: {
		magnum: false, zun: false, k3s: false, manila: false,
		trove: false, swift: false, chat: false, waygate: false,
	} });
	await navigate('/dashboard');
});

afterEach(() => {
	cleanup();
	sidebarOpen.close();
	sidebarExpanded.open();
	wizardOpen.set(false);
	auth.set(initialAuth);
	siteConfig.set(initialSiteConfig);
	betaFeatures.set(initialBetaFeatures);
	localStorage.removeItem('afterglow.beta.volumeBackups');
	localStorage.removeItem('afterglow.beta.databaseBackups');
});

describe('Sidebar global navigation', () => {
	it('keeps tutorial navigation within fixture-backed dashboard routes', async () => {
		mockPage.set({ url: new URL('http://localhost/dashboard?tutorial=on'), data: { mockup: { active: true, profile: 'on' } } });
		render(Sidebar);
		const drawer = await openGlobalNavigation();
		expect(drawer.getByRole('link', { name: '인스턴스' }).getAttribute('href')).toBe('/dashboard/compute/instances');
		expect(drawer.queryByRole('link', { name: '프로젝트 패키지' })).toBeNull();
		expect(drawer.getAllByRole('link').filter(link => link.getAttribute('href')?.startsWith('/palimpsest/'))).toEqual([]);
	});

	it('opens the global launcher for the VM tutorial on desktop before any wizard starts', async () => {
		const previousWidth = window.innerWidth;
		Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1280 });
		try {
			render(Sidebar);
			await tick();
			await getTour('vm-create')!.steps[0].prepare!();
			const drawer = within(screen.getByRole('dialog', { name: '전체 메뉴' }));
			expect(get(wizardOpen)).toBe(false);
			await fireEvent.click(drawer.getByRole('button', { name: 'VM 생성' }));
			expect(screen.queryByRole('dialog', { name: '전체 메뉴' })).toBeNull();
			expect(get(wizardOpen)).toBe(true);
		} finally {
			Object.defineProperty(window, 'innerWidth', { configurable: true, value: previousWidth });
		}
	});

	it('keeps global service destinations closed until the global menu opens', async () => {
		render(Sidebar);
		await tick();

		expect(screen.queryByRole('dialog')).toBeNull();
		expect(screen.queryByRole('complementary', { name: '페이지 메뉴' })).toBeNull();
		expect(screen.queryByRole('link', { name: '인스턴스' })).toBeNull();
		expect(screen.queryByRole('link', { name: '토폴로지' })).toBeNull();

		const drawer = await openGlobalNavigation();
		expect(drawer.getByRole('link', { name: '인스턴스' }).getAttribute('href')).toBe('/dashboard/compute/instances');
		expect(drawer.getByRole('link', { name: '토폴로지' }).getAttribute('href')).toBe('/dashboard/network/topology');
	});

	it('makes service and overview destinations reachable in the global drawer', async () => {
		initSiteConfig({ services: {
			magnum: true, zun: true, k3s: true, manila: true,
			trove: true, swift: true, chat: true, waygate: true,
		} });
		betaFeatures.set({ ...DEFAULT_BETA_FEATURES,
			keyManager: true, volumeSnapshots: true, fileStorageSnapshots: true,
			fileStorageShareNetworks: true, fileStorageSecurityServices: true,
		});
		render(Sidebar);
		await tick();
		const drawer = await openGlobalNavigation();
		const destinations = [
			['개요', '/dashboard'],
			['사용량', '/dashboard/usage'],
			['사용량 리포트', '/dashboard/usage-report'],
			['활동', '/dashboard/activity'],
			['토폴로지', '/dashboard/network/topology'],
			['인스턴스', '/dashboard/compute/instances'],
			['이미지', '/dashboard/compute/images'],
			['볼륨 목록', '/dashboard/volumes'],
			['볼륨 백업', '/dashboard/volumes/backups'],
			['볼륨 스냅샷', '/dashboard/volumes/snapshots'],
			['파일 스토리지', '/dashboard/file-storage'],
			['스냅샷', '/dashboard/file-storage/snapshots'],
			['Share 네트워크', '/dashboard/file-storage/networks'],
			['Security Service', '/dashboard/file-storage/security-services'],
			['K8s 클러스터', '/dashboard/containers/clusters'],
			['컨테이너', '/dashboard/containers/instances'],
			['Drover', '/dashboard/drover'],
			['DB 인스턴스', '/dashboard/database/instances'],
			['DB 백업', '/dashboard/database/backups'],
			['버킷', '/dashboard/object-storage/buckets'],
			['비밀 관리', '/dashboard/secrets'],
			['Lumen', '/dashboard/chat'],
			['이미지 Studio', '/dashboard/chat/images'],
			['오디오 Studio', '/dashboard/chat/audio'],
			['네트워크', '/dashboard/network/networks'],
			['Floating IP', '/dashboard/network/floating-ips'],
			['라우터', '/dashboard/network/routers'],
			['로드밸런서', '/dashboard/network/loadbalancers'],
			['보안 그룹', '/dashboard/network/security-groups'],
			['Waygate', '/dashboard/network/waygate'],
		];
		for (const [label, href] of destinations) {
			expect(drawer.getByRole('link', { name: label }).getAttribute('href')).toBe(href);
		}
	});

	it('opens VM creation from the drawer and closes navigation without changing auth', async () => {
		render(Sidebar);
		await tick();
		const drawer = await openGlobalNavigation();
		const previousAuth = get(auth);

		await fireEvent.click(drawer.getByRole('button', { name: 'VM 생성' }));

		expect(get(wizardOpen)).toBe(true);
		expect(get(sidebarOpen)).toBe(false);
		expect(get(auth)).toEqual(previousAuth);
	});

	it('preserves project selection and current user-mode semantics in the drawer', async () => {
		auth.update(current => ({ ...current, username: 'alice', projectName: 'Team project', isSystemAdmin: true }));
		render(Sidebar);
		await tick();
		const drawer = await openGlobalNavigation();
		const mode = drawer.getByRole('link', { name: '현재 사용자 모드, 관리자 모드로 전환' });

		expect(mode.getAttribute('href')).toBe('/admin');
		expect(mode.getAttribute('title')).toBe('관리자 모드로 전환');
		expect(mode.textContent).toContain('사용자 모드');
		expect(drawer.getByRole('button', { name: 'Team project' }).getAttribute('aria-haspopup')).toBe('menu');
		expect(drawer.getByText('alice')).toBeTruthy();

		auth.update(current => ({ ...current, isSystemAdmin: false }));
		await tick();
		expect(drawer.queryByRole('link', { name: '현재 사용자 모드, 관리자 모드로 전환' })).toBeNull();
	});
});

describe('Sidebar navigation ownership', () => {
	it('keeps selected service destinations reachable when collapsed and expands from the same control', async () => {
		await navigate('/dashboard/compute/instances/instance-1');
		const authBefore = get(auth);
		render(Sidebar);
		await tick();
		const panel = within(screen.getByRole('complementary', { name: '페이지 메뉴' }));
		expect(panel.queryByRole('button', { name: '전체 메뉴' })).toBeNull();
		const toggle = panel.getByRole('button', { name: '서비스 메뉴 접기' });
		toggle.focus();
		await fireEvent.click(toggle);
		const collapsed = within(screen.getByRole('complementary', { name: '페이지 메뉴' }));
		expect(collapsed.getByRole('button', { name: '서비스 메뉴 펼치기' })).toBe(toggle);
		expect(toggle.getAttribute('aria-expanded')).toBe('false');
		expect(document.activeElement).toBe(toggle);
		expect(collapsed.getByRole('link', { name: '인스턴스' }).getAttribute('aria-current')).toBe('page');
		expect(collapsed.getByRole('link', { name: '이미지' }).getAttribute('href')).toBe('/dashboard/compute/images');
		await fireEvent.click(toggle);
		expect(panel.getByRole('button', { name: '서비스 메뉴 접기' })).toBe(toggle);
		expect(toggle.getAttribute('aria-expanded')).toBe('true');
		expect(document.activeElement).toBe(toggle);
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(get(auth)).toEqual(authBefore);
		expect(get(page).url.pathname).toBe('/dashboard/compute/instances/instance-1');
	});

	it('keeps project settings outside global and service menus', async () => {
		await navigate('/dashboard/project-settings');
		render(Sidebar);
		await tick();
		expect(screen.queryByRole('complementary', { name: '페이지 메뉴' })).toBeNull();
		expect(screen.queryByRole('button', { name: '서비스 메뉴 펼치기' })).toBeNull();
		const drawer = await openGlobalNavigation();
		expect(drawer.queryByRole('link', { name: '프로젝트 설정' })).toBeNull();
	});

	it('places topology directly after activity before service destinations', async () => {
		render(Sidebar);
		const drawer = await openGlobalNavigation();
		const navigation = within(drawer.getByRole('navigation', { name: '모든 서비스' }));
		const labels = navigation.getAllByRole('link').map(link => link.textContent?.trim());
		expect(labels.slice(0, 5)).toEqual(['개요', '사용량', '사용량 리포트', '활동', '토폴로지']);
		expect(labels.indexOf('토폴로지')).toBeLessThan(labels.indexOf('인스턴스'));
	});

	it('keeps VM creation available in a visible service sidebar', async () => {
		await navigate('/dashboard/compute/instances/instance-1');
		render(Sidebar);
		await tick();
		await fireEvent.click(screen.getByRole('button', { name: 'VM 생성' }));
		expect(get(wizardOpen)).toBe(true);
	});

	it('keeps topology standalone rather than showing Network contextual destinations', async () => {
		await navigate('/dashboard/network/topology');
		render(Sidebar);
		await tick();

		expect(screen.queryByRole('complementary', { name: '페이지 메뉴' })).toBeNull();
		const drawer = await openGlobalNavigation();
		expect(drawer.getByRole('link', { name: '토폴로지' }).getAttribute('aria-current')).toBe('page');
	});

	it('switches contextual destinations from standalone topology to the nested Network owner', async () => {
		await navigate('/dashboard/network/topology');
		render(Sidebar);
		await tick();
		await navigate('/dashboard/network/networks/network-1');

		expect(screen.getByRole('link', { name: '네트워크' }).getAttribute('aria-current')).toBe('page');
		expect(screen.getByRole('link', { name: 'Floating IP' }).getAttribute('href')).toBe('/dashboard/network/floating-ips');
		expect(screen.queryByRole('link', { name: '토폴로지' })).toBeNull();
		expect(screen.queryByRole('link', { name: '인스턴스' })).toBeNull();

		await navigate('/dashboard/network/topology');
		expect(screen.queryByRole('complementary', { name: '페이지 메뉴' })).toBeNull();
		expect(screen.queryByRole('link', { name: 'Floating IP' })).toBeNull();
	});

	it('owns nested Drover routes outside the container URL prefix', async () => {
		initSiteConfig({ services: { k3s: true } });
		await navigate('/dashboard/drover/cluster-1');
		render(Sidebar);
		await tick();

		expect(screen.getByRole('link', { name: 'Drover' }).getAttribute('aria-current')).toBe('page');
		expect(screen.queryByRole('link', { name: 'K8s 클러스터' })).toBeNull();
		expect(screen.queryByRole('link', { name: '컨테이너' })).toBeNull();
	});

	it('selects the longest volume destination for backup details and the parent for volume details', async () => {
		await navigate('/dashboard/volumes/backups/backup-1');
		render(Sidebar);
		await tick();

		expect(screen.getByRole('link', { name: '볼륨 백업' }).getAttribute('aria-current')).toBe('page');
		expect(screen.getByRole('link', { name: '볼륨 목록' }).getAttribute('aria-current')).toBeNull();

		await navigate('/dashboard/volumes/volume-1');
		expect(screen.getByRole('link', { name: '볼륨 목록' }).getAttribute('aria-current')).toBe('page');
		expect(screen.getByRole('link', { name: '볼륨 백업' }).getAttribute('aria-current')).toBeNull();
	});

	it('keeps backup destinations available despite obsolete browser opt-outs', async () => {
		localStorage.setItem('afterglow.beta.volumeBackups', 'false');
		localStorage.setItem('afterglow.beta.databaseBackups', 'false');
		initSiteConfig({ services: { trove: true } });
		await navigate('/dashboard/volumes/backups');
		render(Sidebar);
		await tick();

		expect(screen.getByRole('link', { name: '볼륨 백업' }).getAttribute('aria-current')).toBe('page');
		const drawer = await openGlobalNavigation();
		expect(drawer.getByRole('link', { name: 'DB 백업' }).getAttribute('href')).toBe('/dashboard/database/backups');
	});

	it.each([
		['/dashboard/chat/images/run-1', '이미지 Studio', '/dashboard/chat/images'],
		['/dashboard/chat/audio/run-1', '오디오 Studio', '/dashboard/chat/audio'],
	])('selects only the longest Studio destination at %s', async (path, label, href) => {
		initSiteConfig({ services: { chat: true } });
		await navigate(path);
		render(Sidebar);
		await tick();

		expect(screen.getByRole('link', { name: label }).getAttribute('href')).toBe(href);
		expect(screen.getByRole('link', { name: label }).getAttribute('aria-current')).toBe('page');
		expect(screen.getByRole('link', { name: 'Lumen' }).getAttribute('aria-current')).toBeNull();
		const other = label === '이미지 Studio' ? '오디오 Studio' : '이미지 Studio';
		expect(screen.getByRole('link', { name: other }).getAttribute('aria-current')).toBeNull();

		await navigate('/dashboard/chat');
		expect(screen.getByRole('link', { name: 'Lumen' }).getAttribute('aria-current')).toBe('page');
		expect(screen.getByRole('link', { name: label }).getAttribute('aria-current')).toBeNull();
	});

	it('selects usage-report without also activating usage or overview', async () => {
		await navigate('/dashboard/usage-report');
		render(Sidebar);
		await tick();
		const drawer = await openGlobalNavigation();

		expect(drawer.getByRole('link', { name: '사용량 리포트' }).getAttribute('aria-current')).toBe('page');
		expect(drawer.getByRole('link', { name: '사용량' }).getAttribute('aria-current')).toBeNull();
		expect(drawer.getByRole('link', { name: '개요' }).getAttribute('aria-current')).toBeNull();
	});
});

describe('Sidebar service and beta visibility', () => {
	it.each([
		['magnum', 'K8s 클러스터'],
		['zun', '컨테이너'],
		['k3s', 'Drover'],
	] as const)('shows the container service when only %s is enabled, without leaking sibling items', async (service, label) => {
		initSiteConfig({ services: { [service]: true } });
		render(Sidebar);
		await tick();
		const drawer = await openGlobalNavigation();

		expect(drawer.getByRole('link', { name: label })).toBeTruthy();
		for (const sibling of ['K8s 클러스터', '컨테이너', 'Drover'].filter(item => item !== label)) {
			expect(drawer.queryByRole('link', { name: sibling })).toBeNull();
		}
		initSiteConfig({ services: { [service]: false } });
		await tick();
		expect(drawer.queryByRole('link', { name: label })).toBeNull();
	});

	it.each([
		['manila', ['파일 스토리지']],
		['trove', ['DB 인스턴스', 'DB 백업']],
		['swift', ['버킷']],
		['chat', ['Lumen', '이미지 Studio', '오디오 Studio']],
		['waygate', ['Waygate']],
	] as const)('updates global destinations when %s changes without hiding unrelated services', async (service, labels) => {
		render(Sidebar);
		await tick();
		const drawer = await openGlobalNavigation();

		for (const label of labels) expect(drawer.queryByRole('link', { name: label })).toBeNull();
		initSiteConfig({ services: { [service]: true } });
		await tick();
		await expandGlobalSections();
		for (const label of labels) expect(drawer.getByRole('link', { name: label })).toBeTruthy();
		initSiteConfig({ services: { [service]: false } });
		await tick();
		for (const label of labels) expect(drawer.queryByRole('link', { name: label })).toBeNull();
		expect(drawer.getByRole('link', { name: '인스턴스' })).toBeTruthy();
	});

	it('hides contextual chat destinations when the service is disabled on a Studio route', async () => {
		initSiteConfig({ services: { chat: true } });
		await navigate('/dashboard/chat/images');
		render(Sidebar);
		await tick();
		expect(screen.getByRole('link', { name: '이미지 Studio' }).getAttribute('aria-current')).toBe('page');

		initSiteConfig({ services: { chat: false } });
		await tick();
		for (const label of ['Lumen', '이미지 Studio', '오디오 Studio']) {
			expect(screen.queryByRole('link', { name: label })).toBeNull();
		}
	});

	it('applies section and item beta gates while keeping ordinary destinations available', async () => {
		initSiteConfig({ services: { manila: true } });
		render(Sidebar);
		await tick();
		const drawer = await openGlobalNavigation();
		const betaDestinations = ['비밀 관리', '볼륨 스냅샷', '스냅샷', 'Share 네트워크', 'Security Service'];

		for (const label of betaDestinations) expect(drawer.queryByRole('link', { name: label })).toBeNull();
		betaFeatures.set({ ...DEFAULT_BETA_FEATURES,
			keyManager: true, volumeSnapshots: true, fileStorageSnapshots: true,
			fileStorageShareNetworks: true, fileStorageSecurityServices: true,
		});
		await tick();
		await expandGlobalSections();
		for (const label of betaDestinations) expect(drawer.getByRole('link', { name: label })).toBeTruthy();
		initSiteConfig({ services: { manila: false } });
		await tick();
		for (const label of ['파일 스토리지', '스냅샷', 'Share 네트워크', 'Security Service']) {
			expect(drawer.queryByRole('link', { name: label })).toBeNull();
		}
		betaFeatures.set({ ...DEFAULT_BETA_FEATURES });
		await tick();
		for (const label of betaDestinations) expect(drawer.queryByRole('link', { name: label })).toBeNull();
		expect(drawer.getByRole('link', { name: '볼륨 목록' })).toBeTruthy();
		expect(drawer.getByRole('link', { name: '볼륨 백업' })).toBeTruthy();
	});
});
