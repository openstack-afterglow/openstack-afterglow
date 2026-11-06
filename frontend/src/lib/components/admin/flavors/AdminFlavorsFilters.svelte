<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-compute';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	let { nameFilter = $bindable('') }: { nameFilter: string } = $props();
</script>

<RegexSearch id="admin-flavor-search" bind:value={nameFilter} label={t('flavors.fields.name')} placeholder={t('flavors.filters.nameSearch')} class="mb-4" />
