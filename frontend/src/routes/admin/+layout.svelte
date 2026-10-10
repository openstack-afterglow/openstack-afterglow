<script lang="ts">
	import { onMount } from 'svelte';
	import { afterNavigate, goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { isAdmin, auth } from '$lib/stores/auth';
	import { api } from '$lib/api/client';
	import AdminSidebar from '$lib/components/AdminSidebar.svelte';
	import VmCreatePanel from '$lib/components/VmCreatePanel.svelte';
	import { wizardOpen } from '$lib/stores/wizard';
	import { loadTutorialStatuses } from '$lib/tutorial/status';
	import Button from '$lib/components/ui/Button.svelte';
	import { t } from '$lib/i18n/ns/admin-ops';
	import { getLocale } from '$lib/i18n/runtime.svelte';
	import { isRouteChange, playRouteEntrance } from '$lib/utils/motion';

	$effect(() => {
		if ($auth.token) void loadTutorialStatuses();
	});

	// mount 시 /me를 강제 호출해 stale 캐시 우회 — 60s 내 admin 박탈을 즉시 반영
	onMount(async () => {
		const { token, projectId, userId } = $auth;
		if (!token) return;
		try {
			const me = await api.get<{ is_system_admin: boolean; roles: string[]; can_write: boolean }>(
				'/api/v1/auth/me', token, projectId ?? undefined,
			);
			if ($auth.token !== token || $auth.projectId !== projectId || $auth.userId !== userId) return;
			auth.update((s) => ({ ...s, isSystemAdmin: me.is_system_admin === true, roles: me.roles ?? s.roles, canWrite: me.can_write }));
		} catch {
			// 실패 시 기존 상태 유지 — $effect의 isAdmin 감시가 처리
		}
	});

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
{:else if !$isAdmin}
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
				{@render children()}
			{/key}
		</main>
	</div>
{#if $wizardOpen}
	<VmCreatePanel adminMode={true} />
{/if}
{/if}
