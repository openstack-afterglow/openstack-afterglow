<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { createWaygateProjectScope } from '$lib/utils/waygateProjectScope';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import WaygateProjectWorkspace from './WaygateProjectWorkspace.svelte';

	let { admin = false }: { admin?: boolean } = $props();
	const scope = createWaygateProjectScope(auth);
</script>

{#key $scope}
	{#if $scope}
		<WaygateProjectWorkspace scope={$scope} {admin} />
	{:else}
		<div class="p-4 md:p-8">
			<PageHeader breadcrumb={admin ? 'ADMIN / WAYGATE' : 'NETWORK / WAYGATE'} title={admin ? 'Waygate 관리' : 'Waygate'} />
			<Alert tone="info">Waygate를 관리할 프로젝트를 선택하세요.</Alert>
		</div>
	{/if}
{/key}
