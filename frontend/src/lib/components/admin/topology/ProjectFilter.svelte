<script lang="ts">
	import { projectNames } from '$lib/stores/projectNames';

	let {
		projectFilter = $bindable<string | null>(null),
		searchText = $bindable(''),
		dropdownOpen = $bindable(false),
	}: {
		projectFilter: string | null;
		searchText: string;
		dropdownOpen: boolean;
	} = $props();

	let projectSuggestions = $derived(
		Array.from($projectNames.entries())
			.filter(([id, name]) =>
				searchText.length === 0 ||
				name.toLowerCase().includes(searchText.toLowerCase()) ||
				id.toLowerCase().includes(searchText.toLowerCase())
			)
			.slice(0, 10)
	);
</script>

<div class="relative project-filter-wrapper">
	<div class="flex items-center bg-surface-sunken border border-line-2 rounded-lg px-3 py-1.5 w-52 focus-within:border-action-warm">
		<input
			type="text"
			placeholder="프로젝트 검색..."
			bind:value={searchText}
			onfocus={() => (dropdownOpen = true)}
			oninput={() => { dropdownOpen = true; if (!searchText) { projectFilter = null; } }}
			class="bg-transparent text-sm text-ink-2 flex-1 outline-none min-w-0"
		/>
		{#if projectFilter}
			<button onclick={() => { projectFilter = null; searchText = ''; dropdownOpen = false; }} class="text-ink-3 hover:text-ink-0 ml-1 flex-shrink-0">✕</button>
		{/if}
	</div>
	{#if dropdownOpen && projectSuggestions.length > 0}
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div
			class="absolute top-full mt-1 left-0 w-64 bg-surface-base border border-line-2 rounded-lg shadow-[var(--shadow-restraint)] z-30 overflow-hidden"
			onmouseleave={() => {}}
		>
			{#each projectSuggestions as [id, name]}
				<button
					class="w-full text-left px-3 py-2 text-xs hover:bg-surface-sunken transition-colors {projectFilter === id ? 'bg-surface-selected/30 text-action-warm' : 'text-ink-2'}"
					onclick={() => { projectFilter = id; searchText = name; dropdownOpen = false; }}
				>
					<div class="font-medium truncate">{name}</div>
					<div class="text-ink-3 font-mono">{id.slice(0, 12)}...</div>
				</button>
			{/each}
		</div>
	{/if}
</div>
