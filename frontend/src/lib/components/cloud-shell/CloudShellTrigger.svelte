<script lang="ts">
	import Button from '$lib/components/ui/Button.svelte';
	import { cloudShell } from '$lib/stores/cloudShell.svelte';
</script>

<Button
	variant="ghost"
	size="icon"
	class="!size-11 lg:!size-8"
	onclick={() => cloudShell.openConsent()}
	ariaLabel="Cloud Shell 열기"
	title="Cloud Shell 열기"
	ariaPressed={cloudShell.visible}
>
	<svg class="size-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
		<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M5 7l4.5 5L5 17M12 17h7" />
	</svg>
</Button>
