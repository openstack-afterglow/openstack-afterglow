<script lang="ts">
	import { t } from '$lib/i18n/ns/vm-wizard';
	import RichText from '$lib/i18n/RichText.svelte';
	import { wizard } from '$lib/stores/wizard';
	import { useVmCreate } from '$lib/stores/vmCreateStore.svelte';
	import SelectImage from '$lib/components/wizard/SelectImage.svelte';

	const s = useVmCreate();
</script>

<div class="mb-4 flex items-center justify-between gap-3">
	<span id="boot-source-label" class="text-sm font-medium text-[var(--color-ink-1)]">{t('boot.source')}</span>
	<div role="group" aria-labelledby="boot-source-label" class="inline-flex overflow-hidden rounded-lg border border-[var(--color-line)]">
		<button
			class="px-3 py-1.5 text-xs font-medium transition-colors {$wizard.bootSource === 'image' ? 'bg-[var(--color-accent)] text-[var(--color-action-on-accent)]' : 'bg-[var(--color-surface-sunken)] text-[var(--color-ink-2)] hover:bg-[var(--color-surface-raised)]'}"
			onclick={() => wizard.update(w => ({ ...w, bootSource: 'image', bootVolumeId: null, bootVolumeName: null }))}
		>{t('boot.image')}</button>
		<button
			class="border-l border-[var(--color-line)] px-3 py-1.5 text-xs font-medium transition-colors {$wizard.bootSource === 'volume' ? 'bg-[var(--color-accent)] text-[var(--color-action-on-accent)]' : 'bg-[var(--color-surface-sunken)] text-[var(--color-ink-2)] hover:bg-[var(--color-surface-raised)]'}"
			onclick={() => wizard.update(w => ({ ...w, bootSource: 'volume', imageId: null, imageName: null }))}
		>{t('boot.volume')}</button>
	</div>
</div>

{#if $wizard.bootSource === 'image'}
	{#snippet imagesLink(text: string)}<a href="/dashboard/compute/images" class="text-[var(--color-accent)] hover:underline">{text}</a>{/snippet}
	<p class="mb-4 hidden text-sm text-[var(--color-ink-2)] md:block"><RichText segments={t.rich('boot.imageHint')} tags={{ images: imagesLink }} /></p>
	<SelectImage images={s.images} selectedId={$wizard.imageId} onSelect={s.selectImage} />
{:else}
	{@const bootableVols = s.volumes.filter(v => v.bootable && v.status === 'available')}
	{#snippet availableStatus(text: string)}<span class="text-green-400">{text}</span>{/snippet}
	<p class="text-sm text-ink-2 mb-4"><RichText segments={t.rich('boot.volumeHint')} tags={{ status: availableStatus }} /></p>
	{#if bootableVols.length === 0}
		<div class="text-center py-10 text-ink-2 text-sm">{t('boot.empty')}</div>
	{:else}
		<div class="space-y-2 max-h-96 overflow-y-auto pr-1">
			{#each bootableVols as vol}
				<button
					onclick={() => wizard.update(w => ({ ...w, bootVolumeId: vol.id, bootVolumeName: vol.name }))}
					class="w-full text-left rounded-lg border px-4 py-3 transition-colors {$wizard.bootVolumeId === vol.id ? 'border-action-warm bg-surface-selected/20' : 'border-line-2 bg-surface-base hover:border-line-2'}"
				>
					<div class="flex items-center justify-between">
						<span class="text-sm text-ink-0 font-medium">{vol.name || vol.id.slice(0, 8)}</span>
						<span class="text-xs text-ink-2 font-mono">{vol.size} GB</span>
					</div>
					{#if vol.volume_image_metadata?.image_name}
						<div class="text-xs text-ink-2 mt-0.5">{vol.volume_image_metadata.image_name}</div>
					{/if}
				</button>
			{/each}
		</div>
	{/if}
{/if}
