<script lang="ts">
	import { afterNavigate, goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { isAdmin, auth, authReady, projectSwitching, isMockAuthActive } from '$lib/stores/auth';
	import AdminSidebar from '$lib/components/AdminSidebar.svelte';
	import VmCreatePanel from '$lib/components/VmCreatePanel.svelte';
	import { wizardOpen } from '$lib/stores/wizard';
	import { loadTutorialStatuses } from '$lib/tutorial/status';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import { t } from '$lib/i18n/ns/admin-ops';
	import { t as td } from '$lib/i18n/ns/domain-auth';
	import { getLocale } from '$lib/i18n/runtime.svelte';
	import { isRouteChange, playRouteEntrance } from '$lib/utils/motion';
	import AdminInventoryScope from '$lib/components/admin/domains/AdminInventoryScope.svelte';
	import { hasAdminInventoryScope } from '$lib/stores/adminInventoryScope';

	$effect(() => {
		if ($auth.token) void loadTutorialStatuses();
	});

	// The root owns /me and recovery. A restored flag never opens this layout,
	// while an already-ready native continuation keeps mounted work intact.
	const mockAdmin = $derived($page.data?.mockup?.active === true && isMockAuthActive());
	const allowed = $derived($isAdmin && (mockAdmin || ($authReady && !$projectSwitching)));
	const checking = $derived(!!$auth.token && !mockAdmin && (!$authReady || $projectSwitching));

	let { children } = $props();
	// The in-page k3s shell must not be destroyed when only its interface language changes.
	const pageLocaleKey = $derived($page.route.id === '/admin/drover' ? $page.route.id : getLocale());
	let mainEl = $state<HTMLElement | null>(null);

	afterNavigate((nav) => {
		if (isRouteChange(nav)) playRouteEntrance(mainEl);
	});
</script>

{#if $auth.token === null}
	<!-- 로딩 중: 빈 화면 -->
{:else if checking}
	<div class="flex min-h-screen items-center justify-center bg-surface-canvas">
		<ActivityIndicator label={td('adminGuard.checking')} />
	</div>
{:else if !allowed}
	<div class="flex flex-col items-center justify-center min-h-screen bg-surface-canvas text-ink-2">
		<div class="text-6xl font-bold text-ink-2 mb-4">404</div>
		<div class="text-xl font-semibold text-ink-2 mb-2">{t('layout.notFound')}</div>
		<div class="text-sm text-ink-2">{t('layout.noAccess')}</div>
		<Button variant="primary" size="sm" class="mt-4" onclick={() => goto('/dashboard')}>{t('layout.dashboard')}</Button>
	</div>
{:else}
	<div class="flex h-[100dvh] overflow-hidden">
		<AdminSidebar />
		<main bind:this={mainEl} id="main-content" tabindex="-1" class="min-w-0 flex-1 overflow-y-auto pt-[var(--app-header-height)] focus:outline-none focus-visible:shadow-[var(--focus-ring)]">
			{#key pageLocaleKey}
				{#if hasAdminInventoryScope($page.url.pathname)}
					<AdminInventoryScope historical={['/admin/instances', '/admin/volumes', '/admin/networks', '/admin/file-storage'].includes($page.url.pathname)} traffic={$page.url.pathname === '/admin/topology'}>
						{@render children()}
					</AdminInventoryScope>
				{:else}
					{@render children()}
				{/if}
			{/key}
		</main>
	</div>
{#if $wizardOpen}
	<VmCreatePanel adminMode={true} />
{/if}
{/if}
