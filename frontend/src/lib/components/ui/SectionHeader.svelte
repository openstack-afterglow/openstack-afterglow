<script lang="ts">
  import type { Snippet } from 'svelte';

  interface Props {
    title: string;
    meta?: string;
    right?: Snippet;
    class?: string;
  }

  let { title, meta, right, class: className = '' }: Props = $props();
</script>

<div class="section-header {className}">
  <div class="section-header-copy">
    <span class="section-header-title">{title}</span>
    {#if meta}
      <span class="section-header-meta">{meta}</span>
    {/if}
  </div>
  {#if right}
    <div class="section-header-right">
      {@render right()}
    </div>
  {/if}
</div>

<style>
  .section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
  }
  .section-header-copy {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    min-width: 0;
  }
  .section-header-title {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 0.6875rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-weight: 500;
    color: var(--color-ink-2);
  }
  .section-header-meta {
    font-size: 0.6875rem;
    color: var(--color-ink-2);
  }
  .section-header-right { flex-shrink: 0; }
</style>
