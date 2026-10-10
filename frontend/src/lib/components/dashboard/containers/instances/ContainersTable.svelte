<script lang="ts">
  import { t } from '$lib/i18n/ns/containers-shell';
  import { t as tc } from '$lib/i18n/ns/common';
  import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
  import StatusChip from '$lib/components/ui/StatusChip.svelte';
  import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';
  import type { ZunContainer } from '$lib/types/zunContainer';

  interface Props {
    containers: ZunContainer[];
    actionTarget?: string | null;
    selectedIds?: ReadonlySet<string>;
    selectableIds?: ReadonlySet<string>;
    selectionDisabled?: boolean;
    onToggleSelect?: (id: string) => void;
    onToggleAll?: () => void;
    onStart?: (id: string) => Promise<void>;
    onStop?: (id: string) => Promise<void>;
    onDelete?: (id: string, name: string) => Promise<void>;
    onOpen?: (id: string) => void;
  }
  let {
    containers,
    actionTarget = null,
    selectedIds = new Set<string>(),
    selectableIds = new Set<string>(),
    selectionDisabled = false,
    onToggleSelect = () => {},
    onToggleAll = () => {},
    onStart = async () => {},
    onStop = async () => {},
    onDelete = async () => {},
  onOpen = () => {},
  }: Props = $props();
  const selectedCount = $derived(selectedIds.size);
  const selectableCount = $derived(selectableIds.size);
  const selectedSelectableCount = $derived([...selectableIds].filter((id) => selectedIds.has(id)).length);
  const allSelected = $derived(selectableCount > 0 && selectedSelectableCount === selectableCount);
  const indeterminate = $derived(selectedSelectableCount > 0 && !allSelected);
</script>

{#if containers.length === 0}
  <div class="containers-table__empty text-center py-20">
    <p class="text-lg mb-2">{t('instances.empty.title')}</p>
    <p class="text-sm">{t('instances.empty.description')}</p>
  </div>
{:else}
  <div class="overflow-x-auto">
    <table class="w-full text-sm">
      <thead>
        <tr class="containers-table__head text-xs uppercase tracking-wide">
          <th class="text-left py-3 pr-3">
            <div class="inline-flex items-center gap-2"><SelectionCheckbox checked={allSelected} indeterminate={indeterminate} disabled={selectionDisabled} ariaLabel={t('instances.selection.allAria')} onclick={onToggleAll} /><span>{t('instances.selection.all')}</span><span class="containers-table__selection-count normal-case" aria-live="polite">{t('instances.selection.count', { count: selectedSelectableCount })}</span></div>
          </th>
          <th class="text-left py-3 pr-6">{t('instances.fields.name')}</th>
          <th class="text-left py-3 pr-6">{t('instances.fields.status')}</th>
          <th class="text-left py-3 pr-6">{t('instances.fields.image')}</th>
          <th class="text-left py-3 pr-6">{t('instances.fields.cpu')}</th>
          <th class="text-left py-3 pr-6">{t('instances.fields.memory')}</th>
          <th class="text-left py-3 pr-6">{t('instances.fields.createdAt')}</th>
          <th class="text-left py-3"></th>
        </tr>
      </thead>
      <tbody>
        {#each containers as c (c.uuid)}
          {@const selectable = selectableIds.has(c.uuid)}
          <tr class="resource-selection-surface containers-table__row transition-colors" data-selected={selectedIds.has(c.uuid)}>
            <td class="py-3 pr-3">
              <SelectionCheckbox checked={selectedIds.has(c.uuid)} disabled={selectionDisabled || !selectable} unavailable={!selectable} ariaLabel={t('instances.selection.itemAria', { name: c.name })} title={!selectable ? t('instances.selection.unavailable') : undefined} onclick={() => onToggleSelect(c.uuid)} />
            </td>
            <td class="py-3 pr-6">
              <button onclick={() => onOpen(c.uuid)} class="containers-table__name font-medium transition-colors text-left max-md:block max-md:max-w-[66vw] max-md:truncate" title={c.name}>{c.name}</button>
            </td>
            <td class="py-3 pr-6"><StatusChip status={c.status} /></td>
            <td class="containers-table__meta py-3 pr-6 text-xs font-mono">{c.image ?? '-'}</td>
            <td class="containers-table__meta py-3 pr-6 text-xs">{c.cpu ?? '-'}</td>
            <td class="containers-table__meta py-3 pr-6 text-xs">{c.memory ?? '-'}</td>
            <td class="containers-table__meta py-3 pr-6 text-xs">{c.created_at?.slice(0, 10) ?? '-'}</td>
            <td class="py-3">
              <div class="flex items-center gap-2">
                {#if actionTarget === c.uuid}<ActivityIndicator size="xs" label={tc('state.processing')} class="text-xs" />{/if}
                {#if c.status === 'Running'}
                  <button onclick={() => onStop(c.uuid)} disabled={actionTarget === c.uuid} class="containers-table__action containers-table__stop text-xs disabled:opacity-40 transition-colors">{t('instances.actions.stop')}</button>
                {:else if c.status === 'Stopped' || c.status === 'Created'}
                  <button onclick={() => onStart(c.uuid)} disabled={actionTarget === c.uuid} class="containers-table__action containers-table__start text-xs disabled:opacity-40 transition-colors">{t('instances.actions.start')}</button>
                {/if}
                <button onclick={() => onDelete(c.uuid, c.name)} disabled={actionTarget === c.uuid} class="containers-table__action containers-table__delete text-xs disabled:opacity-40 transition-colors">{t('instances.actions.delete')}</button>
              </div>
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}


<style>
  .containers-table__empty,
  .containers-table__selection-count,
  .containers-table__meta {
    color: var(--color-ink-2);
  }

  .containers-table__head {
    border-bottom: 1px solid var(--color-line);
    color: var(--color-ink-2);
  }

  .containers-table__row {
    border-bottom: 1px solid color-mix(in oklab, var(--color-line), transparent 45%);
  }

  .containers-table__row:hover {
    background-color: color-mix(in oklab, var(--color-surface-sunken), transparent 45%);
  }

  .containers-table__row[data-selected='true'] {
    background-color: var(--accent-soft);
  }

  .containers-table__name {
    color: var(--color-ink-0);
  }

  .containers-table__name:hover {
    color: var(--color-accent);
  }

  .containers-table__stop {
    color: var(--color-state-warning-text);
  }

  .containers-table__stop:hover {
    color: color-mix(in oklab, var(--color-state-warning-text) 82%, var(--color-ink-0));
  }

  .containers-table__start {
    color: var(--color-state-success-text);
  }

  .containers-table__start:hover {
    color: color-mix(in oklab, var(--color-state-success-text) 82%, var(--color-ink-0));
  }

  .containers-table__delete {
    color: var(--color-state-danger-text);
  }

  .containers-table__delete:hover {
    color: color-mix(in oklab, var(--color-state-danger-text) 82%, var(--color-ink-0));
  }
</style>
