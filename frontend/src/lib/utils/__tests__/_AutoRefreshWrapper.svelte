<script lang="ts">
	import { untrack } from 'svelte';
	import { createAutoRefresh } from '../autoRefresh.svelte';

	interface Props {
		fn?: () => void | Promise<void>;
		storageKey?: string;
		defaultActive?: boolean;
		defaultInterval?: number;
		invokeOnMount?: boolean;
	}

	let {
		fn = () => {},
		storageKey = 'test-key',
		defaultActive = true,
		defaultInterval = 30,
		invokeOnMount = false,
	}: Props = $props();

	let state = untrack(() => createAutoRefresh(fn, {
		storageKey,
		defaultActive,
		defaultInterval,
		invokeOnMount,
	}));
</script>

<div data-testid="active">{state.active}</div>
<div data-testid="interval">{state.intervalSeconds}</div>
<button data-testid="force-refresh" onclick={() => state.refresh()}>refresh</button>
