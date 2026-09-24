<script lang="ts">
	import { useObjectBrowser } from '$lib/stores/objectBrowser.svelte';
	import { ActionMenu, FileIcon, SelectionCheckbox } from '$lib/components/ui';
	import { formatDate, formatObjectSize, shortContentType } from '$lib/utils/format';
	import { observeVisible } from '$lib/utils/observeVisible';
	import type { SwiftObject } from '$lib/types/objectStorage';

	let { obj, fullPath = false }: { obj: SwiftObject; fullPath?: boolean } = $props();

	const s = useObjectBrowser();
	const label = $derived(fullPath ? obj.name : (s.baseName(obj.name) || obj.name));
	const thumb = $derived(s.thumbnailUrl(obj));
	const previewable = $derived(s.isPreviewable(obj.content_type));
	let menuOpen = $state(false);

	function activate() {
		if (previewable) s.openPreview(obj);
		else s.showMeta(obj.name);
	}

	function onCardClick(event: MouseEvent) {
		const target = event.target as HTMLElement;
		if (target.closest('button, input, a, label')) return;
		s.toggleSelect(obj.name);
	}

	function onKeydown(event: KeyboardEvent) {
		if (event.target !== event.currentTarget) return;
		if (event.key === 'Enter') {
			event.preventDefault();
			activate();
		} else if (event.key === ' ') {
			event.preventDefault();
			s.toggleSelect(obj.name);
		}
	}
</script>

<div
	class="resource-selection-surface group flex flex-col overflow-hidden rounded-lg border border-line bg-surface-base transition-colors hover:bg-surface-sunken/40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
	data-selected={s.selected.has(obj.name)}
	role="button"
	tabindex="0"
	aria-label={`파일 ${label}`}
	onclick={onCardClick}
	ondblclick={activate}
	onkeydown={onKeydown}
	use:observeVisible={() => s.requestThumbnail(obj)}
>
	<div class="flex items-center gap-2 px-3 py-2">
		<SelectionCheckbox
			checked={s.selected.has(obj.name)}
			disabled={s.bulkDeleting || s.bulkMoving}
			ariaLabel={`${label} 선택`}
			onclick={() => s.toggleSelect(obj.name)}
		/>
		<FileIcon name={obj.name} contentType={obj.content_type} />
		<span class="min-w-0 flex-1 truncate text-sm text-ink-0 {fullPath ? 'font-mono text-xs' : ''}" title={obj.name}>{label}</span>
		<ActionMenu
			open={menuOpen}
			ariaLabel={`${label} 파일 작업`}
			onopen={() => { menuOpen = true; }}
			onclose={() => { menuOpen = false; }}
		>
			{#if previewable}
				<button
					onclick={() => { menuOpen = false; s.openPreview(obj); }}
					class="w-full px-3 py-1.5 text-left text-[13px] text-ink-2 transition-colors hover:bg-surface-sunken hover:text-ink-0"
				>미리보기</button>
			{/if}
			<button
				onclick={() => { menuOpen = false; s.downloadObject(obj.name); }}
				class="w-full px-3 py-1.5 text-left text-[13px] text-ink-2 transition-colors hover:bg-surface-sunken hover:text-ink-0"
			>다운로드</button>
			<button
				onclick={() => { menuOpen = false; s.showMeta(obj.name); }}
				class="w-full px-3 py-1.5 text-left text-[13px] text-ink-2 transition-colors hover:bg-surface-sunken hover:text-ink-0"
			>정보</button>
			<button
				onclick={() => { menuOpen = false; s.openRename(obj.name); }}
				class="w-full px-3 py-1.5 text-left text-[13px] text-ink-2 transition-colors hover:bg-surface-sunken hover:text-ink-0"
			>이름변경</button>
			<button
				onclick={() => { menuOpen = false; s.openMove(obj.name); }}
				class="w-full px-3 py-1.5 text-left text-[13px] text-ink-2 transition-colors hover:bg-surface-sunken hover:text-ink-0"
			>이동</button>
			<button
				onclick={() => { menuOpen = false; s.deleteObject(obj.name); }}
				class="w-full px-3 py-1.5 text-left text-[13px] text-state-danger-text transition-colors hover:bg-surface-sunken"
			>삭제</button>
		</ActionMenu>
	</div>

	<div class="flex aspect-[4/3] items-center justify-center overflow-hidden bg-surface-sunken">
		{#if thumb}
			<img src={thumb} alt="" loading="lazy" decoding="async" class="h-full w-full object-cover" />
		{:else}
			<FileIcon
				name={obj.name}
				contentType={obj.content_type}
				class="[&_svg]:h-12 [&_svg]:w-12"
			/>
		{/if}
	</div>

	<div class="flex items-center justify-between gap-2 px-3 py-2 text-xs text-ink-2">
		<span class="truncate" title={obj.content_type || '-'}>{shortContentType(obj.content_type)}</span>
		<span class="shrink-0 tabular-nums">{formatObjectSize(obj.bytes)}</span>
	</div>
	<div class="px-3 pb-2 text-xs text-ink-2 tabular-nums">{formatDate(obj.last_modified)}</div>
</div>
