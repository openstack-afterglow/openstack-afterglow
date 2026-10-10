<script lang="ts">
	import type { ImageInfo } from '$lib/types/compute';
	import { createImageCatalog, currentImagesByReference, imageReferenceParts, imageUploadInstant } from '$lib/stores/imageCatalog.svelte';
	import { imageReferenceMatchesQuery } from '$lib/utils/imageReference';
	import { formatSize } from '$lib/utils/format';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { TableShell } from '$lib/components/ui';
	import ImageDigest from '$lib/components/image/ImageDigest.svelte';
	import { t } from '$lib/i18n/ns/vm-wizard';
	import RichText from '$lib/i18n/RichText.svelte';
	let { images, selectedId, onSelect }: {
		images: ImageInfo[];
		selectedId: string | null;
		onSelect: (id: string, name: string) => void;
	} = $props();

	let activeDistro = $state<string | null>(null);
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
	let searchTerm = $state('');
	let filtersOpen = $state(false);
	const activeFilterCount = $derived((searchTerm.trim() ? 1 : 0) + (activeDistro === null ? 0 : 1));

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
	const distros = $derived(
		[...new Set(currentImages.map(i => i.os_distro ?? OTHER_DISTRO))].sort((a, b) => {
			if (a === OTHER_DISTRO) return 1;
			if (b === OTHER_DISTRO) return -1;
			return a.localeCompare(b);
		})
	);

	// Resolve each reference from the full input before applying UI filters.
	const distroFiltered = $derived(
		activeDistro === null
			? currentImages
			: currentImages.filter(i => (i.os_distro ?? OTHER_DISTRO) === activeDistro)
	);

	const filteredImages = $derived(
		distroFiltered.filter((image) => imageReferenceMatchesQuery(image, searchTerm))
	);
	const catalog = createImageCatalog(() => filteredImages, () => images);
	const repositoryGroups = $derived(catalog.repositoryGroups);
	const selectedImage = $derived(images.find(image => image.id === selectedId));
	const openRepository = $derived(expandedRepository === undefined
		? selectedImage ? imageReferenceParts(selectedImage).repository : null
		: expandedRepository);
	const openGroup = $derived(repositoryGroups.find(group => group.repository === openRepository));
	const tagQuery = $derived(tagSearch.trim().toLowerCase());
	const visibleTags = $derived(openGroup?.tags.filter(tag => tag.tag.toLowerCase().includes(tagQuery)) ?? []);
	const uploadFormatter = $derived(new Intl.DateTimeFormat(intlLocale(), {
		year: 'numeric', month: '2-digit', day: '2-digit',
		hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
	}));

	const repositoryTotal = $derived(new Set(currentImages.map(image => imageReferenceParts(image).repository)).size);

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

<div class="mb-4 flex items-center justify-between">
	<button
		type="button"
		aria-controls="vm-image-filters"
		aria-expanded={filtersOpen}
		onclick={() => filtersOpen = !filtersOpen}
		class="inline-flex items-center gap-2 rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-raised)] px-3 py-2 text-sm font-medium text-[var(--color-ink-1)] transition-colors hover:border-[var(--color-line-2)] hover:bg-[var(--color-surface-sunken)]"
	>
		<svg class="h-4 w-4 text-[var(--color-ink-2)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
			<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.75" d="M3 5h18M6 12h12m-9 7h6"/>
		</svg>
		{t('image.filters.title')}
		{#if activeFilterCount > 0}
			<span class="rounded-full bg-[var(--color-accent)] px-1.5 py-0.5 font-mono text-xs text-[var(--color-action-on-accent)]">{activeFilterCount}</span>
		{/if}
	</button>
</div>

{#if filtersOpen}
	<div id="vm-image-filters" class="mb-5 rounded-xl border border-[var(--color-line)] bg-[var(--color-surface-sunken)] p-3">
		<div class="relative mb-3">
			<span class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-ink-3)]">
				<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<circle cx="11" cy="11" r="7"/>
					<path stroke-linecap="round" stroke-linejoin="round" d="m21 21-4.3-4.3"/>
				</svg>
			</span>
			<label for="vm-image-search" class="sr-only">{t('image.searchLabel')}</label>
			<input
				id="vm-image-search"
				type="search"
				bind:value={searchTerm}
				placeholder={t('image.searchPlaceholder')}
				class="w-full rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-raised)] py-2 pl-9 pr-3 text-sm text-[var(--color-ink-1)] outline-none placeholder:text-[var(--color-ink-3)] focus:border-[var(--color-line-2)]"
			/>
		</div>

		<div>
			<p class="mb-2 text-xs font-medium text-[var(--color-ink-2)]">{t('image.filters.osType')}</p>
			<div class="flex flex-wrap gap-2">
				<button
					onclick={() => activeDistro = null}
					class="inline-flex items-center gap-1 rounded-full px-3 py-1.5 text-xs font-medium transition-all {activeDistro === null
						? 'bg-[var(--color-accent)] text-[var(--color-action-on-accent)]'
						: 'bg-[var(--color-surface-raised)] text-[var(--color-ink-2)] hover:bg-[var(--color-surface-base)]'}"
				>
					{#snippet countBadge(text: string)}<span class="font-mono text-[10.5px] opacity-70">{text}</span>{/snippet}
					<RichText segments={t.rich('image.filters.all', { count: repositoryTotal })} tags={{ count: countBadge }} />
				</button>
				{#each distros as d}
					{@const count = new Set(currentImages.filter(image => (image.os_distro ?? OTHER_DISTRO) === d).map(image => imageReferenceParts(image).repository)).size}
					<button
						onclick={() => activeDistro = d}
						class="inline-flex items-center gap-1 rounded-full px-3 py-1.5 text-xs font-medium transition-all {activeDistro === d
							? 'bg-[var(--color-accent)] text-[var(--color-action-on-accent)]'
							: 'bg-[var(--color-surface-raised)] text-[var(--color-ink-2)] hover:bg-[var(--color-surface-base)]'}"
					>{distroLabel(d)} <span class="font-mono text-[10.5px] opacity-70">{count}</span></button>
				{/each}
			</div>
		</div>
	</div>
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
					<label for={`${panelId}-search`} class="sr-only">{t('image.tagSearchLabel', { name: group.repository })}</label>
					<input
						id={`${panelId}-search`}
						type="search"
						bind:value={tagSearch}
						placeholder={t('image.tagSearchPlaceholder')}
						class="mb-3 w-full rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-sunken)] px-3 py-2 text-sm text-[var(--color-ink-1)] outline-none placeholder:text-[var(--color-ink-3)] focus:border-[var(--color-line-2)]"
					/>
					{#if visibleTags.length > 0}
						<TableShell density="compact">
							<div class="min-w-[39rem]">
								<div class="tag-row bg-[var(--color-surface-sunken)] px-3 py-2 text-xs font-medium text-[var(--color-ink-2)]" aria-hidden="true">
									<span>{t('image.columns.tag')}</span>
									<span>{t('image.columns.hash')}</span>
									<span>{t('image.columns.uploadedAt')}</span>
									<span class="text-right">{t('image.columns.size')}</span>
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
												<span class="flex min-w-0 items-center gap-2 text-[var(--color-ink-1)]" title={tag.tag}>
													<span class="min-w-0 truncate font-mono text-sm">{tag.tag}</span>
													{#if selectedId === image.id}
														<svg class="h-4 w-4 shrink-0 text-[var(--color-accent)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" /></svg>
													{/if}
													{#if image.status !== 'active'}<span class="shrink-0 text-xs text-[var(--color-ink-2)]">{image.status}</span>{/if}
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
					{:else}
						<p role="status" class="py-6 text-center text-sm text-[var(--color-ink-2)]">{t('image.tagSearchEmpty')}</p>
					{/if}
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
