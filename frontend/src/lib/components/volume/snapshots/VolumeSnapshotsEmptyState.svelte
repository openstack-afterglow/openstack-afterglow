<script lang="ts">
 let { onCreate, onintent }: { onCreate: () => void; onintent?: () => void } = $props();
</script>

<div class="text-center py-20 text-ink-2">
  <div class="text-5xl mb-4">📸</div>
  <p class="text-lg">볼륨 스냅샷이 없습니다</p>
  <button onclick={onCreate} onpointerenter={onintent} onfocus={onintent} class="text-warm-text hover:text-warm-text-hover text-sm mt-2 inline-block">첫 스냅샷을 생성하세요 →</button>
</div>
