<script lang="ts">
  import { Chart, Arc, Layer } from 'layerchart';

  interface Props {
    label: string;
    used: number;
    limit: number;
    unit?: string;
    size?: 'sm' | 'lg';
  }

  let { label, used, limit, unit = '', size = 'sm' }: Props = $props();

  const pct = $derived(limit > 0 ? Math.min(100, Math.round(used / limit * 100)) : 0);

  // 기존 accent/warning/danger 디자인 토큰 색상 유지
  const fillColor = $derived(
    pct >= 100 ? '#ef4444'
    : pct > 80  ? '#f59e0b'
    : '#8893d4'
  );
  const textColor = $derived(
    pct >= 100 ? '#ef4444'
    : pct > 80  ? '#f59e0b'
    : '#8893d4'
  );

  const dim = $derived(size === 'lg' ? 112 : 72);
  const strokeW = $derived(size === 'lg' ? 10 : 8);
  // innerRadius < 1 → outerRadius의 비율로 해석
  const innerR = $derived(1 - (strokeW * 2) / dim);

  function fmt(v: number): string {
    if (v >= 1024 && unit === 'MB') return `${Math.round(v / 1024)}GB`;
    if (v >= 1024 && unit === 'GB') return `${Math.round(v / 1024)}TB`;
    return `${v}${unit}`;
  }
</script>

<div class="flex flex-col items-center gap-1">
  <div class="relative" style:width="{dim}px" style:height="{dim}px">
    <Chart data={[]} width={dim} height={dim} padding={0}>
      <Layer type="svg">
        <!-- 트랙 (배경 링) -->
        <Arc
          value={100}
          domain={[0, 100]}
          innerRadius={innerR}
          fill="#374151"
        />
        <!-- 사용량 링 -->
        {#if pct > 0}
          <Arc
            value={pct}
            domain={[0, 100]}
            innerRadius={innerR}
            fill={fillColor}
          />
        {/if}
      </Layer>
    </Chart>
    <!-- 중앙 퍼센트 텍스트 (절대 위치) -->
    <div class="absolute inset-0 flex items-center justify-center">
      <span
        class="{size === 'lg' ? 'text-base' : 'text-xs'} font-bold"
        style:color={textColor}
      >
        {limit > 0 ? `${pct}%` : '-'}
      </span>
    </div>
  </div>

  <div class="text-center">
    <div class="{size === 'lg' ? 'text-sm' : 'text-xs'} text-ink-2 font-medium leading-tight">
      {label}
    </div>
    <div class="{size === 'lg' ? 'text-sm' : 'text-xs'} text-ink-3 leading-tight">
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
