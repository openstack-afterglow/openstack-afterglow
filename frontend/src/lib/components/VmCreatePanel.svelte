<script lang="ts">
	import { t } from '$lib/i18n/ns/vm-wizard';
	import { onDestroy, onMount } from 'svelte';
	import { wizard, closeWizard } from '$lib/stores/wizard';
	import { createVmCreateStore, provideVmCreate } from '$lib/stores/vmCreateStore.svelte';
	import SelectFlavor from '$lib/components/wizard/SelectFlavor.svelte';
	import SelectStrategy from '$lib/components/wizard/SelectStrategy.svelte';
	import WizardStepper from '$lib/components/wizard/WizardStepper.svelte';
	import WizardHeader from '$lib/components/wizard/WizardHeader.svelte';
	import WizardFooter from '$lib/components/wizard/WizardFooter.svelte';
	import LoadingSpinner from '$lib/components/LoadingSpinner.svelte';
	import SlidePanel from '$lib/components/SlidePanel.svelte';
	import AdminProjectSelector from '$lib/components/wizard/AdminProjectSelector.svelte';
	import VmDeployProgress from '$lib/components/wizard/VmDeployProgress.svelte';
	import WizardStep1Boot from '$lib/components/wizard/WizardStep1Boot.svelte';
	import WizardStep3Library from '$lib/components/wizard/WizardStep3Library.svelte';
	import WizardStep5Config from '$lib/components/wizard/WizardStep5Config.svelte';
	import WizardStep6Review from '$lib/components/wizard/WizardStep6Review.svelte';
	import { Alert, Button } from '$lib/components/ui';
	import { enter } from '$lib/utils/motion';

	interface Props {
		adminMode?: boolean;
	}
	let { adminMode = false }: Props = $props();

	const s = createVmCreateStore({ adminMode: () => adminMode });
	provideVmCreate(s);

	onMount(() => s.init());
	onDestroy(() => s.destroy());

	/** Horizontal entrance offset of the step body: forward steps arrive from the right, backward from the left. */
	const STEP_SWAP_OFFSET_PX = 16;
	let stepDirection = $state<1 | -1>(1);
	let previousStep: number | null = null;
	$effect.pre(() => {
		const step = $wizard.step;
		if (previousStep !== null && step !== previousStep) stepDirection = step < previousStep ? -1 : 1;
		previousStep = step;
	});
</script>

<SlidePanel onClose={closeWizard} ariaLabel={t('panel.label')} dataTour="wizard-panel" width="w-full md:w-[75vw] max-w-4xl">
	<div class="h-full min-h-0 flex flex-col bg-surface-canvas">
		<div class="min-h-0 flex-1 overflow-y-auto p-4 md:p-8">
			{#if s.needsProjectSelect}
				<AdminProjectSelector />
			{:else if s.loading}
				<div class="flex items-center justify-center py-16">
					<LoadingSpinner size="lg" color="blue">{t('panel.loading')}</LoadingSpinner>
				</div>
			{:else if s.deploying}
				<VmDeployProgress />
			{:else}
				<WizardHeader
					step={s.visibleStepIndex}
					totalSteps={s.visibleTotalSteps}
					stepName={s.visibleStepLabels[s.visibleStepIndex - 1]}
					{adminMode}
					adminProjectName={s.adminSelectedProjectName}
					onReset={s.handleReset}
					onClose={closeWizard}
				/>

				{#if s.hasCurrentStepError}
					<Alert tone="danger" class="mb-6">
						{t('panel.stepError')}
						{#snippet actions()}
							<Button variant="danger-outline" size="sm" onclick={s.retryCurrentStep}>{t('panel.retry')}</Button>
						{/snippet}
					</Alert>
				{/if}

				<div data-tour="wizard-stepper" data-tour-library-visible={s.visibleStepIds.includes(3) ? 'true' : 'false'}>
					<WizardStepper cur={s.visibleStepIndex} totalSteps={s.visibleTotalSteps} stepLabels={s.visibleStepLabels} goTo={s.goToVisible} />
				</div>

				<div class="mb-8" data-tour="wizard-body">
					{#key $wizard.step}
						<div in:enter={{ x: STEP_SWAP_OFFSET_PX * stepDirection, y: 0 }}>
							{#if $wizard.step === 1}
								<WizardStep1Boot />
							{:else if $wizard.step === 2}
								<h2 class="mb-1 flex flex-wrap items-baseline gap-x-2 gap-y-1 text-lg font-semibold text-[var(--color-ink-0)]"><span>{t('panel.flavorTitle')}</span><span class="text-sm font-normal text-[var(--color-ink-2)]">{t('panel.flavorSubtitle')}</span></h2>
								<SelectFlavor
									{adminMode}
									flavors={s.flavors}
									selectedId={$wizard.flavorId}
									selectedName={$wizard.flavorName}
									onSelect={s.selectFlavor}
									quota={s.flavorQuota}
									bootVolumeSizeGb={$wizard.bootSource === 'volume' ? 0 : $wizard.bootVolumeSizeGb || undefined}
									refreshing={s.flavorRefreshing}
									refreshError={s.flavorRefreshError}
									backgroundRefreshing={s.flavorBackgroundRefreshing}
									backgroundRefreshError={s.flavorBackgroundRefreshError}
									onRefresh={s.refreshFlavorOptions}
								/>
							{:else if $wizard.step === 3}
								<WizardStep3Library />
							{:else if $wizard.step === 4}
								<h2 class="text-lg font-semibold text-ink-0 mb-4">{t('panel.strategyTitle')} <span class="text-ink-2 text-sm font-normal">{t('panel.strategySubtitle')}</span></h2>
								<SelectStrategy
									scheduling={$wizard.scheduling}
									onSchedulingChange={s.selectScheduling}
									strategy={$wizard.strategy}
									hasLibraries={$wizard.libraries.length > 0}
									hasPrebuilt={s.hasPrebuilt}
									onStrategyChange={s.selectStrategy}
									mountProtocol={$wizard.mountProtocol}
									onProtocolChange={s.selectMountProtocol}
								/>
							{:else if $wizard.step === 5}
								<WizardStep5Config />
							{:else if $wizard.step === 6}
								<WizardStep6Review />
								{#if s.flavorRefreshing}
									<p class="mt-2 text-sm text-[var(--color-ink-2)]" role="status" aria-live="polite">{t('panel.reviewRefreshing')}</p>
								{/if}
							{/if}
						</div>
					{/key}
				</div>
			{/if}
		</div>

		{#if !s.needsProjectSelect && !s.loading && !s.deploying}
			<WizardFooter
				imageDisplay={$wizard.imageName ?? ($wizard.bootSource === 'volume' ? ($wizard.bootVolumeName ?? null) : null)}
				flavorDisplay={$wizard.flavorName}
				libCount={$wizard.libraries.length}
				step={s.visibleStepIndex}
				totalSteps={s.visibleTotalSteps}
				canPrev={s.visibleStepIndex > 1}
				canNext={s.canNext}
				onCancel={closeWizard}
				onPrev={s.prevStep}
				onNext={s.nextStep}
				onDeploy={s.deploy}
			/>
		{/if}
	</div>
</SlidePanel>
