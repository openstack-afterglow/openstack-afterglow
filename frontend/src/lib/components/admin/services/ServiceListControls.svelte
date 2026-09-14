<script lang="ts">
	import Button from '$lib/components/ui/Button.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';
	import { createServiceListState, serviceFilterLabel, type ServiceFilter, type ServiceListState } from './serviceList';

	let {
		view = $bindable(), filters, sortOptions, total, count, loading = false,
		searchPlaceholder = '호스트, 서비스 유형 등 검색', defaultSortKey = '',
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
</script>

<div class="mb-4 space-y-3" role="region" aria-label="서비스 목록 필터 및 정렬">
	<div class="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-4">
		<Field label="검색" for="{id}-search" class="min-w-0 lg:col-span-2">
			<TextInput id="{id}-search" type="search" bind:value={view.search} placeholder={searchPlaceholder} class="min-h-11 md:min-h-0" />
		</Field>
		<Field label="정렬 기준" for="{id}-sort" class="min-w-0">
			<SelectInput id="{id}-sort" bind:value={view.sortKey} class="min-h-11 md:min-h-0">
				<option value="">원본 순서</option>
				{#each sortOptions as option (option.key)}
					<option value={option.key}>{option.label}</option>
				{/each}
			</SelectInput>
		</Field>
		{#if view.sortKey}
		<div class="flex items-end">
			<Button variant="secondary" size="sm" class="min-h-11 w-full md:min-h-9"
				ariaLabel={view.sortDirection === 'asc' ? '내림차순으로 전환' : '오름차순으로 전환'}
				onclick={() => view.sortDirection = view.sortDirection === 'asc' ? 'desc' : 'asc'}>
				{view.sortDirection === 'asc' ? '오름차순 ↑' : '내림차순 ↓'}
			</Button>
		</div>
		{/if}
	</div>
	{#if filters.length}
		<div class="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
			{#each filters as filter (filter.key)}
				<Field label={filter.label} for="{id}-filter-{filter.key}" class="min-w-0">
					<SelectInput id="{id}-filter-{filter.key}" bind:value={() => view.filters[filter.key] ?? '', (value) => view.filters[filter.key] = value} class="min-h-11 md:min-h-0">
						<option value="">전체</option>
						{#if view.filters[filter.key] && !filter.options.some(option => option.value === view.filters[filter.key])}
							<option value={view.filters[filter.key]}>{serviceFilterLabel(view.filters[filter.key])} (현재 데이터 없음)</option>
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
		<span class="text-xs text-ink-2 tabular-nums" role="status">
			{#if loading && total === 0}불러오는 중…{:else}표시 {count} / 전체 {total}{#if loading} · 새로고침 중…{/if}{/if}
		</span>
		<Button variant="ghost" size="sm" class="min-h-11 md:min-h-0"
			onclick={() => view = createServiceListState(defaultSortKey)}>필터·정렬 초기화</Button>
	</div>
</div>
