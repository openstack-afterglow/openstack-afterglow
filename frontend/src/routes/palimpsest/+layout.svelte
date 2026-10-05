<script lang="ts">
  import Sidebar from '$lib/components/Sidebar.svelte';
  import VmCreatePanel from '$lib/components/VmCreatePanel.svelte';
  import { auth } from '$lib/stores/auth';
  import { projectList } from '$lib/stores/projectList';
  import { wizardOpen } from '$lib/stores/wizard';
  import { getLocale } from '$lib/i18n/runtime.svelte';
  let { children } = $props();
  $effect(() => {
    if ($auth.token && $auth.userId) projectList.prefetch($auth.token, $auth.userId);
  });
</script>

<div class="flex h-[100dvh] overflow-hidden">
  <Sidebar />
  <main id="main-content" tabindex="-1" class="min-w-0 flex-1 overflow-y-auto pt-[var(--app-header-height)] focus:outline-none focus-visible:shadow-[var(--focus-ring)]">
    {#key getLocale()}
      {@render children()}
    {/key}
  </main>
</div>
{#if $wizardOpen}<VmCreatePanel />{/if}
