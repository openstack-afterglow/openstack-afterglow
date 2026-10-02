<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { siteConfig } from '$lib/config/site';
	import { resolveLandingLogoPath } from '$lib/config/brandAssets';
	import { resolvedTheme } from '$lib/stores/theme';
	import LandingPage from '$lib/components/landing/LandingPage.svelte';
	import { auth, isLoggedIn } from '$lib/stores/auth';
	import { t } from '$lib/i18n/ns/public-entry';

	let themeReady = $state(false);
	onMount(() => {
		themeReady = true;
	});
	const consoleHref = $derived($page.data.mockup?.active ? $page.data.mockup.homePath : ($isLoggedIn ? ($auth.projectId ? '/dashboard' : '/select-project') : '/login'));
	const landingLogoPath = $derived(resolveLandingLogoPath($siteConfig, themeReady ? $resolvedTheme : 'dark'));
</script>

<svelte:head>
	<title>{t('landingMeta.title', { siteName: $siteConfig.site_name })}</title>
	<meta
		name="description"
		content={t('landingMeta.description', { siteName: $siteConfig.site_name })}
	/>
</svelte:head>

<main id="main-content" tabindex="-1">
<LandingPage
	siteName={$siteConfig.site_name}
	logoPath={landingLogoPath}
	{consoleHref}
/>
</main>
