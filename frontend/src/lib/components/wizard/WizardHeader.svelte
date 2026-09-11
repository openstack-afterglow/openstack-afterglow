<script lang="ts">
	let { step, totalSteps, stepName, adminMode = false, adminProjectName = null, onReset, onClose }: {
		step: number;
		totalSteps: number;
		stepName: string;
		adminMode?: boolean;
		adminProjectName?: string | null;
		onReset: () => void;
		onClose: () => void;
	} = $props();
</script>

<div class="flex items-start justify-between mb-6">
	<div>
		<h1 class="text-2xl font-bold text-ink-0 tracking-tight leading-tight">
			VM 생성
			{#if adminMode}
				<span class="text-sm font-normal text-action-warm ml-2">관리자 · {adminProjectName ?? ''}</span>
			{/if}
		</h1>
		<div class="text-[12.5px] text-ink-3 font-mono uppercase tracking-[0.06em] mt-1.5">
			STEP <b class="text-warm font-semibold">{step}</b> / {totalSteps} · <b class="text-warm font-semibold">{stepName}</b>
		</div>
	</div>
	<div class="flex items-center gap-3.5 mt-0.5">
		<button
			onclick={onReset}
			class="text-xs text-ink-3 hover:text-ink-2 transition-colors"
		>↺ 새로 시작</button>
		<!-- 닫기는 SlidePanel(`[data-slide-panel-close]`)과 하단 푸터 취소가 담당한다.
		     헤더에 또 두면 위저드 전 구간에서 닫기 컨트롤이 두 개 보인다. -->
	</div>
</div>

<style>
  .text-warm {
    color: var(--color-warm);
  }
</style>
