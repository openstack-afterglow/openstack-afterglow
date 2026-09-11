<script lang="ts">
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

	interface Props {
		adminMode?: boolean;
	}
	let { adminMode = false }: Props = $props();

	const s = createVmCreateStore({ adminMode: () => adminMode });
	provideVmCreate(s);

	onMount(() => s.init());
	onDestroy(() => s.destroy());
</script>

<SlidePanel onClose={closeWizard} ariaLabel="가상 머신 생성" dataTour="wizard-panel" width="w-full md:w-[75vw] max-w-4xl">
	<div class="h-full min-h-0 flex flex-col bg-surface-canvas">
		<div class="min-h-0 flex-1 overflow-y-auto p-4 md:p-8">
			{#if s.needsProjectSelect}
				<AdminProjectSelector />
			{:else if s.loading}
				<div class="flex items-center justify-center py-16">
					<LoadingSpinner size="lg" color="blue">데이터 로드 중...</LoadingSpinner>
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
						현재 단계의 일부 데이터를 불러오지 못했습니다.
						{#snippet actions()}
							<Button variant="danger-outline" size="sm" onclick={s.retryCurrentStep}>다시 시도</Button>
						{/snippet}
					</Alert>
				{/if}

				<div data-tour="wizard-stepper">
					<WizardStepper cur={s.visibleStepIndex} totalSteps={s.visibleTotalSteps} stepLabels={s.visibleStepLabels} goTo={s.goToVisible} />
				</div>

				<div class="mb-8" data-tour="wizard-body">
					{#if $wizard.step === 1}
						<WizardStep1Boot />
					{:else if $wizard.step === 2}
						<h2 class="mb-1 flex flex-wrap items-baseline gap-x-2 gap-y-1 text-lg font-semibold text-[var(--color-ink-0)]"><span>플레이버 선택</span><span class="text-sm font-normal text-[var(--color-ink-2)]">VM의 vCPU / 메모리 / 디스크 스펙</span></h2>
						<SelectFlavor flavors={s.flavors} selectedId={$wizard.flavorId} onSelect={s.selectFlavor} quota={s.flavorQuota} />
					{:else if $wizard.step === 3}
						<WizardStep3Library />
					{:else if $wizard.step === 4}
						<h2 class="text-lg font-semibold text-ink-0 mb-4">배포 전략 <span class="text-ink-3 text-sm font-normal">스케줄링 / 레이어 마운트</span></h2>
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
					{/if}
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
