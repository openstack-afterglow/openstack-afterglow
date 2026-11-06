<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-compute';
	import type { Snippet } from 'svelte';
	import ResourceToolbar from '$lib/components/ui/ResourceToolbar.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	let { nameSearch = $bindable(''), actions }: { nameSearch: string; actions?: Snippet } = $props();
</script>

<ResourceToolbar label={t('instances.filters.toolbar')} {actions}>
	{#snippet filters()}
		<RegexSearch id="admin-instance-search" bind:value={nameSearch} class="min-w-0 w-full md:flex-1" />
	{/snippet}
</ResourceToolbar>
