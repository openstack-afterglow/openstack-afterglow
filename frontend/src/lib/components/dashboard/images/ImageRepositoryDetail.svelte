<script lang="ts">
	import { Button, Card, Pill, StatusChip } from '$lib/components/ui';
	import type { ImageRepositoryGroup } from '$lib/stores/imagesController.svelte';
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

	function formatSize(bytes: number | null | undefined): string {
		if (!bytes) return '-';
		if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
		if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(0)} MB`;
		return `${bytes} B`;
	}
</script>

<Card surface="raised" padding="none" class="repository-detail">
	<div class="detail-header">
		<Button variant="ghost" size="icon" ariaLabel="repository 목록으로 돌아가기" onclick={onBack}>‹</Button>
		<div class="detail-heading">
			<p class="detail-kicker">REPOSITORY</p>
			<h2>{group.repository}</h2>
			<p>{group.images.length}개 tag · 각 버전은 독립적인 Glance 이미지입니다.</p>
		</div>
	</div>

	<div class="table-wrap">
		<table>
			<thead>
				<tr>
					<th>Tag</th>
					<th>상태</th>
					<th>OS</th>
					<th>크기</th>
					<th>업데이트</th>
					<th><span class="sr-only">액션</span></th>
				</tr>
			</thead>
			<tbody>
				{#each group.images as image (image.id)}
					<tr>
						<td>
							<div class="tag-name">:{image.tag ?? 'latest'}</div>
							{#if image.tag === 'latest'}<Pill tone="warm" size="xs">기본</Pill>{/if}
						</td>
						<td><StatusChip status={image.status} /></td>
						<td>{image.os_distro ? osLabel(image.os_distro) : '-'}</td>
						<td>{formatSize(image.size)}</td>
						<td class="date">{(image.updated_at ?? image.created_at ?? '').slice(0, 10) || '-'}</td>
						<td class="action-cell"><Button variant="link" size="xs" onclick={() => onOpenTag(image.id)}>상세 보기</Button></td>
					</tr>
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
	table { width: 100%; border-collapse: collapse; min-width: 42rem; }
	th, td { padding: 0.75rem 1rem; border-bottom: 1px solid var(--color-line); text-align: left; white-space: nowrap; }
	th { color: var(--color-ink-2); font-size: 0.625rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; }
	td { color: var(--color-ink-1); font-size: 0.75rem; }
	tbody tr:hover { background: var(--color-surface-sunken); }
	.tag-name { display: inline-block; margin-right: 0.4rem; color: var(--color-ink-0); font-family: var(--font-mono); font-weight: 600; }
	.date { color: var(--color-ink-2); font-family: var(--font-mono); }
	.action-cell { text-align: right; }
</style>
