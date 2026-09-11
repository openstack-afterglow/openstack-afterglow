<script lang="ts">
	import { onMount } from 'svelte';
	import { projectNames } from '$lib/stores/projectNames';

	let {
		availableHosts,
		hostFilter = $bindable(),
		statusFilter = $bindable(),
		nameSearch = $bindable(),
		projectFilter = $bindable(),
		projectSearchText = $bindable(),
		onChange,
	}: {
		availableHosts: string[];
		hostFilter: string;
		statusFilter: string;
		nameSearch: string;
		projectFilter: string;
		projectSearchText: string;
		onChange: () => void;
	} = $props();

	let projectDropdownOpen = $state(false);
	let nameDebounceTimer = $state<ReturnType<typeof setTimeout> | null>(null);

	let projectSuggestions = $derived(
		Array.from($projectNames.entries())
			.filter(([id, name]) =>
				projectSearchText.length === 0 ||
				name.toLowerCase().includes(projectSearchText.toLowerCase()) ||
				id.toLowerCase().includes(projectSearchText.toLowerCase())
			)
			.slice(0, 10)
	);

	function handleDocumentClick(e: MouseEvent) {
		const target = e.target as HTMLElement;
		if (!target.closest('.project-filter-wrapper')) {
			projectDropdownOpen = false;
		}
	}

	onMount(() => {
		document.addEventListener('click', handleDocumentClick);
		return () => document.removeEventListener('click', handleDocumentClick);
	});
</script>

<div class="flex flex-wrap gap-3 mb-4">
	<select
		bind:value={hostFilter}
		onchange={() => { onChange(); }}
		class="bg-surface-sunken border border-line-2 text-sm text-ink-2 rounded-lg px-2 py-1.5 focus:outline-none focus:border-action-warm"
	>
		<option value="">모든 호스트</option>
		{#each availableHosts as h}
			<option value={h}>{h}</option>
		{/each}
	</select>

	<select
		bind:value={statusFilter}
		onchange={() => { onChange(); }}
		class="bg-surface-sunken border border-line-2 text-sm text-ink-2 rounded-lg px-2 py-1.5 focus:outline-none focus:border-action-warm"
	>
		<option value="">모든 상태</option>
		{#each ['ACTIVE', 'SHUTOFF', 'ERROR', 'SHELVED_OFFLOADED', 'BUILD', 'PAUSED', 'SUSPENDED'] as s}
			<option value={s}>{s}</option>
		{/each}
	</select>

	<input
		type="text"
		placeholder="이름 검색..."
		bind:value={nameSearch}
		oninput={() => {
			if (nameDebounceTimer) clearTimeout(nameDebounceTimer);
			nameDebounceTimer = setTimeout(() => { onChange(); }, 300);
		}}
		class="bg-surface-sunken border border-line-2 text-sm text-ink-2 rounded-lg px-3 py-1.5 w-40 focus:outline-none focus:border-action-warm"
	/>

	<div class="relative project-filter-wrapper">
		<div class="flex items-center bg-surface-sunken border border-line-2 rounded-lg px-3 py-1.5 w-52 focus-within:border-action-warm">
			<input
				type="text"
				placeholder="프로젝트 검색..."
				bind:value={projectSearchText}
				onfocus={() => (projectDropdownOpen = true)}
				oninput={() => { projectDropdownOpen = true; if (!projectSearchText) { projectFilter = ''; } }}
				class="bg-transparent text-sm text-ink-2 flex-1 outline-none min-w-0"
			/>
			{#if projectFilter}
				<button
					onclick={() => {
						projectFilter = '';
						projectSearchText = '';
						projectDropdownOpen = false;
						onChange();
					}}
					class="text-ink-3 hover:text-ink-0 ml-1 flex-shrink-0"
				>✕</button>
			{/if}
		</div>
		{#if projectDropdownOpen && projectSuggestions.length > 0}
			<!-- svelte-ignore a11y_no_static_element_interactions -->
			<div
				class="absolute top-full mt-1 left-0 w-64 bg-surface-base border border-line-2 rounded-lg shadow-[var(--shadow-restraint)] z-20 overflow-hidden"
				onmouseleave={() => {}}
			>
				{#each projectSuggestions as [id, name]}
					<button
						class="w-full text-left px-3 py-2 text-xs hover:bg-surface-sunken transition-colors {projectFilter === id ? 'bg-surface-selected/30 text-action-warm' : 'text-ink-2'}"
						onclick={() => {
							projectFilter = id;
							projectSearchText = name;
							projectDropdownOpen = false;
							onChange();
						}}
					>
						<div class="font-medium truncate">{name}</div>
						<div class="text-ink-3 font-mono">{id.slice(0, 12)}...</div>
					</button>
				{/each}
			</div>
		{/if}
	</div>
</div>
