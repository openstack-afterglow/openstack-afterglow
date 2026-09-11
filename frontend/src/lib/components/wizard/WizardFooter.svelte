<script lang="ts">
	import Button from '$lib/components/ui/Button.svelte';

	let { imageDisplay, flavorDisplay, libCount, step, totalSteps, canPrev, canNext,
		onCancel, onPrev, onNext, onDeploy }: {
		imageDisplay?: string | null;
		flavorDisplay?: string | null;
		libCount?: number;
		step: number;
		totalSteps: number;
		canPrev: boolean;
		canNext: boolean;
		onCancel: () => void;
		onPrev: () => void;
		onNext: () => void;
		onDeploy: () => void;
	} = $props();

	const isLast = $derived(step === totalSteps);
</script>

<div class="wizard-footer sticky bottom-0 z-20 flex flex-none items-center justify-between flex-wrap gap-3 px-4 py-3 md:px-8 md:py-4 bg-[var(--color-surface-base)] border-t border-[var(--color-line)]">
	<!-- selection chips strip -->
	<div class="hidden md:flex flex-wrap items-center gap-2 text-xs text-ink-3 min-w-0">
		{#if imageDisplay}
			<span class="pick">이미지: <b class="text-ink-2 font-mono font-medium">{imageDisplay}</b></span>
		{/if}
		{#if flavorDisplay}
			<span class="pick">플레이버: <b class="text-ink-2 font-mono font-medium">{flavorDisplay}</b></span>
		{/if}
		{#if libCount && libCount > 0}
			<span class="pick">라이브러리: <b class="text-ink-2 font-mono font-medium">{libCount}개</b></span>
		{/if}
	</div>

	<!-- nav buttons -->
	<div class="flex items-center justify-end gap-2 w-full md:w-auto md:ml-auto flex-shrink-0" data-tour="wizard-nav">
		<button
			data-tour="wizard-cancel"
			onclick={onCancel}
			class="wizard-cancel order-2 md:order-none px-4 py-2 text-sm text-ink-2 hover:text-red-400 border border-line-2 hover:border-red-900/60 hover:bg-red-950/20 rounded-lg transition-all"
		>취소</button>
		{#if canPrev}
			<button
				data-tour="wizard-prev"
				onclick={onPrev}
				class="wizard-prev order-1 md:order-none px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors flex items-center gap-1"
			>← 이전</button>
		{/if}
		{#if !isLast}
			<span class="order-3 md:order-none" data-tour="wizard-next"><Button onclick={onNext} disabled={!canNext}>다음 →</Button></span>
		{:else}
			<span class="order-3 md:order-none" data-tour="wizard-next"><Button onclick={onDeploy} disabled={!canNext}>VM 생성</Button></span>
		{/if}
	</div>
</div>

<style>
  .pick {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 10px;
    border-radius: 6px;
    background: var(--color-surface-sunken);
    border: 1px solid var(--color-line);
  }
	.wizard-footer {
		padding-bottom: max(0.75rem, env(safe-area-inset-bottom));
	}
	@media (min-width: 768px) {
		.wizard-footer {
			padding-bottom: max(1rem, env(safe-area-inset-bottom));
		}
	}
</style>
