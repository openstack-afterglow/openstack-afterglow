<script lang="ts">
  import { page } from '$app/stores';
  import { t } from '$lib/i18n/ns/account';
  import { accountNavSection } from '$lib/config/nav';
  import Button from '$lib/components/ui/Button.svelte';
  import PageHeader from '$lib/components/ui/PageHeader.svelte';
  import PageShell from '$lib/components/ui/PageShell.svelte';
  import ProjectSelector from '$lib/components/ProjectSelector.svelte';

  let { children } = $props();
  const currentItem = $derived(
    accountNavSection.items.find(item => item.href === $page.url.pathname)
      ?? accountNavSection.items[0],
  );
</script>

<PageShell>
  <div class="mb-4 flex flex-wrap items-center gap-2">
    <Button href="/dashboard" variant="ghost" size="sm">
      <svg class="size-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" /></svg>
      {t('page.back')}
    </Button>
    <Button href="/dashboard/my-resources" variant="link" size="sm">
      {t('page.resources')}
      <svg class="size-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" /></svg>
    </Button>
  </div>

  <PageHeader breadcrumb={t('page.title')} title={currentItem.label}>
    {#snippet actions()}
      <div class="w-48 max-w-full"><ProjectSelector /></div>
    {/snippet}
  </PageHeader>
  {@render children()}
</PageShell>
