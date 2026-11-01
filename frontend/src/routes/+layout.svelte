<script lang="ts">
	import { onDestroy, onMount, untrack } from 'svelte';
	import { afterNavigate, beforeNavigate, goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { get } from 'svelte/store';
	import { auth, authReady, authRecovery, isLoggedIn, isAdmin, logoutInProgress, enterMockAuth, exitMockAuth, getMockupProfile, isMockAuthActive } from '$lib/stores/auth';
	import { createAuthVerificationController } from '$lib/utils/authVerification';
	import { sessionScopeKey } from '$lib/utils/authSession';
	import { installInteractionAudit, type InteractionAuditController } from '$lib/utils/interactionAudit';
	import { isTourActive } from '$lib/tutorial/engine';
	import { resolvedTheme } from '$lib/stores/theme';
	import { api, getBaseUrl, refreshSession } from '$lib/api/client';
	import { startLogout } from '$lib/utils/logout';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import ProjectSelector from '$lib/components/ProjectSelector.svelte';
	import ProfileImage from '$lib/components/account/ProfileImage.svelte';
	import { t as tAccount } from '$lib/i18n/ns/account';
	import AnnouncementBellButton from '$lib/components/notifications/AnnouncementBellButton.svelte';
	import { createUsageScheduleBell } from '$lib/stores/usageScheduleBell.svelte';
	import { t as usage } from '$lib/i18n/ns/usage-schedule';
	import { siteConfig, initSiteConfig, qualifyBackendAssetPaths, replaceSiteConfig } from '$lib/config/site';
	import { resolveFaviconPath } from '$lib/config/brandAssets';
	import type { PublicSiteConfig } from '$lib/types/siteConfig';
	import type { AnnouncementUser, UnreadCountResponse } from '$lib/types/announcements';
	import { formatIsoDateTime } from '$lib/utils/format';
	import { startSessionRefreshLifecycle } from '$lib/utils/sessionRefreshLifecycle';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import { sidebarOpen } from '$lib/stores/sidebar';
	import Toast from '$lib/components/ui/Toast.svelte';
	import UploadDock from '$lib/components/UploadDock.svelte';
	import CmdPalette from '$lib/components/CmdPalette.svelte';
	import { palette } from '$lib/stores/palette';
	import ConfirmDialog from '$lib/components/ui/ConfirmDialog.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import MockupBanner from '$lib/components/mockup/MockupBanner.svelte';
	import TutorialController from '$lib/tutorial/TutorialController.svelte';
	import { buildMockAuth } from '$lib/mockup/auth';
	import { MOCKUP_QUERY_KEY, MOCKUP_SESSION_KEY, MOCKUP_SERVICE_OVERRIDES, isMockupProfileId, isMockupPathAllowed, getMockupHomePath } from '$lib/mockup/contracts';
	import type { MockupProfileId } from '$lib/mockup/contracts';
	import CloudShellTrigger from '$lib/components/cloud-shell/CloudShellTrigger.svelte';
	import CloudShellAuthorizeDialog from '$lib/components/cloud-shell/CloudShellAuthorizeDialog.svelte';
	import CloudShellDock from '$lib/components/cloud-shell/CloudShellDock.svelte';
	import { cloudShell } from '$lib/stores/cloudShell.svelte';
	import { t } from '$lib/i18n/ns/shell';
	import { t as tn } from '$lib/i18n/ns/nav';
	import { getLocale, initLocale, restoreKeyDebugMode, setLocale } from '$lib/i18n/runtime.svelte';
	import LocaleSelect from '$lib/i18n/LocaleSelect.svelte';
	import ThemeSelect from '$lib/components/ThemeSelect.svelte';
	import { isDocsPath } from '$lib/docs/paths';
	import { documentationNavItem } from '$lib/config/nav';
	import { isProjectAgnosticPath } from '$lib/config/routes';
	import './layout.css';

	let { children, data } = $props();
	// Must run before any child renders: SSR and hydration both translate with the request locale.
	initLocale(untrack(() => data.locale));
	$effect.pre(() => { setLocale(data.locale); });
	const initialSiteConfig = untrack(() => data.siteConfig);
	const initialMockup = untrack(() => data.mockup);
	let themeReady = $state(false);
	let unreadAnnouncementCount = $state(0);
	let mockupClientReady = $state(false);
	let clientMockProfile = $state<MockupProfileId | null>(null);
	let enteredMockProfile: MockupProfileId | null = null;
	let previousMockupActive = initialMockup.active;
	let explicitMockupOff = false;
	let brandRefreshSerial = 0;
	const faviconPath = $derived(resolveFaviconPath($siteConfig));
	const mockup = $derived(data.mockup);
	const mockupAdminActive = $derived(mockup.active && mockup.profile === 'admin');
	const publicRoutes = ['/', '/login', '/logout', '/signup', '/recover', '/auth/callback', '/oauth/claude/authorize', '/oauth/mcp/authorize'];
	const isDocumentationRoute = $derived(isDocsPath($page.url.pathname));
	const authVerification = createAuthVerificationController();
	let unreadFetchSerial = 0;
	let unreadOwnerRevision = $state(0);
	let recoveryBusy = $state(false);
	let recoveryClock = $state(Date.now());
	const authenticationUnavailable = $derived(
		!!$auth.token && $authRecovery?.token === $auth.token
		&& !mockup.active && !isMockAuthActive() && !isDocumentationRoute && !publicRoutes.includes($page.url.pathname),
	);
	const recoveryWait = $derived(Math.max(0, Math.ceil((($authRecovery?.retryAt ?? 0) - recoveryClock) / 1000)));
	$effect(() => {
		if (!authenticationUnavailable) return;
		recoveryClock = Date.now();
		const timer = window.setInterval(() => { recoveryClock = Date.now(); }, 1000);
		return () => window.clearInterval(timer);
	});

	async function retryAuthentication() {
		if (recoveryBusy || $logoutInProgress || recoveryWait > 0) return;
		recoveryBusy = true;
		try {
			await refreshSession();
		} catch {
			// The coordinator keeps the recovery screen and updates its cooldown.
		} finally {
			recoveryBusy = false;
		}
	}

	replaceSiteConfig(initialSiteConfig);

	async function refreshPublicSiteConfig() {
		const serial = ++brandRefreshSerial;
		try {
			const config = await api.get<Partial<PublicSiteConfig>>('/api/v1/site-config');
			if (serial !== brandRefreshSerial || mockup.active) return;
			initSiteConfig(qualifyBackendAssetPaths(config, getBaseUrl()));
		} catch {
			// Branding refresh is best effort; the server-provided config remains visible.
		}
	}

	async function refreshUnreadAnnouncementCount() {
		const state = get(auth);
		const { token, projectId } = state;
		const owner = sessionScopeKey(state);
		const serial = ++unreadFetchSerial;
		if (isDocumentationRoute || mockup.active || isMockAuthActive() || !get(authReady) || !token) {
			unreadAnnouncementCount = 0;
			return;
		}
		try {
			const res = await api.get<UnreadCountResponse>('/api/v1/announcements/unread-count', token, projectId ?? undefined);
			if (serial !== unreadFetchSerial || sessionScopeKey(get(auth)) !== owner || !get(auth).token || !get(authReady)) return;
			unreadAnnouncementCount = res.unread_count;
		} catch {
			// 표시는 best-effort다. 기존 미읽음 상태는 일시적인 조회 실패로 지우지 않는다.
		}
	}

	// 종 아이콘 드롭다운 — 최근 공지를 즉시 보여주고, 전체 목록은 알림함으로 이동
	let bellOpen = $state(false);
	let bellItems = $state<AnnouncementUser[] | null>(null);
	let bellError = $state(false);
	let bellContainer = $state<HTMLDivElement | null>(null);
	let bellButton = $state<HTMLButtonElement | null>(null);
	let bellFetchSerial = 0;
	const usageBell = createUsageScheduleBell({ enabled: () => !isDocumentationRoute && !mockup.active && !isMockAuthActive() });
	// Fence same-tick scope/logout ABA before effects can batch it away. Token
	// rotation keeps display state and already pending display reads.
	let previousAnnouncementOwner = '';
	const unsubscribeAnnouncementOwner = auth.subscribe(state => {
		const owner = JSON.stringify([!!state.token, sessionScopeKey(state)]);
		if (owner === previousAnnouncementOwner) return;
		previousAnnouncementOwner = owner;
		unreadOwnerRevision++;
		unreadFetchSerial++;
		bellFetchSerial++;
		unreadAnnouncementCount = 0;
		bellOpen = false;
		bellItems = null;
	});
	onDestroy(unsubscribeAnnouncementOwner);
	const unsubscribeAnnouncementReady = authReady.subscribe(ready => {
		if (ready) return;
		unreadOwnerRevision++;
		unreadFetchSerial++;
		unreadAnnouncementCount = 0;
	});
	onDestroy(unsubscribeAnnouncementReady);

	function bellDotColor(severity: AnnouncementUser['severity']): string {
		if (severity === 'danger') return 'var(--color-state-danger)';
		if (severity === 'warning') return 'var(--color-state-warning)';
		return 'var(--color-accent)';
	}

	async function toggleBellDropdown() {
		bellOpen = !bellOpen;
		if (!bellOpen) return;
		void usageBell.refresh();
		bellError = false;
		bellItems = null;
		const serial = ++bellFetchSerial;
		const token = $auth.token;
		if (mockup.active || isMockAuthActive() || !token) {
			bellItems = [];
			return;
		}
		try {
			const items = await api.get<AnnouncementUser[]>('/api/v1/announcements', token, $auth.projectId ?? undefined);
			if (serial !== bellFetchSerial) return;
			bellItems = items.slice(0, 6);
			void refreshUnreadAnnouncementCount();
		} catch {
			if (serial !== bellFetchSerial) return;
			bellItems = [];
			bellError = true;
		}
	}

	function closeBellAndGo(id?: number) {
		bellOpen = false;
		void goto(id != null ? `/dashboard/notifications?focus=${id}` : '/dashboard/notifications');
	}

	const unreadDisplayOwner = $derived(JSON.stringify([unreadOwnerRevision, sessionScopeKey($auth), !!$auth.token, $authReady,
		isDocumentationRoute, mockup.active, isMockAuthActive()]));
	$effect(() => {
		unreadDisplayOwner;
		untrack(() => void refreshUnreadAnnouncementCount());
	});
	createAutoRefresh(() => refreshUnreadAnnouncementCount(), {
		storageKey: 'announcement-unread-count', defaultInterval: 60, invokeOnMount: false,
	});

	$effect(() => {
		if (!bellOpen || typeof document === 'undefined') return;
		const onPointerDown = (event: MouseEvent) => {
			if (bellContainer && !bellContainer.contains(event.target as Node)) bellOpen = false;
		};
		const onKeyDown = (event: KeyboardEvent) => {
			if (event.key !== 'Escape') return;
			bellOpen = false;
			// 드롭다운 내부에 있던 키보드 포커스가 body로 떨어지지 않게 트리거로 복귀
			bellButton?.focus();
		};
		document.addEventListener('mousedown', onPointerDown);
		document.addEventListener('keydown', onKeyDown);
		return () => {
			document.removeEventListener('mousedown', onPointerDown);
			document.removeEventListener('keydown', onKeyDown);
		};
	});

	$effect.pre(() => {
		const active = mockup.active;
		if (active) {
			brandRefreshSerial += 1;
			initSiteConfig({ services: MOCKUP_SERVICE_OVERRIDES });
			if (mockupClientReady && mockup.profile && clientMockProfile === mockup.profile && enteredMockProfile !== mockup.profile) {
				if (!isMockAuthActive() || getMockupProfile() !== mockup.profile || !get(auth).token) {
					enterMockAuth(buildMockAuth(mockup.profile, $page.url.pathname), mockup.profile);
				}
				enteredMockProfile = mockup.profile;
			}
		} else if (explicitMockupOff) {
			if (isMockAuthActive()) exitMockAuth();
			void refreshPublicSiteConfig();
			enteredMockProfile = null;
			explicitMockupOff = false;
		} else if (
			$page.url.pathname !== '/logout' &&
			mockupClientReady &&
			clientMockProfile &&
			isMockAuthActive() &&
			$page.url.searchParams.get(MOCKUP_QUERY_KEY) !== clientMockProfile
		) {
			const path = $page.url.pathname;
			const nextPath =
				(path.startsWith('/dashboard') || path.startsWith('/admin') || isDocsPath(path)) &&
				isMockupPathAllowed(clientMockProfile, path)
					? path
					: getMockupHomePath(clientMockProfile);
			const next = new URL(nextPath === path ? $page.url.href : nextPath, $page.url.origin);
			next.searchParams.set(MOCKUP_QUERY_KEY, clientMockProfile);
			void goto(`${next.pathname}${next.search}${next.hash}`, { replaceState: true });
		}
		previousMockupActive = active;
	});
	beforeNavigate(({ to, cancel }) => {
		if (typeof window === 'undefined' || !to?.url || to.url.origin !== location.origin) return;
		const requested = to.url.searchParams.get(MOCKUP_QUERY_KEY);
		if (requested === 'off') {
			sessionStorage.removeItem(MOCKUP_SESSION_KEY);
			clientMockProfile = null;
			explicitMockupOff = true;
			return;
		}
		if (isMockupProfileId(requested)) {
			sessionStorage.setItem(MOCKUP_SESSION_KEY, requested);
			clientMockProfile = requested;
			return;
		}
		const profile = clientMockProfile;
		if (!profile || to.url.pathname === '/logout') return;
		const next = new URL(to.url);
		next.searchParams.set(MOCKUP_QUERY_KEY, profile);
		cancel();
		void goto(`${next.pathname}${next.search}${next.hash}`);
	});



	// Domain selection and IAM work without a project; admin exemption remains system-only.
	const projectAgnostic = $derived(isProjectAgnosticPath($page.url.pathname, $isAdmin));

	// Token-bearing onboarding links are public and render without console chrome.
	const isOnboardingRoute = $derived($page.url.pathname.startsWith('/invitations/') || $page.url.pathname.startsWith('/registrations/') || $page.url.pathname.startsWith('/recover/'));
	const shelllessRoutes = ['/', '/login', '/logout', '/signup', '/recover', '/auth/callback', '/select-project', '/select-domain', '/oauth/claude/authorize', '/oauth/mcp/authorize'];
	const showAppChrome = $derived($isLoggedIn && !$logoutInProgress && !isDocumentationRoute && !shelllessRoutes.includes($page.url.pathname) && !isOnboardingRoute);
	$effect(() => {
		const token = $auth.token;
		const projectId = $auth.projectId;
		const userId = $auth.userId;
		const sessionId = $auth.sessionId;
		const enabled = $siteConfig.services.cloud_shell && !mockup.active && !isMockAuthActive();
		if (!enabled || !token || !projectId || !userId || !sessionId) {
			cloudShell.bindIdentity(null);
			return;
		}
		cloudShell.bindIdentity({
			token,
			userId,
			sessionId,
			projectId,
			projectName: $auth.projectName || projectId,
		});
	});
	$effect(() => {
		$page.url.pathname;
		sidebarOpen.close();
	});

	$effect(() => {
		if (!mockupClientReady) return;
		if (!$logoutInProgress && !$isLoggedIn && !isDocumentationRoute && !publicRoutes.includes($page.url.pathname) && !isOnboardingRoute) {
			goto('/login', { replaceState: true });
		}
	});

	$effect(() => {
		if (!$logoutInProgress && $page.url.pathname !== '/logout' && $authReady && $isLoggedIn && !$auth.projectId && !isDocumentationRoute && !projectAgnostic && !isOnboardingRoute) {
			goto('/select-project');
		}
	});

	// Only restored/unverified sessions need /me; fresh mapped logins are ready.
	$effect(() => {
		authVerification.setEnabled($page.url.pathname !== '/logout' && !isDocumentationRoute && !mockup.active);
	});

	let interactionAudit: InteractionAuditController | undefined;
	beforeNavigate(({ from, willUnload }) => {
		interactionAudit?.prepareNavigation();
		if (willUnload) interactionAudit?.navigate(from?.route.id ?? null, 'external');
	});
	afterNavigate(({ from, to }) => {
		if (from) interactionAudit?.navigate(from.route.id, to?.route.id ?? null);
	});

	onMount(() => {
		themeReady = true;
		restoreKeyDebugMode();
		const requested = location.pathname === '/logout' ? 'off' : $page.url.searchParams.get(MOCKUP_QUERY_KEY);
		let bootstrapUrl: string | null = null;
		if (isMockupProfileId(requested)) {
			clientMockProfile = requested;
			sessionStorage.setItem(MOCKUP_SESSION_KEY, requested);
			if ((location.pathname.startsWith('/dashboard') || location.pathname.startsWith('/admin')) && !isMockupPathAllowed(requested, location.pathname)) {
				bootstrapUrl = `${getMockupHomePath(requested)}?${MOCKUP_QUERY_KEY}=${requested}`;
			}
		} else if (requested === 'off') {
			sessionStorage.removeItem(MOCKUP_SESSION_KEY);
			clientMockProfile = null;
			explicitMockupOff = true;
		} else {
			const stored = sessionStorage.getItem(MOCKUP_SESSION_KEY);
			if (isMockupProfileId(stored)) {
				clientMockProfile = stored;
				const nextPath = (location.pathname.startsWith('/dashboard') || location.pathname.startsWith('/admin') || isDocsPath(location.pathname)) && isMockupPathAllowed(stored, location.pathname)
					? location.pathname
					: getMockupHomePath(stored);
				const next = new URL(nextPath === location.pathname ? location.href : nextPath, location.origin);
				next.searchParams.set(MOCKUP_QUERY_KEY, stored);
				bootstrapUrl = `${next.pathname}${next.search}${next.hash}`;
			}
		}
		if (clientMockProfile && !isMockAuthActive()) {
			enterMockAuth(buildMockAuth(clientMockProfile, $page.url.pathname), clientMockProfile);
			enteredMockProfile = clientMockProfile;
		}
		mockupClientReady = true;
		interactionAudit = installInteractionAudit({
			getOwner: () => get(auth),
			getRoute: () => get(page).route.id,
			getBaseUrl,
			isSuppressed: () => mockup.active || isMockAuthActive() || isTourActive(),
			subscribeOwner: (changed) => auth.subscribe(changed),
		});
		interactionAudit.navigate(get(page).route.id);
		if (bootstrapUrl) void goto(bootstrapUrl, { replaceState: true });
		if (!mockup.active && !bootstrapUrl) void refreshPublicSiteConfig();

		const stopSessionRefresh = startSessionRefreshLifecycle({
			getSession: () => ({
				token: isDocsPath(location.pathname) ? null : $auth.token,
				refreshToken: $auth.refreshToken,
				accessExpiresAt: $auth.accessExpiresAt,
				isMock: mockup.active || isMockAuthActive(),
				isLoggingOut: $logoutInProgress,
			}),
			refreshSession,
		});


		return () => {
			stopSessionRefresh();
			interactionAudit?.destroy();
			interactionAudit = undefined;
		};
	});

	onDestroy(() => {
		authVerification.dispose();
		void cloudShell.close('destroy', { keepDock: false });
	});

	// 테마 변경 시 <html> 클래스 업데이트
	$effect(() => {
		if (typeof document === 'undefined') return;
		document.documentElement.classList.toggle('light', themeReady && $resolvedTheme === 'light');
	});

	let logoutConfirming = false;
	async function logout() {
		if ($logoutInProgress || logoutConfirming) return;
		const owner = sessionScopeKey(get(auth));
		logoutConfirming = true;
		try {
			if (!await confirmDialog(t('logout.confirm'))) return;
			if ($logoutInProgress || sessionScopeKey(get(auth)) !== owner) return;
			void startLogout();
		} finally {
			logoutConfirming = false;
		}
	}
</script>

<svelte:head><link rel="icon" href={faviconPath} /></svelte:head>

{#if showAppChrome}
	<a
		href="#main-content"
		class="fixed left-3 top-3 z-[calc(var(--z-command)+2)] -translate-y-20 rounded-md bg-surface-raised px-3 py-2 text-sm font-medium text-ink-0 shadow-lg transition-transform focus:translate-y-0"
	>{t('skipToContent')}</a>
	<header class="console-header fixed top-0 left-0 right-0 z-[var(--z-header)] h-[var(--app-header-height)] flex items-center gap-1 sm:gap-3 border-b border-line px-2 sm:px-3 md:px-6">
		<div class="material-chrome pointer-events-none absolute inset-0 -z-10" aria-hidden="true"></div>
		<div class="header-context flex min-w-0 items-center gap-2 sm:gap-3">
			<button
				id="app-sidebar-trigger"
				onclick={() => sidebarOpen.toggle()}
				class="-ml-2 flex size-11 shrink-0 items-center justify-center rounded-md text-ink-2 transition-colors hover:bg-surface-sunken hover:text-ink-0 focus-visible:outline-none focus-visible:shadow-[var(--focus-ring)] lg:size-8"
				aria-label={tn('accessibility.openAllMenu')}
				aria-expanded={$sidebarOpen}
				aria-controls="app-navigation-menu"
			>
				<svg class="size-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" /></svg>
			</button>
			<a href={$page.url.pathname.startsWith('/admin') ? '/admin' : '/dashboard'} class="flex min-w-0 items-center gap-2.5 text-[15px] font-semibold tracking-tight text-ink-0 transition-colors hover:text-ink-1" title={$siteConfig.site_name}>
				<img src="/afterglow-symbol.svg" alt="" width="24" height="24" class="shrink-0" />
				<span class="hidden max-w-36 truncate sm:block">{$siteConfig.site_name}</span>
			</a>
			{#if $page.url.pathname !== '/admin' && !$page.url.pathname.startsWith('/admin/')}
				<div class="hidden min-w-0 md:block md:w-36 xl:w-44"><ProjectSelector /></div>
			{/if}
		</div>

		<!-- 검색 입력 (⌘K 트리거) -->
		<button
			onclick={() => palette.open()}
			class="header-search hidden min-w-0 cursor-text items-center gap-2 rounded-md border border-line-2 bg-surface-sunken py-1.5 pl-3 pr-2 text-[13px] text-ink-2 transition-colors hover:bg-surface-selected xl:flex"
			aria-label={t('search.label')}
		>
			<svg class="size-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-4.35-4.35M17 11A6 6 0 115 11a6 6 0 0112 0z"/></svg>
			<span class="min-w-0 flex-1 truncate text-left">{t('search.placeholder')}</span>
			<kbd class="shrink-0 rounded border border-line px-1.5 py-0.5 font-mono text-xs text-ink-2">⌘K</kbd>
		</button>

		<!-- 우측 컨트롤 -->
		<div class="ml-auto flex shrink-0 items-center gap-0 sm:gap-1 md:gap-2">
			<button onclick={() => palette.open()} aria-label={t('search.label')} class="hidden size-11 shrink-0 items-center justify-center rounded-md text-ink-2 transition-colors hover:bg-surface-sunken hover:text-ink-0 focus-visible:outline-none focus-visible:shadow-[var(--focus-ring)] md:flex xl:hidden">
				<svg class="size-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="m21 21-4.35-4.35M17 11a6 6 0 1 1-12 0 6 6 0 0 1 12 0" /></svg>
			</button>
			{#if $siteConfig.services.cloud_shell && !mockup.active}
				<div class="hidden shrink-0 lg:block">
					<CloudShellTrigger />
				</div>
			{/if}

			{#if $isAdmin && !mockupAdminActive}
				{#if $page.url.pathname.startsWith('/admin')}
					<a href="/dashboard"
						aria-label={t('mode.adminCurrent')}
						title={t('mode.switchToUser')}
						class="hidden lg:flex items-center gap-1.5 px-3 h-8 rounded-lg border text-xs font-semibold transition-colors bg-action-warm/15 border-action-warm/50 text-warm-text hover:bg-action-warm-hover/25">
						<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 2l8 4v6c0 5-3.5 9-8 10-4.5-1-8-5-8-10V6l8-4z"/></svg>
						{t('mode.admin')}
					</a>
				{:else}
					<a href="/admin"
						aria-label={t('mode.userCurrent')}
						title={t('mode.switchToAdmin')}
						class="hidden lg:flex items-center gap-1.5 px-3 h-8 rounded-lg border text-xs font-semibold transition-colors bg-surface-base border-line-2 text-ink-1 hover:border-line-2 hover:text-ink-0">
						<svg class="w-3.5 h-3.5 text-ink-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/></svg>
						{t('mode.user')}
					</a>
				{/if}
			{/if}

			<LocaleSelect id="app-header-locale" />
			<a href="/docs" aria-label={tn('items.documentation')} title={tn('items.documentation')} class="flex h-11 min-w-11 shrink-0 items-center justify-center gap-1.5 rounded-md px-2 text-ink-2 transition-colors hover:bg-surface-sunken hover:text-ink-0 focus-visible:outline-none focus-visible:shadow-[var(--focus-ring)] lg:h-8 lg:min-w-8">
				<svg class="size-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d={documentationNavItem.icon} /></svg>
				<span class="hidden text-xs font-medium sm:inline">Docs</span>
			</a>

			<ThemeSelect id="app-header-theme" />

			<!-- 알림 아이콘 + 드롭다운 -->
			<div class="relative" bind:this={bellContainer}>
				<AnnouncementBellButton
					bind:element={bellButton}
					count={unreadAnnouncementCount}
					usageCount={usageBell.count}
					usageOverdue={usageBell.overdue}
					usageUnavailable={usageBell.failed}
					usageLoading={usageBell.loading}
					open={bellOpen}
					onclick={toggleBellDropdown}
				/>
				{#if bellOpen}
					<!-- 모바일: 바텀 시트 / sm 이상: 종 아이콘 기준 드롭다운 (ProjectSelector 패턴 준용). 진입: 시트는 아래에서, 드롭다운은 종 아래로. -->
					<div
						class="motion-enter fixed left-0 bottom-0 w-full rounded-t-xl sm:absolute sm:left-auto sm:right-0 sm:bottom-auto sm:top-full sm:mt-2 sm:w-80 sm:rounded-xl border shadow-[var(--shadow-restraint)] sm:shadow-[var(--shadow-popover)] z-50 overflow-hidden [--motion-enter-offset:1rem] sm:[--motion-enter-offset:-0.375rem]"
						style="background: var(--color-surface-raised); border-color: var(--color-line);"
					>
						<p class="px-4 pt-3 pb-2 text-xs uppercase tracking-wide text-[var(--color-ink-3)]">{t('bell.title')}</p>
						<div class="mx-4 mb-3 min-w-0 rounded-md border border-line p-3 text-sm">
							<p class="font-medium text-ink-0">{usage('reminders')}</p>
							{#if usageBell.loading}<LoadingState variant="inline" class="mt-1" label={usage('loading')} />{/if}
							{#if usageBell.failed}<p class="mt-1 text-xs text-state-danger-text" role="alert">{usage('loadFailed')}</p>{/if}
							{#if usageBell.count !== null}
								<p class="mt-1 text-xs text-ink-1">{usage('bellCount', { count: usageBell.count })}</p>
								{#if usageBell.overdue > 0}<p class="mt-1 text-xs text-state-danger-text">{usage('bellOverdue', { count: usageBell.overdue })}</p>{/if}
							{/if}
							<button onclick={() => closeBellAndGo()} class="mt-2 min-h-11 text-left text-xs text-accent underline underline-offset-4">{usage('manage')}</button>
						</div>
						{#if bellItems === null}
							<div class="px-4 pb-3"><LoadingState variant="inline" label={t('bell.loading')} /></div>
						{:else if bellError}
							<p class="px-4 pb-3 text-xs text-[var(--color-state-danger)]">{t('bell.failed')}</p>
						{:else if bellItems.length === 0}
							<p class="px-4 pb-3 text-xs text-[var(--color-ink-3)]">{t('bell.empty')}</p>
						{:else}
							<ul class="max-h-80 overflow-y-auto">
								{#each bellItems as item (item.id)}
									<li>
										<button
											onclick={() => closeBellAndGo(item.id)}
											class="w-full text-left px-4 py-2.5 flex items-start gap-2.5 hover:bg-[var(--color-surface-sunken)] transition-colors"
										>
											<span class="mt-1.5 w-2 h-2 rounded-full flex-shrink-0" style="background: {bellDotColor(item.severity)};"></span>
											<span class="flex-1 min-w-0">
												<span class="block text-xs text-[var(--color-ink-0)] truncate {item.is_read ? '' : 'font-semibold'}">{item.title}</span>
												<span class="block text-xs text-[var(--color-ink-3)] mt-0.5 tabular-nums">{formatIsoDateTime(item.created_at)}</span>
											</span>
											{#if !item.is_read}
												<span class="mt-1 text-xs uppercase tracking-wide text-[var(--color-accent)] flex-shrink-0">{t('bell.unread')}</span>
											{/if}
										</button>
									</li>
								{/each}
							</ul>
						{/if}
						<div class="border-t" style="border-color: var(--color-line);">
							<button
								onclick={() => closeBellAndGo()}
								class="w-full px-4 py-2.5 text-xs text-center text-[var(--color-accent)] hover:bg-[var(--color-surface-sunken)] transition-colors"
							>{t('bell.viewAll')}</button>
						</div>
					</div>
				{/if}
			</div>

			<!-- 유저 아바타 -->
			<a
				href={mockupAdminActive ? '/admin' : '/dashboard/account'}
				class="flex size-11 shrink-0 items-center justify-center rounded-full focus-visible:outline-none focus-visible:shadow-[var(--focus-ring)] lg:size-8"
				title={$auth.domainName ? `${$auth.username ?? ''} @ ${$auth.domainName}` : $auth.username}
				aria-label={tAccount('profile.image.open')}
			><ProfileImage name={$auth.username ?? ''} label={tAccount('profile.image.alt')} /></a>

			<!-- 로그아웃 -->
			<button
				onclick={() => logout()}
				disabled={$logoutInProgress}
				aria-label={t('logout.action')}
				class="flex size-11 items-center justify-center rounded-md text-ink-2 transition-colors hover:bg-surface-sunken hover:text-state-danger focus-visible:outline-none focus-visible:shadow-[var(--focus-ring)] lg:size-8"
				title={t('logout.action')}
			>
				<svg class="size-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"/></svg>
			</button>
		</div>
	</header>
	{#if !mockup.active}
		<UploadDock />
	{/if}
	{#if !mockup.active || mockupAdminActive}
		<CmdPalette />
	{/if}
{/if}

{#if $isLoggedIn && !$logoutInProgress && $page.url.pathname !== '/logout' && $siteConfig.services.cloud_shell && !mockup.active}
	<CloudShellAuthorizeDialog />
	<CloudShellDock />
{/if}

{#if $isLoggedIn}
	<ConfirmDialog />
{/if}
{#if mockup.active && !isDocumentationRoute}
	<MockupBanner profile={mockup.profile} />
{/if}
{#if $isLoggedIn && !$logoutInProgress && $page.url.pathname !== '/logout' && !isDocumentationRoute}
	<TutorialController />
{/if}
<Toast />

<!-- Console layouts own the page remount boundary so their sidebars and VM wizard stay mounted. -->
<div class="min-h-[100dvh] bg-surface-canvas text-ink-1 {mockup.active ? 'mockup-active' : ''}">
	{#if $page.url.pathname === '/dashboard' || $page.url.pathname.startsWith('/dashboard/') || $page.url.pathname === '/admin' || $page.url.pathname.startsWith('/admin/') || $page.url.pathname.startsWith('/palimpsest/')}
		{@render children()}
	{:else}
		{#key getLocale()}
			{@render children()}
		{/key}
	{/if}
</div>

{#if authenticationUnavailable}
<div class="fixed inset-0 z-[calc(var(--z-command)+2)]">
<Modal open={authenticationUnavailable} dismissible={false} labelledBy="auth-recovery-title">
	<div class="w-[min(28rem,calc(100vw-2rem))]">
		<Card surface="modal" padding="lg">
			<div class="space-y-4">
				<h2 id="auth-recovery-title" class="text-lg font-semibold text-ink-0">{t('authRecovery.title')}</h2>
				<p role="alert" class="text-sm leading-relaxed text-ink-1">{t('authRecovery.body')}</p>
				<p class="text-xs text-ink-2">{t('authRecovery.hint')}</p>
				<div class="flex flex-wrap justify-end gap-3">
					<Button variant="secondary" disabled={$logoutInProgress} onclick={logout}>{t('logout.action')}</Button>
					<Button disabled={recoveryBusy || $logoutInProgress || recoveryWait > 0} onclick={retryAuthentication}>
						{#if recoveryBusy}<LoadingState variant="control" label={t('authRecovery.checking')} />{:else}{recoveryWait > 0 ? t('authRecovery.retryIn', { seconds: recoveryWait }) : t('authRecovery.retry')}{/if}
					</Button>
				</div>
			</div>
		</Card>
	</div>
</Modal>
</div>
{/if}

<style>
	.header-context {
		flex-shrink: 0;
	}

	.header-search {
		flex: 1 1 0%;
		max-width: 24rem;
		margin-inline: auto;
	}
</style>
