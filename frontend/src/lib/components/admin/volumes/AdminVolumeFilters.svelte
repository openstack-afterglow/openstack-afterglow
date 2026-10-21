<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-storage';
	import { volumeStatusLabel } from './AdminVolumeStatusSummary.svelte';
	import { onDestroy } from 'svelte';

	let {
		statusFilter = $bindable(''),
		nameSearch = $bindable(''),
		statusOptions,
		onChange,
	}: {
		statusFilter: string;
		nameSearch: string;
		statusOptions: string[];
		onChange: () => void;
	} = $props();

	let nameDebounceTimer = $state<ReturnType<typeof setTimeout> | null>(null);
	onDestroy(() => { if (nameDebounceTimer) clearTimeout(nameDebounceTimer); });

</script>

<div class="flex flex-wrap gap-3 mb-4">
	<select
		bind:value={statusFilter}
		onchange={() => { onChange(); }}
		class="bg-surface-sunken border border-line-2 text-sm text-ink-2 rounded-lg px-2 py-1.5 focus:outline-none focus:border-action-warm"
	>
		<option value="">{t('volumeList.allStatuses')}</option>
		{#each statusOptions as status}
			<option value={status}>{volumeStatusLabel(status)}</option>
		{/each}
	</select>
	<input
		type="text"
		placeholder={t('volumeList.searchName')}
		bind:value={nameSearch}
		oninput={() => {
			if (nameDebounceTimer) clearTimeout(nameDebounceTimer);
			nameDebounceTimer = setTimeout(() => { onChange(); }, 300);
		}}
		class="bg-surface-sunken border border-line-2 text-sm text-ink-2 rounded-lg px-3 py-1.5 w-40 focus:outline-none focus:border-action-warm"
	/>
</div>
