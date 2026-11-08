<script lang="ts">
	import HeaderAccountControls from '../HeaderAccountControls.svelte';

	let { unread = false, logoutDisabled = false, onlogout = () => {}, allowPath }: {
		unread?: boolean;
		logoutDisabled?: boolean;
		onlogout?: () => void;
		allowPath?: (href: string) => boolean;
	} = $props();
	let outsideActivations = $state(0);
</script>

<button type="button" data-testid="outside" onmousedown={() => { outsideActivations += 1; }} onclick={() => { outsideActivations += 1; }}>밖</button>
<output data-testid="outside-activations">{outsideActivations}</output>
<HeaderAccountControls username="alice" title="alice @ lab" {unread} {logoutDisabled} {onlogout} {allowPath} />
