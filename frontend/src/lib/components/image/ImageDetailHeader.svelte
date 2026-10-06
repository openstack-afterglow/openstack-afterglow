<script lang="ts">
	import { t } from '$lib/i18n/ns/images-keys';
	import { useImageDetailController } from '$lib/stores/imageDetailController.svelte';
	import { visibilityBadge, visibilityLabel } from '$lib/utils/format';
	import ImageVerificationBadge from './ImageVerificationBadge.svelte';
	import { imageVerificationStatus } from '$lib/stores/imageCatalog.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';

	interface Props {
		onClose?: () => void;
	}
	let { onClose }: Props = $props();

	const s = useImageDetailController();
</script>

<div class="flex items-start justify-between px-6 py-4 border-b border-[var(--color-line)] shrink-0">
	<div class="min-w-0 pr-4">
		{#if s.image}
			<h2 class="text-lg font-bold text-ink-0 break-all">{s.image.name}</h2>
			<div class="text-xs text-[var(--color-ink-2)] font-mono mt-1 break-all">{t('detailHeader.repositoryTag', { repository: s.image.repository ?? s.image.name, tag: s.image.tag ?? 'latest' })}</div>
			<div class="flex items-center gap-2 mt-1.5 flex-wrap">
				<StatusChip status={s.image.status} />
				<ImageVerificationBadge status={imageVerificationStatus(s.image)} />
				<span class="px-2 py-0.5 rounded text-xs font-medium {visibilityBadge(s.image.visibility)}">
					{visibilityLabel(s.image.visibility)}
				</span>
				{#if s.image.protected}
					<span class="px-2 py-0.5 rounded text-xs font-medium text-[var(--color-state-warning)] bg-[var(--color-state-warning)]/15">{t('detailHeader.protected')}</span>
				{/if}
			</div>
		{:else if s.loading}
			<div class="h-6 w-48 rounded motion-skeleton"></div>
		{/if}
	</div>
	<!-- 닫기 버튼은 SlidePanel 이 제공한다(`[data-slide-panel-close]`) -->
</div>
