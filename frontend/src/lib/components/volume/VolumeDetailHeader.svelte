<script lang="ts">
  import { useVolumeDetailController } from '$lib/stores/volumeDetailController.svelte';
  import DetailHeader from '$lib/components/ui/DetailHeader.svelte';
  import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';

  interface Props {
    ar: { active: boolean; intervalSeconds: number; intervalOptions: number[] };
    onClose?: () => void;
  }
  let { ar = $bindable(), onClose }: Props = $props();

  const s = useVolumeDetailController();
</script>

<DetailHeader title={s.volume?.name || 'Volume'} status={s.volume?.status ?? null}>
  {#snippet actions()}
    <AutoRefreshControl
      bind:active={ar.active}
      bind:intervalSeconds={ar.intervalSeconds}
      intervalOptions={ar.intervalOptions}
      refreshing={s.loading}
      onManualRefresh={() => s.loadAll()}
    />
    <!-- 닫기 버튼은 SlidePanel 이 제공한다(`[data-slide-panel-close]`) -->
  {/snippet}
</DetailHeader>
