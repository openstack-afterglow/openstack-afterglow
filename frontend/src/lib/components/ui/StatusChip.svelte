<script module lang="ts">
  import type { SettledSignal } from '$lib/design/characterFormats.js';
  // Only success and failure are implied by tone. Warning/neutral/info cover many unrelated states
  // (observed, unknown native codes, stopped, attachable…), so they get the neutral `[ · ]` mark
  // unless the status map declares an explicit outcome such as canceled.
  const toneSignal: Partial<Record<'success' | 'warning' | 'danger' | 'info' | 'neutral', SettledSignal>> = {
    success: 'success',
    danger: 'failed',
  };
</script>

<script lang="ts">
  import { getStatusStyle, getStatusLabel, type StatusKind } from '$lib/config/statusColors';
  import { settledSignal } from '$lib/design/characterFormats.js';
  import CharacterSpinner from './CharacterSpinner.svelte';

  interface Props {
    status: string | null | undefined;
    class?: string;
    kind?: StatusKind;
    label?: string;
  }

  let { status, label, kind = 'resource', class: className = '' }: Props = $props();

  const s = $derived(getStatusStyle(status, kind));
  const mark = $derived(s.signal ?? toneSignal[s.tone] ?? 'info');
</script>

<span class="chip chip-{s.tone} {className}" title={status || undefined}>
  {#if s.pulse}
    <CharacterSpinner class="glyph" />
  {:else}
    <span class="glyph" data-signal={mark} data-art={settledSignal(mark)} aria-hidden="true"></span>
  {/if}
  <span class="label">{label ?? getStatusLabel(status, kind)}</span>
</span>

<style>
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 2px 10px;
    border-radius: 999px;
    font-size: var(--type-support);
    font-weight: 500;
    border: 1px solid transparent;
    line-height: 1.6;
    max-width: 100%;
  }

  .label {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  /* Decorative glyph is generated content, so the chip's text stays the status label. */
  .chip :global(.glyph) { flex-shrink: 0; font-family: var(--font-mono); font-size: 0.85em; white-space: pre; }
  .chip :global(.glyph)::before { content: attr(data-art); }

  .chip-success {
    background: color-mix(in oklab, var(--color-state-success) 14%, transparent);
    color: var(--color-state-success-text);
    border-color: color-mix(in oklab, var(--color-state-success) 30%, transparent);
  }
  .chip-warning {
    background: color-mix(in oklab, var(--color-state-warning) 14%, transparent);
    color: var(--color-state-warning-text);
    border-color: color-mix(in oklab, var(--color-state-warning) 30%, transparent);
  }
  .chip-danger {
    background: color-mix(in oklab, var(--color-state-danger) 14%, transparent);
    color: var(--color-state-danger-text);
    border-color: color-mix(in oklab, var(--color-state-danger) 30%, transparent);
  }
  .chip-info {
    background: color-mix(in oklab, var(--color-state-info) 14%, transparent);
    color: var(--color-state-info-text);
    border-color: color-mix(in oklab, var(--color-state-info) 30%, transparent);
  }
  .chip-neutral {
    background: color-mix(in oklab, var(--color-state-neutral) 14%, transparent);
    color: var(--color-state-neutral-text);
    border-color: color-mix(in oklab, var(--color-state-neutral) 30%, transparent);
  }

</style>
