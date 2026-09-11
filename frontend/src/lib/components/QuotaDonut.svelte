<script lang="ts">
  interface Props {
    label: string;
    used: number;
    limit: number;
    unit?: string;
    size?: 'sm' | 'lg';
  }

  let { label, used, limit, unit = '', size = 'sm' }: Props = $props();

  const r = $derived(size === 'lg' ? 44 : 28);
  const circumference = $derived(2 * Math.PI * r);

  const pct = $derived(limit > 0 ? Math.min(100, Math.round(used / limit * 100)) : 0);
  const dashOffset = $derived(circumference - (pct / 100) * circumference);
  const gradientId = $derived(
    pct >= 100 ? 'donut-grad-danger'
    : pct > 80 ? 'donut-grad-warning'
    : 'donut-grad-accent'
  );
  const textColor = 'var(--color-ink-0)';

  function fmt(v: number): string {
    if (v >= 1024 && unit === 'MB') return `${Math.round(v / 1024)}GB`;
    if (v >= 1024 && unit === 'GB') return `${Math.round(v / 1024)}TB`;
    return `${v}${unit}`;
  }
</script>

<div class="flex flex-col items-center gap-1">
  <div class="relative {size === 'lg' ? 'w-28 h-28' : 'w-16 h-16'}">
    <svg viewBox="0 0 {size === 'lg' ? '112 112' : '72 72'}" class="w-full h-full -rotate-90">
      <defs>
        <linearGradient id="donut-grad-accent" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%"   stop-color="#8893d4"/>
          <stop offset="35%"  stop-color="#b08cd6"/>
          <stop offset="75%"  stop-color="#f4976c"/>
          <stop offset="100%" stop-color="#f472b6"/>
        </linearGradient>
        <linearGradient id="donut-grad-warning" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%"   stop-color="#f4976c"/>
          <stop offset="50%"  stop-color="#f59e0b"/>
          <stop offset="100%" stop-color="#f472b6"/>
        </linearGradient>
        <linearGradient id="donut-grad-danger" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%"   stop-color="#ef4444"/>
          <stop offset="50%"  stop-color="#dc2626"/>
          <stop offset="100%" stop-color="#be185d"/>
        </linearGradient>
      </defs>
      <!-- Background track -->
      <circle
        cx={size === 'lg' ? 56 : 36} cy={size === 'lg' ? 56 : 36} r={r}
        fill="none"
        stroke="var(--color-line-2)"
        stroke-width={size === 'lg' ? 10 : 8}
      />
      <!-- Usage arc -->
      <circle
        cx={size === 'lg' ? 56 : 36} cy={size === 'lg' ? 56 : 36} r={r}
        fill="none"
        stroke="url(#{gradientId})"
        stroke-width={size === 'lg' ? 10 : 8}
        stroke-linecap="round"
        stroke-dasharray={circumference}
        stroke-dashoffset={dashOffset}
        class="transition-all duration-700"
      />
    </svg>
    <div class="absolute inset-0 flex items-center justify-center">
      <span class="{size === 'lg' ? 'text-base' : 'text-xs'} font-bold" style="color: {textColor}">{limit > 0 ? `${pct}%` : '-'}</span>
    </div>
  </div>
  <div class="text-center">
    <div class="{size === 'lg' ? 'text-sm' : 'text-xs'} text-ink-2 font-medium leading-tight">{label}</div>
    <div class="{size === 'lg' ? 'text-sm' : 'text-xs'} text-ink-2 leading-tight">
      {#if limit > 0}
        {fmt(used)} / {fmt(limit)}
      {:else if limit === -1}
        {fmt(used)} / 무제한
      {:else}
        {fmt(used)}
      {/if}
    </div>
  </div>
</div>
