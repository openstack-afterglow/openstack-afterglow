<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { createImageDetailController, provideImageDetailController } from '$lib/stores/imageDetailController.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import ImageDetailHeader from '$lib/components/image/ImageDetailHeader.svelte';
	import ImageInfoSection from '$lib/components/image/ImageInfoSection.svelte';
	import ImageSizeSection from '$lib/components/image/ImageSizeSection.svelte';
	import ImageMetadataSection from '$lib/components/image/ImageMetadataSection.svelte';
	import ImageWindowsSetupSection from '$lib/components/image/ImageWindowsSetupSection.svelte';
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
		// Track every identity dimension explicitly; controller state must not retrigger this effect.
		const current = { imageId, token: $auth.token, projectId: $auth.projectId, isAdmin };
		untrack(() => {
			s.reset();
			if (current.imageId && current.token) void s.loadImage();
		});
	});
	onDestroy(() => s.reset());
</script>

<div class="flex flex-col h-full motion-fade" aria-busy={s.loading}>
	<ImageDetailHeader {onClose} />

	<div class="flex min-h-0 flex-1 flex-col overflow-y-auto {s.loading && !s.image ? '' : 'p-5 space-y-4'}">
		{#if s.loading && !s.image}
			<LoadingState variant="surface" />
		{:else if s.error}
			<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm">{s.error}</div>
		{:else if s.image}
			<ImageInfoSection />
			<ImageSizeSection />
			<ImageMetadataSection />
			<ImageWindowsSetupSection />
			{#if $auth.token && s.image.status === 'active' && s.canExport}
				<ImageExportSection />
			{/if}
			{#if s.canManageImage}<ImageVisibilitySection />{/if}
			{#if s.image.visibility === 'shared' && s.canManageImage}<ImageMembersSection />{/if}
			{#if Object.keys(s.image.properties).length > 0 || s.canEditMetadata}<ImagePropertiesSection />{/if}
			{#if s.canManageImage}<ImageDeleteAction />{/if}
		{/if}
	</div>
</div>
