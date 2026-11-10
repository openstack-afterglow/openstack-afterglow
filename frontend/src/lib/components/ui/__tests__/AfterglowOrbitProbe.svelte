<script lang="ts">
	// Test double for AfterglowOrbit: exposes the props a caller passed, so wiring tests can see them.
	let { interactive = false }: { interactive?: boolean } = $props();
</script>

<span data-testid="orbit-probe" data-interactive={String(interactive)}></span>
