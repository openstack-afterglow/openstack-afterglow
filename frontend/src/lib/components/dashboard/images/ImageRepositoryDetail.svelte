<script lang="ts">
	import { AnimatedNumber, Button, Card, CompactResourceCard, Pill, ResponsiveTable, StatusChip } from '$lib/components/ui';
	import { imageUploadTime, imageVerificationStatus, type ImageRepositoryGroup } from '$lib/stores/imageCatalog.svelte';
	import ImageDigest from '$lib/components/image/ImageDigest.svelte';
	import type { ImageInfo } from '$lib/types/compute';
	import ImageVerificationBadge from '$lib/components/image/ImageVerificationBadge.svelte';
	import { osLabel } from '$lib/utils/imageOs';
	import { t } from '$lib/i18n/ns/images-keys';

	let {
		group,
		onBack,
		onOpenTag,
	}: {
		group: ImageRepositoryGroup;
		onBack: () => void;
		onOpenTag: (imageId: string) => void;
	} = $props();

	let expandedTags = $state<Set<string>>(new Set());
	function formatSize(bytes: number | null | undefined): string {
		if (bytes == null) return '-';
		if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
		if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(0)} MB`;
		return `${bytes} B`;
	}
</script>

{#snippet versionRow(image: ImageInfo, tag: string, current: boolean)}
	{@const uploaded = imageUploadTime(image)}
	<tr>
		<td>
			<div class="tag-name">:{tag}</div>
			<Pill tone={current ? 'accent' : 'neutral'} size="xs">{current ? t('repositoryDetail.current') : t('repositoryDetail.previous')}</Pill>
			{#if tag === 'latest'}<Pill tone="warm" size="xs">{t('repositoryDetail.default')}</Pill>{/if}
		</td>
		<td><ImageDigest {image} /></td>
		<td><StatusChip status={image.status} /></td>
		<td><ImageVerificationBadge status={imageVerificationStatus(image)} /></td>
		<td>{image.os_distro ? osLabel(image.os_distro) : '-'}</td>
		<td>{formatSize(image.size)}</td>
		<td class="date">{uploaded === null ? '-' : new Date(uploaded).toISOString().slice(0, 10)}</td>
		<td class="action-cell"><Button variant="link" size="xs" onclick={() => onOpenTag(image.id)}>{t('repositoryDetail.viewDetails')}</Button></td>
	</tr>
{/snippet}

{#snippet versionCard(image: ImageInfo, tag: string, current: boolean)}
	{@const uploaded = imageUploadTime(image)}
	<CompactResourceCard>
		<div class="flex flex-wrap items-center gap-2">
			<h3 class="font-mono font-semibold text-sm text-ink-0 break-all">:{tag}</h3>
			<StatusChip status={image.status} />
			<Pill tone={current ? 'accent' : 'neutral'} size="xs">{current ? t('repositoryDetail.current') : t('repositoryDetail.previous')}</Pill>
			{#if tag === 'latest'}<Pill tone="warm" size="xs">{t('repositoryDetail.default')}</Pill>{/if}
		</div>
		<div class="flex flex-wrap items-center gap-2 text-xs text-ink-1">
			<ImageVerificationBadge status={imageVerificationStatus(image)} />
			<span>{image.os_distro ? osLabel(image.os_distro) : '-'}</span>
			<span>{formatSize(image.size)}</span>
		</div>
		{#snippet details()}
			<dl class="space-y-2 text-xs">
				<div><dt class="text-ink-2">{t('repositoryDetail.digest')}</dt><dd><ImageDigest {image} /></dd></div>
				<div><dt class="text-ink-2">{t('repositoryDetail.uploaded')}</dt><dd class="font-mono text-ink-1">{uploaded === null ? '-' : new Date(uploaded).toISOString().slice(0, 10)}</dd></div>
			</dl>
		{/snippet}
		{#snippet actions()}
			<Button variant="link" size="xs" onclick={() => onOpenTag(image.id)}>{t('repositoryDetail.viewDetails')}</Button>
		{/snippet}
	</CompactResourceCard>
{/snippet}

{#snippet previousToggle(tag: string, count: number)}
	<Button variant="ghost" size="xs" ariaLabel={expandedTags.has(tag) ? t('repositoryDetail.collapsePreviousLabel', { tag, count }) : t('repositoryDetail.showPreviousLabel', { tag, count })}
		ariaExpanded={expandedTags.has(tag)} onclick={() => {
			const next = new Set(expandedTags);
			if (next.has(tag)) next.delete(tag); else next.add(tag);
			expandedTags = next;
		}} class="min-h-11 lg:min-h-0 max-w-full !whitespace-normal">
		<AnimatedNumber value={count} format={(value) => expandedTags.has(tag) ? t('repositoryDetail.collapsePrevious', { count: Math.round(value) }) : t('repositoryDetail.showPrevious', { count: Math.round(value) })} />
	</Button>
{/snippet}

<Card surface="raised" padding="none" class="motion-fade repository-detail">
	<div class="detail-header">
		<Button variant="ghost" size="icon" ariaLabel={t('repositoryDetail.back')} onclick={onBack}>‹</Button>
		<div class="detail-heading">
			<p class="detail-kicker">{t('repositoryDetail.kicker')}</p>
			<h2>{group.repository}</h2>
			<p><AnimatedNumber value={group.tags.length} format={(value) => t('repositoryDetail.description', { tagCount: Math.round(value), imageCount: group.images.length })} /></p>
		</div>
	</div>

	<ResponsiveTable>
		{#snippet cards()}
			{#each group.tags as version (version.tag)}
				<div class="min-w-0 space-y-2 p-3">
					{@render versionCard(version.latest, version.tag, version.latest.id === version.current.id)}
					{#if version.images.length > 1}
						{@render previousToggle(version.tag, version.images.length - 1)}
						{#if expandedTags.has(version.tag)}
							{#each version.images.filter((image) => image.id !== version.latest.id) as image (image.id)}
								{@render versionCard(image, version.tag, false)}
							{/each}
						{/if}
					{/if}
				</div>
			{/each}
		{/snippet}
	<div class="table-wrap">
		<table>
			<thead>
				<tr>
					<th>{t('repositoryDetail.tag')}</th>
					<th>{t('repositoryDetail.digest')}</th>
					<th>{t('repositoryDetail.status')}</th>
					<th>{t('repositoryDetail.trust')}</th>
					<th>{t('repositoryDetail.os')}</th>
					<th>{t('repositoryDetail.size')}</th>
					<th>{t('repositoryDetail.uploaded')}</th>
					<th><span class="sr-only">{t('repositoryDetail.actions')}</span></th>
				</tr>
			</thead>
			<tbody>
				{#each group.tags as version (version.tag)}
					{@render versionRow(version.latest, version.tag, version.latest.id === version.current.id)}
					{#if version.images.length > 1}
						<tr><td colspan="8">
							{@render previousToggle(version.tag, version.images.length - 1)}
						</td></tr>
						{#if expandedTags.has(version.tag)}
							{#each version.images.filter((image) => image.id !== version.latest.id) as image (image.id)}
								{@render versionRow(image, version.tag, false)}
							{/each}
						{/if}
					{/if}
				{/each}
			</tbody>
		</table>
	</div>
	</ResponsiveTable>
</Card>

<style>
	:global(.repository-detail) { overflow: hidden; }
	.detail-header { display: flex; align-items: flex-start; gap: 0.75rem; padding: 1.25rem 1.5rem; border-bottom: 1px solid var(--color-line); }
	.detail-heading { min-width: 0; }
	.detail-kicker { margin: 0 0 0.3rem; color: var(--color-warm); font-size: 0.625rem; font-weight: 700; letter-spacing: 0.14em; }
	h2 { margin: 0; color: var(--color-ink-0); font-family: var(--font-mono); font-size: 1.05rem; overflow-wrap: anywhere; }
	.detail-heading p:last-child { margin: 0.35rem 0 0; color: var(--color-ink-2); font-size: 0.75rem; }
	.table-wrap { overflow-x: auto; }
	table { width: 100%; border-collapse: collapse; min-width: 48rem; }
	th, td { padding: 0.75rem 1rem; border-bottom: 1px solid var(--color-line); text-align: left; white-space: nowrap; }
	th { color: var(--color-ink-2); font-size: 0.625rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; }
	td { color: var(--color-ink-1); font-size: 0.75rem; }
	tbody tr:hover { background: var(--color-surface-sunken); }
	.tag-name { display: inline-block; max-width: 14rem; margin-right: 0.4rem; color: var(--color-ink-0); font-family: var(--font-mono); font-weight: 600; white-space: normal; overflow-wrap: anywhere; }
	.date { color: var(--color-ink-2); font-family: var(--font-mono); }
	.action-cell { text-align: right; }
</style>
