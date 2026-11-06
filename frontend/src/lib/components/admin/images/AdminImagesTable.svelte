<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-compute';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { Button, Pill, StatusChip, TableShell } from '$lib/components/ui';
	import ImageDigest from '$lib/components/image/ImageDigest.svelte';
	import ImageVerificationBadge from '$lib/components/image/ImageVerificationBadge.svelte';
	import { projectNames } from '$lib/stores/projectNames';
	import { imageReferenceParts } from '$lib/stores/imageCatalog.svelte';
	import type { AdminImage } from '$lib/types/adminImage';
	import { formatSize } from '$lib/utils/format';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import TableColumnHeader from '$lib/components/ui/TableColumnHeader.svelte';
	import type { TableView } from '$lib/utils/tableView.svelte';
	import TableColumnControl from '$lib/components/ui/TableColumnControl.svelte';

	let {
		images, selectedImageId, togglingId, verifyingId, currentImageIds,
		view,
		deletingId = null,
		onOpenDetail, onEdit, onToggleActivation, onDelete, onToggleVerification,
	}: {
		images: AdminImage[];
		view: TableView<AdminImage>;
		selectedImageId: string | null;
		togglingId: string | null;
		verifyingId: string | null;
		deletingId?: string | null;
		currentImageIds: ReadonlySet<string>;
		onOpenDetail: (img: AdminImage) => void;
		onEdit: (img: AdminImage) => void;
		onToggleActivation: (img: AdminImage) => void;
		onDelete: (img: AdminImage) => void;
		onToggleVerification: (img: AdminImage) => void;
	} = $props();
</script>

{#snippet imageActions(img: AdminImage)}
	<div class="flex flex-wrap items-center gap-2" aria-label={t('images.table.manageLabel', { name: img.name, id: img.id.slice(0, 8) })}>
		<Button variant="secondary" size="xs" onclick={() => onToggleVerification(img)}
			disabled={verifyingId === img.id || (img.verification_status !== 'verified' && img.status !== 'active')}
			title={img.status !== 'active' && img.verification_status !== 'verified' ? t('images.table.verificationHelp') : undefined}>
			{#if verifyingId === img.id}<span class="inline-flex items-center gap-2" role="status"><LoadingState variant="control" label="" aria-hidden="true" /><span>{t('images.processing')}</span></span>{:else}{img.verification_status === 'verified' ? t('images.table.revokeVerification') : t('images.table.approveVerification')}{/if}
		</Button>
		{#if img.status === 'active' || img.status === 'deactivated'}
			<Button variant="ghost" size="xs" onclick={() => onToggleActivation(img)} disabled={togglingId === img.id}>
				{#if togglingId === img.id}<span class="inline-flex items-center gap-2" role="status"><LoadingState variant="control" label="" aria-hidden="true" /><span>{t('images.processing')}</span></span>{:else}{img.status === 'active' ? t('images.table.deactivate') : t('images.table.activate')}{/if}
			</Button>
		{/if}
		<Button variant="link" size="xs" onclick={() => onEdit(img)}>{t('images.edit.action')}</Button>
		{#if !img.protected}
			<Button variant="danger-outline" size="xs" onclick={() => onDelete(img)} disabled={deletingId === img.id}>
				{#if deletingId === img.id}
					<span class="inline-flex items-center gap-2" role="status"><LoadingState variant="control" label="" aria-hidden="true" /><span>{t('images.delete.pending')}</span></span>
				{:else}{t('images.delete.action')}{/if}
			</Button>
		{/if}
	</div>
{/snippet}

<ResponsiveTable>
	{#snippet cards()}
		{#each images as img (img.id)}
			<CompactResourceCard selected={selectedImageId === img.id}>
				<button type="button" class="min-h-11 break-all text-left font-mono text-sm font-semibold text-ink-0" aria-label={t('images.table.detailLabel', { name: img.name, id: img.id.slice(0, 8) })} onclick={() => onOpenDetail(img)}>{img.name}</button>
				<div class="flex flex-wrap gap-2"><StatusChip status={img.status} /><ImageVerificationBadge status={img.verification_status} /><Pill tone={currentImageIds.has(img.id) ? 'accent' : 'neutral'} size="xs">{currentImageIds.has(img.id) ? t('images.table.current') : t('images.table.previous')}</Pill></div>
				<div class="space-y-1 text-xs text-ink-2"><p>{formatSize(img.size)} · {img.disk_format || '-'}</p><p class="break-all">{t('images.table.project')}: {img.owner ? ($projectNames.get(img.owner) ?? img.owner.slice(0, 8)) : '-'}</p></div>
				{#snippet actions()}{@render imageActions(img)}{/snippet}
				{#snippet details()}<div class="space-y-2 break-all text-xs text-ink-2"><ImageDigest image={img} /><p>{t('images.table.uploadedAt')}: {img.created_at?.slice(0, 10) || '-'}</p><p>{img.visibility === 'public' ? t('images.visibility.publicValue') : img.visibility === 'community' ? t('images.visibility.communityValue') : img.visibility === 'shared' ? t('images.visibility.sharedValue') : img.visibility === 'private' ? t('images.visibility.privateValue') : img.visibility}</p><p class="font-mono">{img.owner ?? '-'}</p></div>{/snippet}
			</CompactResourceCard>
		{/each}
	{/snippet}
	<TableShell density="compact">
		<table>
			<thead><tr>
				<th scope="col" aria-sort={view.direction('tag')}><div class="flex flex-wrap gap-2">{#each ['tag', 'repository', 'os_distro'] as key}<TableColumnControl {view} columnKey={key} />{/each}</div></th>
				{#each ['id', 'verification', 'status', 'visibility', 'size', 'disk_format', 'owner', 'created_at'] as key}
					<TableColumnHeader {view} columnKey={key} />
				{/each}
				<th scope="col">{t('images.table.actions')}</th>
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
						<td>{@render imageActions(img)}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</TableShell>
</ResponsiveTable>
