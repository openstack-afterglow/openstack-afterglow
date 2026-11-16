<script lang="ts">
 import { Button, Card, Pill, StatusChip } from '$lib/components/ui';
 import { recoveryVolumeName, type RecoveryGroup } from './recoveryPoints';
 import { formatStorage } from '$lib/utils/format';
 import { intlLocale } from '$lib/i18n/runtime.svelte';
 import { t } from '$lib/i18n/ns/volume';
 let { group, kind, inventoryKnown = true, policyKnown = true, onOpen }: { group: RecoveryGroup; kind: 'backup' | 'snapshot'; inventoryKnown?: boolean; policyKnown?: boolean; onOpen: () => void } = $props();
</script>
<Card surface="raised" padding="lg" class="space-y-4 min-w-0">
 <div class="flex flex-wrap items-start gap-2">
  <h2 class="min-w-0 flex-1 text-base font-semibold break-all"><button class="text-left hover:text-warm-text focus-visible:outline focus-visible:outline-2 focus-visible:outline-action-warm rounded-sm min-h-11" onclick={onOpen}>{recoveryVolumeName(group, inventoryKnown)}</button></h2>
  {#if group.volume}<StatusChip status={group.volume.status} />{/if}
 </div>
 <p class="text-xs font-mono text-ink-2 break-all">{group.id}</p>
 <dl class="grid grid-cols-2 gap-3 text-sm">
  <div><dt class="text-ink-2">{t('backupGroups.volumeSize')}</dt><dd>{group.volume ? formatStorage(group.volume.size) : '—'}</dd></div>
  <div><dt class="text-ink-2">{t(kind === 'backup' ? 'backupGroups.count' : 'snapshotGroups.count')}</dt><dd>{group.points.length}</dd></div>
  <div class="col-span-2"><dt class="text-ink-2">{t('backupGroups.latest')}</dt><dd class="tabular-nums">{group.latest ? new Date(group.latest).toLocaleString(intlLocale()) : '—'}</dd></div>
 </dl>
 <Pill tone={policyKnown && group.policy?.enabled ? 'success' : 'neutral'}>{!policyKnown ? t('backupGroups.policyUnknown') : t(group.policy ? group.policy.enabled ? 'backupGroups.policyActive' : 'backupGroups.policyPaused' : 'backupGroups.noPolicy')}</Pill>
 <div><Button variant="ghost" size="sm" onclick={onOpen}>{t('backupGroups.open')}</Button></div>
</Card>
