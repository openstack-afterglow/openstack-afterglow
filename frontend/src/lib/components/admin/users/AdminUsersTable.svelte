<script lang="ts">
  import { rowChanged, rowEnter, rowExit, rowReflow } from '$lib/utils/rowMotion';
  import { isSystemAccount } from '$lib/utils/systemAccount';
  import SystemAccountNotice from '$lib/components/identity/SystemAccountNotice.svelte';
	import type { TableView } from '$lib/utils/tableView.svelte';
	import TableColumnHeader from '$lib/components/ui/TableColumnHeader.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
  import type { User } from '$lib/types/common';
  import Pagination from '$lib/components/ui/Pagination.svelte';
  import { t } from '$lib/i18n/ns/admin-identity';
  import Button from '$lib/components/ui/Button.svelte';
  import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
  import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
  import Pill from '$lib/components/ui/Pill.svelte';

  let {
    users,
    view,
    refreshing,
    page,
    hasPrev,
    hasNext,
    onEdit,
    onDelete,
    actorId,
    deleteDisabled,
    onPrev,
    onNext,
    tourDeleteId = null,
    embedded = false,
  }: {
    users: User[];
    view: TableView<User>;
    refreshing: boolean;
    page: number;
    hasPrev: boolean;
    hasNext: boolean;
    onEdit: (user: User) => void;
    onDelete: (user: User) => void;
    actorId: string | null;
    deleteDisabled: boolean;
    onPrev: () => void;
    onNext: () => void;
    tourDeleteId?: string | null;
    embedded?: boolean;
  } = $props();
</script>

  <div data-tour="admin-identity-status-filter"><TableViewControls {view} /></div>
  <ResponsiveTable {embedded}>
    {#snippet cards()}
      {#each users as u, index (u.id)}
        <CompactResourceCard>
          <div data-tour={index === 0 ? 'admin-identity-row' : undefined} class="flex flex-wrap items-center justify-between gap-2">
            {#if isSystemAccount(u)}<span class="text-sm text-ink-0">{u.name}</span>{:else}<Button variant="link" size="sm" onclick={() => onEdit(u)}>{u.name}</Button>{/if}
            <Pill tone={u.enabled ? 'success' : 'danger'}>{u.enabled ? t('userTable.enabled') : t('userTable.disabled')}</Pill>
          </div>
          <p class="break-all text-sm text-ink-2">{u.email || '-'}</p>
          <SystemAccountNotice identity={u} />
          <Button variant="danger-outline" size="sm" class="min-h-11 justify-self-start" disabled={deleteDisabled || isSystemAccount(u) || u.id === actorId} ariaLabel={u.id === actorId ? t('userDelete.selfProtected') : t('userDelete.actionLabel', { name: u.name })} dataTour={u.id === tourDeleteId ? 'admin-users-delete' : undefined} onclick={() => { if (!isSystemAccount(u)) onDelete(u); }}>{t('actions.delete')}</Button>
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
<TableColumnHeader {view} columnKey="name" />
<TableColumnHeader {view} columnKey="email" />
<TableColumnHeader {view} columnKey="status" />
<TableColumnHeader {view} columnKey="id" />
<TableColumnHeader {view} columnKey="firstActivity" />
          <th class="text-right py-2">{t('userDelete.actions')}</th>
        </tr>
      </thead>
      <tbody>
        {#each users as u, index (u.id)}
          <tr
            class="border-b border-line/50 text-xs hover:bg-surface-sunken/50 transition-colors cursor-pointer"
            data-tour={index === 0 ? 'admin-identity-row' : undefined}
            in:rowEnter out:rowExit animate:rowReflow use:rowChanged={u}
          >
            <td class="py-2 pr-4 text-ink-0">{#if isSystemAccount(u)}<span class="text-sm">{u.name}</span>{:else}<Button variant="link" size="sm" onclick={() => onEdit(u)}>{u.name}</Button>{/if}<SystemAccountNotice identity={u} /></td>
            <td class="py-2 pr-4 text-ink-2">{u.email || '-'}</td>
            <td class="py-2 pr-4">
              <span class="px-1.5 py-0.5 rounded text-xs font-medium {u.enabled ? 'bg-green-900/30 text-green-400' : 'bg-red-900/30 text-red-400'}">{u.enabled ? t('userTable.enabled') : t('userTable.disabled')}</span>
            </td>
            <td class="py-2 pr-4 text-ink-2 font-mono text-xs">{u.id.slice(0, 8)}</td>
            <td class="py-2 text-ink-2">{(u.first_seen ?? u.created_at)?.slice(0, 10) ?? '-'}</td>
            <td class="py-2 text-right"><Button variant="danger-outline" size="sm" disabled={deleteDisabled || isSystemAccount(u) || u.id === actorId} ariaLabel={u.id === actorId ? t('userDelete.selfProtected') : t('userDelete.actionLabel', { name: u.name })} dataTour={u.id === tourDeleteId ? 'admin-users-delete' : undefined} onclick={() => { if (!isSystemAccount(u)) onDelete(u); }}>{t('actions.delete')}</Button></td>
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
