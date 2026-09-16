<script lang="ts">
	let {
		searchInput = $bindable(),
		visibilityFilter = $bindable(),
		onSearchChange,
		onVisibilityChange,
	}: {
		searchInput: string;
		visibilityFilter: string;
		onSearchChange: (v: string) => void;
		onVisibilityChange: () => void;
	} = $props();

	let searchTimeout: ReturnType<typeof setTimeout>;

	function handleSearchInput() {
		clearTimeout(searchTimeout);
		searchTimeout = setTimeout(() => {
			onSearchChange(searchInput);
		}, 400);
	}
</script>

<div class="flex flex-wrap gap-3 mb-4">
	<input
		type="text"
		placeholder="이름 검색"
		bind:value={searchInput}
		oninput={handleSearchInput}
		class="bg-surface-sunken border border-line-2 text-sm text-ink-2 rounded-lg px-3 py-1.5 w-48 focus:outline-none focus:border-action-warm"
	/>
	<select
		bind:value={visibilityFilter}
		onchange={onVisibilityChange}
		class="bg-surface-sunken border border-line-2 text-sm text-ink-2 rounded-lg px-3 py-1.5 focus:outline-none focus:border-action-warm"
	>
		<option value="">공개 범위 전체</option>
		<option value="public">Public</option>
		<option value="community">Community</option>
		<option value="shared">Shared</option>
		<option value="private">Private</option>
	</select>
</div>
