<script lang="ts">
	import { useObjectBrowser } from '$lib/stores/objectBrowser.svelte';
	import { ActionMenu, FileIcon, SelectionCheckbox } from '$lib/components/ui';
	import type { SwiftObject } from '$lib/types/objectStorage';

	let { obj }: { obj: SwiftObject } = $props();

	const s = useObjectBrowser();
	const label = $derived(s.baseName(obj.name) || obj.name);
	let menuOpen = $state(false);

	function open() {
		s.navigatePrefix(obj.name);
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
			open();
		} else if (event.key === ' ') {
			event.preventDefault();
			s.toggleSelect(obj.name);
		}
	}
</script>

<div
	class="resource-selection-surface group flex items-center gap-2.5 rounded-lg border border-line bg-surface-base px-3 py-2.5 transition-colors hover:bg-surface-sunken/40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
	data-selected={s.selected.has(obj.name)}
	role="button"
	tabindex="0"
	aria-label={`폴더 ${label}`}
	onclick={onCardClick}
	ondblclick={open}
	onkeydown={onKeydown}
>
	<SelectionCheckbox
		checked={s.selected.has(obj.name)}
		disabled={s.bulkDeleting || s.bulkMoving}
		ariaLabel={`${label} 선택`}
		onclick={() => s.toggleSelect(obj.name)}
	/>
	<FileIcon name={obj.name} isDir />
	<span class="min-w-0 flex-1 truncate text-sm font-medium text-ink-0" title={label}>{label}</span>
	<ActionMenu
		open={menuOpen}
		ariaLabel={`${label} 폴더 작업`}
		onopen={() => { menuOpen = true; }}
		onclose={() => { menuOpen = false; }}
	>
		<button
			onclick={() => { menuOpen = false; open(); }}
			class="w-full px-3 py-1.5 text-left text-[13px] text-ink-2 transition-colors hover:bg-surface-sunken hover:text-ink-0"
		>열기</button>
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
