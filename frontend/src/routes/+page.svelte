<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { siteConfig } from '$lib/config/site';
	import { resolveLandingLogoPath } from '$lib/config/brandAssets';
	import { resolvedTheme } from '$lib/stores/theme';
	import LandingPage from '$lib/components/landing/LandingPage.svelte';
	import { auth, isLoggedIn } from '$lib/stores/auth';

	let themeReady = $state(false);
	onMount(() => {
		themeReady = true;
	});
	const consoleHref = $derived($page.data.mockup?.active ? $page.data.mockup.homePath : ($isLoggedIn ? ($auth.projectId ? '/dashboard' : '/select-project') : '/login'));
	const landingLogoPath = $derived(resolveLandingLogoPath($siteConfig, themeReady ? $resolvedTheme : 'dark'));
</script>

<svelte:head>
	<title>{$siteConfig.site_name} | 연구실 클라우드 제공 콘솔</title>
	<meta
		name="description"
		content={`${$siteConfig.site_name}는 연구실과 교육 조직이 컴퓨팅 자원, Kubernetes, 공유 스토리지, AI/ML 라이브러리 레이어를 한 화면에서 제공하고 운영하도록 돕는 클라우드 포털입니다.`}
	/>
</svelte:head>

<main id="main-content" tabindex="-1">
<LandingPage
	siteName={$siteConfig.site_name}
	logoPath={landingLogoPath}
	{consoleHref}
/>
</main>
