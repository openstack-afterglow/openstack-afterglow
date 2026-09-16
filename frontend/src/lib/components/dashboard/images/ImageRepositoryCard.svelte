<script lang="ts">
	import { Button, Card, Pill } from '$lib/components/ui';
	import { OS_EMOJI, OS_LOGOS, osLabel } from '$lib/utils/imageOs';
	import type { ImageRepositoryGroup } from '$lib/stores/imagesController.svelte';

	let {
		group,
		onOpen,
		onOpenTag,
	}: {
		group: ImageRepositoryGroup;
		onOpen: () => void;
		onOpenTag: (imageId: string) => void;
	} = $props();

	const previewTags = $derived(group.images.slice(0, 5));
	const latest = $derived(group.latest);
	const distro = $derived(latest.os_distro ? osLabel(latest.os_distro) : '운영체제 정보 없음');
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
		<Pill tone="accent" dot>{group.images.length} tags</Pill>
		<span>최근 tag</span>
		<code>:{latest.tag ?? 'latest'}</code>
		{#if latest.updated_at || latest.created_at}
			<time datetime={latest.updated_at ?? latest.created_at ?? ''}>{(latest.updated_at ?? latest.created_at ?? '').slice(0, 10)}</time>
		{/if}
	</div>

	<div class="tag-section">
		<div class="section-label">버전 선택</div>
		<div class="tag-list">
			{#each previewTags as image (image.id)}
				<button type="button" class="tag-chip" onclick={() => onOpenTag(image.id)}>
					<span>:{image.tag ?? 'latest'}</span>
					{#if image.tag === 'latest'}<Pill tone="warm" size="xs">기본</Pill>{/if}
				</button>
			{/each}
			{#if group.images.length > previewTags.length}
				<span class="more-tags">+{group.images.length - previewTags.length}</span>
			{/if}
		</div>
	</div>

	<Button variant="ghost" size="sm" class="browse-button" onclick={onOpen}>모든 tag 조회</Button>
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
		text-overflow: ellipsis;
		overflow: hidden;
		white-space: nowrap;
		cursor: pointer;
	}
	.repository-link:hover { color: var(--color-accent); }
	.repository-heading p { margin: 0.2rem 0 0; color: var(--color-ink-2); font-size: 0.7rem; }
	.repository-meta { display: flex; align-items: center; gap: 0.45rem; color: var(--color-ink-2); font-size: 0.6875rem; }
	.repository-meta code { color: var(--color-ink-1); font-family: var(--font-mono); }
	.repository-meta time { margin-left: auto; font-family: var(--font-mono); }
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
	}
	.tag-chip:hover, .tag-chip:focus-visible { border-color: var(--color-accent); color: var(--color-ink-0); outline: none; }
	.more-tags { color: var(--color-ink-2); font-family: var(--font-mono); font-size: 0.6875rem; }
	:global(.browse-button) { justify-self: start; padding-inline: 0; }
</style>
