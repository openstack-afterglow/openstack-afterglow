<script lang="ts">
  let {
    attachments,
    attachedInstances,
  }: {
    attachments: Record<string, unknown>[];
    attachedInstances: Map<string, string>;
  } = $props();

  function sid(a: Record<string, unknown>): string {
    return (a.server_id as string) ?? '';
  }

  function dev(a: Record<string, unknown>): string {
    return (a.device as string) ?? '-';
  }
</script>

<div class="bg-surface-base border border-line rounded-lg p-6">
  <h2 class="text-sm font-semibold text-ink-2 uppercase tracking-wide mb-4">연결 정보</h2>
  {#if attachments.length === 0}
    <p class="text-sm text-ink-3">미연결</p>
  {:else}
    <table class="w-full text-sm">
      <thead>
        <tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
          <th class="text-left py-2 pr-6">인스턴스</th>
          <th class="text-left py-2 pr-6">디바이스</th>
          <th class="text-left py-2">ID</th>
        </tr>
      </thead>
      <tbody>
        {#each attachments as a}
          <tr class="border-b border-line/50">
            <td class="py-2 pr-6">
              <a
                href="/dashboard/instances/{sid(a)}"
                class="text-action-warm hover:text-action-warm-hover transition-colors"
              >
                {attachedInstances.get(sid(a)) ?? sid(a).slice(0, 8) + '…'}
              </a>
            </td>
            <td class="py-2 pr-6 text-ink-2 font-mono text-xs">{dev(a)}</td>
            <td class="py-2 text-ink-3 font-mono text-xs">{sid(a)}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</div>
