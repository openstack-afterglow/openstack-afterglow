<script lang="ts">
	import SlidePanel from '../SlidePanel.svelte';

	interface Props {
		onClose: () => void;
		content?: string;
		dataTour?: string;
		storageKey?: string;
	}

	let { onClose, content = '테스트 내용', dataTour, storageKey }: Props = $props();
</script>

<SlidePanel {onClose} {dataTour} {storageKey} ariaLabel="테스트 패널">
	{content}
</SlidePanel>
