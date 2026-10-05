<script lang="ts">
	import { t } from '$lib/i18n/ns/network-resources';
  import EmptyState from '$lib/components/ui/EmptyState.svelte';
</script>

<EmptyState headline={t('router.empty.title')} description={t('router.empty.description')} />
