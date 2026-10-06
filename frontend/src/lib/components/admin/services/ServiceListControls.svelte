<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-ops';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';
	import { createServiceListState, serviceFilterLabel, type ServiceFilter, type ServiceListState } from './serviceList';

	let {
		view = $bindable(), filters, sortOptions, total, count, loading = false,
		searchPlaceholder, defaultSortKey = '',
	}: {
		view: ServiceListState;
		filters: ServiceFilter[];
		sortOptions: { key: string; label: string }[];
		total: number;
		count: number;
		loading?: boolean;
		searchPlaceholder?: string;
		defaultSortKey?: string;
	} = $props();

	const id = $props.id();
	const shownSearchPlaceholder = $derived(searchPlaceholder ?? t('services.list.searchPlaceholder'));
</script>

<div class="mb-4 space-y-3" role="region" aria-label={t('services.list.controlsLabel')}>
	<div class="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-4">
		<Field label={t('services.list.search')} for="{id}-search" class="min-w-0 lg:col-span-2">
			<TextInput id="{id}-search" type="search" bind:value={view.search} placeholder={shownSearchPlaceholder} class="min-h-11 md:min-h-0" />
		</Field>
		<Field label={t('services.list.sortBy')} for="{id}-sort" class="min-w-0">
			<SelectInput id="{id}-sort" bind:value={view.sortKey} class="min-h-11 md:min-h-0">
				<option value="">{t('services.list.originalOrder')}</option>
				{#each sortOptions as option (option.key)}
					<option value={option.key}>{option.label}</option>
				{/each}
			</SelectInput>
		</Field>
		{#if view.sortKey}
		<div class="flex items-end">
			<Button variant="secondary" size="sm" class="min-h-11 w-full md:min-h-9"
				ariaLabel={view.sortDirection === 'asc' ? t('services.list.switchDescending') : t('services.list.switchAscending')}
				onclick={() => view.sortDirection = view.sortDirection === 'asc' ? 'desc' : 'asc'}>
				{view.sortDirection === 'asc' ? t('services.list.ascending') : t('services.list.descending')}
			</Button>
		</div>
		{/if}
	</div>
	{#if filters.length}
		<div class="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
			{#each filters as filter (filter.key)}
				<Field label={filter.label} for="{id}-filter-{filter.key}" class="min-w-0">
					<SelectInput id="{id}-filter-{filter.key}" bind:value={() => view.filters[filter.key] ?? '', (value) => view.filters[filter.key] = value} class="min-h-11 md:min-h-0">
						<option value="">{t('services.list.all')}</option>
						{#if view.filters[filter.key] && !filter.options.some(option => option.value === view.filters[filter.key])}
							<option value={view.filters[filter.key]}>{t('services.list.unavailableFilter', { value: serviceFilterLabel(view.filters[filter.key], filter.key) })}</option>
						{/if}
						{#each filter.options as option (option.value)}
							<option value={option.value}>{option.label}</option>
						{/each}
					</SelectInput>
				</Field>
			{/each}
		</div>
	{/if}
	<div class="flex flex-wrap items-center justify-between gap-2">
		<span class="inline-flex items-center gap-1.5 text-xs text-ink-2 tabular-nums" role="status">
			{#if loading}<ActivityIndicator size="xs" />{/if}
			<span>{#if loading && total === 0}{t('services.list.loading')}{:else}{t(loading ? 'services.list.countRefreshing' : 'services.list.count', { count, total })}{/if}</span>
		</span>
		<Button variant="ghost" size="sm" class="min-h-11 md:min-h-0"
			onclick={() => view = createServiceListState(defaultSortKey)}>{t('services.list.reset')}</Button>
	</div>
</div>
