<script lang="ts">
	import { Button, Card, Pill, StatusChip, TableShell } from '$lib/components/ui';
	import ImageDigest from '$lib/components/image/ImageDigest.svelte';
	import ImageVerificationBadge from '$lib/components/image/ImageVerificationBadge.svelte';
	import { projectNames } from '$lib/stores/projectNames';
	import { imageReferenceParts } from '$lib/stores/imageCatalog.svelte';
	import type { AdminImage } from '$lib/types/adminImage';
	import { formatSize } from '$lib/utils/format';

	let {
		images, selectedImageId, togglingId, verifyingId, currentImageIds,
		onOpenDetail, onEdit, onToggleActivation, onDelete, onToggleVerification,
	}: {
		images: AdminImage[];
		selectedImageId: string | null;
		togglingId: string | null;
		verifyingId: string | null;
		currentImageIds: ReadonlySet<string>;
		onOpenDetail: (img: AdminImage) => void;
		onEdit: (img: AdminImage) => void;
		onToggleActivation: (img: AdminImage) => void;
		onDelete: (img: AdminImage) => void;
		onToggleVerification: (img: AdminImage) => void;
	} = $props();
</script>

{#snippet actions(img: AdminImage)}
	<div class="flex flex-wrap items-center gap-2" aria-label={`${img.name} (${img.id.slice(0, 8)}) 관리`}>
		<Button variant="secondary" size="xs" onclick={() => onToggleVerification(img)}
			disabled={verifyingId === img.id || (img.verification_status !== 'verified' && img.status !== 'active')}
			title={img.status !== 'active' && img.verification_status !== 'verified' ? 'active 이미지의 내용을 확인한 뒤 검증할 수 있습니다.' : undefined}>
			{verifyingId === img.id ? '처리 중…' : img.verification_status === 'verified' ? '검증 해제' : '검증 승인'}
		</Button>
		{#if img.status === 'active' || img.status === 'deactivated'}
			<Button variant="ghost" size="xs" onclick={() => onToggleActivation(img)} disabled={togglingId === img.id}>
				{togglingId === img.id ? '처리 중…' : img.status === 'active' ? '비활성화' : '활성화'}
			</Button>
		{/if}
		<Button variant="link" size="xs" onclick={() => onEdit(img)}>수정</Button>
		{#if !img.protected}<Button variant="danger-outline" size="xs" onclick={() => onDelete(img)}>삭제</Button>{/if}
	</div>
{/snippet}

<div class="grid grid-cols-1 gap-3.5 md:grid-cols-2 lg:hidden" aria-label="이미지 tag 카드">
	{#each images as img (img.id)}
		<Card padding="lg" class="space-y-3">
			<button type="button" class="w-full break-all text-left font-mono text-sm font-semibold text-ink-0 hover:text-accent" aria-label={`${img.name} (${img.id.slice(0, 8)}) 상세`} onclick={() => onOpenDetail(img)}>{img.name}</button>
			<div class="flex flex-wrap gap-2"><Pill tone={currentImageIds.has(img.id) ? 'accent' : 'neutral'} size="xs">{currentImageIds.has(img.id) ? '현재' : '이전'}</Pill><StatusChip status={img.status} /><ImageVerificationBadge status={img.verification_status} /><Pill tone="neutral">{img.visibility}</Pill></div>
			<ImageDigest image={img} />
			<dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
				<dt class="text-ink-2">프로젝트</dt><dd class="break-all text-ink-1">{img.owner ? ($projectNames.get(img.owner) ?? img.owner) : '-'}</dd>
				<dt class="text-ink-2">크기 · 포맷</dt><dd class="text-ink-1">{formatSize(img.size)} · {img.disk_format || '-'}</dd>
				<dt class="text-ink-2">업로드일</dt><dd class="tabular-nums text-ink-1">{img.created_at?.slice(0, 10) || '-'}</dd>
			</dl>
			{@render actions(img)}
		</Card>
	{/each}
</div>
<div class="hidden lg:block">
	<TableShell density="compact">
		<table>
			<thead><tr>
				<th scope="col">이미지 / Tag</th><th scope="col">SHA 해시 · ID</th><th scope="col">검증</th><th scope="col">상태</th><th scope="col">공개 범위</th>
				<th scope="col">크기</th><th scope="col">포맷</th><th scope="col">프로젝트</th><th scope="col">업로드일</th><th scope="col">액션</th>
			</tr></thead>
			<tbody>
				{#each images as img (img.id)}
					{@const reference = imageReferenceParts(img)}
					<tr class={selectedImageId === img.id ? 'bg-surface-selected' : ''}>
						<td><button type="button" class="block max-w-64 text-left font-mono text-ink-0 hover:text-accent" aria-label={`${img.name} (${img.id.slice(0, 8)}) 상세`} title={`${img.name} · ${img.id}`} onclick={() => onOpenDetail(img)}>
							<span class="block break-all font-semibold">:{reference.tag} <Pill tone={currentImageIds.has(img.id) ? 'accent' : 'neutral'} size="xs">{currentImageIds.has(img.id) ? '현재' : '이전'}</Pill></span>
							<span class="block truncate text-xs text-ink-2">{reference.repository}</span>
						</button></td>
						<td><ImageDigest image={img} /></td>
						<td><ImageVerificationBadge status={img.verification_status} /></td>
						<td><StatusChip status={img.status} /></td>
						<td><Pill tone="neutral" size="xs">{img.visibility}</Pill></td>
						<td class="tabular-nums">{formatSize(img.size)}</td><td>{img.disk_format || '-'}</td>
						<td title={img.owner}>{img.owner ? ($projectNames.get(img.owner) ?? img.owner.slice(0, 8)) : '-'}</td>
						<td class="tabular-nums">{img.created_at?.slice(0, 10) || '-'}</td>
						<td>{@render actions(img)}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</TableShell>
</div>
