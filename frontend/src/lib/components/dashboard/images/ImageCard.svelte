<script lang="ts">
	import { OS_LOGOS, OS_EMOJI, osLabel } from '$lib/utils/imageOs';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import type { ImageInfo } from '$lib/types/compute';
	import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';

	let {
		img,
		isOwner,
		toggling,
		deleting,
		selected = false,
		selectable = false,
		selectionDisabled = false,
		onSelect,
		onToggleSelect,
		onToggleActivation,
		onEdit,
		onDelete,
	}: {
		img: ImageInfo;
		isOwner: boolean;
		toggling: boolean;
		deleting: boolean;
		selected?: boolean;
		selectable?: boolean;
		selectionDisabled?: boolean;
		onSelect: (id: string) => void;
		onToggleSelect: () => void;
		onToggleActivation: (img: ImageInfo) => void;
		onEdit: (img: ImageInfo) => void;
		onDelete: (id: string, name: string) => void;
	} = $props();

	function formatSize(bytes: number | null): string {
		if (!bytes) return '-';
		const gb = bytes / 1024 / 1024 / 1024;
		return gb >= 1 ? `${Math.round(gb * 10) / 10} GB` : `${Math.round(bytes / 1024 / 1024)} MB`;
	}
</script>

<article
	class="resource-selection-surface bg-[var(--color-surface-raised)] border border-[var(--color-line)] rounded-lg p-4 flex flex-col gap-3 hover:border-[var(--color-line-2)] transition-colors"
	data-selected={selected}
>
	<!-- Header: selection + icon + detail -->
	<div class="flex items-center gap-2.5">
		<SelectionCheckbox
			checked={selected}
			disabled={!selectable || selectionDisabled}
			unavailable={!selectable}
			title={!selectable ? '현재 프로젝트 소유 이미지만 선택할 수 있습니다.' : undefined}
			onclick={onToggleSelect}
			ariaLabel={`${img.name} 선택`}
		/>
		<div class="w-10 h-10 rounded-lg bg-[var(--color-surface-sunken)] border border-[var(--color-line)] flex items-center justify-center overflow-hidden shrink-0">
			{#if img.os_distro && OS_LOGOS[img.os_distro]}
				<img src={OS_LOGOS[img.os_distro]} alt={img.os_distro} class="w-6 h-6 object-contain" />
			{:else if img.os_distro && OS_EMOJI[img.os_distro]}
				<span class="text-lg">{OS_EMOJI[img.os_distro]}</span>
			{:else}
				<span class="text-lg">💿</span>
			{/if}
		</div>
		<button
			type="button"
			class="flex-1 min-w-0 text-left"
			onclick={() => onSelect(img.id)}
		>
			<div class="text-[var(--color-ink-0)] text-[13px] font-medium truncate font-mono">{img.repository ?? img.name}</div>
			<div class="flex items-center gap-1.5 mt-1">
				<span class="text-[10px] text-[var(--color-ink-3)] font-mono">tag</span>
				<Pill tone={img.tag === 'latest' || !img.tag ? 'warm' : 'accent'} size="xs">{img.tag ?? 'latest'}</Pill>
			</div>
		</button>
	</div>

	<!-- Footer: status + visibility + size -->
	<div class="flex items-center gap-2 text-[11px]">
		<StatusChip status={img.status} />
		{#if img.visibility === 'public'}
			<Pill tone="info" size="xs">공개</Pill>
		{:else if img.visibility === 'shared'}
			<Pill tone="accent" size="xs">공유</Pill>
		{:else if img.visibility === 'community'}
			<Pill tone="warm" size="xs">커뮤니티</Pill>
		{:else}
			<Pill tone="neutral" size="xs">비공개</Pill>
		{/if}
		<span class="ml-auto text-[var(--color-ink-3)]">{formatSize(img.size ?? null)}</span>
	</div>

	<!-- Actions (own images only) -->
	{#if isOwner}
		<div class="flex items-center gap-1 pt-1 border-t border-[var(--color-line)]">
			{#if img.status === 'active' || img.status === 'deactivated'}
				<button
					onclick={() => onToggleActivation(img)}
					disabled={toggling}
					class="text-[11px] {img.status === 'active' ? 'text-[var(--color-state-warning)] hover:text-[var(--color-warm-2)]' : 'text-[var(--color-state-success)] hover:text-[var(--color-state-success)]'} disabled:text-[var(--color-ink-3)] transition-colors px-2 py-1 rounded hover:bg-[var(--color-surface-sunken)]"
				>{toggling ? '...' : img.status === 'active' ? '비활성화' : '활성화'}</button>
			{/if}
			<button
				onclick={() => onEdit(img)}
				class="text-[11px] text-[var(--color-accent)] hover:text-[var(--color-ink-0)] transition-colors px-2 py-1 rounded hover:bg-[var(--color-accent)]/15"
			>편집</button>
			<button
				onclick={() => onDelete(img.id, img.name)}
				disabled={deleting}
				class="text-[11px] text-[var(--color-state-danger)] hover:text-[var(--color-state-danger)] disabled:text-[var(--color-ink-3)] transition-colors px-2 py-1 rounded hover:bg-[var(--color-state-danger)]/15"
			>{deleting ? '삭제 중...' : '삭제'}</button>
		</div>
	{/if}
</article>
