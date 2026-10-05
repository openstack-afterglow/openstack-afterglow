<script lang="ts">
  import { t } from '$lib/i18n/ns/volume';
  import { useVolumeDetailController } from '$lib/stores/volumeDetailController.svelte';
  import DetailHeader from '$lib/components/ui/DetailHeader.svelte';
  import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';

  interface Props {
    ar: { active: boolean; intervalSeconds: number; intervalOptions: number[] };
  }
  let { ar = $bindable() }: Props = $props();

  const s = useVolumeDetailController();
</script>

<DetailHeader
  title={s.volume ? s.volume.name || s.volume.id : t('detailHeader.title')}
  subtitle={s.volume?.name ? s.volume.id : undefined}
  status={s.volume?.status ?? null}
>
  {#snippet actions()}
    <AutoRefreshControl
      bind:active={ar.active}
      bind:intervalSeconds={ar.intervalSeconds}
      intervalOptions={ar.intervalOptions}
      refreshing={s.loading}
      onManualRefresh={() => s.loadAll()}
    />
    <!-- 닫기는 SlidePanel(`[data-slide-panel-close]`) 또는 전체 화면 라우트의 목록 링크가 제공한다 -->
  {/snippet}
</DetailHeader>
