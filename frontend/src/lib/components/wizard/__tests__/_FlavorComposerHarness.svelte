<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { wizard } from '$lib/stores/wizard';
	import { createVmCreateStore, type VmCreateStore } from '$lib/stores/vmCreateStore.svelte';
	import FlavorComposer from '../FlavorComposer.svelte';
	import WizardFooter from '../WizardFooter.svelte';
	import WizardStepper from '../WizardStepper.svelte';
	let { adminMode = false, navigationControls = false, onStore }: { adminMode?: boolean; navigationControls?: boolean; onStore?: (store: VmCreateStore) => void } = $props();
	const s = createVmCreateStore({ adminMode: () => adminMode });
	onMount(() => { onStore?.(s); s.init(); });
	onDestroy(() => s.destroy());
</script>
<button onclick={() => s.selectAdminProject('target-a', 'Target A')}>Target A</button>
<button onclick={() => s.selectAdminProject('target-b', 'Target B')}>Target B</button>
<button onclick={() => s.handleReset()}>Reset wizard</button>
<span data-testid="native-selected">{$wizard.flavorId ?? 'none'}</span>
<span data-testid="wizard-step">{$wizard.step}</span>
<span data-testid="native-flavors">{s.flavors.map(flavor => flavor.id).join(',')}</span>
<span data-testid="can-next">{s.canNext ? 'yes' : 'no'}</span>
{#if navigationControls}
	<WizardStepper cur={s.visibleStepIndex} totalSteps={s.visibleTotalSteps} stepLabels={s.visibleStepLabels} goTo={s.goToVisible} />
	<button onclick={s.prevStep}>Previous step</button>
	<button onclick={s.nextStep}>Next step</button>
	<button onclick={() => s.goTo(5)}>Jump to configuration</button>
	<button onclick={() => s.goToVisible(3)}>Jump by visible step</button>
{/if}
<FlavorComposer controller={s.composer} {adminMode} flavors={s.flavors} selectedId={$wizard.flavorId} selectedName={$wizard.flavorName} onSelect={s.selectFlavor} quota={s.flavorQuota} bootVolumeSizeGb={$wizard.bootVolumeSizeGb} initialLoading={s.optionStatus.flavors === 'idle' || s.optionStatus.flavors === 'loading'} refreshing={s.flavorRefreshing} refreshError={s.flavorRefreshError ?? s.optionErrors.flavors ?? null} backgroundRefreshing={s.flavorBackgroundRefreshing} backgroundRefreshError={s.flavorBackgroundRefreshError} onRefresh={s.refreshFlavorOptions} />
<WizardFooter step={s.visibleStepIndex} totalSteps={s.visibleTotalSteps} canPrev={s.visibleStepIndex > 1} canNext={s.canNext} composer={$wizard.step === 2 ? s.composer : undefined} onCancel={() => {}} onPrev={s.prevStep} onNext={s.nextStep} onDeploy={s.deploy} />
