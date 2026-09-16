<script lang="ts">
  import { onMount } from 'svelte';
  import { siteConfig } from '$lib/config/site';
  import { resolvedTheme } from '$lib/stores/theme';

  let themeReady = $state(false);

  onMount(() => {
    themeReady = true;
  });

  const resolvedLoginLogoSrc = $derived(
    $resolvedTheme === 'dark'
      ? ($siteConfig.logo_light_path || $siteConfig.logo_path)
      : ($siteConfig.logo_dark_path || $siteConfig.logo_path)
  );

  const loginLogoSrc = $derived(themeReady ? resolvedLoginLogoSrc : '');
</script>

<div class="text-center mb-8">
  <div class="h-24 sm:h-32 md:h-40 lg:h-48 mb-4 flex items-center justify-center">
    {#if loginLogoSrc}
      <img src={loginLogoSrc} alt={$siteConfig.site_name} class="h-full w-auto mx-auto" />
    {/if}
  </div>
  <h1 class="text-4xl font-bold text-ink-0 mb-2">{$siteConfig.site_name}</h1>
  <p class="text-ink-2 text-sm">{$siteConfig.site_description}</p>
  <a class="login-home-link" href="/" aria-label="메인 홈페이지로 돌아가기">
    <span aria-hidden="true">←</span>
    <span>메인 홈페이지로 돌아가기</span>
  </a>
</div>

<style>
  .login-home-link {
    display: inline-flex;
    align-items: center;
    gap: 0.375rem;
    margin-top: 0.875rem;
    color: var(--color-ink-2);
    font-size: 0.8125rem;
    line-height: 1.25rem;
    text-decoration: none;
    transition: color 150ms ease;
  }

  .login-home-link:hover {
    color: var(--color-ink-0);
  }

  .login-home-link:focus-visible {
    outline: 2px solid var(--color-accent);
    outline-offset: 4px;
    border-radius: 0.25rem;
  }
</style>
