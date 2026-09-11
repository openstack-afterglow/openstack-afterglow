<script lang="ts">
	import { createVmCreateStore } from '../vmCreateStore.svelte';

	let { adminMode = false }: { adminMode?: boolean } = $props();
	const store = createVmCreateStore({ adminMode: () => adminMode });
</script>

<button data-testid="init" onclick={() => store.init()}>init</button>
<button data-testid="destroy" onclick={() => store.destroy()}>destroy</button>
<button data-testid="step-five" onclick={() => store.goTo(5)}>step five</button>
<button data-testid="project-a" onclick={() => store.selectAdminProject('project-a', 'Project A')}>project a</button>
<button data-testid="project-b" onclick={() => store.selectAdminProject('project-b', 'Project B')}>project b</button>
<span data-testid="loading">{store.loading ? 'loading' : 'ready'}</span>
<span data-testid="flavor">{store.flavors[0]?.name ?? 'none'}</span>
<span data-testid="network">{store.wizardState.networkName ?? 'none'}</span>
<span data-testid="quota">{store.flavorQuota?.cores?.limit ?? 'none'}</span>
