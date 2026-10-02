<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-compute';
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
	<div class="flex flex-wrap items-center gap-2" aria-label={t('images.table.manageLabel', { name: img.name, id: img.id.slice(0, 8) })}>
		<Button variant="secondary" size="xs" onclick={() => onToggleVerification(img)}
			disabled={verifyingId === img.id || (img.verification_status !== 'verified' && img.status !== 'active')}
			title={img.status !== 'active' && img.verification_status !== 'verified' ? t('images.table.verificationHelp') : undefined}>
			{verifyingId === img.id ? t('images.processing') : img.verification_status === 'verified' ? t('images.table.revokeVerification') : t('images.table.approveVerification')}
		</Button>
		{#if img.status === 'active' || img.status === 'deactivated'}
			<Button variant="ghost" size="xs" onclick={() => onToggleActivation(img)} disabled={togglingId === img.id}>
				{togglingId === img.id ? t('images.processing') : img.status === 'active' ? t('images.table.deactivate') : t('images.table.activate')}
			</Button>
		{/if}
		<Button variant="link" size="xs" onclick={() => onEdit(img)}>{t('images.edit.action')}</Button>
		{#if !img.protected}<Button variant="danger-outline" size="xs" onclick={() => onDelete(img)}>{t('images.delete.action')}</Button>{/if}
	</div>
{/snippet}

<div class="grid grid-cols-1 gap-3.5 md:grid-cols-2 lg:hidden" aria-label={t('images.table.tagCards')}>
	{#each images as img (img.id)}
		<Card padding="lg" class="space-y-3">
			<button type="button" class="w-full break-all text-left font-mono text-sm font-semibold text-ink-0 hover:text-accent" aria-label={t('images.table.detailLabel', { name: img.name, id: img.id.slice(0, 8) })} onclick={() => onOpenDetail(img)}>{img.name}</button>
			<div class="flex flex-wrap gap-2"><Pill tone={currentImageIds.has(img.id) ? 'accent' : 'neutral'} size="xs">{currentImageIds.has(img.id) ? t('images.table.current') : t('images.table.previous')}</Pill><StatusChip status={img.status} /><ImageVerificationBadge status={img.verification_status} /><Pill tone="neutral">{img.visibility === 'public' ? t('images.visibility.publicValue') : img.visibility === 'community' ? t('images.visibility.communityValue') : img.visibility === 'shared' ? t('images.visibility.sharedValue') : img.visibility === 'private' ? t('images.visibility.privateValue') : img.visibility}</Pill></div>
			<ImageDigest image={img} />
			<dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
				<dt class="text-ink-2">{t('images.table.project')}</dt><dd class="break-all text-ink-1">{img.owner ? ($projectNames.get(img.owner) ?? img.owner) : '-'}</dd>
				<dt class="text-ink-2">{t('images.table.sizeFormat')}</dt><dd class="text-ink-1">{formatSize(img.size)} · {img.disk_format || '-'}</dd>
				<dt class="text-ink-2">{t('images.table.uploadedAt')}</dt><dd class="tabular-nums text-ink-1">{img.created_at?.slice(0, 10) || '-'}</dd>
			</dl>
			{@render actions(img)}
		</Card>
	{/each}
</div>
<div class="hidden lg:block">
	<TableShell density="compact">
		<table>
			<thead><tr>
				<th scope="col">{t('images.table.imageTag')}</th><th scope="col">{t('images.table.hashId')}</th><th scope="col">{t('images.table.verification')}</th><th scope="col">{t('images.table.status')}</th><th scope="col">{t('images.visibility.label')}</th>
				<th scope="col">{t('images.table.size')}</th><th scope="col">{t('images.table.format')}</th><th scope="col">{t('images.table.project')}</th><th scope="col">{t('images.table.uploadedAt')}</th><th scope="col">{t('images.table.actions')}</th>
			</tr></thead>
			<tbody>
				{#each images as img (img.id)}
					{@const reference = imageReferenceParts(img)}
					<tr class={selectedImageId === img.id ? 'bg-surface-selected' : ''}>
						<td><button type="button" class="block max-w-64 text-left font-mono text-ink-0 hover:text-accent" aria-label={t('images.table.detailLabel', { name: img.name, id: img.id.slice(0, 8) })} title={`${img.name} · ${img.id}`} onclick={() => onOpenDetail(img)}>
							<span class="block break-all font-semibold">:{reference.tag} <Pill tone={currentImageIds.has(img.id) ? 'accent' : 'neutral'} size="xs">{currentImageIds.has(img.id) ? t('images.table.current') : t('images.table.previous')}</Pill></span>
							<span class="block truncate text-xs text-ink-2">{reference.repository}</span>
						</button></td>
						<td><ImageDigest image={img} /></td>
						<td><ImageVerificationBadge status={img.verification_status} /></td>
						<td><StatusChip status={img.status} /></td>
						<td><Pill tone="neutral" size="xs">{img.visibility === 'public' ? t('images.visibility.publicValue') : img.visibility === 'community' ? t('images.visibility.communityValue') : img.visibility === 'shared' ? t('images.visibility.sharedValue') : img.visibility === 'private' ? t('images.visibility.privateValue') : img.visibility}</Pill></td>
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
