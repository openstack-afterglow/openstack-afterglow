<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { closeWizard, wizard } from '../wizard';
	import { createVmCreateStore, provideVmCreate, type VmCreateStore } from '../vmCreateStore.svelte';
	import WizardStep5Config from '$lib/components/wizard/WizardStep5Config.svelte';
	import WizardStep6Review from '$lib/components/wizard/WizardStep6Review.svelte';
	import WizardFooter from '$lib/components/wizard/WizardFooter.svelte';

	let { adminMode = false, onStore }: { adminMode?: boolean; onStore: (store: VmCreateStore) => void } = $props();
	const store = createVmCreateStore({ adminMode: () => adminMode });
	provideVmCreate(store);
	onMount(() => onStore(store));
	onMount(() => store.init());
	onDestroy(() => store.destroy());
</script>

{#if $wizard.step === 5}<WizardStep5Config />{/if}
{#if $wizard.step === 6}<WizardStep6Review />{/if}
<button data-testid="next" onclick={() => store.nextStep()}>Next</button>
<button data-testid="deploy" onclick={() => store.deploy()}>Deploy</button>
<span data-testid="readiness">{store.canNext ? 'ready' : 'blocked'}</span>
<WizardFooter
	step={store.visibleStepIndex}
	totalSteps={store.visibleTotalSteps}
	canPrev={store.visibleStepIndex > 1}
	canNext={store.canNext}
	onCancel={closeWizard}
	onPrev={() => store.prevStep()}
	onNext={() => store.nextStep()}
	onDeploy={() => store.deploy()}
/>
