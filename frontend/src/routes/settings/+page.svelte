<script lang="ts">
	import { goto } from '$app/navigation';
	import SettingsModal from '$lib/components/SettingsModal.svelte';

	let open = $state(true);

	function handleClose() {
		open = false;
		goto('/dashboard');
	}
</script>

<main id="main-content" tabindex="-1">
	<SettingsModal {open} onclose={handleClose} />
</main>
