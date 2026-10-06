<script module lang="ts">
	import { PROVISION_ICON } from './provisionIcons';

	/** Pipeline icon for each step the deployment stream reports. */
	const DEPLOY_STAGE_ICONS: Record<string, string> = {
		manila_preparing: PROVISION_ICON.sharedFolder,
		boot_volume_creating: PROVISION_ICON.disk,
		upper_volume_creating: PROVISION_ICON.layers,
		userdata_generating: PROVISION_ICON.script,
		server_creating: PROVISION_ICON.server,
		attaching_volume: PROVISION_ICON.link,
		floating_ip_creating: PROVISION_ICON.globe,
		completed: PROVISION_ICON.checkCircle,
	};
</script>

<script lang="ts">
	import { t } from '$lib/i18n/ns/vm-wizard';
	import { useVmCreate } from '$lib/stores/vmCreateStore.svelte';
	import { AnimatedNumber, ProgressTrack, ProvisionPipeline, StepProgress } from '$lib/components/ui';
	import type { PipelineStage, ProgressStepItem, StepProgressStatus } from '$lib/components/ui';

	const s = useVmCreate();

	// A failed deployment leaves this screen (the store clears `deploying`), so the pseudo-step is never listed.
	const steps = $derived<ProgressStepItem[]>(
		s.progressSteps
			.filter((step) => step.id !== 'failed')
			.map((step) => ({
				id: step.id,
				label: step.label,
				description: step.description,
				meta: s.stepElapsedSeconds[step.id] === undefined ? undefined : t(
					step.id === s.currentStep ? 'progress.stageElapsed' : 'progress.stageDuration',
					{ seconds: Math.floor(s.stepElapsedSeconds[step.id]) },
				),
			})),
	);
	const stages = $derived<PipelineStage[]>(
		steps.map((step) => ({ id: step.id, label: step.label, icon: DEPLOY_STAGE_ICONS[step.id] ?? '' })),
	);
	const status = $derived<StepProgressStatus>(s.currentStep === 'completed' ? 'done' : 'running');
	const percent = $derived(Math.max(0, Math.min(100, s.progress)));
</script>

<div class="mb-6">
	<h1 class="text-xl font-bold text-ink-0">{t('progress.title')}</h1>
	<p class="text-sm text-ink-2 mt-1">{t('progress.subtitle')}</p>
</div>

<section class="motion-enter bg-surface-base rounded-xl border border-line-2 p-4 md:p-6 mb-6" aria-labelledby="vm-deploy-progress-title">
	<h2 id="vm-deploy-progress-title" class="text-lg font-semibold text-ink-0 mb-4">{t('progress.heading')}</h2>

	<ProvisionPipeline {stages} current={s.currentStep} {status} label={t('progress.stages')} decorative class="mb-5" />

	<ProgressTrack
		value={s.progress > 0 ? s.progress : null}
		label={t('progress.percentage')}
		tone={status === 'done' ? 'success' : 'accent'}
		active={status === 'running'}
		size="md"
	/>
	<div class="mt-2 flex items-center justify-between gap-3 text-xs text-ink-2">
		<span class="font-mono text-sm text-ink-0">
			<AnimatedNumber value={Math.round(percent)} />%
		</span>
		{#if s.elapsedSeconds !== null}
			<span class="tabular-nums">{t('progress.elapsed', { seconds: Math.floor(s.elapsedSeconds) })}</span>
		{/if}
	</div>
	<p class="mt-3 min-h-5 text-sm text-ink-2" role="status" aria-live="polite">{s.progressMessage}</p>

	<StepProgress {steps} current={s.currentStep} {status} label={t('progress.stages')} class="mt-5" />
</section>
