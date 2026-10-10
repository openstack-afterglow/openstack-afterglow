<script lang="ts">
	import { t } from '$lib/i18n/ns/images-keys';
	import { ActivityIndicator } from '$lib/components/ui';
	let {
		onFile,
	}: {
		onFile: (file: File) => void;
	} = $props();

	let active = $state(false);

	function hasFiles(e: DragEvent): boolean {
		const types = e.dataTransfer?.types;
		if (!types) return false;
		for (let i = 0; i < types.length; i++) if (types[i] === 'Files') return true;
		return false;
	}

	function onEnter(e: DragEvent) {
		if (!hasFiles(e)) return;
		e.preventDefault();
		active = true;
	}
	function onOver(e: DragEvent) {
		if (!hasFiles(e)) return;
		e.preventDefault();
		active = true;
	}
	function onLeave(e: DragEvent) {
		if (!hasFiles(e)) return;
		if (e.clientX <= 0 || e.clientY <= 0 || e.clientX >= window.innerWidth || e.clientY >= window.innerHeight) {
			active = false;
		}
	}
	function onDrop(e: DragEvent) {
		if (!hasFiles(e)) return;
		e.preventDefault();
		active = false;
		const f = e.dataTransfer?.files?.[0];
		if (f) onFile(f);
	}
</script>

<svelte:window
	ondragenter={onEnter}
	ondragover={onOver}
	ondragleave={onLeave}
	ondrop={onDrop}
/>

{#if active}
	<div class="motion-fade fixed inset-0 z-40 bg-surface-scrim/60 border-2 border-dashed border-accent pointer-events-none flex items-center justify-center px-4">
		<div class="motion-pop bg-surface-base border border-accent rounded-xl px-8 py-5 text-ink-0 text-base font-medium shadow-[var(--shadow-overlay-compact)]">
			<ActivityIndicator variant="upload" size="lg" label={t('dropOverlay.prompt')} />
		</div>
	</div>
{/if}
