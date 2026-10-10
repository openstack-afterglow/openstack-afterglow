<script lang="ts">
	import { page } from '$app/stores';
	import { afterNavigate } from '$app/navigation';
	import { isRouteChange, playRouteEntrance } from '$lib/utils/motion';
	import Sidebar from '$lib/components/Sidebar.svelte';
	import VmCreatePanel from '$lib/components/VmCreatePanel.svelte';
	import { auth } from '$lib/stores/auth';
	import { projectList } from '$lib/stores/projectList';
	import { wizardOpen } from '$lib/stores/wizard';
	import { loadTutorialStatuses } from '$lib/tutorial/status';
	import { getLocale } from '$lib/i18n/runtime.svelte';
	let { children } = $props();
	// Terminal routes own live sockets and scrollback; language is display state, not their lifetime.
	const pageLocaleKey = $derived(
		$page.route.id === '/dashboard/containers/instances/[id]'
		|| $page.route.id === '/dashboard/drover'
		|| $page.route.id === '/dashboard/drover/[id]'
			? $page.route.id
			: getLocale(),
	);
	let mainEl = $state<HTMLElement | null>(null);

	afterNavigate((nav) => {
		if (isRouteChange(nav)) playRouteEntrance(mainEl);
	});

	// 로그인 사용자의 튜토리얼 이력을 조회해, 미체험 투어 버튼 강조 판정에 사용한다.
	// 하드 새로고침 시 auth 토큰 복원은 비동기이므로 onMount 일회성이 아니라 토큰이
	// 준비된 뒤 반응해 조회한다(loadTutorialStatuses 는 멱등 → 최초 1회만 실제 로드).
	// (status 모듈 import 로 'afterglow:tour-complete' 완료 리스너도 등록된다.)
	$effect(() => {
		if ($auth.token) {
			void loadTutorialStatuses();
			if ($auth.userId) projectList.prefetch($auth.token, $auth.userId);
		}
	});
</script>

<!-- One viewport-bounded workspace; main is the only content scroll owner. -->
<div class="flex h-[100dvh] overflow-hidden">
	<Sidebar />
	<main bind:this={mainEl} id="main-content" tabindex="-1" class="min-w-0 flex-1 overflow-y-auto pt-[var(--app-header-height)] focus:outline-none focus-visible:shadow-[var(--focus-ring)]">
		{#key pageLocaleKey}
			{@render children()}
		{/key}
	</main>
</div>

{#if $wizardOpen}
	<VmCreatePanel />
{/if}
