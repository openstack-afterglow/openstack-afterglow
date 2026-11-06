<script lang="ts">
	let {
		ports = [],
		loading = false,
		markerStack = [],
		nextMarker = null,
		onPrev,
		onNext,
	}: {
		ports?: Array<{ id: string; name?: string }>;
		loading?: boolean;
		markerStack?: string[];
		nextMarker?: string | null;
		onPrev?: () => void;
		onNext?: () => void;
	} = $props();
</script>

{#each ports as port}
	<span>{port.name}</span>
{/each}
<span data-testid="marker-depth">{markerStack.length}</span>
<button disabled={loading || markerStack.length === 0} onclick={onPrev}>Previous ports</button>
<button disabled={loading || !nextMarker} onclick={onNext}>Next ports</button>
