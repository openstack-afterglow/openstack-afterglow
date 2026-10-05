<script lang="ts">
	import { t } from '$lib/i18n/ns/object-storage';
	import RichText from '$lib/i18n/RichText.svelte';
</script>

<div class="mt-4 px-4 py-3 text-xs text-warm-text/80 bg-amber-950/20 border border-action-warm/50 rounded-lg">
	<RichText segments={t.rich('buckets.quarantineNotice.body')} classes={{ strong: 'text-warm-text' }} />
</div>
