<script lang="ts">
  import type { Snippet } from 'svelte';

  interface Props {
    value: number;
    max?: number;
    size?: number;
    stroke?: number;
    color?: string;
    track?: string;
    center?: Snippet;
    class?: string;
  }

  let {
    value,
    max = 100,
    size = 80,
    stroke = 8,
    color = 'var(--color-accent)',
    track = 'rgba(255,255,255,0.06)',
    center,
    class: className = '',
  }: Props = $props();

  const r = $derived((size - stroke) / 2);
  const pct = $derived(max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0);
  const cx = $derived(size / 2);
</script>

<div class="donut-wrap {className}" style="width:{size}px;height:{size}px">
  <svg width={size} height={size} viewBox="0 0 {size} {size}">
    <circle
      cx={cx}
      cy={cx}
      r={r}
      fill="none"
      stroke={track}
      stroke-width={stroke}
    />
    <circle
      class="donut-fill"
      pathLength="1"
      cx={cx}
      cy={cx}
      r={r}
      fill="none"
      stroke={color}
      stroke-width={stroke}
      stroke-linecap="round"
      stroke-dasharray="1"
      stroke-dashoffset={1 - pct / 100}
      transform="rotate(-180 {cx} {cx})"
    />
  </svg>
  {#if center}
    <div class="donut-center">
      {@render center()}
    </div>
  {/if}
</div>

<style>
  .donut-wrap {
    position: relative;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
  .donut-fill {
    animation: motion-draw var(--motion-duration-data) var(--motion-ease-emphasized) backwards;
    transition: stroke-dashoffset var(--motion-duration-data) var(--motion-ease-emphasized);
  }
  .donut-center {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    pointer-events: none;
  }
</style>
