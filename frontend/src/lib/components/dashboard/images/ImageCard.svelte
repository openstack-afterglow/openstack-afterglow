<script lang="ts">
	import { OS_LOGOS, OS_EMOJI } from '$lib/utils/imageOs';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import type { ImageInfo } from '$lib/types/compute';
	import ImageVerificationBadge from '$lib/components/image/ImageVerificationBadge.svelte';
	import ImageDigest from '$lib/components/image/ImageDigest.svelte';
	import { imageReferenceParts, imageVerificationStatus } from '$lib/stores/imageCatalog.svelte';
	import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';

	let {
		img,
		current,
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
		current: boolean;
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
	const reference = $derived(imageReferenceParts(img));

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
	<div class="flex items-start gap-2.5 min-w-0">
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
			<div class="text-[var(--color-ink-0)] text-[13px] font-medium font-mono break-all">{reference.repository}</div>
			<div class="flex items-start gap-1.5 mt-1 min-w-0">
				<span class="text-xs text-[var(--color-ink-2)] font-mono shrink-0">tag</span>
				<Pill tone={reference.tag === 'latest' ? 'warm' : 'accent'} size="xs" class="image-tag">{reference.tag}</Pill>
			</div>
		</button>
	</div>

	<!-- Footer: status + visibility + size -->
	<div class="flex flex-wrap items-center gap-2 text-xs">
		<Pill tone={current ? 'accent' : 'neutral'} size="xs">{current ? '현재' : '이전'}</Pill>
		<StatusChip status={img.status} />
		<ImageVerificationBadge status={imageVerificationStatus(img)} />
		{#if img.visibility === 'public'}
			<Pill tone="info" size="xs">공개</Pill>
		{:else if img.visibility === 'shared'}
			<Pill tone="accent" size="xs">공유</Pill>
		{:else if img.visibility === 'community'}
			<Pill tone="warm" size="xs">커뮤니티</Pill>
		{:else}
			<Pill tone="neutral" size="xs">비공개</Pill>
		{/if}
		<span class="ml-auto text-[var(--color-ink-2)]">{formatSize(img.size ?? null)}</span>
	</div>
	<ImageDigest image={img} />

	<!-- Actions (own images only) -->
	{#if isOwner}
		<div class="flex flex-wrap items-center gap-1 pt-1 border-t border-[var(--color-line)]">
			{#if img.status === 'active' || img.status === 'deactivated'}
				<button
					onclick={() => onToggleActivation(img)}
					disabled={toggling}
					class="text-xs {img.status === 'active' ? 'text-[var(--color-state-warning)] hover:text-[var(--color-warm-2)]' : 'text-[var(--color-state-success)] hover:text-[var(--color-state-success)]'} disabled:text-[var(--color-ink-3)] transition-colors px-2 py-1 rounded hover:bg-[var(--color-surface-sunken)]"
				>{toggling ? '...' : img.status === 'active' ? '비활성화' : '활성화'}</button>
			{/if}
			<button
				onclick={() => onEdit(img)}
				class="text-xs text-[var(--color-accent)] hover:text-[var(--color-ink-0)] transition-colors px-2 py-1 rounded hover:bg-[var(--color-accent)]/15"
			>편집</button>
			<button
				onclick={() => onDelete(img.id, img.name)}
				disabled={deleting}
				class="text-xs text-[var(--color-state-danger)] hover:text-[var(--color-state-danger)] disabled:text-[var(--color-ink-3)] transition-colors px-2 py-1 rounded hover:bg-[var(--color-state-danger)]/15"
			>{deleting ? '삭제 중...' : '삭제'}</button>
		</div>
	{/if}
</article>

<style>
	:global(.image-tag) { min-width: 0; white-space: normal; overflow-wrap: anywhere; }
</style>
