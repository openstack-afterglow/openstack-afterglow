<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { createVmCreateStore, provideVmCreate, type VmCreateStore } from '$lib/stores/vmCreateStore.svelte';
	import WizardStep5Config from '../WizardStep5Config.svelte';
	import WizardStep6Review from '../WizardStep6Review.svelte';
	import WizardFooter from '../WizardFooter.svelte';

	let { component, adminMode = false, onStore, onNext, onDeploy }: {
		component: 'config' | 'review' | 'footer';
		adminMode?: boolean;
		onStore?: (store: VmCreateStore) => void;
		onNext?: () => void;
		onDeploy?: () => void;
	} = $props();
	const store = createVmCreateStore({ adminMode: () => adminMode });
	provideVmCreate(store);
	onMount(() => {
		onStore?.(store);
		store.init();
	});
	onDestroy(() => store.destroy());
</script>

{#if component === 'config'}<WizardStep5Config />{/if}
{#if component === 'review'}<WizardStep6Review />{/if}
<WizardFooter
	step={store.visibleStepIndex}
	totalSteps={store.visibleTotalSteps}
	canPrev={store.visibleStepIndex > 1}
	canNext={store.canNext}
	windowsUnsupported={store.windowsUnsupported}
	onCancel={() => {}}
	onPrev={store.prevStep}
	onNext={onNext ?? store.nextStep}
	onDeploy={onDeploy ?? (() => { void store.deploy(); })}
/>
