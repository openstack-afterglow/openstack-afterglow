<script lang="ts">
  import type { User } from '$lib/types/common';
  import Pagination from '$lib/components/ui/Pagination.svelte';

  let {
    users,
    refreshing,
    page,
    hasPrev,
    hasNext,
    onEdit,
    onPrev,
    onNext,
  }: {
    users: User[];
    refreshing: boolean;
    page: number;
    hasPrev: boolean;
    hasNext: boolean;
    onEdit: (user: User) => void;
    onPrev: () => void;
    onNext: () => void;
  } = $props();
</script>

  <div class="overflow-x-auto">
    <table class="w-full text-sm">
      <thead>
        <tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
          <th class="text-left py-2 pr-4">이름</th>
          <th class="text-left py-2 pr-4">이메일</th>
          <th class="text-left py-2 pr-4">상태</th>
          <th class="text-left py-2 pr-4">ID</th>
          <th class="text-left py-2">최초 활동일</th>
        </tr>
      </thead>
      <tbody>
        {#each users as u, index (u.id)}
          <tr
            class="border-b border-line/50 text-xs hover:bg-surface-sunken/50 transition-colors cursor-pointer"
            onclick={() => onEdit(u)}
            data-tour={index === 0 ? 'admin-identity-row' : undefined}
          >
            <td class="py-2 pr-4 text-ink-0"><span class="max-md:block max-md:max-w-[66vw] max-md:truncate" title={u.name}>{u.name}</span></td>
            <td class="py-2 pr-4 text-ink-2">{u.email || '-'}</td>
            <td class="py-2 pr-4">
              <span class="px-1.5 py-0.5 rounded text-xs font-medium {u.enabled ? 'bg-green-900/30 text-green-400' : 'bg-red-900/30 text-red-400'}">{u.enabled ? '활성' : '비활성'}</span>
            </td>
            <td class="py-2 pr-4 text-ink-3 font-mono text-xs">{u.id.slice(0, 8)}</td>
            <td class="py-2 text-ink-3">{(u.first_seen ?? u.created_at)?.slice(0, 10) ?? '-'}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
  <Pagination
    {page}
    {hasPrev}
    {hasNext}
    {onPrev}
    {onNext}
  />
