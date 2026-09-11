<script lang="ts">
  import { Chart, Area, Spline, Axis, Layer, Highlight, Tooltip } from 'layerchart';

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
    mainKey?: string;
    extraKeys?: string[];
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

  const points = $derived(data.length > 0 ? data : []);

  const latestVal = $derived(points.length > 0 ? (points[points.length - 1][mainKey] ?? 0) : 0);
  const prevVal = $derived(points.length > 1 ? (points[points.length - 2][mainKey] ?? latestVal) : latestVal);
  const delta = $derived(latestVal - prevVal);

  const maxVal = $derived(
    Math.max(1,
      ...points.map(d => d[mainKey] ?? 0),
      ...extraKeys.flatMap(k => points.map(d => d[k] ?? 0))
    )
  );

  const xGet = (d: DataPoint) => new Date(d.ts * 1000);
  const yGet = (d: DataPoint) => d[mainKey] ?? 0;

  function fmtDate(ts: number): string {
    const d = new Date(ts * 1000);
    return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:00`;
  }
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
    <div class="h-[140px]">
      <Chart
        data={points}
        x={xGet}
        y={yGet}
        yDomain={[0, maxVal]}
        padding={{ left: 40, bottom: 28, top: 12, right: 16 }}
      >
        <Layer type="svg">
          <Axis
            placement="left"
            ticks={4}
            format={(v: number) => String(Math.round(v))}
            labelProps={{ class: 'text-[9px] fill-gray-500' }}
            rule={false}
          />
          <Axis
            placement="bottom"
            ticks={5}
            format={(d: Date) => `${d.getMonth() + 1}/${d.getDate()}`}
            labelProps={{ class: 'text-[8px] fill-gray-500' }}
            rule={false}
          />

          <!-- 메인 시리즈: 채우기 영역 + 라인 -->
          <Area fill="rgba(59, 130, 246, 0.12)" stroke="none" />
          <Spline stroke="#3b82f6" strokeWidth={2} />

          <!-- 추가 시리즈: 점선 라인 -->
          {#each extraKeys as key}
            {#if EXTRA_COLORS[key]}
              <Spline
                y={(d: DataPoint) => d[key] ?? 0}
                stroke={EXTRA_COLORS[key]}
                strokeWidth={1.5}
                stroke-dasharray="4 2"
                opacity={0.7}
              />
            {/if}
          {/each}

          <Highlight
            lines={{ class: 'stroke-gray-600', strokeWidth: 1 }}
            points={{ class: 'fill-blue-500', r: 3 }}
          />
        </Layer>

        <!-- HTML 툴팁 오버레이 -->
        <Tooltip.Root>
          {#snippet children({ data: d })}
            <div class="bg-surface-sunken border border-line-2 rounded-lg text-xs shadow-[var(--shadow-restraint)] px-2.5 py-2 min-w-[110px]">
              <div class="text-ink-2 mb-1.5 font-medium">{fmtDate(d.ts)}</div>
              <div class="flex justify-between gap-4">
                <span class="text-action-warm">{mainKey}</span>
                <span class="text-ink-0 font-bold">{d[mainKey] ?? 0}</span>
              </div>
              {#each extraKeys as key}
                {#if EXTRA_COLORS[key]}
                  <div class="flex justify-between gap-4 mt-0.5">
                    <span style="color: {EXTRA_COLORS[key]}">{key}</span>
                    <span class="text-ink-0">{d[key] ?? 0}</span>
                  </div>
                {/if}
              {/each}
            </div>
          {/snippet}
        </Tooltip.Root>
      </Chart>
    </div>

    {#if extraKeys.length > 0}
      <div class="flex flex-wrap gap-3 mt-2">
        <div class="flex items-center gap-1">
          <div class="w-4 h-0.5 bg-action-warm"></div>
          <span class="text-xs text-ink-3">{mainKey}</span>
        </div>
        {#each extraKeys as key}
          {#if EXTRA_COLORS[key]}
            <div class="flex items-center gap-1">
              <div class="w-4 h-0.5 opacity-70" style="background: {EXTRA_COLORS[key]}"></div>
              <span class="text-xs text-ink-3">{key}</span>
            </div>
          {/if}
        {/each}
      </div>
    {/if}
  {/if}
</div>
