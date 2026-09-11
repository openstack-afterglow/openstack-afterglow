<script lang="ts">
	import { wizard } from '$lib/stores/wizard';
	import { useVmCreate } from '$lib/stores/vmCreateStore.svelte';
	import SelectImage from '$lib/components/wizard/SelectImage.svelte';

	const s = useVmCreate();
</script>

<div class="mb-4 flex items-center justify-between gap-3">
	<span id="boot-source-label" class="text-sm font-medium text-[var(--color-ink-1)]">부팅 소스</span>
	<div role="group" aria-labelledby="boot-source-label" class="inline-flex overflow-hidden rounded-lg border border-[var(--color-line)]">
		<button
			class="px-3 py-1.5 text-xs font-medium transition-colors {$wizard.bootSource === 'image' ? 'bg-[var(--color-accent)] text-[var(--color-action-on-accent)]' : 'bg-[var(--color-surface-sunken)] text-[var(--color-ink-2)] hover:bg-[var(--color-surface-raised)]'}"
			onclick={() => wizard.update(w => ({ ...w, bootSource: 'image', bootVolumeId: null, bootVolumeName: null }))}
		>OS 이미지</button>
		<button
			class="border-l border-[var(--color-line)] px-3 py-1.5 text-xs font-medium transition-colors {$wizard.bootSource === 'volume' ? 'bg-[var(--color-accent)] text-[var(--color-action-on-accent)]' : 'bg-[var(--color-surface-sunken)] text-[var(--color-ink-2)] hover:bg-[var(--color-surface-raised)]'}"
			onclick={() => wizard.update(w => ({ ...w, bootSource: 'volume', imageId: null, imageName: null }))}
		>기존 부팅 볼륨</button>
	</div>
</div>

{#if $wizard.bootSource === 'image'}
	<p class="mb-4 hidden text-sm text-[var(--color-ink-2)] md:block">Glance에 등록된 공개 이미지, 직접 업로드한 이미지는 <a href="/dashboard/compute/images" class="text-[var(--color-accent)] hover:underline">이미지 페이지</a>에서 관리할 수 있습니다.</p>
	<SelectImage images={s.images} selectedId={$wizard.imageId} onSelect={s.selectImage} />
{:else}
	{@const bootableVols = s.volumes.filter(v => v.bootable && v.status === 'available')}
	<p class="text-sm text-ink-2 mb-4">부팅 가능하고 <span class="text-green-400">available</span> 상태인 볼륨만 표시됩니다.</p>
	{#if bootableVols.length === 0}
		<div class="text-center py-10 text-ink-3 text-sm">부팅 가능한 볼륨이 없습니다.</div>
	{:else}
		<div class="space-y-2 max-h-96 overflow-y-auto pr-1">
			{#each bootableVols as vol}
				<button
					onclick={() => wizard.update(w => ({ ...w, bootVolumeId: vol.id, bootVolumeName: vol.name }))}
					class="w-full text-left rounded-lg border px-4 py-3 transition-colors {$wizard.bootVolumeId === vol.id ? 'border-action-warm bg-surface-selected/20' : 'border-line-2 bg-surface-base hover:border-line-2'}"
				>
					<div class="flex items-center justify-between">
						<span class="text-sm text-ink-0 font-medium">{vol.name || vol.id.slice(0, 8)}</span>
						<span class="text-xs text-ink-3 font-mono">{vol.size} GB</span>
					</div>
					{#if vol.volume_image_metadata?.image_name}
						<div class="text-xs text-ink-3 mt-0.5">{vol.volume_image_metadata.image_name}</div>
					{/if}
				</button>
			{/each}
		</div>
	{/if}
{/if}
