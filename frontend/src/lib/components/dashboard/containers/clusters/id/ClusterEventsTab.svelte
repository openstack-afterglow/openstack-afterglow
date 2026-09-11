<script lang="ts">
  import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
  import type { StackEvent } from '$lib/types/cluster';
  import { resourceStatusColor } from '$lib/types/cluster';

  let { events, loading, onRefresh }: { events: StackEvent[]; loading: boolean; onRefresh: () => void } = $props();
</script>

<div class="flex items-center justify-between mb-3">
  <div class="text-sm text-ink-2">{events.length}개 이벤트 (최신순)</div>
  <button onclick={onRefresh} class="text-xs text-ink-2 hover:text-ink-0 transition-colors">새로고침</button>
</div>
{#if loading}
  <LoadingSkeleton variant="table" rows={8} />
{:else if events.length === 0}
  <div class="text-ink-3 text-sm">스택 이벤트 정보를 불러올 수 없습니다</div>
{:else}
  <div class="overflow-x-auto">
    <table class="w-full text-sm">
      <thead>
        <tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
          <th class="text-left py-2 pr-4">이벤트 시각</th>
          <th class="text-left py-2 pr-4">리소스</th>
          <th class="text-left py-2 pr-4">상태</th>
          <th class="text-left py-2">사유</th>
        </tr>
      </thead>
      <tbody>
        {#each events as e}
          <tr class="border-b border-line/50 text-xs">
            <td class="py-2 pr-4 text-ink-2 font-mono whitespace-nowrap">{e.event_time?.slice(0, 19).replace('T', ' ') ?? '-'}</td>
            <td class="py-2 pr-4 text-ink-0">{e.resource_name}</td>
            <td class="py-2 pr-4">
              <span class="{resourceStatusColor(e.resource_status)} font-medium">{e.resource_status}</span>
            </td>
            <td class="py-2 text-ink-3">{e.resource_status_reason ?? '-'}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}
