<script lang="ts">
  import { t } from '$lib/i18n/ns/containers-shell';
  import RichText from '$lib/i18n/RichText.svelte';
  interface Props {
    available: boolean;
    message: string | null;
  }
  let { available, message }: Props = $props();
</script>

{#snippet label(text: string)}<span class="font-medium">{text}</span>{/snippet}

{#if !available}
  <div class="bg-yellow-900/30 border border-yellow-700 text-yellow-300 rounded-lg px-4 py-3 text-sm mb-4">
    <RichText segments={t.rich('instances.service.banner')} tags={{ label }} />
  </div>
{/if}
