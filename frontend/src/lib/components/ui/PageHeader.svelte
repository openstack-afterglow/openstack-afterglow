<script lang="ts">
  import type { Snippet } from 'svelte';

  interface Props {
    breadcrumb: string;
    title: string;
    subtitle?: string;
    actions?: Snippet;
    class?: string;
  }

  let { breadcrumb, title, subtitle, actions, class: className = '' }: Props = $props();
</script>

<div class="page-header {className}">
  <div>
    <div class="page-header-breadcrumb">
      <span class="md:hidden">{breadcrumb.includes(' / ') ? breadcrumb.split(' / ').at(-1) : breadcrumb}</span>
      <span class="hidden md:inline">{breadcrumb}</span>
    </div>
    <h1 class="page-header-title">{title}</h1>
    {#if subtitle}
      <p class="page-header-subtitle">{subtitle}</p>
    {/if}
  </div>
  {#if actions}
    <div class="page-header-actions">
      {@render actions()}
    </div>
  {/if}
</div>

<style>
  .page-header {
    display: flex;
    min-width: 0;
    flex-direction: column;
    align-items: stretch;
    gap: 0.75rem;
    margin-bottom: 1.5rem;
  }
  .page-header > :first-child {
    min-width: 0;
  }
  .page-header-breadcrumb {
    margin-bottom: 0.25rem;
    font-size: 0.75rem;
    letter-spacing: -0.01em;
    font-weight: 500;
    color: var(--color-ink-2);
  }
  .page-header-title {
    margin: 0;
    color: var(--color-ink-0);
    font-size: 1.25rem;
    font-weight: 600;
    line-height: 1.75rem;
    letter-spacing: -0.015em;
    text-wrap: balance;
  }
  .page-header-subtitle {
    max-width: 65ch;
    margin: 0.125rem 0 0;
    font-size: 0.875rem;
    color: var(--color-ink-2);
    text-wrap: pretty;
  }
  .page-header-actions {
    display: flex;
    width: 100%;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.5rem;
  }
  @media (min-width: 1024px) {
    .page-header {
      flex-direction: row;
      align-items: flex-start;
      justify-content: space-between;
      gap: 1rem;
    }
    .page-header-actions {
      width: auto;
      max-width: 60%;
      flex-shrink: 0;
      justify-content: flex-end;
      margin-left: 1rem;
    }
  }
</style>
