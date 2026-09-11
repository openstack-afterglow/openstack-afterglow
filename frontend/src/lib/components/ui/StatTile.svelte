<script lang="ts">
  import type { Snippet } from 'svelte';

  type Accent = 'blue' | 'cyan' | 'violet' | 'emerald' | 'amber' | 'teal' | 'rose' | 'indigo' | 'admin-tone';

  interface Props {
    label: string;
    value: string | number;
    unit?: string;
    delta?: string;
    icon?: Snippet;
    accent?: Accent;
    suffix?: string;
    iconBgClass?: string;
    progress?: { value: number; max: number };
    footer?: Snippet;
    children?: Snippet;
    class?: string;
    flat?: boolean;
  }

  let {
    label,
    value,
    unit,
    suffix,
    delta,
    icon,
    accent = 'blue',
    iconBgClass,
    progress,
    footer,
    flat = false,
    class: className = '',
  }: Props = $props();

  const displayUnit = $derived(unit ?? suffix);

  const TONE_MAP: Record<Accent, string> = {
    blue: 'icon-accent',
    cyan: 'icon-info',
    violet: 'icon-accent2',
    emerald: 'icon-success',
    amber: 'icon-warning',
    teal: 'icon-info',
    rose: 'icon-danger',
    indigo: 'icon-accent2',
    'admin-tone': 'icon-admin-tone',
  };

  const chipClass = $derived(iconBgClass ?? TONE_MAP[accent] ?? TONE_MAP.blue);
  const TILE_TONE_MAP: Record<Accent, string> = {
    blue: 'tile-accent',
    cyan: 'tile-info',
    violet: 'tile-accent2',
    emerald: 'tile-success',
    amber: 'tile-warning',
    teal: 'tile-info',
    rose: 'tile-danger',
    indigo: 'tile-accent2',
    'admin-tone': 'tile-admin-tone',
  };

  const tileToneClass = $derived(TILE_TONE_MAP[accent] ?? TILE_TONE_MAP.blue);


  const pct = $derived(
    progress && progress.max > 0
      ? Math.min(100, Math.round((progress.value / progress.max) * 100))
      : 0
  );
  const progressTone = $derived(
    pct > 80 ? 'progress-danger' : pct > 60 ? 'progress-warning' : 'progress-accent'
  );
</script>

<div class="stat-tile {flat ? 'stat-tile-flat' : ''} {tileToneClass} {className}">
  {#if icon}
    <div class="icon-chip {chipClass}">
      {@render icon()}
    </div>
  {/if}
  <div class="stat-body">
    <div class="stat-label">{label}</div>
    <div class="stat-value-row">
      <div class="stat-value">{value}</div>
      {#if displayUnit}<div class="stat-unit">{displayUnit}</div>{/if}
      {#if delta}<div class="stat-delta">{delta}</div>{/if}
    </div>
    {#if progress && progress.max > 0}
      <div class="progress-track">
        <div class="progress-bar {progressTone}" style="width:{pct}%"></div>
      </div>
    {:else if footer}
      <div class="stat-footer">
        {@render footer()}
      </div>
    {/if}
  </div>
</div>

<style>
  .stat-tile {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    border: 1px solid var(--color-line);
    border-radius: 0.5rem;
    background: var(--color-surface-base);
    padding: 1rem;
    transition: border-color var(--motion-duration-fast) var(--motion-ease-standard), background var(--motion-duration-fast) var(--motion-ease-standard);
  }
  :global(a:hover) > .stat-tile,
  :global(a:focus-visible) > .stat-tile {
    border-color: var(--stat-tile-ring);
    background: var(--color-surface-selected);
  }
  .stat-tile-flat {
    border: 0;
    border-radius: 0;
    background: var(--color-surface-base);
  }
  :global(a:hover) > .stat-tile-flat,
  :global(a:focus-visible) > .stat-tile-flat {
    border-color: transparent;
    background: var(--color-surface-selected);
  }
  .tile-accent {
    --stat-tile-tone: var(--color-accent);
    --stat-tile-ring: var(--accent-ring);
  }
  .tile-accent2 {
    --stat-tile-tone: var(--color-accent-2);
    --stat-tile-ring: color-mix(in oklab, var(--color-accent-2) 30%, transparent);
  }
  .tile-success {
    --stat-tile-tone: var(--color-state-success);
    --stat-tile-ring: color-mix(in oklab, var(--color-state-success) 30%, transparent);
  }
  .tile-warning {
    --stat-tile-tone: var(--color-state-warning);
    --stat-tile-ring: color-mix(in oklab, var(--color-state-warning) 30%, transparent);
  }
  .tile-danger {
    --stat-tile-tone: var(--color-state-danger);
    --stat-tile-ring: color-mix(in oklab, var(--color-state-danger) 30%, transparent);
  }
  .tile-info {
    --stat-tile-tone: var(--color-state-info);
    --stat-tile-ring: color-mix(in oklab, var(--color-state-info) 30%, transparent);
  }
  .tile-admin-tone {
    --stat-tile-tone: var(--admin-tone);
    --stat-tile-ring: var(--admin-tone-ring);
  }
  .stat-body {
    flex: 1 1 0;
    min-width: 0;
  }
  .stat-label {
    font-size: 0.75rem;
    letter-spacing: -0.01em;
    font-weight: 500;
    color: var(--color-ink-2);
  }
  .stat-value-row {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    margin-top: 0.125rem;
    flex-wrap: wrap;
  }
  .stat-value {
    font-size: 1.75rem;
    font-weight: 700;
    line-height: 1;
    color: var(--color-ink-0);
  }
  .stat-unit {
    font-size: 0.75rem;
    color: var(--color-ink-2);
  }
  .stat-delta {
    margin-left: auto;
    font-size: 0.6875rem;
    font-weight: 500;
    color: var(--color-state-success);
  }
  .stat-footer { margin-top: 0.25rem; }
  .progress-track {
    margin-top: 0.5rem;
    width: 100%;
    height: 0.25rem;
    overflow: hidden;
    border-radius: 999px;
    background: var(--color-surface-sunken);
  }
  .progress-bar {
    height: 0.25rem;
    border-radius: 999px;
    transition: width var(--motion-duration-base) var(--motion-ease-standard);
  }
  .icon-chip {
    width: 2.25rem;
    height: 2.25rem;
    border-radius: 0.375rem;
    border: 1px solid transparent;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }
  .stat-tile-flat .icon-chip {
    width: 2rem;
    height: 2rem;
    border: 0;
    background: transparent;
    box-shadow: none;
  }
  .icon-accent {
    background: var(--accent-soft);
    border-color: var(--accent-ring);
    color: var(--color-accent);
  }
  .icon-accent2 {
    background: color-mix(in oklab, var(--color-accent-2) 14%, transparent);
    border-color: color-mix(in oklab, var(--color-accent-2) 30%, transparent);
    color: var(--color-accent-2);
  }
  .icon-success {
    background: color-mix(in oklab, var(--color-state-success) 14%, transparent);
    border-color: color-mix(in oklab, var(--color-state-success) 30%, transparent);
    color: var(--color-state-success);
  }
  .icon-warning {
    background: color-mix(in oklab, var(--color-state-warning) 14%, transparent);
    border-color: color-mix(in oklab, var(--color-state-warning) 30%, transparent);
    color: var(--color-state-warning);
  }
  .icon-danger {
    background: color-mix(in oklab, var(--color-state-danger) 14%, transparent);
    border-color: color-mix(in oklab, var(--color-state-danger) 30%, transparent);
    color: var(--color-state-danger);
  }
  .icon-info {
    background: color-mix(in oklab, var(--color-state-info) 14%, transparent);
    border-color: color-mix(in oklab, var(--color-state-info) 30%, transparent);
    color: var(--color-state-info);
  }
  .icon-admin-tone {
    background: var(--admin-tone-soft);
    border-color: var(--admin-tone-ring);
    color: var(--admin-tone);
  }
  .progress-accent { background: var(--color-accent); }
  .progress-warning { background: var(--color-state-warning); }
  .progress-danger { background: var(--color-state-danger); }
</style>
