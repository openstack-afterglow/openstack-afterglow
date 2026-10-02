<script lang="ts">
	import { t } from '$lib/i18n/ns/vm-wizard';
	import RichText from '$lib/i18n/RichText.svelte';
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
			{t('header.title')}
			{#if adminMode}
				<span class="text-sm font-normal text-warm-text ml-2">{t('header.adminProject', { name: adminProjectName ?? '' })}</span>
			{/if}
		</h1>
		<div class="step-progress text-[12.5px] text-ink-2 font-mono uppercase tracking-[0.06em] mt-1.5">
			<RichText segments={t.rich('header.step', { step, total: totalSteps, name: stepName })} classes={{ strong: 'font-semibold' }} />
		</div>
	</div>
	<div class="flex items-center gap-3.5 mt-0.5">
		<button
			onclick={onReset}
			class="text-xs text-ink-2 hover:text-ink-2 transition-colors"
		>{t('header.reset')}</button>
		<!-- 닫기는 SlidePanel(`[data-slide-panel-close]`)과 하단 푸터 취소가 담당한다.
		     헤더에 또 두면 위저드 전 구간에서 닫기 컨트롤이 두 개 보인다. -->
	</div>
</div>

<style>
  .step-progress :global(strong) {
    color: var(--color-warm);
  }
</style>
