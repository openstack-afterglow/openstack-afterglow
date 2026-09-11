<script lang="ts">
  import type { Snippet } from 'svelte';
  import StatusChip from './StatusChip.svelte';

  interface Props {
    title: string;
    subtitle?: string;
    status?: string | null;
    secondaryStatus?: string | null;
    meta?: Snippet;
    actions?: Snippet;
    size?: 'lg' | 'md' | 'sm';
    class?: string;
  }

  let {
    title,
    subtitle,
    status,
    secondaryStatus,
    meta,
    actions,
    size = 'md',
    class: className = ''
  }: Props = $props();

  const titleClass = $derived(size === 'lg' ? 'text-xl' : size === 'sm' ? 'text-sm' : 'text-lg');
</script>

<div class="flex items-start justify-between mb-6 gap-4 {className}">
  <div class="min-w-0 flex-1">
    <div class="flex items-center gap-2 flex-wrap">
      <h2 class="{titleClass} font-bold text-ink-0 truncate">{title}</h2>
      {#if status}<StatusChip {status} />{/if}
      {#if secondaryStatus}<StatusChip status={secondaryStatus} />{/if}
    </div>
    {#if subtitle}
      <div class="text-[13px] text-ink-2 mt-1 truncate font-mono">{subtitle}</div>
    {/if}
    {#if meta}
      <div class="mt-2">{@render meta()}</div>
    {/if}
  </div>
  {#if actions}
    <div class="flex items-center gap-2 flex-shrink-0 flex-wrap justify-end">
      {@render actions()}
    </div>
  {/if}
</div>
