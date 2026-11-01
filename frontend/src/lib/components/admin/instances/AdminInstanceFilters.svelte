<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-compute';
	import { onDestroy } from 'svelte';
	import ResourceSortSelect from '$lib/components/ui/ResourceSortSelect.svelte';
	import type { ResourceSort } from '$lib/utils/resourceSort';
	import type { Snippet } from 'svelte';
	import { Field, ResourceToolbar, TextInput, SelectInput } from '$lib/components/ui';

	let {
		availableHosts,
		hostFilter = $bindable(),
		statusFilter = $bindable(),
		nameSearch = $bindable(),
		sort = $bindable<ResourceSort>('created_desc'),
		onChange,
		actions,
	}: {
		availableHosts: string[];
		hostFilter: string;
		statusFilter: string;
		nameSearch: string;
		sort?: ResourceSort;
		onChange: () => void;
		actions?: Snippet;
	} = $props();

	let nameDebounceTimer = $state<ReturnType<typeof setTimeout> | null>(null);
	onDestroy(() => { if (nameDebounceTimer) clearTimeout(nameDebounceTimer); });

</script>

{#snippet statusLabel(status: string)}
	{#if status === 'ACTIVE'}{t('instances.status.active')}{:else if status === 'SHUTOFF'}{t('instances.status.shutoff')}{:else if status === 'ERROR'}{t('instances.status.error')}{:else if status === 'SHELVED_OFFLOADED'}{t('instances.status.shelvedOffloaded')}{:else if status === 'BUILD'}{t('instances.status.build')}{:else if status === 'PAUSED'}{t('instances.status.paused')}{:else if status === 'SUSPENDED'}{t('instances.status.suspended')}{:else}{status}{/if}
{/snippet}

<ResourceToolbar label={t('instances.filters.toolbar')} {actions}>
	{#snippet filters()}
		<Field label={t('instances.table.name')} for="admin-instance-search" class="min-w-0 w-full md:flex-1 md:basis-48">
			<TextInput id="admin-instance-search" type="search" placeholder={t('instances.filters.nameSearch')} ariaLabel={t('instances.filters.nameSearch')} bind:value={nameSearch} oninput={() => {
				if (nameDebounceTimer) clearTimeout(nameDebounceTimer);
				nameDebounceTimer = setTimeout(() => { onChange(); }, 300);
			}} />
		</Field>
		<Field label={t('instances.table.host')} for="admin-instance-host" class="min-w-0 max-w-full w-full md:w-auto"><SelectInput id="admin-instance-host" bind:value={hostFilter} ariaLabel={t('instances.filters.allHosts')} onchange={onChange}><option value="">{t('instances.filters.allHosts')}</option>{#each availableHosts as host}<option value={host}>{host}</option>{/each}</SelectInput></Field>
		<Field label={t('instances.table.status')} for="admin-instance-status" class="min-w-0 max-w-full w-full md:w-auto"><SelectInput id="admin-instance-status" bind:value={statusFilter} ariaLabel={t('instances.filters.allStatuses')} onchange={onChange}><option value="">{t('instances.filters.allStatuses')}</option>{#each ['ACTIVE', 'SHUTOFF', 'ERROR', 'SHELVED_OFFLOADED', 'BUILD', 'PAUSED', 'SUSPENDED'] as status}<option value={status}>{@render statusLabel(status)}</option>{/each}</SelectInput></Field>
		<ResourceSortSelect id="admin-instance-sort" bind:value={sort} onchange={onChange} />
	{/snippet}
</ResourceToolbar>
