<script lang="ts">
	import type { ImageInfo } from '$lib/types/compute';
	import type { FlavorOption } from '$lib/types/flavor';
	import { hasGpuImageMetadata, imageFlavorProfile, imageRecommendations } from '$lib/utils/imageRecommendation';
	import { createImageCatalog, currentImagesByReference, imageReferenceParts, imageUploadInstant } from '$lib/stores/imageCatalog.svelte';
	import { createTableView, type TableColumn } from '$lib/utils/tableView.svelte';
	import TableColumnControl from '$lib/components/ui/TableColumnControl.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import type { ImageTagGroup } from '$lib/stores/imageCatalog.svelte';
	import { formatSize } from '$lib/utils/format';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { Alert, Button, CompactResourceCard, ResponsiveTable, StatusChip, TableShell } from '$lib/components/ui';
	import ImageDigest from '$lib/components/image/ImageDigest.svelte';
	import { t } from '$lib/i18n/ns/vm-wizard';
	let { images, selectedId, onSelect, selectedFlavor = null }: {
		images: ImageInfo[];
		selectedId: string | null;
		onSelect: (id: string, name: string) => void;
		selectedFlavor?: FlavorOption | null;
	} = $props();

	const OTHER_DISTRO = '__other__';

	function referenceName(image: ImageInfo): string {
		const { repository, tag } = imageReferenceParts(image);
		return `${repository}:${tag}`;
	}

	function selectionName(image: ImageInfo): string {
		const sourceName = image.name.trim();
		return sourceName && sourceName !== imageReferenceParts(image).repository ? sourceName : referenceName(image);
	}
	const chooserId = $props.id();
	let expandedRepository = $state<string | null | undefined>(undefined);
	let tagSearch = $state('');

	const distroLabels: Record<string, string> = {
		ubuntu: 'Ubuntu', centos: 'CentOS', rocky: 'Rocky Linux',
		debian: 'Debian', 'fedora-coreos': 'Fedora CoreOS', fedora: 'Fedora', rhel: 'RHEL',
		windows: 'Windows', cirros: 'CirrOS',
	};

	// 배포판은 범주형 식별자다. 상태 톤(success/info/neutral)을 빌리면 목록이 건강 상태처럼
	// 읽히므로 범주형 팔레트인 --color-chart-* 만 쓴다.
	const distroColors: Record<string, string> = {
		ubuntu: 'bg-[var(--color-chart-1)]', centos: 'bg-[var(--color-chart-5)]', rocky: 'bg-[var(--color-chart-2)]',
		debian: 'bg-[var(--color-chart-3)]', fedora: 'bg-[var(--color-chart-1)]', 'fedora-coreos': 'bg-[var(--color-chart-6)]',
		rhel: 'bg-[var(--color-chart-4)]', windows: 'bg-[var(--color-chart-6)]', cirros: 'bg-[var(--color-chart-5)]',
	};

	const distroLogos: Record<string, string> = {
		ubuntu: '/logos/Ubuntu.png',
		centos: '/logos/CentOS.png',
		fedora: '/logos/Fedora.png',
		'fedora-coreos': '/logos/coreos.png',
		cirros: '/logos/Cirros.png',
		windows: '/logos/Windows.png',
	};

	function logoPath(distro: string | null): string | null {
		return distroLogos[distro ?? ''] ?? null;
	}

	const currentImages = $derived([...currentImagesByReference(images).values()]);
	const currentIds = $derived(new Set(currentImages.map(image => image.id)));
	const previousSelected = $derived(selectedId && !currentIds.has(selectedId)
		? images.find(image => image.id === selectedId) ?? null
		: null);
	const previousSelectedMissing = $derived(selectedId !== null && !currentIds.has(selectedId) && !previousSelected);
	const catalog = createImageCatalog(() => currentImages, () => images);
	const repositoryGroups = $derived(catalog.repositoryGroups);
	const selectedImage = $derived(images.find(image => image.id === selectedId));
	const flavorProfile = $derived(imageFlavorProfile(selectedFlavor));
	const recommendations = $derived(imageRecommendations(images, selectedFlavor));
	const cpuDriverWarning = $derived(flavorProfile !== null && !flavorProfile.gpu && selectedImage && hasGpuImageMetadata(selectedImage));
	const openRepository = $derived(expandedRepository === undefined
		? selectedImage ? imageReferenceParts(selectedImage).repository : null
		: expandedRepository);
	const openGroup = $derived(repositoryGroups.find(group => group.repository === openRepository));
	const tagColumns = $derived<TableColumn<ImageTagGroup>[]>([
		{ key: 'tag', label: t('image.columns.tag'), value: row => row.tag },
		{ key: 'hash', label: t('image.columns.hash'), value: row => row.current.os_hash_value ?? row.current.id },
		{ key: 'uploaded', label: t('image.columns.uploadedAt'), value: row => imageUploadInstant(row.current) },
		{ key: 'size', label: t('image.columns.size'), value: row => row.current.size },
	]);
	const tagView = createTableView({ rows: () => openGroup?.tags ?? [], columns: () => tagColumns, search: () => tagSearch });
	const visibleTags = $derived(tagView.rows);
	const retainedTagConditions = $derived(Boolean(tagSearch || tagView.sort || Object.keys(tagView.filters).length));
	const uploadFormatter = $derived(new Intl.DateTimeFormat(intlLocale(), {
		year: 'numeric', month: '2-digit', day: '2-digit',
		hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
	}));


	function distroLabel(d: string): string {
		return d === OTHER_DISTRO ? t('image.distro.other') : distroLabels[d] ?? d;
	}

	function avatarLetter(name: string): string {
		return name.charAt(0).toUpperCase();
	}

	function avatarColor(distro: string | null): string {
		return distroColors[distro ?? ''] ?? 'bg-[var(--color-state-neutral)]';
	}

	function toggleRepository(repository: string): void {
		if (openRepository === repository) {
			expandedRepository = null;
		} else {
			expandedRepository = repository;
			tagSearch = '';
		}
	}

</script>

<RegexSearch id="vm-image-search" bind:value={catalog.searchQuery} label={t('image.searchLabel')} placeholder={t('image.searchPlaceholder')} />
<TableViewControls view={catalog.view} class="" />
{#if !openGroup && retainedTagConditions}
	<section aria-label={t('image.columns.tag')} class="mb-4 space-y-3">
		<RegexSearch id={`${chooserId}-retained-tag-search`} bind:value={tagSearch} label={t('image.columns.tag')} placeholder={t('image.tagSearchPlaceholder')} />
		<TableViewControls view={tagView} class="" />
		<p class="text-sm text-ink-2">{t('image.tagSearchEmpty')}</p>
	</section>
{/if}

{#if flavorProfile}
	<section aria-label={t('image.recommendation.title')} class="mb-4 text-sm text-[var(--color-ink-2)]">
		<p>{flavorProfile.gpu ? t('image.recommendation.gpuHelp') : t('image.recommendation.cpuHelp')}</p>
		{#if flavorProfile.gpu && recommendations.size === 0}
			<p class="mt-1">{t('image.recommendation.noMatch')}</p>
		{/if}
	</section>
{/if}
{#if cpuDriverWarning}
	<Alert tone="warning" title={t('image.recommendation.cpuWarningTitle')} class="mb-4">
		{t('image.recommendation.cpuWarning')}
	</Alert>
{/if}

{#if previousSelected || previousSelectedMissing}
	<section aria-label={t('image.previous.label')} class="mb-4 rounded-xl border border-[var(--color-line-2)] bg-[var(--color-surface-sunken)] p-4 text-sm text-[var(--color-ink-1)]">
		<p class="mb-2 font-semibold">{t('image.previous.title')}</p>
		{#if previousSelected}
			<p class="font-mono">{referenceName(previousSelected)}</p>
		{:else}
			<p>{t('image.previous.missing')}</p>
		{/if}
		<code class="block break-all text-xs" aria-label={t('image.previous.idLabel', { id: selectedId })}>ID {selectedId}</code>
		<p class="mt-2 text-xs text-[var(--color-ink-2)]">{t('image.previous.help')}</p>
	</section>
{/if}

<div role="list" aria-label={t('image.repositoryListLabel')} class="grid grid-cols-1 @lg/panel:grid-cols-2 @3xl/panel:grid-cols-3 gap-3">
	{#each repositoryGroups as group (group.repository)}
		{@const image = group.latest}
		{@const expanded = openRepository === group.repository}
		{@const panelId = `${chooserId}-tags-${encodeURIComponent(group.repository)}`}
		<div role="listitem" class="min-w-0 rounded-xl border transition-colors {expanded
			? 'col-span-full border-[var(--color-accent)] bg-[var(--color-surface-selected)]'
			: 'border-[var(--color-line)] bg-[var(--color-surface-raised)] hover:border-[var(--color-line-2)]'}">
			<button
				type="button"
				onclick={() => toggleRepository(group.repository)}
				aria-label={t('image.repositoryLabel', { name: group.repository })}
				aria-controls={panelId}
				aria-expanded={expanded}
				class="w-full min-w-0 rounded-xl p-4 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--color-accent)]"
			>
				<div class="flex items-center gap-3">
					{#if logoPath(image.os_distro ?? null)}
						<img src={logoPath(image.os_distro ?? null)} alt="" class="h-12 w-12 flex-shrink-0 rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-sunken)] p-1 object-contain" />
					{:else}
						<div aria-hidden="true" class="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-lg {avatarColor(image.os_distro ?? null)} text-sm font-bold text-[var(--color-action-on-accent)]">
							{avatarLetter(group.repository)}
							</div>
					{/if}
					<div class="min-w-0 flex-1">
						<p class="break-all font-mono text-sm font-semibold text-[var(--color-ink-0)]">{group.repository}</p>
						<p class="mt-1 text-xs text-[var(--color-ink-2)]">{[distroLabel(image.os_distro ?? OTHER_DISTRO), image.os_type].filter(Boolean).join(' · ')}</p>
						<p class="mt-1 text-xs text-[var(--color-ink-2)]">{t('image.tagCount', { count: group.tags.length })}</p>
						{#if group.images.some(candidate => recommendations.has(candidate.id))}
							<p class="mt-1 text-xs font-medium text-[var(--color-accent)]">{t('image.recommendation.repository')}</p>
						{/if}
						{#if selectedImage && imageReferenceParts(selectedImage).repository === group.repository}
							<p class="mt-1 truncate text-xs text-[var(--color-ink-2)]" title={imageReferenceParts(selectedImage).tag}>{t('image.selectedTag', { tag: imageReferenceParts(selectedImage).tag })}</p>
						{/if}
					</div>
					{#if group.images.some(image => image.id === selectedId)}
						<svg class="h-4 w-4 shrink-0 text-[var(--color-accent)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
						</svg>
					{/if}
					<svg class="h-4 w-4 shrink-0 text-[var(--color-ink-2)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.75" d={expanded ? 'm6 15 6-6 6 6' : 'm6 9 6 6 6-6'} />
					</svg>
				</div>
			</button>
			{#if expanded}
				<section id={panelId} aria-label={t('image.tagsTitle', { name: group.repository })} class="min-w-0 border-t border-[var(--color-line)] p-3 @lg/panel:p-4">
					<p class="mb-3 text-xs text-[var(--color-ink-2)]">{t('image.tagsHelp')}</p>
					<RegexSearch id={`${panelId}-search`} bind:value={tagSearch} label={t('image.tagSearchLabel', { name: group.repository })} placeholder={t('image.tagSearchPlaceholder')} />
					<TableViewControls view={tagView} />
					{#if visibleTags.length === 0}<p role="status" class="py-6 text-center text-sm text-ink-2">{t('image.tagSearchEmpty')}</p>{/if}
						<ResponsiveTable>
							{#snippet cards()}
								{#each visibleTags as tag (tag.tag)}
									{@const image = tag.current}
									{@const instant = imageUploadInstant(image)}
									<CompactResourceCard selected={selectedId === image.id}>
										<div class="flex min-w-0 flex-wrap items-start justify-between gap-2"><h3 class="min-w-0 break-all font-mono text-sm line-clamp-2" title={tag.tag}>{tag.tag}</h3><StatusChip status={image.status} /></div>
										<p class="text-xs text-ink-2">{t('image.columns.size')}: {formatSize(image.size ?? null)}</p>
										{#if recommendations.get(image.id) === 'gpu'}<p class="text-xs text-accent">{t('image.recommendation.gpu', { vendor: image.gpu_vendor })}</p>{:else if recommendations.get(image.id) === 'general'}<p class="text-xs text-accent">{t('image.recommendation.general')}</p>{/if}
										{#snippet actions()}<Button variant="secondary" size="sm" disabled={image.status !== 'active'} ariaPressed={selectedId === image.id} title={image.status === 'active' ? tag.tag : t('image.inactiveReason', { status: image.status })} onclick={() => onSelect(image.id, selectionName(image))}>{image.status === 'active' ? t('image.selectLabel', { name: referenceName(image) }) : t('image.unselectableLabel', { name: referenceName(image), status: image.status })}</Button>{/snippet}
										{#snippet details()}
											<div class="min-w-0 space-y-2 break-words text-xs text-ink-2">
												<ImageDigest {image} showId={false} compact />
												<p>{t('image.columns.uploadedAt')}: {#if instant === null}-{:else}<time datetime={image.created_at ?? undefined}>{uploadFormatter.format(Math.trunc(instant / 1000))}</time>{/if}</p>
												{#if hasGpuImageMetadata(image)}<p>{t('image.recommendation.driverImage')}</p>{/if}
											</div>
										{/snippet}
									</CompactResourceCard>
								{/each}
							{/snippet}
						<TableShell density="compact">
							<div class="min-w-[39rem]">
								<div class="tag-row bg-[var(--color-surface-sunken)] px-3 py-2 text-xs font-medium text-[var(--color-ink-2)]">
									{#each tagColumns as column}<TableColumnControl view={tagView} columnKey={column.key} />{/each}
								</div>
								<ul class="m-0 list-none p-0">
									{#each visibleTags as tag (tag.tag)}
										{@const image = tag.current}
										{@const instant = imageUploadInstant(image)}
										<li class="border-t border-[var(--color-line)]">
											<button
												type="button"
												disabled={image.status !== 'active'}
												onclick={() => onSelect(image.id, selectionName(image))}
												aria-label={image.status === 'active' ? t('image.selectLabel', { name: referenceName(image) }) : t('image.unselectableLabel', { name: referenceName(image), status: image.status })}
												aria-pressed={selectedId === image.id}
												title={image.status === 'active' ? tag.tag : t('image.inactiveReason', { status: image.status })}
												class="tag-row min-h-11 w-full px-3 py-2 text-left text-sm transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--color-accent)] disabled:cursor-not-allowed {selectedId === image.id
													? 'bg-[var(--color-surface-selected)]'
													: 'bg-[var(--color-surface-base)] enabled:hover:bg-[var(--color-surface-sunken)]'}"
											>
												<span class="flex min-w-0 flex-wrap items-center gap-2 text-[var(--color-ink-1)]" title={tag.tag}>
													<span class="min-w-0 truncate font-mono text-sm">{tag.tag}</span>
													{#if selectedId === image.id}
														<svg class="h-4 w-4 shrink-0 text-[var(--color-accent)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" /></svg>
													{/if}
													{#if image.status !== 'active'}<span class="shrink-0 text-xs text-[var(--color-ink-2)]">{image.status}</span>{/if}
													{#if recommendations.get(image.id) === 'gpu'}
														<span class="text-xs font-medium text-[var(--color-accent)]">{t('image.recommendation.gpu', { vendor: image.gpu_vendor })}</span>
													{:else if recommendations.get(image.id) === 'general'}
														<span class="text-xs font-medium text-[var(--color-accent)]">{t('image.recommendation.general')}</span>
													{/if}
													{#if hasGpuImageMetadata(image)}
														<span class="text-xs text-[var(--color-ink-2)]">{t('image.recommendation.driverImage')}</span>
													{/if}
												</span>
												<ImageDigest {image} showId={false} compact />
												<span class="whitespace-nowrap text-xs tabular-nums text-[var(--color-ink-2)]">
													{#if instant === null}-{:else}<time datetime={image.created_at ?? undefined} title={image.created_at ?? undefined}>{uploadFormatter.format(Math.trunc(instant / 1000))}</time>{/if}
												</span>
												<span class="whitespace-nowrap text-right text-xs tabular-nums text-[var(--color-ink-2)]">{formatSize(image.size ?? null)}</span>
											</button>
										</li>
									{/each}
								</ul>
							</div>
						</TableShell>
						</ResponsiveTable>
				</section>
			{/if}
		</div>
	{/each}

	{#if repositoryGroups.length === 0}
		<p class="col-span-full py-10 text-center text-sm text-[var(--color-ink-2)]">{t('image.empty')}</p>
	{/if}
</div>

<style>
	.tag-row {
		display: grid;
		grid-template-columns: minmax(18rem, 1fr) 4.5rem 9rem 4rem;
		align-items: center;
		column-gap: 0.5rem;
	}
</style>
