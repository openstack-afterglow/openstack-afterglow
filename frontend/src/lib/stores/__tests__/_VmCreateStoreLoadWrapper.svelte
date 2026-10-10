<script lang="ts">
	import { onDestroy } from 'svelte';
	import { createVmCreateStore } from '../vmCreateStore.svelte';

	let { adminMode = false }: { adminMode?: boolean } = $props();
	const store = createVmCreateStore({ adminMode: () => adminMode });
	onDestroy(() => store.destroy());
</script>

<button data-testid="init" onclick={() => store.init()}>init</button>
<button data-testid="destroy" onclick={() => store.destroy()}>destroy</button>
<button data-testid="step-two" onclick={() => store.goTo(2)}>step two</button>
<button data-testid="step-five" onclick={() => store.goTo(5)}>step five</button>
<button data-testid="step-six" onclick={() => store.goTo(6)}>step six</button>
<button data-testid="project-a" onclick={() => store.selectAdminProject('project-a', 'Project A')}>project a</button>
<button data-testid="project-b" onclick={() => store.selectAdminProject('project-b', 'Project B')}>project b</button>
<button data-testid="select-first-flavor" onclick={() => store.flavors[0] && store.selectFlavor(store.flavors[0].id, store.flavors[0].name)}>select flavor</button>
<button data-testid="refresh-manual" onclick={() => store.refreshFlavorOptions('manual')}>refresh</button>
<button data-testid="refresh-periodic" onclick={() => store.refreshFlavorOptions('periodic')}>periodic</button>
<button data-testid="deploy" onclick={() => store.deploy()}>deploy</button>
<button data-testid="next" onclick={() => store.canNext && store.nextStep()}>next</button>
<button data-testid="reset" onclick={() => store.handleReset()}>reset</button>
<span data-testid="loading">{store.loading ? 'loading' : 'ready'}</span>
<span data-testid="flavor">{store.flavors[0]?.name ?? 'none'}</span>
<span data-testid="network">{store.wizardState.networkName ?? 'none'}</span>
<span data-testid="quota">{store.flavorQuota?.cores?.limit ?? 'none'}</span>
<span data-testid="step">{store.wizardState.step}</span>
<span data-testid="selected-flavor">{store.wizardState.flavorId ?? 'none'}</span>
<span data-testid="flavor-block">{store.selectedFlavorBlock ?? 'none'}</span>
<span data-testid="can-next">{store.canNext ? 'yes' : 'no'}</span>
<span data-testid="refreshing">{store.flavorRefreshing ? 'refreshing' : 'idle'}</span>
<span data-testid="refresh-error">{store.flavorRefreshError ?? 'none'}</span>
<span data-testid="background-refreshing">{store.flavorBackgroundRefreshing ? 'refreshing' : 'idle'}</span>
<span data-testid="background-refresh-error">{store.flavorBackgroundRefreshError ?? 'none'}</span>
<span data-testid="deploying">{store.deploying ? 'deploying' : 'idle'}</span>
<span data-testid="deploy-step">{store.currentStep}</span>
<span data-testid="elapsed">{store.elapsedSeconds ?? 'none'}</span>
<span data-testid="step-elapsed">{JSON.stringify(store.stepElapsedSeconds)}</span>
