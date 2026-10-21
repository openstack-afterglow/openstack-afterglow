<script lang="ts">
  import type { User } from '$lib/types/common';
  import Pagination from '$lib/components/ui/Pagination.svelte';
  import { t } from '$lib/i18n/ns/admin-identity';
  import Button from '$lib/components/ui/Button.svelte';
  import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
  import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
  import Pill from '$lib/components/ui/Pill.svelte';

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

  <ResponsiveTable>
    {#snippet cards()}
      {#each users as u, index (u.id)}
        <CompactResourceCard>
          <div data-tour={index === 0 ? 'admin-identity-row' : undefined} class="flex flex-wrap items-center justify-between gap-2">
            <Button variant="link" size="sm" onclick={() => onEdit(u)}>{u.name}</Button>
            <Pill tone={u.enabled ? 'success' : 'danger'}>{u.enabled ? t('userTable.enabled') : t('userTable.disabled')}</Pill>
          </div>
          <p class="break-all text-sm text-ink-2">{u.email || '-'}</p>
          {#snippet details()}
            <dl class="space-y-2 text-xs">
              <div><dt class="text-ink-2">{t('userTable.id')}</dt><dd class="break-all font-mono">{u.id}</dd></div>
              <div><dt class="text-ink-2">{t('userTable.firstActivity')}</dt><dd>{(u.first_seen ?? u.created_at)?.slice(0, 10) ?? '-'}</dd></div>
            </dl>
          {/snippet}
        </CompactResourceCard>
      {/each}
    {/snippet}
  <div class="overflow-x-auto">
    <table class="w-full text-sm">
      <thead>
        <tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
          <th class="text-left py-2 pr-4">{t('userTable.name')}</th>
          <th class="text-left py-2 pr-4">{t('userTable.email')}</th>
          <th class="text-left py-2 pr-4">{t('userTable.status')}</th>
          <th class="text-left py-2 pr-4">{t('userTable.id')}</th>
          <th class="text-left py-2">{t('userTable.firstActivity')}</th>
        </tr>
      </thead>
      <tbody>
        {#each users as u, index (u.id)}
          <tr
            class="border-b border-line/50 text-xs hover:bg-surface-sunken/50 transition-colors cursor-pointer"
            data-tour={index === 0 ? 'admin-identity-row' : undefined}
          >
            <td class="py-2 pr-4 text-ink-0"><Button variant="link" size="sm" onclick={() => onEdit(u)}>{u.name}</Button></td>
            <td class="py-2 pr-4 text-ink-2">{u.email || '-'}</td>
            <td class="py-2 pr-4">
              <span class="px-1.5 py-0.5 rounded text-xs font-medium {u.enabled ? 'bg-green-900/30 text-green-400' : 'bg-red-900/30 text-red-400'}">{u.enabled ? t('userTable.enabled') : t('userTable.disabled')}</span>
            </td>
            <td class="py-2 pr-4 text-ink-2 font-mono text-xs">{u.id.slice(0, 8)}</td>
            <td class="py-2 text-ink-2">{(u.first_seen ?? u.created_at)?.slice(0, 10) ?? '-'}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
  </ResponsiveTable>
  <Pagination
    {page}
    {hasPrev}
    {hasNext}
    {onPrev}
    {onNext}
  />
