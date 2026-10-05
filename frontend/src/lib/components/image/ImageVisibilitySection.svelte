<script lang="ts">
	import { t } from '$lib/i18n/ns/images-keys';
	import { useImageDetailController, VISIBILITY_OPTIONS } from '$lib/stores/imageDetailController.svelte';
	import Button from '$lib/components/ui/Button.svelte';

	const s = useImageDetailController();
</script>

<div class="bg-surface-base border border-line rounded-lg p-5">
	<h3 class="text-xs font-semibold text-ink-2 uppercase tracking-wide mb-3">{t('visibilitySection.title')}</h3>
	<div class="flex items-center gap-3 flex-wrap">
		<select
			bind:value={s.visibilityValue}
			class="bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm"
		>
			{#each VISIBILITY_OPTIONS as opt}
				<option value={opt.value}>{opt.label}</option>
			{/each}
		</select>
		<Button onclick={() => s.saveVisibility()} disabled={s.savingVisibility || s.visibilityValue === s.image!.visibility}>
			{s.savingVisibility ? t('visibilitySection.saving') : t('visibilitySection.save')}
		</Button>
		{#if s.visibilitySuccess}
			<span class="text-green-400 text-sm">{t('visibilitySection.saved')}</span>
		{/if}
		{#if s.visibilityError}
			<span class="text-red-400 text-sm">{s.visibilityError}</span>
		{/if}
	</div>
</div>
