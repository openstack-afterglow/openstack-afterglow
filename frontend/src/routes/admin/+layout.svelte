<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { isAdmin, auth } from '$lib/stores/auth';
	import { api } from '$lib/api/client';
	import AdminSidebar from '$lib/components/AdminSidebar.svelte';
	import VmCreatePanel from '$lib/components/VmCreatePanel.svelte';
	import { wizardOpen } from '$lib/stores/wizard';
	import { loadTutorialStatuses } from '$lib/tutorial/status';
	import Button from '$lib/components/ui/Button.svelte';

	$effect(() => {
		if ($auth.token) void loadTutorialStatuses();
	});

	// mount 시 /me를 강제 호출해 stale 캐시 우회 — 60s 내 admin 박탈을 즉시 반영
	onMount(async () => {
		if (!$auth.token) return;
		try {
			const me = await api.get<{ is_system_admin: boolean; roles: string[] }>(
				'/api/v1/auth/me',
				$auth.token,
				$auth.projectId ?? undefined,
			);
			auth.update((s) => ({ ...s, isSystemAdmin: me.is_system_admin === true, roles: me.roles ?? s.roles }));
		} catch {
			// 실패 시 기존 상태 유지 — $effect의 isAdmin 감시가 처리
		}
	});

	let { children } = $props();
</script>

{#if $auth.token === null}
	<!-- 로딩 중: 빈 화면 -->
{:else if !$isAdmin}
	<div class="flex flex-col items-center justify-center min-h-screen bg-surface-canvas text-ink-2">
		<div class="text-6xl font-bold text-ink-2 mb-4">404</div>
		<div class="text-xl font-semibold text-ink-2 mb-2">페이지를 찾을 수 없습니다</div>
		<div class="text-sm text-ink-2">접근 권한이 없거나 존재하지 않는 페이지입니다.</div>
		<Button variant="primary" size="sm" class="mt-4" onclick={() => goto('/dashboard')}>대시보드로 이동</Button>
	</div>
{:else}
	<div class="flex h-[100dvh] overflow-hidden">
		<AdminSidebar />
		<main id="main-content" tabindex="-1" class="min-w-0 flex-1 overflow-y-auto pt-[var(--app-header-height)] focus:outline-none focus-visible:shadow-[var(--focus-ring)]">
			{@render children()}
		</main>
	</div>
{#if $wizardOpen}
	<VmCreatePanel adminMode={true} />
{/if}
{/if}
