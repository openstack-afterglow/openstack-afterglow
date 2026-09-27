<script lang="ts">
	import { Button, Card, Pill, StatusChip } from '$lib/components/ui';
	import { imageUploadTime, imageVerificationStatus, type ImageRepositoryGroup } from '$lib/stores/imageCatalog.svelte';
	import ImageDigest from '$lib/components/image/ImageDigest.svelte';
	import type { ImageInfo } from '$lib/types/compute';
	import ImageVerificationBadge from '$lib/components/image/ImageVerificationBadge.svelte';
	import { osLabel } from '$lib/utils/imageOs';

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
		if (!bytes) return '-';
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
			<Pill tone={current ? 'accent' : 'neutral'} size="xs">{current ? '현재' : '이전'}</Pill>
			{#if tag === 'latest'}<Pill tone="warm" size="xs">기본</Pill>{/if}
		</td>
		<td><ImageDigest {image} /></td>
		<td><StatusChip status={image.status} /></td>
		<td><ImageVerificationBadge status={imageVerificationStatus(image)} /></td>
		<td>{image.os_distro ? osLabel(image.os_distro) : '-'}</td>
		<td>{formatSize(image.size)}</td>
		<td class="date">{uploaded === null ? '-' : new Date(uploaded).toISOString().slice(0, 10)}</td>
		<td class="action-cell"><Button variant="link" size="xs" onclick={() => onOpenTag(image.id)}>상세 보기</Button></td>
	</tr>
{/snippet}

<Card surface="raised" padding="none" class="repository-detail">
	<div class="detail-header">
		<Button variant="ghost" size="icon" ariaLabel="repository 목록으로 돌아가기" onclick={onBack}>‹</Button>
		<div class="detail-heading">
			<p class="detail-kicker">REPOSITORY</p>
			<h2>{group.repository}</h2>
			<p>{group.tags.length}개 tag · {group.images.length}개 업로드 이미지. 현재 tag와 이전 업로드를 SHA 해시·ID로 구분합니다.</p>
		</div>
	</div>

	<div class="table-wrap">
		<table>
			<thead>
				<tr>
					<th>Tag</th>
					<th>SHA 해시 · ID</th>
					<th>상태</th>
					<th>신뢰 상태</th>
					<th>OS</th>
					<th>크기</th>
					<th>업로드</th>
					<th><span class="sr-only">액션</span></th>
				</tr>
			</thead>
			<tbody>
				{#each group.tags as version (version.tag)}
					{@render versionRow(version.latest, version.tag, version.latest.id === version.current.id)}
					{#if version.images.length > 1}
						<tr><td colspan="8">
							<Button variant="ghost" size="xs" ariaLabel={`:${version.tag} 이전 업로드 ${version.images.length - 1}개 ${expandedTags.has(version.tag) ? '접기' : '보기'}`}
								ariaExpanded={expandedTags.has(version.tag)} onclick={() => {
									const next = new Set(expandedTags);
									if (next.has(version.tag)) next.delete(version.tag); else next.add(version.tag);
									expandedTags = next;
								}}>
								이전 업로드 {version.images.length - 1}개 {expandedTags.has(version.tag) ? '접기' : '보기'}
							</Button>
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
