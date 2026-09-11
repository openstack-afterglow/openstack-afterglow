<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { createImageDetailController, provideImageDetailController } from '$lib/stores/imageDetailController.svelte';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import ImageDetailHeader from '$lib/components/image/ImageDetailHeader.svelte';
	import ImageInfoSection from '$lib/components/image/ImageInfoSection.svelte';
	import ImageSizeSection from '$lib/components/image/ImageSizeSection.svelte';
	import ImageMetadataSection from '$lib/components/image/ImageMetadataSection.svelte';
	import ImageExportSection from '$lib/components/image/ImageExportSection.svelte';
	import ImageVisibilitySection from '$lib/components/image/ImageVisibilitySection.svelte';
	import ImageMembersSection from '$lib/components/image/ImageMembersSection.svelte';
	import ImagePropertiesSection from '$lib/components/image/ImagePropertiesSection.svelte';
	import ImageDeleteAction from '$lib/components/image/ImageDeleteAction.svelte';

	interface Props {
		imageId: string;
		isAdmin?: boolean;
		onClose?: () => void;
		onDelete?: (id: string) => void;
	}

	let { imageId, isAdmin = false, onClose, onDelete }: Props = $props();

	const s = createImageDetailController({
		imageId: () => imageId,
		token: () => $auth.token ?? undefined,
		projectId: () => $auth.projectId ?? undefined,
		isAdmin: () => isAdmin,
		onDelete: (id) => onDelete?.(id),
		onClose: () => onClose?.(),
	});
	provideImageDetailController(s);


	$effect(() => {
		const currentImageId = imageId;
		const currentToken = $auth.token;
		s.reset();
		if (!currentImageId || !currentToken) return;
		void s.loadImage();
	});
</script>

<div class="flex flex-col h-full">
	<ImageDetailHeader {onClose} />

	<div class="flex-1 overflow-y-auto px-6 py-5 space-y-4">
		{#if s.loading}
			<LoadingSkeleton variant="card" rows={5} />
		{:else if s.error}
			<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm">{s.error}</div>
		{:else if s.image}
			<ImageInfoSection />
			<ImageSizeSection />
			<ImageMetadataSection />
			{#if $auth.token && s.image.status === 'active'}
				<ImageExportSection />
			{/if}
			{#if s.isOwner}<ImageVisibilitySection />{/if}
			{#if s.image.visibility === 'shared' && s.isOwner}<ImageMembersSection />{/if}
			{#if Object.keys(s.image.properties).length > 0 || s.canEditMetadata}<ImagePropertiesSection />{/if}
			{#if s.isOwner}<ImageDeleteAction />{/if}
		{/if}
	</div>
</div>
