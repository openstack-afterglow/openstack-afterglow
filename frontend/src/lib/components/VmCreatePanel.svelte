<script lang="ts">
	import { t } from '$lib/i18n/ns/vm-wizard';
	import { onDestroy, onMount } from 'svelte';
	import { wizard, closeWizard } from '$lib/stores/wizard';
	import { createVmCreateStore, provideVmCreate } from '$lib/stores/vmCreateStore.svelte';
	import FlavorComposer from '$lib/components/wizard/FlavorComposer.svelte';
	import { consumerFlavorLabel } from '$lib/utils/flavorDisplay';
	import VmResourcePreparation from '$lib/components/wizard/VmResourcePreparation.svelte';
	import WizardStepper from '$lib/components/wizard/WizardStepper.svelte';
	import WizardHeader from '$lib/components/wizard/WizardHeader.svelte';
	import WizardFooter from '$lib/components/wizard/WizardFooter.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import SlidePanel from '$lib/components/SlidePanel.svelte';
	import AdminProjectSelector from '$lib/components/wizard/AdminProjectSelector.svelte';
	import VmDeployProgress from '$lib/components/wizard/VmDeployProgress.svelte';
	import WizardStep1Boot from '$lib/components/wizard/WizardStep1Boot.svelte';
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
	const composer = s.composer;
	let preparedScope = $state<string | null>(null);
	$effect(() => {
		if (!$composer.ready) preparedScope = null;
		if ($composer.ready && $composer.options && !$composer.loading && !$composer.error
			&& !$composer.historyLoading && !$composer.historyError && s.optionStatus.flavors === 'loaded') {
			preparedScope = $composer.draftScope;
		}
	});
	const preparingResources = $derived($wizard.step === 2 && (!$composer.ready || preparedScope !== $composer.draftScope));
	const showPreparation = $derived(!s.needsProjectSelect && preparingResources);
	const fullAreaLoading = $derived(showPreparation || s.loading && $wizard.step !== 2);
	const preparationTasks = $derived.by(() => {
		type Status = 'pending' | 'complete' | 'failed';
		const resources: Status = $composer.error ? 'failed' : $composer.options ? 'complete' : 'pending';
		return [
			...(!$composer.ready ? [{ id: 'auth', label: t('preparation.auth'), status: 'pending' as Status }] : []),
			{ id: 'resources', label: t('preparation.resources'), status: resources },
			{ id: 'gpu', label: t('preparation.gpu'), status: resources },
			{ id: 'history', label: t('preparation.history'), status: $composer.historyError ? 'failed' as Status : $composer.historyLoading || !$composer.ready ? 'pending' as Status : 'complete' as Status },
			{ id: 'catalog', label: t('preparation.catalog'), status: s.flavorRefreshing ? 'pending' as Status : s.optionStatus.flavors === 'error' ? 'failed' as Status : s.optionStatus.flavors === 'loaded' ? 'complete' as Status : 'pending' as Status },
		];
	});
	function retryPreparation() {
		if (!$composer.ready) return;
		if ($composer.error) void composer.refresh('manual');
		if ($composer.historyError) void composer.loadHistory();
		if (s.optionStatus.flavors === 'error') void s.refreshFlavorOptions('manual');
	}
	const flavorDisplay = $derived($wizard.flavorId ? consumerFlavorLabel(s.flavors.find(f => f.id === $wizard.flavorId)) : null);

	onMount(() => s.init());
	onDestroy(() => s.destroy());

	/** Horizontal entrance offset of the step body: forward steps arrive from the right, backward from the left. */
	const STEP_SWAP_OFFSET_PX = 16;
	let stepDirection = $state<1 | -1>(1);
	let previousStep: number | null = null;
	$effect.pre(() => {
		const step = s.visibleStepIndex;
		if (previousStep !== null && step !== previousStep) stepDirection = step < previousStep ? -1 : 1;
		previousStep = step;
	});
</script>

<SlidePanel onClose={closeWizard} ariaLabel={t('panel.label')} dataTour="wizard-panel" width="w-full md:w-[75vw] max-w-4xl" closePlacement={fullAreaLoading ? 'overlay' : 'flow'}>
	<div class="h-full min-h-0 flex flex-col" class:bg-surface-canvas={!fullAreaLoading}>
		<div data-vm-preparation-surface={fullAreaLoading ? '' : undefined} class={fullAreaLoading ? 'relative min-h-0 flex-1' : 'min-h-0 flex-1 overflow-y-auto p-4 md:p-8'}>
			{#if s.needsProjectSelect}
				<AdminProjectSelector />
			{:else if preparingResources}
				<VmResourcePreparation tasks={preparationTasks} error={preparationTasks.some(task => task.status === 'failed')} retrying={preparationTasks.some(task => task.status === 'pending')} onRetry={retryPreparation} />
			{:else if s.loading && $wizard.step !== 2}
				<LoadingState variant="surface" label={t('panel.loading')} />
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

				{#if s.hasCurrentStepError && $wizard.step !== 2}
					<Alert tone="danger" class="mb-6">
						{t('panel.stepError')}
						<ul class="mt-1 list-disc pl-5 text-sm" data-testid="step-error-items">
							{#each s.currentStepErrors as failure (failure.key)}
								<li>{t('panel.stepErrorItem', { item: failure.label, reason: failure.message })}</li>
							{/each}
						</ul>
						{#snippet actions()}
							<Button variant="danger-outline" size="sm" onclick={s.retryCurrentStep}>{t('panel.retry')}</Button>
						{/snippet}
					</Alert>
				{/if}

				<div data-tour="wizard-stepper">
					<WizardStepper cur={s.visibleStepIndex} totalSteps={s.visibleTotalSteps} stepLabels={s.visibleStepLabels} goTo={s.goToVisible} />
				</div>

				<div class="mb-8" data-tour="wizard-body">
					{#key $wizard.step}
						<div in:enter={{ x: STEP_SWAP_OFFSET_PX * stepDirection, y: 0 }}>
							{#if $wizard.step === 1}
								<WizardStep1Boot />
							{:else if $wizard.step === 2}
								<h2 class="mb-1 flex flex-wrap items-baseline gap-x-2 gap-y-1 text-lg font-semibold text-[var(--color-ink-0)]"><span>{t('panel.flavorTitle')}</span><span class="text-sm font-normal text-[var(--color-ink-2)]">{t('panel.flavorSubtitle')}</span></h2>
								<FlavorComposer
									controller={s.composer}
									{adminMode}
									flavors={s.flavors}
									selectedId={$wizard.flavorId}
									selectedName={$wizard.flavorName}
									onSelect={s.selectFlavor}
									quota={s.flavorQuota}
									bootVolumeSizeGb={$wizard.bootSource === 'volume' ? 0 : $wizard.bootVolumeSizeGb || undefined}
									initialLoading={s.optionStatus.flavors === 'idle' || s.optionStatus.flavors === 'loading'}
									refreshing={s.flavorRefreshing}
									refreshError={s.flavorRefreshError ?? s.optionErrors.flavors ?? null}
									backgroundRefreshing={s.flavorBackgroundRefreshing}
									backgroundRefreshError={s.flavorBackgroundRefreshError}
									onRefresh={s.refreshFlavorOptions}
								/>
							{:else if $wizard.step === 5}
								<WizardStep5Config />
							{:else if $wizard.step === 6}
								<WizardStep6Review />
								{#if s.flavorRefreshing}
									<LoadingState variant="inline" label={t('panel.reviewRefreshing')} class="mt-2" />
								{/if}
							{/if}
						</div>
					{/key}
				</div>
			{/if}
		</div>

		{#if !s.needsProjectSelect && !preparingResources && (!s.loading || $wizard.step === 2) && !s.deploying}
			<WizardFooter
				imageDisplay={$wizard.imageName ?? ($wizard.bootSource === 'volume' ? ($wizard.bootVolumeName ?? null) : null)}
				{flavorDisplay}
				step={s.visibleStepIndex}
				totalSteps={s.visibleTotalSteps}
				canPrev={s.visibleStepIndex > 1}
				canNext={s.canNext}
				composer={$wizard.step === 2 ? composer : undefined}
				windowsUnsupported={s.windowsUnsupported}
				onCancel={closeWizard}
				onPrev={s.prevStep}
				onNext={s.nextStep}
				onDeploy={s.deploy}
			/>
		{/if}
	</div>
</SlidePanel>
