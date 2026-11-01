<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-storage';
	import { getStatusLabel } from '$lib/config/statusColors';
	import { onDestroy } from 'svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';
	import ResourceSortSelect from '$lib/components/ui/ResourceSortSelect.svelte';
	import type { ResourceSort } from '$lib/utils/resourceSort';

	let {
		statusFilter = $bindable(''), nameSearch = $bindable(''),
		volumeType = $bindable(''), minSize = $bindable(''), maxSize = $bindable(''),
		sort = $bindable<ResourceSort>('created_desc'),
		statusOptions, onChange, onInvalidate = () => {},
	}: {
		statusFilter: string; nameSearch: string;
		volumeType?: string; minSize?: string; maxSize?: string;
		sort?: ResourceSort;
		statusOptions: string[]; onChange: () => void; onInvalidate?: () => void;
	} = $props();

	let timer: ReturnType<typeof setTimeout> | undefined;
	function changed(debounce = false) {
		clearTimeout(timer);
		onInvalidate();
		if (debounce) timer = setTimeout(onChange, 300);
		else onChange();
	}
	onDestroy(() => clearTimeout(timer));
</script>

<div class="admin-volume-filters" data-testid="admin-volume-filters">
	<Field label={t('volumeList.column.status')} for="admin-volume-status">
		<SelectInput id="admin-volume-status" bind:value={statusFilter} onchange={(event) => { statusFilter = (event.target as HTMLSelectElement).value; changed(); }}>
			<option value="">{t('volumeList.allStatuses')}</option>
			{#each statusOptions as status}<option value={status}>{getStatusLabel(status, 'volume')}</option>{/each}
		</SelectInput>
	</Field>
	<Field label={t('volumeList.filters.nameOrId')} for="admin-volume-search">
		<TextInput id="admin-volume-search" type="search" bind:value={nameSearch} placeholder={t('volumeList.searchName')} oninput={() => changed(true)} />
	</Field>
	<Field label={t('volumeDetail.volumeType')} for="admin-volume-type">
		<TextInput id="admin-volume-type" bind:value={volumeType} oninput={() => changed(true)} />
	</Field>
	<Field label={t('volumeList.filters.minSize')} for="admin-volume-min-size" help={t('volumeList.filters.sizeHelp')}>
		<TextInput id="admin-volume-min-size" inputmode="numeric" bind:value={minSize} oninput={() => changed(true)} />
	</Field>
	<Field label={t('volumeList.filters.maxSize')} for="admin-volume-max-size" help={t('volumeList.filters.sizeHelp')}>
		<TextInput id="admin-volume-max-size" inputmode="numeric" bind:value={maxSize} oninput={() => changed(true)} />
	</Field>
	<ResourceSortSelect id="admin-volume-sort" bind:value={sort} onchange={() => changed()} />
</div>

<style>
	.admin-volume-filters {
		display: grid;
		grid-template-columns: minmax(0, 1fr);
		column-gap: 0.75rem;
		row-gap: 0.375rem;
		width: 100%;
		min-width: 0;
	}
	.admin-volume-filters :global(.field) {
		display: grid;
		grid-template-rows: subgrid;
		grid-row: span 3;
		min-width: 0;
	}
	@media (min-width: 768px) {
		.admin-volume-filters { grid-template-columns: repeat(2, minmax(0, 1fr)); }
	}
	@media (min-width: 1024px) {
		.admin-volume-filters { grid-template-columns: repeat(3, minmax(0, 1fr)); }
	}
</style>
