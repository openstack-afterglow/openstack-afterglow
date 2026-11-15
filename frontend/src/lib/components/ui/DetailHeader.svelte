<script lang="ts">
  import type { Snippet } from 'svelte';
  import StatusChip from './StatusChip.svelte';
  import type { StatusKind } from '$lib/config/statusColors';

  interface Props {
    title: string;
    subtitle?: string;
    status?: string | null;
    secondaryStatus?: string | null;
    statusKind?: StatusKind;
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
    statusKind = 'resource',
    meta,
    actions,
    size = 'md',
    class: className = ''
  }: Props = $props();

  const titleClass = $derived(size === 'lg' ? 'text-[length:var(--type-console-title)]' : size === 'sm' ? 'text-sm' : 'text-lg');
</script>

<div class="flex flex-wrap items-start justify-between mb-6 gap-4 {className}">
  <div class="min-w-0 flex-1 basis-48">
    <div class="flex items-center gap-2 flex-wrap">
      <h2 class="{titleClass} font-bold text-ink-0 truncate">{title}</h2>
      {#if status}<StatusChip {status} kind={statusKind} />{/if}
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
    <div class="flex min-w-0 max-w-full items-center gap-2 flex-wrap justify-end">
      {@render actions()}
    </div>
  {/if}
</div>
