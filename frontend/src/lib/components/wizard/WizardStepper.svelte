<script lang="ts">
	let { cur, totalSteps, stepLabels, goTo }: {
		cur: number;
		totalSteps: number;
		stepLabels: string[];
		goTo: (n: number) => void;
	} = $props();

	const progressPct = $derived(((cur - 1) / Math.max(1, totalSteps - 1)) * 100);
</script>

<div class="stepper-container hidden md:block">
	<div class="full-stepper relative bg-surface-base border border-line rounded-xl px-5 py-2.5 mb-5">
		<!-- progress track (background) + fill (자식으로 좌표계 통일) -->
		<div class="absolute left-5 right-5 top-1/2 h-[2px] bg-surface-sunken rounded-full -translate-y-1/2 overflow-hidden">
			<div class="h-full progress-fill rounded-full" style="width: {progressPct}%"></div>
		</div>

		<!-- step dots + labels -->
		<div class="relative flex justify-between">
			{#each stepLabels as label, i}
				{@const step = i + 1}
				{@const isDone = cur > step}
				{@const isCurrent = cur === step}

				<button
					type="button"
					onclick={() => { if (isDone) goTo(step); }}
					class="flex items-center gap-1.5 bg-surface-base px-1 {isDone ? 'cursor-pointer' : 'cursor-default'}"
					tabindex={isDone ? 0 : -1}
					aria-current={isCurrent ? 'step' : undefined}
				>
					{#if isDone}
						<div class="step-dot-done w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 transition-transform hover:scale-105">
							<svg class="w-3 h-3 text-ink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"/>
							</svg>
						</div>
					{:else if isCurrent}
						<div class="step-dot-current w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 text-xs font-bold text-ink-0">
							{step}
						</div>
					{:else}
						<div class="w-6 h-6 rounded-full bg-surface-sunken border border-line-2 flex items-center justify-center flex-shrink-0 text-[11px] font-medium text-ink-3">
							{step}
						</div>
					{/if}
					<span class="text-[11px] font-medium {isCurrent ? 'text-ink-0' : isDone ? 'text-ink-2 group-hover:text-ink-0' : 'text-ink-3'}">{label}</span>
				</button>
			{/each}
		</div>
	</div>
</div>

<style>
  .progress-fill {
    background: var(--gradient-warm);
    transition: width 0.4s cubic-bezier(0.2, 0.7, 0.2, 1);
  }
  .step-dot-done {
    background: var(--gradient-warm);
  }
  .step-dot-current {
    background: var(--gradient-warm);
    box-shadow: 0 0 12px color-mix(in oklab, var(--color-warm) 40%, transparent);
  }
</style>
