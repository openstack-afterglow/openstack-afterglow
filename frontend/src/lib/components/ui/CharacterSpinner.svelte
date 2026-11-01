<script lang="ts">
	// Separate component so only mounted (in-flight) spinners subscribe to the shared clock;
	// settled glyphs elsewhere must not keep the 140ms ticker running.
	import { statusSignal } from '$lib/design/characterFormats.js';
	import { characterStep } from './characterTicker';

	let { class: className = '' }: { class?: string } = $props();
</script>

<span class="{className}" data-signal="active" data-art={statusSignal('spinner', $characterStep)} aria-hidden="true"></span>
