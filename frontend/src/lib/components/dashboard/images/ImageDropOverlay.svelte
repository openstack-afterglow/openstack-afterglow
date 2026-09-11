<script lang="ts">
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
	<div class="fixed inset-0 z-40 bg-surface-selected/20 border-2 border-dashed border-action-warm pointer-events-none flex items-center justify-center">
		<div class="bg-surface-base border border-action-warm rounded-xl px-8 py-5 text-action-warm text-base font-medium shadow-[var(--shadow-restraint)]">
			이미지 파일을 놓으면 업로드 모달이 열립니다
		</div>
	</div>
{/if}
