<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-compute';
	import type { GpuFilterOption } from './flavorGpuFilters';
	let {
		nameFilter = $bindable(),
		vcpuFilter = $bindable(),
		ramFilter = $bindable(),
		diskFilter = $bindable(),
		gpuFilter = $bindable(),
		gpuOptions,
	}: {
		nameFilter: string;
		vcpuFilter: string;
		ramFilter: string;
		diskFilter: string;
		gpuFilter: string;
		gpuOptions: GpuFilterOption[];
	} = $props();
</script>

<div class="flex flex-wrap gap-3 mb-4">
	<input
		type="text"
		placeholder={t('flavors.filters.nameSearch')}
		bind:value={nameFilter}
		class="bg-surface-sunken border border-line-2 text-sm text-ink-2 rounded-lg px-3 py-1.5 w-40 focus:outline-none focus:border-action-warm"
	/>
	<input
		type="number"
		placeholder={t('flavors.fields.vcpu')}
		bind:value={vcpuFilter}
		class="bg-surface-sunken border border-line-2 text-sm text-ink-2 rounded-lg px-3 py-1.5 w-24 focus:outline-none focus:border-action-warm"
	/>
	<input
		type="number"
		placeholder={t('flavors.fields.ramMb')}
		bind:value={ramFilter}
		class="bg-surface-sunken border border-line-2 text-sm text-ink-2 rounded-lg px-3 py-1.5 w-28 focus:outline-none focus:border-action-warm"
	/>
	<input
		type="number"
		placeholder={t('flavors.fields.diskGb')}
		bind:value={diskFilter}
		class="bg-surface-sunken border border-line-2 text-sm text-ink-2 rounded-lg px-3 py-1.5 w-28 focus:outline-none focus:border-action-warm"
	/>
	<select
		bind:value={gpuFilter}
		class="bg-surface-sunken border border-line-2 text-sm text-ink-2 rounded-lg px-3 py-1.5 focus:outline-none focus:border-action-warm"
	>
		{#each gpuOptions as option}
			<option value={option.value}>{option.label}</option>
		{/each}
	</select>
</div>
