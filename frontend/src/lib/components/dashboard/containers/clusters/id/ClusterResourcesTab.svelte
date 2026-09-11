<script lang="ts">
  import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
  import type { StackResource } from '$lib/types/cluster';
  import { resourceStatusColor } from '$lib/types/cluster';

  let { resources, loading, onRefresh }: { resources: StackResource[]; loading: boolean; onRefresh: () => void } = $props();
</script>

<div class="flex items-center justify-between mb-3">
  <div class="text-sm text-ink-2">{resources.length}개 리소스</div>
  <button onclick={onRefresh} class="text-xs text-ink-2 hover:text-ink-0 transition-colors">새로고침</button>
</div>
{#if loading}
  <LoadingSkeleton variant="table" rows={5} />
{:else if resources.length === 0}
  <div class="text-ink-3 text-sm">스택 리소스 정보를 불러올 수 없습니다</div>
{:else}
  <div class="overflow-x-auto">
    <table class="w-full text-sm">
      <thead>
        <tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
          <th class="text-left py-2 pr-4">리소스 이름</th>
          <th class="text-left py-2 pr-4">타입</th>
          <th class="text-left py-2 pr-4">Physical ID</th>
          <th class="text-left py-2 pr-4">상태</th>
          <th class="text-left py-2">생성일</th>
        </tr>
      </thead>
      <tbody>
        {#each resources as r}
          <tr class="border-b border-line/50 text-xs">
            <td class="py-2 pr-4 text-ink-0 font-medium"><span class="max-md:block max-md:max-w-[66vw] max-md:truncate" title={r.resource_name}>{r.resource_name}</span></td>
            <td class="py-2 pr-4 text-ink-3 font-mono text-xs">{r.resource_type}</td>
            <td class="py-2 pr-4 text-ink-3 font-mono text-xs">{r.physical_resource_id?.slice(0, 12) || '-'}</td>
            <td class="py-2 pr-4">
              <span class="{resourceStatusColor(r.resource_status)} text-xs">{r.resource_status}</span>
              {#if r.resource_status_reason}
                <div class="text-ink-3 text-xs mt-0.5">{r.resource_status_reason}</div>
              {/if}
            </td>
            <td class="py-2 text-ink-3">{r.created_at?.slice(0, 16).replace('T', ' ') ?? '-'}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}
