<script lang="ts">
	import { onDestroy, onMount, untrack } from 'svelte';
	import { createImageDetailController, provideImageDetailController } from '$lib/stores/imageDetailController.svelte';
	import type { ImageDetailController } from '$lib/stores/imageDetailController.svelte';
	import ImageWindowsSetupSection from '../ImageWindowsSetupSection.svelte';
	import ImagePropertiesSection from '../ImagePropertiesSection.svelte';

	// The shared panel also mounts export polling, members, and deletion. This focused
	// consumer keeps the real setup/properties components and controller context while
	// making all four scope inputs and authoritative top-level fields observable.
	interface Props {
		imageId?: string;
		token?: string;
		projectId?: string;
		isAdmin?: boolean;
		onController: (controller: ImageDetailController) => void;
	}
	let { imageId = 'image-a', token = 'token-a', projectId = 'project-a', isAdmin = false, onController }: Props = $props();
	const s = createImageDetailController({
		imageId: () => imageId, token: () => token,
		projectId: () => projectId, isAdmin: () => isAdmin,
	});
	provideImageDetailController(s);
	onMount(() => { onController(s); });
	onDestroy(() => s.reset());

	$effect(() => {
		const scope = { imageId, token, projectId, isAdmin };
		untrack(() => {
			s.reset();
			if (scope.imageId && scope.token) void s.loadImage();
		});
	});
</script>

<div aria-busy={s.loading} data-testid="image-consumer">
	{#if s.loading}
		<p role="status">Loading image</p>
	{:else if s.error}
		<p role="alert">{s.error}</p>
	{:else if s.image}
		<dl aria-label="Authoritative image projection">
			{#each Object.entries(s.image).filter(([key]) => key !== 'properties') as [key, value]}
				<dt>{key}</dt>
				<dd data-testid={`projection-${key}`}>{Array.isArray(value) ? value.join(', ') : String(value)}</dd>
			{/each}
		</dl>
		<section aria-label="Windows setup consumer"><ImageWindowsSetupSection /></section>
		<section aria-label="Image properties consumer"><ImagePropertiesSection /></section>
	{/if}
</div>
