<script lang="ts">
  import type { Snippet } from 'svelte';
  import AssetGlyph from './AssetGlyph.svelte';

  interface Props {
    icon?: string;
    headline: string;
    description?: string;
    cta?: Snippet;
    class?: string;
  }

  let { icon, headline, description, cta, class: className = '' }: Props = $props();
</script>

<div class="empty-state flex flex-col items-center justify-center py-16 px-4 text-center {className}">
  <div class="empty-art mb-4"><AssetGlyph variant="empty" /></div>
  {#if icon}
    <svg class="empty-icon mb-2" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d={icon}/>
    </svg>
  {/if}
  <div class="motion-enter text-[15px] font-semibold text-ink-0 mb-1" style="--motion-index: 1">{headline}</div>
  {#if description}
    <div class="motion-enter text-[13px] text-ink-2 max-w-xs" style="--motion-index: 2">{description}</div>
  {/if}
  {#if cta}
    <div class="motion-enter mt-4" style="--motion-index: 3">{@render cta()}</div>
  {/if}
</div>

<style>
  .empty-art { max-width: 100%; }
  .empty-icon { width: 1.25rem; height: 1.25rem; color: var(--color-ink-2); }
</style>
