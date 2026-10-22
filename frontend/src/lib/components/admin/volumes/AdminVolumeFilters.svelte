<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-storage';
	import { volumeStatusLabel } from './AdminVolumeStatusSummary.svelte';
	import { onDestroy } from 'svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';

	let {
		statusFilter = $bindable(''), nameSearch = $bindable(''),
		volumeType = $bindable(''), minSize = $bindable(''), maxSize = $bindable(''),
		statusOptions, onChange, onInvalidate = () => {},
	}: {
		statusFilter: string; nameSearch: string;
		volumeType?: string; minSize?: string; maxSize?: string;
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

<div class="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5" data-testid="admin-volume-filters">
	<Field label={t('volumeList.column.status')} for="admin-volume-status">
		<SelectInput id="admin-volume-status" bind:value={statusFilter} onchange={(event) => { statusFilter = (event.target as HTMLSelectElement).value; changed(); }}>
			<option value="">{t('volumeList.allStatuses')}</option>
			{#each statusOptions as status}<option value={status}>{volumeStatusLabel(status)}</option>{/each}
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
</div>
