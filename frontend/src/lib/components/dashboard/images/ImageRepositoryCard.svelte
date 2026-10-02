<script lang="ts">
	import { Button, Card, Pill } from '$lib/components/ui';
	import ImageVerificationBadge from '$lib/components/image/ImageVerificationBadge.svelte';
	import { imageReferenceParts, imageUploadTime, imageVerificationStatus, type ImageRepositoryGroup } from '$lib/stores/imageCatalog.svelte';
	import { OS_EMOJI, OS_LOGOS, osLabel } from '$lib/utils/imageOs';
	import { t } from '$lib/i18n/ns/images-keys';

	let {
		group,
		onOpen,
		onOpenTag,
	}: {
		group: ImageRepositoryGroup;
		onOpen: () => void;
		onOpenTag: (imageId: string) => void;
	} = $props();

	const previewTags = $derived(group.tags.slice(0, 5));
	const latest = $derived(group.latest);
	const distro = $derived(latest.os_distro ? osLabel(latest.os_distro) : t('repositoryCard.noOsInfo'));
	const uploadTime = $derived(imageUploadTime(latest));
	const trustCounts = $derived.by(() => {
		const counts = { verified: 0, unverified: 0, unavailable: 0 };
		for (const image of group.images) counts[imageVerificationStatus(image)]++;
		return counts;
	});
</script>

<Card surface="raised" padding="lg" class="repository-card">
	<div class="repository-header">
		<div class="repository-avatar">
			{#if latest.os_distro && OS_LOGOS[latest.os_distro]}
				<img src={OS_LOGOS[latest.os_distro]} alt="" />
			{:else if latest.os_distro && OS_EMOJI[latest.os_distro]}
				<span aria-hidden="true">{OS_EMOJI[latest.os_distro]}</span>
			{:else}
				<span aria-hidden="true">◈</span>
			{/if}
		</div>
		<div class="repository-heading">
			<button type="button" class="repository-link" onclick={onOpen}>{group.repository}</button>
			<p>{distro}</p>
		</div>
	</div>

	<div class="repository-meta">
		<Pill tone="accent" dot>{t('repositoryCard.imageCount', { tagCount: group.tags.length, imageCount: group.images.length })}</Pill>
		<span class="trust-counts">
			<Pill tone="success" size="xs">{t('repositoryCard.verifiedCount', { count: trustCounts.verified })}</Pill>
			<Pill tone="warning" size="xs">{t('repositoryCard.unverifiedCount', { count: trustCounts.unverified })}</Pill>
			<Pill tone="neutral" size="xs">{t('repositoryCard.unavailableCount', { count: trustCounts.unavailable })}</Pill>
		</span>
		<span>{t('repositoryCard.recentUpload')}</span>
		<code>:{imageReferenceParts(latest).tag}</code>
		{#if uploadTime !== null}
			<time datetime={latest.created_at ?? ''}>{new Date(uploadTime).toISOString().slice(0, 10)}</time>
		{/if}
	</div>

	<div class="tag-section">
		<div class="section-label">{t('repositoryCard.selectVersion')}</div>
		<div class="tag-list">
			{#each previewTags as version (version.tag)}
				{@const image = version.latest}
				<button type="button" class="tag-chip" onclick={() => onOpenTag(image.id)}>
					<span>:{version.tag}</span>
					<Pill tone={image.id === version.current.id ? 'accent' : 'neutral'} size="xs">{image.id === version.current.id ? t('repositoryCard.current') : t('repositoryCard.previous')}</Pill>
					{#if version.tag === 'latest'}<Pill tone="warm" size="xs">{t('repositoryCard.default')}</Pill>{/if}
					<ImageVerificationBadge status={imageVerificationStatus(image)} />
					{#if version.images.length > 1}<span>{t('repositoryCard.uploadCount', { count: version.images.length })}</span>{/if}
				</button>
			{/each}
			{#if group.tags.length > previewTags.length}
				<span class="more-tags">+{group.tags.length - previewTags.length}</span>
			{/if}
		</div>
	</div>

	<Button variant="ghost" size="sm" class="browse-button" onclick={onOpen}>{t('repositoryCard.browseTags')}</Button>
</Card>

<style>
	:global(.repository-card) {
		display: grid;
		gap: 1rem;
		transition: border-color 0.15s, transform 0.15s, box-shadow 0.15s;
	}
	:global(.repository-card:hover) {
		border-color: var(--color-line-2);
		box-shadow: 0 12px 30px color-mix(in oklab, var(--color-surface-canvas) 45%, transparent);
		transform: translateY(-1px);
	}
	.repository-header { display: flex; align-items: center; gap: 0.75rem; min-width: 0; }
	.repository-avatar {
		width: 2.75rem;
		height: 2.75rem;
		flex: 0 0 auto;
		display: grid;
		place-items: center;
		border: 1px solid var(--color-line-2);
		border-radius: 0.75rem;
		background: var(--color-surface-sunken);
		color: var(--color-warm);
		font-size: 1.25rem;
	}
	.repository-avatar img { width: 1.8rem; height: 1.8rem; object-fit: contain; }
	.repository-heading { min-width: 0; }
	.repository-link {
		max-width: 100%;
		padding: 0;
		border: 0;
		background: transparent;
		color: var(--color-ink-0);
		font-family: var(--font-mono);
		font-size: 0.875rem;
		font-weight: 650;
		text-align: left;
		white-space: normal;
		overflow-wrap: anywhere;
		cursor: pointer;
	}
	.repository-link:hover { color: var(--color-accent); }
	.repository-heading p { margin: 0.2rem 0 0; color: var(--color-ink-2); font-size: 0.7rem; }
	.repository-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 0.45rem; color: var(--color-ink-2); font-size: 0.6875rem; min-width: 0; }
	.repository-meta code { min-width: 0; color: var(--color-ink-1); font-family: var(--font-mono); overflow-wrap: anywhere; }
	.repository-meta time { margin-left: auto; font-family: var(--font-mono); }
	.trust-counts { display: flex; flex-wrap: wrap; gap: 0.4rem; width: 100%; }
	.tag-section { display: grid; gap: 0.5rem; padding-top: 0.85rem; border-top: 1px solid var(--color-line); }
	.section-label { color: var(--color-ink-2); font-size: 0.6875rem; font-weight: 600; }
	.tag-list { display: flex; flex-wrap: wrap; align-items: center; gap: 0.4rem; }
	.tag-chip {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		padding: 0.3rem 0.5rem;
		border: 1px solid var(--color-line-2);
		border-radius: 0.4rem;
		background: var(--color-surface-sunken);
		color: var(--color-ink-1);
		font-family: var(--font-mono);
		font-size: 0.6875rem;
		cursor: pointer;
		max-width: 100%;
		min-width: 0;
		text-align: left;
		overflow-wrap: anywhere;
		white-space: normal;
	}
	.tag-chip > span:first-child { min-width: 0; overflow-wrap: anywhere; }
	.tag-chip:hover, .tag-chip:focus-visible { border-color: var(--color-accent); color: var(--color-ink-0); outline: none; }
	.more-tags { color: var(--color-ink-2); font-family: var(--font-mono); font-size: 0.6875rem; }
	:global(.browse-button) { justify-self: start; padding-inline: 0; }
</style>
