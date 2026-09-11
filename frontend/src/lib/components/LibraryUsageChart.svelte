<script lang="ts">
  interface TsPoint {
    ts: number;
    [key: string]: number | undefined;
  }

  interface Props {
    data: TsPoint[];
    title?: string;
    currentRange?: string;
    onRangeChange?: (range: string) => void;
  }

  let {
    data,
    title = '라이브러리 사용량',
    currentRange = '7d',
    onRangeChange
  }: Props = $props();

  const RANGES = ['1d', '2d', '7d', '30d'];
  const RANGE_LABELS: Record<string, string> = { '1d': '1일', '2d': '2일', '7d': '7일', '30d': '30일' };

  const PALETTE = [
    '#60a5fa', '#4ade80', '#f87171', '#fbbf24', '#c084fc',
    '#34d399', '#fb923c', '#38bdf8', '#a78bfa', '#f472b6',
  ];

  // 최신 스냅샷에서 사용 키 추출 (lib: / layer: 접두어 제거)
  const latestPoint = $derived(data.length > 0 ? data[data.length - 1] : null);

  const topKeys = $derived.by(() => {
    if (!latestPoint) return [] as { key: string; label: string; color: string }[];
    return Object.entries(latestPoint)
      .filter(([k]) => k !== 'ts' && k.includes(':'))
      .sort(([, a], [, b]) => (b ?? 0) - (a ?? 0))
      .slice(0, 8)
      .map(([k], i) => ({
        key: k,
        label: k.replace(/^(lib|layer):/, ''),
        color: PALETTE[i % PALETTE.length],
      }));
  });

  // 최신 사용량 합계
  const totalUsage = $derived(
    topKeys.reduce((sum, { key }) => sum + ((latestPoint?.[key] as number) ?? 0), 0)
  );
</script>

<div class="bg-surface-base border border-line rounded-xl p-5">
  <div class="flex items-center justify-between mb-4">
    <div class="flex items-center gap-3">
      <h3 class="text-sm font-semibold text-ink-2">{title}</h3>
      {#if totalUsage > 0}
        <span class="text-xl font-bold text-ink-0">{totalUsage}</span>
        <span class="text-xs text-ink-3">활성 VM</span>
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

  {#if data.length === 0 || topKeys.length === 0}
    <div class="flex items-center justify-center h-24 text-ink-3 text-sm">
      수집된 데이터가 없습니다 (라이브러리가 적재된 VM이 없거나 아직 스냅샷이 저장되지 않았습니다)
    </div>
  {:else}
    <!-- 수평 바 차트 (최신 스냅샷 기준) -->
    <div class="space-y-2">
      {#each topKeys as { key, label, color }}
        {@const val = (latestPoint?.[key] as number) ?? 0}
        {@const pct = totalUsage > 0 ? (val / totalUsage) * 100 : 0}
        <div class="flex items-center gap-3">
          <div class="w-28 text-xs text-ink-2 truncate text-right">{label}</div>
          <div class="flex-1 h-3 bg-surface-sunken rounded-full overflow-hidden">
            <div
              class="h-full rounded-full transition-all duration-500"
              style="width: {pct}%; background-color: {color};"
            ></div>
          </div>
          <div class="w-6 text-xs text-ink-2 text-right">{val}</div>
        </div>
      {/each}
    </div>
  {/if}
</div>
