<script lang="ts">
	import type { Project } from '$lib/types/quotas';

	let {
		projects,
		search = $bindable(''),
		selectedId = $bindable(''),
		selectedName = $bindable(''),
		onSelected,
	}: {
		projects: Project[];
		search?: string;
		selectedId?: string;
		selectedName?: string;
		onSelected: (id: string, name: string) => void;
	} = $props();

	let showDropdown = $state(false);

	const filtered = $derived(
		search
			? projects.filter(p => p.name.toLowerCase().includes(search.toLowerCase()))
			: projects
	);

	function pick(p: Project) {
		selectedId = p.id;
		selectedName = p.name;
		search = p.name;
		showDropdown = false;
		onSelected(p.id, p.name);
	}
</script>

<div class="mb-6 relative max-w-md">
	<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-projectselector-36">프로젝트 선택</label>
	<input id="field-projectselector-36"
		type="text"
		bind:value={search}
		onfocus={() => showDropdown = true}
		oninput={() => {
			showDropdown = true;
			if (!search) {
				selectedId = '';
				selectedName = '';
				onSelected('', '');
			}
		}}
		onblur={() => setTimeout(() => { showDropdown = false; }, 150)}
		placeholder="프로젝트 이름으로 검색..."
		class="w-full bg-surface-sunken border border-line-2 text-sm text-ink-2 rounded-lg px-3 py-2 focus:outline-none focus:border-action-warm"
	/>
	{#if showDropdown && filtered.length > 0}
		<div class="absolute z-10 w-full mt-1 bg-surface-sunken border border-line-2 rounded-lg shadow-[var(--shadow-restraint)] max-h-60 overflow-y-auto">
			{#each filtered as p (p.id)}
				<button
					type="button"
					onmousedown={() => pick(p)}
					class="w-full text-left px-3 py-2 text-sm text-ink-2 hover:bg-surface-selected transition-colors {selectedId === p.id ? 'bg-surface-selected text-ink-0' : ''}"
				>{p.name}</button>
			{/each}
		</div>
	{/if}
	{#if selectedName}
		<div class="mt-1 text-xs text-ink-3">선택됨: <span class="text-action-warm">{selectedName}</span></div>
	{/if}
</div>
