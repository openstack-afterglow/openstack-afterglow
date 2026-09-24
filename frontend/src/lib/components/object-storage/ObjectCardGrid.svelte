<script lang="ts">
	import { useObjectBrowser } from '$lib/stores/objectBrowser.svelte';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import { EmptyState, SelectionCheckbox } from '$lib/components/ui';
	import ObjectFileCard from './ObjectFileCard.svelte';
	import ObjectFolderCard from './ObjectFolderCard.svelte';

	const s = useObjectBrowser();
	const folders = $derived(s.gridRows.filter((row) => row.isDir));
	const files = $derived(s.gridRows.filter((row) => !row.isDir));
	const searching = $derived(s.filterText.trim().length > 0);
</script>

{#if s.loading}
	<LoadingSkeleton variant="card" rows={8} />
{:else if s.gridRows.length === 0}
	<EmptyState
		icon="M2 6a2 2 0 012-2h4l2 2h6a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z"
		headline={searching ? '검색 결과가 없습니다' : '오브젝트가 없습니다'}
		description={searching
			? '다른 키워드를 입력하거나 검색 범위를 넓혀보세요'
			: '파일을 업로드하거나 새 폴더를 만들어보세요'}
	/>
{:else}
	<div class="space-y-4">
		<div class="flex items-center gap-2.5 border-b border-line pb-2">
			<SelectionCheckbox
				checked={s.visibleSelectedCount > 0 && s.visibleSelectedCount === s.visibleObjectCount}
				indeterminate={s.visibleSelectedCount > 0 && s.visibleSelectedCount < s.visibleObjectCount}
				disabled={s.bulkDeleting || s.bulkMoving}
				ariaLabel="표시된 오브젝트 전체 선택"
				onclick={s.toggleSelectAll}
			/>
			<span class="text-xs text-ink-2">{s.visibleObjectCount}개</span>
		</div>

		{#if folders.length}
			<section class="space-y-2">
				<h3 class="text-xs font-medium uppercase tracking-wider text-ink-2">폴더</h3>
				<div class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
					{#each folders as row (row.obj.name)}
						<ObjectFolderCard obj={row.obj} />
					{/each}
				</div>
			</section>
		{/if}

		{#if files.length}
			<section class="space-y-2">
				<h3 class="text-xs font-medium uppercase tracking-wider text-ink-2">파일</h3>
				<div class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
					{#each files as row (row.obj.name)}
						<ObjectFileCard obj={row.obj} fullPath={row.fullPath} />
					{/each}
				</div>
			</section>
		{/if}
	</div>
{/if}
