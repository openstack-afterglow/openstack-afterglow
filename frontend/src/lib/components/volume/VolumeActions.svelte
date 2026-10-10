<script lang="ts">
  import { t } from '$lib/i18n/ns/volume';
  import { auth } from '$lib/stores/auth';
  import { betaFeatures } from '$lib/stores/betaFeatures';
  import { useVolumeDetailController } from '$lib/stores/volumeDetailController.svelte';
  import { bootFromVolume } from '$lib/stores/volumesController.svelte';
  import ActionMenu from '$lib/components/ui/ActionMenu.svelte';
  import Button from '$lib/components/ui/Button.svelte';
  import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
  import VolumeOperationItems from '$lib/components/volume/VolumeOperationItems.svelte';
  import type { Volume } from '$lib/types/volume';

  let { onExtend, onBackup, onSnapshot, onTransfer }: {
    onExtend: (volume: Volume) => void;
    onBackup: (volume: Volume) => void;
    onSnapshot: (volume: Volume) => void;
    onTransfer: (volume: Volume) => void;
  } = $props();

  const s = useVolumeDetailController();
  let menuOpen = $state(false);
  let menuScope = '';
  $effect(() => {
    const scope = `${$auth.projectId ?? ''}\u0000${s.volume?.id ?? ''}`;
    if (scope === menuScope) return;
    menuScope = scope;
    menuOpen = false;
  });
</script>

<div class="flex items-center gap-2 flex-wrap" aria-label={t('volumeActions.actions')}>
  <Button onclick={() => s.openRenameModal()} size="sm" variant="secondary">{t('volumeActions.rename')}</Button>
  {#if s.volume!.status === 'available'}
    <Button onclick={() => s.openAttachModal()} size="sm">{t('volumeActions.attach')}</Button>
  {/if}
  <Button onclick={() => s.deleteVolume()} disabled={!s.canDelete} size="sm" variant="danger-outline" title={s.volume!.attachments.length > 0 ? t('volumeActions.attachedDeleteUnavailable') : undefined}>
    {#if s.deleting}<ActivityIndicator size="xs" tone="danger" />{/if}{s.deleting ? t('volumeActions.deleting') : t('volumeActions.delete')}
  </Button>
  <span class="text-sm text-ink-2">{t('volumeActions.actions')}</span>
  <ActionMenu open={menuOpen} onopen={() => menuOpen = true} onclose={() => menuOpen = false} ariaLabel={t('volumeActions.namedActions', { name: s.volume!.name || s.volume!.id })}>
    <VolumeOperationItems
      volume={s.volume!}
      onclose={() => menuOpen = false}
      onRename={() => s.openRenameModal()}
      onBoot={bootFromVolume}
      {onExtend}
      {onBackup}
      {onSnapshot}
      {onTransfer}
      onForceDelete={() => s.forceDeleteVolume()}
      onDelete={() => s.deleteVolume()}
      volumeSnapshotsEnabled={$betaFeatures.volumeSnapshots}
      isSystemAdmin={!!$auth.isSystemAdmin}
      deleting={s.deleting}
    />
  </ActionMenu>
</div>
