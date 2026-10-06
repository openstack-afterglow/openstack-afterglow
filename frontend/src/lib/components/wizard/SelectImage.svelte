<script lang="ts">
	import { tick } from 'svelte';
	import type { ImageInfo } from '$lib/types/compute';
	import { createImageCatalog, currentImagesByReference, imageReferenceParts, imageUploadInstant } from '$lib/stores/imageCatalog.svelte';
	import { imageReferenceMatchesQuery } from '$lib/utils/imageReference';
	import { formatDate, formatSize } from '$lib/utils/format';
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
	let expandedRepository = $state<string | null>(null);
	let tagPanel: HTMLElement | undefined = $state();
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
	const openRepository = $derived(expandedRepository ?? (selectedImage ? imageReferenceParts(selectedImage).repository : null));
	const openGroup = $derived(repositoryGroups.find(group => group.repository === openRepository));

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

	function uploadDate(image: ImageInfo): string {
		const instant = imageUploadInstant(image);
		return instant === null ? '' : formatDate(new Date(Math.trunc(instant / 1000)).toISOString());
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

<div class="grid grid-cols-1 @lg/panel:grid-cols-2 @3xl/panel:grid-cols-3 gap-3">
	{#each repositoryGroups as group (group.repository)}
		{@const image = group.latest}
		<button
			type="button"
			onclick={async () => {
				expandedRepository = group.repository;
				await tick();
				tagPanel?.scrollIntoView?.({ block: 'nearest' });
			}}
			aria-label={t('image.repositoryLabel', { name: group.repository })}
			aria-controls="vm-image-tags"
			aria-expanded={openRepository === group.repository}
			class="min-w-0 rounded-xl border p-4 text-left transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--color-accent)] {openRepository === group.repository
				? 'border-[var(--color-accent)] bg-[var(--color-surface-selected)]'
				: 'border-[var(--color-line)] bg-[var(--color-surface-raised)] hover:border-[var(--color-line-2)]'}"
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
				</div>
				{#if group.images.some(image => image.id === selectedId)}
					<svg class="h-4 w-4 shrink-0 text-[var(--color-accent)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
					</svg>
				{/if}
			</div>
		</button>
	{/each}

	{#if repositoryGroups.length === 0}
		<p class="col-span-full py-10 text-center text-sm text-[var(--color-ink-2)]">{t('image.empty')}</p>
	{/if}
</div>

{#if openGroup}
	<section bind:this={tagPanel} id="vm-image-tags" aria-label={t('image.tagsTitle', { name: openGroup.repository })} class="mt-4 rounded-xl border border-[var(--color-line)] bg-[var(--color-surface-raised)] p-4">
		<h3 class="text-sm font-semibold text-[var(--color-ink-0)]">{t('image.tagsTitle', { name: openGroup.repository })}</h3>
		<p class="mt-1 text-xs text-[var(--color-ink-2)]">{t('image.tagsHelp')}</p>
		<div class="mt-3 grid grid-cols-1 gap-2 @lg/panel:grid-cols-2">
			{#each openGroup.tags as tag (tag.tag)}
				{@const image = tag.current}
				{@const date = uploadDate(image)}
				<button
					type="button"
					disabled={image.status !== 'active'}
					onclick={() => onSelect(image.id, selectionName(image))}
					aria-label={image.status === 'active' ? t('image.selectLabel', { name: referenceName(image) }) : t('image.unselectableLabel', { name: referenceName(image), status: image.status })}
					aria-pressed={selectedId === image.id}
					class="min-w-0 rounded-lg border p-3 text-left transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--color-accent)] disabled:cursor-not-allowed {selectedId === image.id
						? 'border-[var(--color-accent)] bg-[var(--color-surface-selected)]'
						: 'border-[var(--color-line)] bg-[var(--color-surface-base)] enabled:hover:border-[var(--color-line-2)]'}"
				>
					<p class="break-all font-mono text-sm font-medium text-[var(--color-ink-1)]">{tag.tag}</p>
					{#if image.size || date}
						<div class="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs tabular-nums text-[var(--color-ink-2)]">
							{#if image.size}<span>{formatSize(image.size)}</span>{/if}
							{#if date}<time datetime={image.created_at ?? undefined}>{date}</time>{/if}
						</div>
					{/if}
					{#if image.status !== 'active'}
						<p class="mt-1 text-xs text-[var(--color-ink-2)]">{t('image.inactiveReason', { status: image.status })}</p>
					{/if}
				</button>
			{/each}
		</div>
	</section>
{/if}
