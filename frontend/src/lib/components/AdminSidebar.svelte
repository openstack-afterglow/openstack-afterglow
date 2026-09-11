<script lang="ts">
	import { page } from '$app/stores';
	import { auth } from '$lib/stores/auth';
	import { sidebarOpen } from '$lib/stores/sidebar';
	import ProjectSelector from '$lib/components/ProjectSelector.svelte';
	import { siteConfig } from '$lib/config/site';
	import RingMark from '$lib/components/ui/RingMark.svelte';
	import { palette } from '$lib/stores/palette';
	import { betaFeatures, type BetaFeatures } from '$lib/stores/betaFeatures';
	import { isMockupPathAllowed } from '$lib/mockup/contracts';

	type BetaFeatureKey = keyof BetaFeatures;
	const mockupAdminActive = $derived($page.data.mockup?.active === true && $page.data.mockup.profile === 'admin');


	const sections = $state([
		{
			label: 'Compute',
			prefix: '/admin/instances',
			icon: 'M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2',
			open: false,
			items: [
				{ label: '전체 인스턴스', href: '/admin/instances', service: null },
				{ label: 'Flavor', href: '/admin/flavors', service: null },
				{ label: '이미지', href: '/admin/images', service: null },
				{ label: '하이퍼바이저', href: '/admin/hypervisors', service: null },
			],
		},
		{
			label: '스토리지',
			prefix: '/admin/volumes',
			icon: 'M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4',
			open: false,
			items: [
				{ label: '전체 볼륨', href: '/admin/volumes', service: null },
				{ label: '파일 스토리지', href: '/admin/file-storage', service: 'manila' as const },
				{ label: 'DB 인스턴스', href: '/admin/database-instances', service: 'trove' as const },
				{ label: 'Object Storage', href: '/admin/object-storage', service: 'swift' as const },
			],
		},
		{
			label: 'Palimpsest',
			prefix: '/admin/libraries',
			icon: 'M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253',
			open: false,
			items: [
				{ label: '레이어 관리', href: '/admin/libraries', service: null },
			],
		},
		{
			label: '네트워크',
			prefix: '/admin/topology',
			icon: 'M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9',
			open: false,
			items: [
				{ label: '토폴로지', href: '/admin/topology', service: null },
				{ label: '네트워크', href: '/admin/networks', service: null },
				{ label: 'Floating IP', href: '/admin/floating-ips', service: null },
				{ label: '라우터', href: '/admin/routers', service: null },
				{ label: '로드밸런서', href: '/admin/loadbalancers', service: null },
				{ label: '포트', href: '/admin/ports', service: null },
			],
		},
		{
			label: '컨테이너',
			prefix: '/admin/containers',
			icon: 'M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4',
			open: false,
			service: null as null,
			items: [
				{ label: '전체 컨테이너', href: '/admin/containers', service: 'zun' as const },
				{ label: 'Drover', href: '/admin/drover', service: 'k3s' as const },
				{ label: '클러스터 템플릿', href: '/admin/drover/templates', service: 'k3s' as const },
			],
		},
		{
			label: 'Key Manager',
			prefix: '/admin/secrets',
			icon: 'M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z',
			open: false,
			beta: 'keyManager' as BetaFeatureKey,
			items: [
				{ label: '프로젝트 쿼터', href: '/admin/secrets', service: null },
			],
		},
		{
			label: '모니터링',
			prefix: '/admin/monitoring',
			icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z',
			open: false,
			items: [
				{ label: '통합 모니터링', href: '/admin/monitoring', service: null },
				{ label: '노드', href: '/admin/monitoring/node', service: null },
				{ label: 'MySQL', href: '/admin/monitoring/mysql', service: null },
				{ label: 'HAProxy', href: '/admin/monitoring/haproxy', service: null },
				{ label: 'RabbitMQ', href: '/admin/monitoring/rabbitmq', service: null },
				{ label: 'Memcached', href: '/admin/monitoring/memcached', service: null },
				{ label: 'etcd', href: '/admin/monitoring/etcd', service: null },
				{ label: 'Libvirt', href: '/admin/monitoring/libvirt', service: null },
				{ label: 'OpenStack', href: '/admin/monitoring/openstack', service: null },
				{ label: 'Ceph', href: '/admin/monitoring/ceph', service: null },
			],
		},
		{
			label: '시스템',
			prefix: '/admin/services',
			icon: 'M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z',
			open: false,
			items: [
				{ label: '서비스 상태', href: '/admin/services', service: null },
				{ label: '고아 리소스', href: '/admin/orphans', service: null },
				{ label: 'Notion 연동', href: '/admin/notion', service: null },
				{ label: '공지 관리', href: '/admin/announcements', service: null },
				{ label: '기본 설정', href: '/admin/settings', service: null },
			],
		},
		{
			label: 'AI 채팅',
			prefix: '/admin/chat',
			icon: 'M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z',
			open: false,
			service: 'chat' as const,
			items: [
				{ label: '채팅 통계', href: '/admin/chat/stats', service: 'chat' as const },
				{ label: '사용자 쿼터', href: '/admin/chat/quotas', service: 'chat' as const },
				{ label: '프로바이더 설정', href: '/admin/chat', service: 'chat' as const },
				{ label: '모델 설정', href: '/admin/chat/models', service: 'chat' as const },
				{ label: '도구 설정', href: '/admin/chat/tools', service: 'chat' as const },
			],
		},
		{
			label: 'Identity',
			prefix: '/admin/users',
			icon: 'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z',
			open: false,
			items: [
				{ label: '사용자', href: '/admin/users', service: null },
				{ label: '프로젝트', href: '/admin/projects', service: null },
				{ label: '쿼터', href: '/admin/quotas', service: null },
				{ label: '그룹', href: '/admin/groups', service: null },
				{ label: '역할', href: '/admin/roles', service: null },
				{ label: '시스템 관리자', href: '/admin/system-admins', service: null },
			],
		},
	]);

	$effect(() => {
		const pathname = $page.url.pathname;
		for (const section of sections) {
			if (pathname.startsWith(section.prefix) || section.items.some(item => pathname.startsWith(item.href))) {
				section.open = true;
			}
		}
	});

	// 페이지 이동 시 모바일 드로어 자동 닫기
	$effect(() => {
		$page.url.pathname;
		sidebarOpen.close();
	});
	function closeMobileSidebar() {
		sidebarOpen.close();
		document.getElementById('app-sidebar-trigger')?.focus();
	}

	function isBetaVisible(beta?: BetaFeatureKey): boolean {
		return mockupAdminActive || !beta || Boolean($betaFeatures[beta]);
	}

	function isItemVisible(item: { href: string; beta?: BetaFeatureKey; service?: string | null }): boolean {
		if (mockupAdminActive) return isMockupPathAllowed('admin', item.href);
		if (!isBetaVisible(item.beta)) return false;
		const svcs = $siteConfig.services as Record<string, boolean> | undefined;
		if (!item.service) return true;
		return svcs?.[item.service] ?? false;
	}

	function isSectionVisible(section: { beta?: BetaFeatureKey; service?: string | null; items: { href: string; beta?: BetaFeatureKey; service?: string | null }[] }): boolean {
		if (mockupAdminActive) return section.items.some(item => isItemVisible(item));
		const svcs = $siteConfig.services as Record<string, boolean> | undefined;
		if (!isBetaVisible(section.beta)) return false;
		if (section.service && !(svcs?.[section.service] ?? false)) return false;
		return section.items.some(item => isItemVisible(item));
	}
</script>

<!-- 오버레이 배경 (모바일만) -->
{#if $sidebarOpen}
	<button
		class="fixed inset-0 z-[var(--z-sidebar)] bg-surface-scrim-soft md:hidden"
		onclick={closeMobileSidebar}
		aria-label="메뉴 닫기"
	></button>
{/if}

<aside
	id="app-sidebar"
	class="fixed inset-y-0 left-0 z-[var(--z-sidebar)] flex h-[100dvh] w-[var(--app-sidebar-width)] flex-col overflow-y-auto border-r border-line bg-surface-base transition-transform duration-[var(--motion-duration-panel)] ease-out {$sidebarOpen ? 'translate-x-0' : '-translate-x-full'} md:sticky md:top-0 md:shrink-0 md:translate-x-0 md:transition-none"
	aria-label="관리자 탐색"
>
	<!-- 로고 헤더 with Admin badge -->
	<div class="flex h-[var(--app-header-height)] shrink-0 items-center gap-2.5 border-b border-line px-4">
		<RingMark size={24} />
		<a href="/admin" class="text-[15px] font-semibold tracking-tight text-ink-0 transition-colors hover:text-ink-1">
			{$siteConfig.site_name}
		</a>
		<span class="ml-auto rounded-md border border-[var(--admin-tone-ring)] bg-[var(--admin-tone-soft)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--admin-tone)]">Admin</span>
	</div>

	<!-- 검색 버튼 (1024px 미만에서만 표시) -->
	<div class="px-3 pb-1 pt-2 lg:hidden">
		<button
			onclick={() => palette.open()}
			class="flex w-full items-center gap-2 rounded-md border border-line-2 bg-surface-sunken py-1.5 pl-3 pr-2 text-[13px] text-ink-2 transition-colors hover:bg-surface-selected"
			aria-label="검색 (⌘K)"
		>
			<svg class="size-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-4.35-4.35M17 11A6 6 0 115 11a6 6 0 0112 0z"/></svg>
			<span class="flex-1 text-left">리소스 검색...</span>
			<kbd class="rounded border border-line px-1.5 py-0.5 font-mono text-[10px]">⌘K</kbd>
		</button>
	</div>

	<nav class="flex-1 min-h-0 overflow-y-auto px-3 py-3 space-y-0.5">
		<!-- 개요 -->
		<a
			href="/admin"
			aria-current={$page.url.pathname === '/admin' ? 'page' : undefined}
			class="nav-item flex h-8 items-center gap-2 rounded-md px-3 text-[13px] transition-colors"
			class:nav-active={$page.url.pathname === '/admin'}
		>
			<svg class="size-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path></svg>
			개요
		</a>

		<!-- 섹션들 -->
		{#each sections as section}
			{#if isSectionVisible(section)}
			<div>
				<button
					onclick={() => section.open = !section.open}
					class="flex items-center justify-between w-full px-3 py-2 rounded-lg text-sm transition-colors {$page.url.pathname.startsWith(section.prefix) || section.items.some(item => $page.url.pathname.startsWith(item.href)) ? 'text-ink-0' : 'text-ink-2 hover:text-ink-0 hover:bg-surface-sunken'}"
				>
					<div class="flex items-center gap-1.5">
						{#if section.icon}
							<svg class="w-3.5 h-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d={section.icon}></path></svg>
						{/if}
						<span>{section.label}</span>
					</div>
					<span class="text-xs text-ink-3">{section.open ? '▾' : '▸'}</span>
				</button>

				{#if section.open}
					<div class="ml-3 mt-0.5 space-y-0.5">
						{#each section.items as item}
							{#if isItemVisible(item)}
							<a
								href={item.href}
								aria-current={$page.url.pathname === item.href ? 'page' : undefined}
								class="nav-item nav-sub flex h-8 items-center rounded-md px-3 text-[13px] transition-colors"
								class:nav-active={$page.url.pathname === item.href}
							>
								{item.label}
							</a>
							{/if}
						{/each}
					</div>
				{/if}
			</div>
			{/if}
		{/each}
	</nav>

	<!-- 하단: 사용자 정보 + 사용자 모드 전환 -->
	<div class="border-t border-line shrink-0">
		<!-- 데스크톱: 관리자 정보 -->
		<div class="hidden md:block px-4 py-3">
			<div class="text-[10px] text-ink-3 uppercase tracking-widest font-medium">관리자</div>
			<div class="text-[13px] text-ink-1 font-medium mt-0.5 truncate">{$auth.username}</div>
		</div>

		<!-- 모바일 전용 -->
		<div class="p-3 lg:hidden">
			<div class="text-[10px] text-ink-3 uppercase tracking-wide px-1 mb-1.5">프로젝트</div>
			<ProjectSelector />
		</div>
		{#if !mockupAdminActive}
		<div class="p-3 pt-0 lg:hidden">
			<a href="/dashboard"
				class="nav-item nav-active flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors">
				<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"></path></svg>
				사용자 모드
			</a>
		</div>
		{/if}
		<div class="p-3 pt-0 md:hidden border-t border-line">
			<div class="px-3 text-xs text-ink-3">{$auth.username}</div>
		</div>
	</div>
</aside>

<style>
	.nav-item {
		color: var(--color-ink-2);
		font-weight: 500;
	}
	.nav-item:hover:not(.nav-active) {
		color: var(--color-ink-0);
		background-color: var(--color-surface-sunken);
	}
	.nav-sub {
		color: var(--color-ink-2);
	}
	.nav-sub:hover:not(.nav-active) {
		color: var(--color-ink-1);
	}
	.nav-active {
		background: var(--color-surface-selected);
		color: var(--color-ink-0);
		font-weight: 600;
	}

	@media (pointer: coarse) {
		.nav-item {
			min-height: 2.75rem;
		}
	}
</style>