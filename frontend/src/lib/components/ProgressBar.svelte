<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { HTMLAttributes } from 'svelte/elements';

	interface Step {
		id: string;
		label: string;
		description?: string;
	}

	interface Props extends HTMLAttributes<HTMLDivElement> {
		steps: Step[];
		currentStep: string;
		progress: number;
		error?: string;
	}

	let { steps, currentStep, progress, error, ...restProps }: Props = $props();

	function getStepStatus(stepId: string, currentStepId: string): 'completed' | 'active' | 'pending' {
		const stepOrder = steps.map(s => s.id);
		const currentIndex = stepOrder.indexOf(currentStepId);
		const stepIndex = stepOrder.indexOf(stepId);

		if (stepIndex < currentIndex) return 'completed';
		if (stepIndex === currentIndex) return 'active';
		return 'pending';
	}
</script>

<div class="w-full" {...restProps}>
	<!-- Progress bar -->
	<div class="relative mb-6">
		<div class="h-2 bg-surface-sunken rounded-full overflow-hidden">
			<div
				class="h-full bg-action-warm transition-all duration-500 ease-out"
				style="width: {progress}%"
			></div>
		</div>
		<div class="flex justify-between mt-2 text-xs text-ink-3">
			<span>0%</span>
			<span>{progress}%</span>
		</div>
	</div>

	<!-- Steps -->
	<div class="space-y-4">
		{#each steps as step, i}
			{@const status = getStepStatus(step.id, currentStep)}
			<div class="flex items-start gap-3">
				<!-- Step indicator -->
				<div class="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium transition-colors
					{status === 'completed' ? 'bg-green-600 text-ink-0' : ''}
					{status === 'active' ? 'bg-action-warm text-ink-0 animate-pulse' : ''}
					{status === 'pending' ? 'bg-surface-sunken text-ink-3' : ''}
				">
					{#if status === 'completed'}
						<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
						</svg>
					{:else}
						{i + 1}
					{/if}
				</div>

				<!-- Step content -->
				<div class="flex-1 pt-1">
					<div class="flex items-center gap-2">
						<span class="font-medium {status === 'active' ? 'text-ink-0' : status === 'completed' ? 'text-green-400' : 'text-ink-3'}">
							{step.label}
						</span>
						{#if status === 'active'}
							<div class="flex gap-0.5">
								<div class="w-1 h-1 bg-blue-400 rounded-full animate-bounce" style="animation-delay: 0ms"></div>
								<div class="w-1 h-1 bg-blue-400 rounded-full animate-bounce" style="animation-delay: 150ms"></div>
								<div class="w-1 h-1 bg-blue-400 rounded-full animate-bounce" style="animation-delay: 300ms"></div>
							</div>
						{/if}
					</div>
					{#if step.description && status !== 'pending'}
						<p class="text-xs text-ink-3 mt-0.5">{step.description}</p>
					{/if}
				</div>
			</div>
		{/each}
	</div>

	<!-- Error message -->
	{#if error}
		<div class="mt-4 p-3 bg-red-900/30 border border-red-700 rounded-lg">
			<div class="flex items-start gap-2">
				<svg class="w-5 h-5 text-red-400 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
				</svg>
				<div>
					<p class="text-red-300 font-medium">배포 실패</p>
					<p class="text-red-400/80 text-sm mt-1">{error}</p>
				</div>
			</div>
		</div>
	{/if}
</div>