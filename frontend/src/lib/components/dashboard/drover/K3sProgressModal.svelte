<script lang="ts">
	import { t } from '$lib/i18n/ns/drover-pages';
	import { t as td } from '$lib/i18n/ns/drover';
	import type { K3sProgressController } from '$lib/stores/k3sProgress.svelte';
	import { k3sProgressState, type K3sStep } from '$lib/components/k3sSteps';
	import { Alert, AnimatedNumber, Button, ProgressTrack, ProvisionPipeline, StepProgress } from '$lib/components/ui';
	import type { ProgressStepItem } from '$lib/components/ui';

	let {
		controller,
		activeSteps,
		onClose,
		onViewCluster,
	}: {
		controller: K3sProgressController;
		activeSteps: K3sStep[];
		onClose: () => void;
		onViewCluster: (clusterId: string) => void;
	} = $props();

	const progressState = $derived(k3sProgressState(controller.step, controller.stepTimings, activeSteps));
	const listSteps = $derived<ProgressStepItem[]>(
		activeSteps.map((step) => {
			const startedAt = controller.stepTimings[step.id];
			return { id: step.id, label: step.label, meta: startedAt != null ? `${startedAt}s~` : undefined };
		}),
	);
	const running = $derived(progressState.status === 'running');
	const percent = $derived(Math.max(0, Math.min(100, controller.pct)));
	const stepsLabel = $derived(controller.mode === 'delete' ? t('cluster.deleteTitle') : t('cluster.createTitle'));
</script>

<div class="motion-fade fixed inset-0 bg-surface-scrim/70 flex items-center justify-center z-50">
	<div data-tour="drover-progress" class="motion-pop bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-xl mx-4 max-h-[calc(100dvh-2rem)] overflow-y-auto shadow-[var(--shadow-restraint)]">
		<h2 class="text-lg font-semibold text-ink-0 mb-4">
			{controller.mode === 'delete' ? t('cluster.deleteTitle') : t('cluster.createTitle')}
		</h2>

		<ProvisionPipeline stages={activeSteps} current={progressState.current} status={progressState.status} label={stepsLabel} decorative class="mb-4" />

		<ProgressTrack
			value={running && controller.pct <= 0 ? null : controller.pct}
			label={stepsLabel}
			tone={progressState.status === 'done' ? 'success' : progressState.status === 'failed' ? 'danger' : 'accent'}
			active={running}
		/>
		<div class="mt-2 flex items-center justify-between gap-3 text-xs text-ink-2">
			<span class="font-mono text-sm text-ink-0">
				{#if running && controller.pct <= 0}{td('steps.prepare')}{:else}<AnimatedNumber value={Math.round(percent)} />%{/if}
			</span>
			{#if controller.elapsedSeconds > 0}
				<span class="flex-shrink-0">{t('progress.elapsed', { seconds: controller.elapsedSeconds })}</span>
			{/if}
		</div>
		<p class="mt-2 mb-4 min-h-5 text-sm text-ink-2" role="status" aria-live="polite">{controller.msg}</p>

		<StepProgress steps={listSteps} current={progressState.current} status={progressState.status} label={stepsLabel} class="mb-4" />

		{#if controller.error}
			<Alert tone="danger" class="mb-4">{controller.error}</Alert>
		{/if}
		{#if controller.isTerminal}
			<div class="flex justify-end gap-3">
				<Button variant="ghost" onclick={onClose}>{t('actions.close')}</Button>
				{#if controller.createdClusterId && controller.step === 'completed' && controller.mode === 'create'}
					<Button onclick={() => onViewCluster(controller.createdClusterId!)}>{t('progress.viewCluster')}</Button>
				{/if}
			</div>
		{:else}
			<div class="flex items-center justify-between gap-3">
				<p class="text-xs text-ink-2">{t('progress.background')}</p>
				<Button variant="outline" size="sm" onclick={onClose}>{t('actions.close')}</Button>
			</div>
		{/if}
	</div>
</div>
