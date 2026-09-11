<script lang="ts">
  interface DataPoint {
    ts: number;
    total?: number;
    active?: number;
    shutoff?: number;
    error?: number;
    shelved?: number;
    in_use?: number;
    available?: number;
    [key: string]: number | undefined;
  }

  interface Props {
    data: DataPoint[];
    title: string;
    mainKey?: string;      // 주요 지표 키 (기본: 'total')
    extraKeys?: string[];  // 추가로 표시할 키 목록
    onRangeChange?: (range: string) => void;
    currentRange?: string;
  }

  let { data, title, mainKey = 'total', extraKeys = [], onRangeChange, currentRange = '7d' }: Props = $props();

  const RANGES = ['1d', '2d', '7d', '30d'];
  const RANGE_LABELS: Record<string, string> = { '1d': '1일', '2d': '2일', '7d': '7일', '30d': '30일' };

  const EXTRA_COLORS: Record<string, string> = {
    active:    '#4ade80',
    shutoff:   '#9ca3af',
    error:     '#f87171',
    shelved:   '#c084fc',
    in_use:    '#60a5fa',
    available: '#34d399',
    other:     '#fbbf24',
  };

  const SVG_W = 600;
  const SVG_H = 140;
  const PAD_L = 40;
  const PAD_R = 16;
  const PAD_T = 12;
  const PAD_B = 28;

  function getVal(d: DataPoint, key: string): number {
    return d[key] ?? 0;
  }

  const points = $derived(data.length > 0 ? data : []);

  const allMainValues = $derived(points.map(d => getVal(d, mainKey)));
  const maxVal = $derived(Math.max(1, ...allMainValues, ...extraKeys.flatMap(k => points.map(d => getVal(d, k)))));
  const minTs = $derived(points.length > 0 ? points[0].ts : 0);
  const maxTs = $derived(points.length > 0 ? points[points.length - 1].ts : 1);
  const tsRange = $derived(Math.max(1, maxTs - minTs));

  function x(ts: number): number {
    return PAD_L + ((ts - minTs) / tsRange) * (SVG_W - PAD_L - PAD_R);
  }
  function y(val: number): number {
    return PAD_T + (1 - val / maxVal) * (SVG_H - PAD_T - PAD_B);
  }
  function polyline(key: string): string {
    return points.map(d => `${x(d.ts)},${y(getVal(d, key))}`).join(' ');
  }

  // 최신값 vs 이전값 비교 (증감)
  const latestVal = $derived(points.length > 0 ? getVal(points[points.length - 1], mainKey) : 0);
  const prevVal = $derived(points.length > 1 ? getVal(points[points.length - 2], mainKey) : latestVal);
  const delta = $derived(latestVal - prevVal);

  // X축 레이블 (최대 5개)
  const xLabels = $derived.by(() => {
    if (points.length === 0) return [] as { ts: number; label: string }[];
    const step = Math.max(1, Math.floor(points.length / 5));
    const result: { ts: number; label: string }[] = [];
    for (let i = 0; i < points.length; i += step) {
      const d = new Date(points[i].ts * 1000);
      result.push({ ts: points[i].ts, label: `${d.getMonth()+1}/${d.getDate()} ${String(d.getHours()).padStart(2,'0')}h` });
    }
    return result;
  });
</script>

<div class="bg-surface-base border border-line rounded-xl p-5">
  <div class="flex items-center justify-between mb-4">
    <div class="flex items-center gap-3">
      <h3 class="text-sm font-semibold text-ink-2">{title}</h3>
      {#if points.length > 0}
        <span class="text-xl font-bold text-ink-0">{latestVal}</span>
        {#if delta > 0}
          <span class="text-xs text-green-400 bg-green-900/30 px-1.5 py-0.5 rounded">+{delta}</span>
        {:else if delta < 0}
          <span class="text-xs text-red-400 bg-red-900/30 px-1.5 py-0.5 rounded">{delta}</span>
        {/if}
      {/if}
    </div>
    <div class="flex gap-1">
      {#each RANGES as r}
        <button
          onclick={() => onRangeChange?.(r)}
          class="text-xs px-2 py-0.5 rounded transition-colors {currentRange === r ? 'bg-action-warm text-ink-0' : 'text-ink-3 hover:text-ink-2'}"
        >{RANGE_LABELS[r]}</button>
      {/each}
    </div>
  </div>

  {#if points.length === 0}
    <div class="flex items-center justify-center h-24 text-ink-3 text-sm">
      수집된 데이터가 없습니다 (서버 시작 후 30초 뒤 첫 스냅샷이 저장됩니다)
    </div>
  {:else}
    <svg viewBox="0 0 {SVG_W} {SVG_H}" class="w-full" style="height: 140px;">
      <!-- 그리드 라인 -->
      {#each [0.25, 0.5, 0.75, 1] as frac}
        <line
          x1={PAD_L} y1={y(maxVal * frac)}
          x2={SVG_W - PAD_R} y2={y(maxVal * frac)}
          stroke="#374151" stroke-width="1"
        />
        <text x={PAD_L - 4} y={y(maxVal * frac) + 4} text-anchor="end" font-size="9" fill="#6b7280">
          {Math.round(maxVal * frac)}
        </text>
      {/each}

      <!-- 추가 라인들 -->
      {#each extraKeys as key}
        {#if EXTRA_COLORS[key]}
          <polyline
            points={polyline(key)}
            fill="none"
            stroke={EXTRA_COLORS[key]}
            stroke-width="1.5"
            stroke-dasharray="4 2"
            opacity="0.7"
          />
        {/if}
      {/each}

      <!-- 메인 영역 채우기 -->
      {#if points.length > 1}
        <polygon
          points="{x(points[0].ts)},{y(0)} {polyline(mainKey)} {x(points[points.length-1].ts)},{y(0)}"
          fill="#3b82f6"
          opacity="0.12"
        />
        <!-- 메인 라인 -->
        <polyline
          points={polyline(mainKey)}
          fill="none"
          stroke="#3b82f6"
          stroke-width="2"
          stroke-linejoin="round"
          stroke-linecap="round"
        />
      {/if}

      <!-- 데이터 포인트 -->
      {#each points as d}
        <circle cx={x(d.ts)} cy={y(getVal(d, mainKey))} r="2.5" fill="#3b82f6" />
      {/each}

      <!-- X축 레이블 -->
      {#each xLabels as lbl}
        <text x={x(lbl.ts)} y={SVG_H - 4} text-anchor="middle" font-size="8" fill="#6b7280">{lbl.label}</text>
      {/each}
    </svg>

    <!-- 범례 -->
    {#if extraKeys.length > 0}
      <div class="flex flex-wrap gap-3 mt-2">
        <div class="flex items-center gap-1">
          <div class="w-4 h-0.5 bg-action-warm"></div>
          <span class="text-xs text-ink-3">{mainKey}</span>
        </div>
        {#each extraKeys as key}
          {#if EXTRA_COLORS[key]}
            <div class="flex items-center gap-1">
              <div class="w-4 h-0.5" style="background:{EXTRA_COLORS[key]}; opacity:0.7; border-top: 1px dashed {EXTRA_COLORS[key]}"></div>
              <span class="text-xs text-ink-3">{key}</span>
            </div>
          {/if}
        {/each}
      </div>
    {/if}
  {/if}
</div>
