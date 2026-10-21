<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-compute';
	import { onDestroy } from 'svelte';

	let {
		availableHosts,
		hostFilter = $bindable(),
		statusFilter = $bindable(),
		nameSearch = $bindable(),
		onChange,
	}: {
		availableHosts: string[];
		hostFilter: string;
		statusFilter: string;
		nameSearch: string;
		onChange: () => void;
	} = $props();

	let nameDebounceTimer = $state<ReturnType<typeof setTimeout> | null>(null);
	onDestroy(() => { if (nameDebounceTimer) clearTimeout(nameDebounceTimer); });

</script>

{#snippet statusLabel(status: string)}
	{#if status === 'ACTIVE'}{t('instances.status.active')}{:else if status === 'SHUTOFF'}{t('instances.status.shutoff')}{:else if status === 'ERROR'}{t('instances.status.error')}{:else if status === 'SHELVED_OFFLOADED'}{t('instances.status.shelvedOffloaded')}{:else if status === 'BUILD'}{t('instances.status.build')}{:else if status === 'PAUSED'}{t('instances.status.paused')}{:else if status === 'SUSPENDED'}{t('instances.status.suspended')}{:else}{status}{/if}
{/snippet}

<div class="flex flex-wrap gap-3 mb-4">
	<select
		bind:value={hostFilter}
		onchange={() => { onChange(); }}
		class="bg-surface-sunken border border-line-2 text-sm text-ink-2 rounded-lg px-2 py-1.5 focus:outline-none focus:border-action-warm"
	>
		<option value="">{t('instances.filters.allHosts')}</option>
		{#each availableHosts as h}
			<option value={h}>{h}</option>
		{/each}
	</select>

	<select
		bind:value={statusFilter}
		onchange={() => { onChange(); }}
		class="bg-surface-sunken border border-line-2 text-sm text-ink-2 rounded-lg px-2 py-1.5 focus:outline-none focus:border-action-warm"
	>
		<option value="">{t('instances.filters.allStatuses')}</option>
		{#each ['ACTIVE', 'SHUTOFF', 'ERROR', 'SHELVED_OFFLOADED', 'BUILD', 'PAUSED', 'SUSPENDED'] as s}
			<option value={s}>{@render statusLabel(s)}</option>
		{/each}
	</select>

	<input
		type="text"
		placeholder={t('instances.filters.nameSearch')}
		bind:value={nameSearch}
		oninput={() => {
			if (nameDebounceTimer) clearTimeout(nameDebounceTimer);
			nameDebounceTimer = setTimeout(() => { onChange(); }, 300);
		}}
		class="bg-surface-sunken border border-line-2 text-sm text-ink-2 rounded-lg px-3 py-1.5 w-40 focus:outline-none focus:border-action-warm"
	/>

</div>
