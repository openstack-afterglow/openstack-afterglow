<script lang="ts">
	import { t } from '$lib/i18n/ns/object-storage';
	import RichText from '$lib/i18n/RichText.svelte';
	let { retentionDays = 30 }: { retentionDays?: number } = $props();
</script>

{#snippet heading(text: string)}<strong class="text-orange-400">{text}</strong>{/snippet}

<div class="mt-4 px-4 py-3 text-xs text-orange-400/80 bg-orange-950/20 border border-orange-900/50 rounded-lg">
	<RichText segments={t.rich('buckets.trashNotice.body', { retentionDays })} tags={{ heading }} />
</div>
